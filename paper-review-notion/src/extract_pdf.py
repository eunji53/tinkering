"""논문 PDF에서 텍스트/그림/표를 추출해 output/ 폴더에 저장하는 1단계 테스트 스크립트.

그림/표는 "Figure N", "Table N" 캡션 텍스트를 찾아서 그 주변 영역(벡터 그래픽 포함)을
페이지 렌더링 방식으로 통째로 크롭한다. 임베딩된 raster 이미지만 뽑거나 선(line) 기반으로
표를 감지하는 방식은 이 논문처럼 벡터로 그려진 그림이나 선이 거의 없는 표(booktabs 스타일)를
놓치기 때문에 사용하지 않는다.

실행 예:
    python extract_pdf.py                          # ../input/LIGHTRAG.pdf 기본 처리
    python extract_pdf.py --pdf ../input/foo.pdf    # 다른 PDF 처리
"""

import argparse
import re
import unicodedata
from datetime import date
from pathlib import Path

import fitz  # PyMuPDF

SRC_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SRC_DIR.parent

# 논문마다 캡션 표기가 제각각이라("Figure 1:", "Fig. 1.", "Fig 1 Left:", "TABLE 1", "Tab. 1" 등)
# Figure/Fig, Table/Tab 축약형과 대소문자, 번호 뒤 마침표/콜론 유무를 모두 허용한다.
CAPTION_RE = re.compile(r"^(figure|fig|table|tab)\.?\s*(\d+)\b", re.IGNORECASE)
HEADING_RE = re.compile(r"^\d+(\.\d+)*\s+[A-Z]")
# 수식 번호는 보통 "(1)"처럼 소괄호 안에 1~3자리 숫자로만 끝난다. 인용 연도 "(2020)"처럼
# 4자리인 경우는 제외해 본문 인용과 헷갈리지 않게 한다. 번호 앞은 줄 시작이나 공백이어야
# 한다. "π(1)", "f(1)"처럼 기호에 붙은 괄호는 수식 번호가 아니라 수식의 일부다.
EQUATION_NUM_RE = re.compile(r"(?:^|\s)\((\d{1,3})\)\s*$")


# TeX의 큰 기호 글꼴(cmex)은 PDF에 문자 정보(ToUnicode)가 없으면 글자 코드가 그대로 나온다.
# 예: ⋃ → "[", ∑ → "X", 큰 괄호 → "\x00"/"\x01". cmex10의 표준 글자 배치로 되돌린다.
CMEX_MAP = {
    **{chr(c): "(" for c in (0x00, 0x10, 0x12, 0x20)},
    **{chr(c): ")" for c in (0x01, 0x11, 0x13, 0x21)},
    **{chr(c): "[" for c in (0x02, 0x14, 0x22)},
    **{chr(c): "]" for c in (0x03, 0x15, 0x23)},
    **{chr(c): "{" for c in (0x08, 0x1A, 0x28)},
    **{chr(c): "}" for c in (0x09, 0x1B, 0x29)},
    "\x04": "⌊", "\x05": "⌋", "\x06": "⌈", "\x07": "⌉", "\x0a": "⟨", "\x0b": "⟩", "\x0c": "|", "\x0d": "‖",
    "P": "∑", "X": "∑", "Q": "∏", "Y": "∏", "R": "∫", "Z": "∫", "S": "⋃", "[": "⋃", "T": "⋂", "\\": "⋂",
    "V": "⋀", "^": "⋀", "W": "⋁", "_": "⋁", "`": "∐", "a": "∐", **{chr(c): "√" for c in range(0x70, 0x75)},
}
CONTROL_RE = re.compile(r"[\x00-\x09\x0b-\x1f]")


def _clean_text(text: str) -> str:
    """제어 문자를 지우고, 따로 떨어져 나온 부정 사선(U+0338)을 뒤 기호와 합친다.
    "f(∅)̸ = ∅" → "f(∅)≠ ∅", "̸ ∈" → "∉" (CMSY 글꼴이 사선을 별도 글자로 내보내는 경우)."""
    text = re.sub(r"̸\s*(\S)", lambda m: unicodedata.normalize("NFC", m.group(1) + "̸"), text)
    return CONTROL_RE.sub("", text)


def _cmex_without_unicode(doc: fitz.Document) -> set:
    """문자 정보 없이 글자 코드가 그대로 나오는 cmex 글꼴 이름들. 정상적으로 유니코드가
    나오는 cmex 글꼴에까지 CMEX_MAP을 적용하면 진짜 "["가 "⋃"로 바뀌므로, 제어 문자를
    내보내는(= 문자 정보가 없는) 글꼴에만 적용한다."""
    fonts = set()
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                for span in line["spans"]:
                    if "CMEX" in span["font"].upper() and CONTROL_RE.search(span["text"]):
                        fonts.add(span["font"])
    return fonts


def _line_text(line: dict, cmex_fonts: set) -> str:
    parts = []
    for span in line["spans"]:
        text = span["text"]
        if span["font"] in cmex_fonts:
            text = "".join(CMEX_MAP.get(c, c) for c in text)
        parts.append(text)
    return "".join(parts)


GREEK_LATEX = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ϵ": "epsilon", "ε": "varepsilon", "ζ": "zeta",
    "η": "eta", "θ": "theta", "ϑ": "vartheta", "ι": "iota", "κ": "kappa", "λ": "lambda", "µ": "mu", "μ": "mu",
    "ν": "nu", "ξ": "xi", "π": "pi", "ϖ": "varpi", "ρ": "rho", "ϱ": "varrho", "σ": "sigma", "ς": "varsigma",
    "τ": "tau", "υ": "upsilon", "ϕ": "phi", "φ": "varphi", "χ": "chi", "ψ": "psi", "ω": "omega",
    "Γ": "Gamma", "∆": "Delta", "Δ": "Delta", "Θ": "Theta", "Λ": "Lambda", "Ξ": "Xi", "Π": "Pi", "Σ": "Sigma",
    "Υ": "Upsilon", "Φ": "Phi", "Ψ": "Psi", "Ω": "Omega",
}
SYMBOL_LATEX = {
    "∈": "\\in", "∉": "\\notin", "∋": "\\ni", "⊂": "\\subset", "⊆": "\\subseteq", "⊃": "\\supset", "⊇": "\\supseteq",
    "⊊": "\\subsetneq", "∪": "\\cup", "∩": "\\cap", "⋃": "\\bigcup", "⋂": "\\bigcap", "∅": "\\emptyset",
    "≤": "\\le", "≥": "\\ge", "≠": "\\neq", "≈": "\\approx", "≡": "\\equiv", "∼": "\\sim", "∝": "\\propto",
    "→": "\\to", "←": "\\leftarrow", "↦": "\\mapsto", "⇒": "\\Rightarrow", "⇔": "\\Leftrightarrow",
    "∀": "\\forall", "∃": "\\exists", "¬": "\\neg", "∧": "\\land", "∨": "\\lor", "∞": "\\infty",
    "∑": "\\sum", "∏": "\\prod", "∫": "\\int", "√": "\\sqrt", "∂": "\\partial", "∇": "\\nabla",
    "×": "\\times", "·": "\\cdot", "◦": "\\circ", "∘": "\\circ", "±": "\\pm", "−": "-", "∗": "*", "⋆": "\\star",
    "…": "\\ldots", "···": "\\cdots", "⋯": "\\cdots", "|": "|", "‖": "\\|", "⟨": "\\langle", "⟩": "\\rangle",
    "⌊": "\\lfloor", "⌋": "\\rfloor", "⌈": "\\lceil", "⌉": "\\rceil", "△": "\\triangle", "′": "'",
    "▷": "\\triangleright", "⊤": "\\top", "⊥": "\\perp", "ℓ": "\\ell", "̸": "\\not ", "{": "\\{", "}": "\\}", "\\": "\\setminus ",
    "_": "\\_", "%": "\\%", "#": "\\#", "&": "\\&", "$": "\\$",
}
MATH_ALNUM_STYLES = [("DOUBLE-STRUCK", "mathbb"), ("FRAKTUR", "mathfrak"), ("SCRIPT", "mathcal"), ("BOLD", "mathbf")]


def _font_kind(font: str) -> str | None:
    """TeX 글꼴 이름으로 글자의 수식 역할을 정한다. 대문자 필기체가 CMSY에 들어 있는 것처럼 TeX는
    글꼴마다 맡은 글자 모양이 고정돼 있다. None이면 본문 글꼴."""
    f = font.upper()
    if "MSBM" in f:
        return "bb"
    if "EUFM" in f or "EUFB" in f:
        return "frak"
    if "RSFS" in f or "EUSM" in f or "EUSB" in f:
        return "scr"
    if "CMSY" in f or "CMBSY" in f:
        return "sy"
    if "CMEX" in f:
        return "ex"
    if "CMMIB" in f:
        return "bfmi"
    if "CMMI" in f or MATH_FONT_RE.search(font):
        return "mi"
    # 아래는 수식 안에서만 수식으로 본다(본문·제목에도 쓰이는 글꼴).
    if re.match(r"CMBX\d", f):
        return "bf"
    if re.match(r"CMR\d", f):
        return "rm"
    if MONO_FONT_RE.search(font):
        return "tt"
    return None


def _char_latex(c: str, kind: str) -> str:
    if c in GREEK_LATEX:
        cmd = "\\" + GREEK_LATEX[c]
        return f"\\boldsymbol{{{cmd}}}" if kind in ("bf", "bfmi") else cmd
    if c in SYMBOL_LATEX:
        return SYMBOL_LATEX[c]
    if c.isascii() and c.isalpha():
        style = {"sy": "mathcal", "bb": "mathbb", "frak": "mathfrak", "scr": "mathscr", "bf": "mathbf", "bfmi": "boldsymbol"}.get(kind)
        if style and (kind != "sy" or c.isupper()):
            return f"\\{style}{{{c}}}"
        return c
    if ord(c) > 0x2000 and unicodedata.name(c, "").startswith("MATHEMATICAL"):
        # Word 등 TeX가 아닌 도구로 만든 PDF는 𝒞, ℝ 같은 유니코드 수식 글자를 쓴다.
        name, base = unicodedata.name(c), unicodedata.normalize("NFKC", c)
        for key, style in MATH_ALNUM_STYLES:
            if key in name:
                return f"\\{style}{{{base}}}"
        return base
    return c


def _append_latex(out: str, piece: str) -> str:
    """"\\in" 바로 뒤에 글자가 오면 "\\inA"가 되므로 명령 뒤에 공백을 둔다."""
    if out and re.search(r"\\[A-Za-z]+$", out) and re.match(r"[A-Za-z]", piece):
        out += " "
    return out + piece


def _span_latex(text: str, kind: str) -> str:
    if kind == "tt":
        return "\\texttt{" + "".join(SYMBOL_LATEX.get(c, c) if c in "_%#&${}" else c for c in text.strip()) + "}"
    if kind == "sy":
        # ↦는 CMSY의 "7" 모양 글자(mapstochar)와 →를 겹쳐 만든다.
        text = text.replace("7→", "↦").replace("7", " ")
    if kind == "rm":
        # 수식 안의 똑바른 글씨 단어(log, softmax 등)는 \mathrm으로 묶는다.
        return re.sub(
            r"[A-Za-z]{2,}|.",
            lambda m: f"\\mathrm{{{m.group(0)}}}" if len(m.group(0)) > 1 else _char_latex(m.group(0), kind),
            text,
        )
    out = ""
    for c in text:
        out = _append_latex(out, "\\mapstochar" if c == "\u2000" else _char_latex(c, kind))
    return out


def _tidy_latex(latex: str) -> str:
    latex = re.sub(r"\\mapstochar\s*\\to", r"\\mapsto", latex)
    latex = re.sub(r"\\not\s*=", r"\\neq", latex)
    latex = re.sub(r"\\not\s*\\in\b", r"\\notin", latex)
    latex = re.sub(r"\^\{('+)\}", r"\1", latex)  # 위첨자 프라임: θ^{'} → θ'
    # 따로 떨어져 나온 글자 위 장식 기호를 뒤 글자와 합친다: "¯K" → \bar{K}
    for mark, cmd in (("¯", "bar"), ("˜", "tilde"), ("ˆ", "hat"), ("˙", "dot")):
        latex = re.sub(re.escape(mark) + r"\s*((?:\\[A-Za-z]+\{[^{}]*\}|\\[A-Za-z]+|[A-Za-z]))", rf"\\{cmd}{{\1}}", latex)
    # 근호는 바로 뒤 한 덩어리(문자 + 첨자)를 감싼다: √dk → \sqrt{d_{k}}
    latex = re.sub(r"\\sqrt\s*((?:\\[A-Za-z]+|[A-Za-z0-9])(?:[_^]\{[^{}]*\})*)", r"\\sqrt{\1}", latex)
    return re.sub(r" {2,}", " ", latex).strip()


def _line_latex(line: dict, cmex_fonts: set, text_fonts: set) -> str:
    """본문 한 줄에서 수식 글꼴로 쓰인 구간을 찾아 $...$ LaTeX로 바꾼다.

    아래첨자·위첨자는 글자 크기(본문 수식 글자보다 15% 이상 작음)와 기준선 높이(아래면 아래첨자,
    위면 위첨자)로 판단한다. "C({vi})" → "$\\mathcal{C}(\\{v_{i}\\})$". 본문 글꼴과 겸용인 글꼴
    (CMR 똑바른 글씨, 굵은 글씨, 고정폭)은 수식 글꼴 사이에 끼어 있을 때만 수식으로 보고, 그 글꼴이
    이 문서의 본문 글꼴(text_fonts)이면 글자 단어는 수식에 넣지 않는다(환각 논문은 본문이 CMR).
    """
    spans = [s for s in line["spans"] if s["text"]]
    kinds = [_font_kind(s["font"]) for s in spans]
    starters = {"bb", "frak", "scr", "sy", "ex", "mi", "bfmi"}

    def joins_math(i: int) -> bool:
        """본문과 겸용인 글꼴의 조각이 앞뒤 수식과 이어지는지."""
        text = spans[i]["text"]
        prev_math = i > 0 and in_math[i - 1]
        if kinds[i] is None:
            # 수식 바로 뒤에 공백 없이 붙은 작은 본문 글꼴 글자는 첨자다(Boogu "t_shift"의 "shift").
            prev = spans[i - 1] if i > 0 else None
            if prev_math and not text.startswith(" ") and spans[i]["size"] < 0.85 * prev["size"]:
                kinds[i] = "rm"
                return True
            return False
        next_math = i + 1 < len(spans) and kinds[i + 1] in starters and not text.endswith(" ")
        if not re.search(r"[A-Za-z]", text):
            return prev_math or next_math  # 괄호·숫자·연산자
        if spans[i]["font"] in text_fonts:
            return False
        word = text.strip()
        return prev_math and next_math and " " not in word and len(word) <= 10  # 수식 중간의 log, softmax

    in_math: list[bool] = []
    for i, kind in enumerate(kinds):
        in_math.append(kind in starters or joins_math(i))

    out, i = [], 0
    while i < len(spans):
        if not in_math[i]:
            # 본문의 "$400K" 같은 기호가 수식 구분자 "$...$"와 섞이지 않도록 이스케이프한다.
            out.append(spans[i]["text"].replace("$", "\\$"))
            i += 1
            continue
        j = i
        while j < len(spans) and in_math[j]:
            j += 1
        run = spans[i:j]
        run_kinds = kinds[i:j]
        base_size = max((s["size"] for s, k in zip(run, run_kinds) if k != "ex"), default=max(s["size"] for s in run))
        # 기준선은 큰 기호(∑ 등 cmex)를 뺀 본래 크기 글자들의 기준선 중앙값으로 잡는다. 첫 글자만 보면
        # 큰 기호의 기준선을 잡아 아래첨자를 위첨자로 오인한다.
        base_ys = sorted(
            s["origin"][1] for s, k in zip(run, run_kinds)
            if k != "ex" and s["size"] >= base_size - 0.1 and s["text"].strip()
        )
        base_y = base_ys[len(base_ys) // 2] if base_ys else run[0]["origin"][1]
        latex, script = "", None
        for s, kind in zip(run, run_kinds):
            text = s["text"]
            if s["font"] in cmex_fonts:
                text = "".join(CMEX_MAP.get(c, c) for c in text)
            piece = _span_latex(text.strip() if kind != "tt" else text, kind) if text.strip() else " "
            small = s["size"] < 0.85 * base_size
            new_script = ("_" if s["origin"][1] > base_y + 0.5 else "^") if small else None
            if new_script != script:
                if script:
                    latex += "}"
                if new_script:
                    latex += new_script + "{"
                script = new_script
            latex = _append_latex(latex, piece) if piece.strip() else latex + " "
        if script:
            latex += "}"
        # 수식 앞뒤의 공백과 문장 부호(쉼표·마침표)는 $ 밖으로 뺀다. PDF에 공백이 없어 본문 단어와
        # 수식이 붙어 있으면("∅and") 사이에 공백을 넣는다.
        raw = "".join(s["text"] for s in run)
        m = re.search(r"[\s.,;:]*$", latex)
        body = _tidy_latex(latex[: m.start()])
        tail = re.sub(r"\s+", " ", m.group(0))
        if not body:
            out.append(raw)
        else:
            lead = re.match(r"\s*", raw).group(0) or (" " if out and re.search(r"[A-Za-z]$", out[-1]) else "")
            if not tail and j < len(spans) and re.match(r"[A-Za-z]", spans[j]["text"]):
                tail = " "
            out.append(f"{lead}${body}${tail}")
        i = j
    return "".join(out)


def _join_lines(lines: list[str]) -> str:
    """같은 블록의 줄을 잇되, 줄 끝 하이픈으로 끊긴 단어("Foun-" + "dational")는 붙인다.
    다음 줄이 대문자·숫자로 시작하면("Visualization-" + "Easy") 원래 하이픈으로 보고 남긴다."""
    out: list[str] = []
    for line in lines:
        if out and re.search(r"[A-Za-z]-$", out[-1]) and re.match(r"[a-z]", line):
            out[-1] = out[-1][:-1] + line
        else:
            out.append(line)
    return "\n".join(out)


def extract_text(
    doc: fitz.Document, out_dir: Path, figures_and_tables: list[dict], equations: list[dict]
) -> None:
    """페이지별 본문 텍스트를 정리해 저장한다.

    PDF 글자를 위치 순서대로 그대로 꺼내면 그림 안의 라벨 조각("1 1 1 0 0", 축 눈금)이 본문에
    섞이고, 수식은 기호마다 줄이 쪼개진다. 이미 찾아 둔 그림/표/수식 영역을 이용해 그림·표는
    캡션과 이미지 경로 한 줄로, 수식은 번호·이미지 경로를 붙인 한 줄로 바꾼다. 머리글·쪽
    번호는 뺀다. 원본 그대로의 텍스트는 비교용으로 text_raw/에 따로 남긴다(제어 문자만 제거).
    """
    text_dir = out_dir / "text"
    raw_dir = out_dir / "text_raw"
    text_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    page_blocks = [_text_blocks(page) for page in doc]
    body_size = _body_font_size(page_blocks)
    running = _running_texts(page_blocks, [page.rect.height for page in doc])
    cmex_fonts = _cmex_without_unicode(doc)
    text_fonts = _text_fonts(doc)

    regions_by_page: dict = {}
    for item in figures_and_tables:
        folder = "figures" if item["kind"] == "Figure" else "tables"
        caption = " ".join(_clean_text(item["caption"]).split())
        label = f"[{caption} → {folder}/{item['file']}]"
        regions_by_page.setdefault(item["page"], []).append(
            {
                "rect": item["region"],
                "label": label,
                "kind": "figure" if item["kind"] == "Figure" else "table",
                "caption": re.sub(r"\W", "", caption),
            }
        )
    for eq in equations:
        name = ", ".join(f"({n})" for n in eq["numbers"]) or eq.get("label", "")
        label = f"[수식 {name} → equations/{eq['file']}]"
        regions_by_page.setdefault(eq["page"], []).append({"rect": eq["region"], "label": label, "kind": "equation"})

    full_text_parts = []
    for page_index, page in enumerate(doc, start=1):
        raw = _clean_text(page.get_text())
        (raw_dir / f"page_{page_index:03d}.txt").write_text(raw, encoding="utf-8")

        regions = regions_by_page.get(page_index, [])
        eq_lines: dict = {id(r): [] for r in regions}
        emitted = set()
        out: list[str] = []
        front_end = 0.0
        if page_index == 1:
            abstract = [b["rect"].y0 for b in page_blocks[0] if b["text"].strip().lower().startswith("abstract")]
            front_end = min(abstract) if abstract else 0.0
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            rect = fitz.Rect(b["bbox"])
            texts = [_line_text(line, cmex_fonts) for line in b["lines"]]
            block_text = "\n".join(texts)
            if not block_text.strip():
                continue
            if _in_margin(rect, page.rect.height) and (
                _normalize_running(block_text) in running or block_text.strip().isdigit()
            ):
                continue  # 머리글/바닥글, 쪽 번호
            # 그림 크롭이 넓게 잡혀 본문까지 덮는 경우(예: ResNet 1쪽 그림 위의 제목·저자·초록)에
            # 본문을 잃지 않도록, 본문 크기의 문장 문단과 본문보다 큰 글자(제목·저자·소제목)는
            # 영역 안이어도 남긴다. 그림 안의 라벨은 대개 본문보다 작다.
            size = max((s["size"] for line in b["lines"] for s in line["spans"]), default=0)
            body_paragraph = not CAPTION_RE.match(block_text.strip()) and (
                (_is_paragraph(block_text) and _is_prose(block_text) and abs(size - body_size) <= 1)
                or size >= body_size + 1.5
            )
            kept: list[str] = []
            for line, text in zip(b["lines"], texts):
                center = fitz.Rect(line["bbox"])
                center = fitz.Point((center.x0 + center.x1) / 2, (center.y0 + center.y1) / 2)
                region = next((r for r in regions if r["rect"].contains(center)), None)
                # 캡션의 둘째 줄 이후가 따로 떨어진 블록이면 본문 문단처럼 보이지만, 표시 줄에 이미
                # 캡션 전체가 들어 있으므로 남기지 않는다.
                in_caption = (
                    region is not None and region["kind"] != "equation"
                    and re.sub(r"\W", "", block_text) in region["caption"]
                )
                if region is None or (region["kind"] == "figure" and body_paragraph and not in_caption):
                    # 1쪽 제목·저자·소속의 각주 기호(∗, †, 1,5)는 수식이 아니므로 Abstract 위쪽은 그대로 둔다.
                    if line["bbox"][3] <= front_end:
                        kept.append(_line_text(line, cmex_fonts).replace("$", "\\$"))
                    else:
                        kept.append(_line_latex(line, cmex_fonts, text_fonts))
                    continue
                # 수식은 기호 조각을, 표는 셀 내용을 모아 두었다가 줄 단위로 다시 만든다. 그림 안의
                # 라벨·눈금은 버린다. 표의 숫자는 실험 결과라 요약에 필요하다.
                if region["kind"] == "equation" or (region["kind"] == "table" and not in_caption):
                    # 표 셀과 따로 떨어진 수식의 텍스트는 원문 그대로 두되, "$"는 수식 구분자와 섞이지 않게 이스케이프한다.
                    eq_lines[id(region)].append(({"rect": fitz.Rect(line["bbox"]), "text": text.replace("$", "\\$")}, 0))
                if id(region) not in emitted:
                    emitted.add(id(region))
                    if kept:
                        out.append(_join_lines(kept))
                        kept = []
                    out.append(region)  # 자리만 잡아 두고, 수식 텍스트를 다 모은 뒤 채운다
            if kept:
                out.append(_join_lines(kept))

        lines_out = []
        for item in out:
            if isinstance(item, dict):
                if item["kind"] == "equation":
                    # 큰 기호(⋃, ∑)는 위쪽 좌표가 앞서서 단순 정렬하면 순서가 뒤섞인다. 화면상의 한 줄로
                    # 묶은 뒤 줄 안에서는 왼쪽부터 읽는다.
                    body = " ".join(row["text"].strip() for row in _rows(eq_lines[id(item)]) if row["text"].strip())
                    lines_out.append(f"{item['label']} {body}")
                elif item["kind"] == "table":
                    # 같은 높이의 셀을 왼쪽부터 " | "로 이어 표의 한 행으로 만든다.
                    lines_out.append(item["label"])
                    for row in _rows(eq_lines[id(item)]):
                        cells = [line["text"].strip() for line, _ in sorted(row["lines"], key=lambda t: t[0]["rect"].x0)]
                        cells = [c for c in cells if c]
                        if cells:
                            lines_out.append(" | ".join(cells))
                else:
                    lines_out.append(item["label"])
            else:
                lines_out.append(item)
        page_text = _clean_text("\n".join(lines_out)) + "\n"
        (text_dir / f"page_{page_index:03d}.txt").write_text(page_text, encoding="utf-8")
        full_text_parts.append(f"\n\n## Page {page_index}\n\n{page_text}")

    (out_dir / "full_text.md").write_text("".join(full_text_parts), encoding="utf-8")
    print(f"[text] {len(doc)}개 페이지 텍스트 추출 완료 -> {text_dir}")


def _block_stats(text: str) -> tuple[int, float]:
    lines = [line for line in text.strip().split("\n") if line.strip()]
    if not lines:
        return 0, 0.0
    avg_len = sum(len(line) for line in lines) / len(lines)
    return len(lines), avg_len


def _is_paragraph(text: str) -> bool:
    n_lines, avg_len = _block_stats(text)
    return n_lines >= 2 and avg_len > 45


def _looks_like_mention(text: str) -> bool:
    """"Figure 5 presents ...", "Table 4 shows ..."처럼 번호 뒤가 소문자 단어로 이어지면
    캡션이 아니라 본문에서 그림/표를 언급한 문장으로 본다.

    진짜 캡션은 번호 뒤에 ':'/'.'가 오거나("Figure 5:"), 제목이 대문자로 시작한다
    ("Figure 6 Boogu Arena ..."). 줄 길이로 구분하면 단 폭에 따라 결과가 뒤집힌다.
    """
    match = CAPTION_RE.match(text.strip())
    if not match:
        return False
    rest = text.strip()[match.end():].lstrip()
    # "Table 24-35 presents ..."처럼 범위·나열로 이어지는 언급도 있어서, 소문자만 거르지 않고
    # 캡션다운 시작(구분 기호나 대문자 제목)이 아니면 모두 언급으로 본다.
    return bool(rest) and not (rest[0] in ":.|(" or rest[0].isupper())


def _is_body_paragraph(text: str, rect: fitz.Rect, cap_rect: fitz.Rect, size: float, body_size: float) -> bool:
    """그림/표 경계를 찾을 때 쓰는, 캡션 폭과 글자 크기를 기준으로 한 본문 문단 판정.

    글자 수만 보면(_is_paragraph) 논문 양식에 따라 틀린다. 좁은 2단 양식의 본문은 한 줄이
    45자가 안 되어 문단으로 안 잡히고, 반대로 그림 안의 좁은 설명 상자(예: Boogu의
    Figure 17 프롬프트 상자)는 줄이 길어서 문단으로 잡혀 스캔이 그림 중간에서 멈춘다.
    본문 문단은 보통 캡션과 비슷한 폭(같은 컬럼 전체)을 차지하고, 본문 글자 크기로
    쓰인다는 점을 함께 본다. size/body_size는 블록과 문서 본문의 대표 글자 크기(pt)다.
    """
    # 그림 안의 주석은 본문보다 확연히 작은 글자로 쓰인다(예: 환각 논문 Figure 16의 두 줄
    # 주석). 폭만으로는 2단 양식의 본문 단과 구분이 안 되므로 글자 크기로 먼저 거른다.
    if body_size > 0 and size < 0.85 * body_size:
        return False
    n_lines, avg_len = _block_stats(text)
    width_ratio = rect.width / cap_rect.width if cap_rect.width > 0 else 1.0
    if n_lines == 1:
        # 표 바로 앞의 "... has the following specifications:" 같은 한 줄짜리 본문 문장.
        # 표 머리글 행은 이렇게 문장부호로 끝나는 긴 문장이 아니다. 그림 안의 한 줄 강조
        # 문구(환각 논문 Figure 13, 본문보다 1pt 작음)와 구분하려고 본문 크기일 때만 인정한다.
        stripped = text.strip()
        return (
            abs(size - body_size) <= 0.5
            and width_ratio >= 0.6
            and len(stripped.split()) >= 6
            and stripped[-1] in ".:"
        )
    if n_lines < 2:
        return False
    # 캡션 폭의 40% 미만인 블록은 그림 내부 요소로 본다. 캡션이 2단 전체 폭일 때 한 단의
    # 본문(약 48%)은 여전히 문단으로 잡히도록 경계를 그보다 낮게 둔다.
    if width_ratio < 0.4:
        return False
    if avg_len > 45:
        return True
    # 완화된 기준(30자)은 3줄 이상에만 쓴다. 하위 그림 라벨("(a) ... (b) ...")처럼 넓고
    # 짧은 두 줄짜리 블록까지 문단으로 보면 그림 바로 위에서 스캔이 멈춘다(Boogu Figure 20).
    return n_lines >= 3 and width_ratio >= 0.6 and avg_len > 30


def _is_heading(text: str) -> bool:
    stripped = text.strip()
    if HEADING_RE.match(stripped):
        return True
    words = stripped.split()
    # "M =" 같은 짧은 수식 조각이 대문자 한 글자 때문에 헤딩으로 오인되지 않도록
    # 최소 길이와 '=' 미포함 조건을 둔다. 실제 섹션 제목(ABSTRACT 등)은 이 조건을 만족한다.
    # 번호 없는 대문자 제목은 한 줄짜리만 인정한다. 표의 한 행("GPT-4\n-\n91.9\n85.9")처럼
    # 여러 줄로 쪼개진 블록은 모델명이 대문자라는 이유만으로 제목이 되면 안 된다.
    if "\n" in stripped:
        return False
    # 그림 안의 수식 조각("∞∩R∞(Q)")도 대문자 몇 개 때문에 isupper()가 참이 된다.
    # 실제 제목은 거의 알파벳으로만 이루어져 있다.
    visible = [c for c in stripped if not c.isspace()]
    letter_ratio = sum(c.isalpha() for c in visible) / len(visible) if visible else 0.0
    return (
        stripped.isupper()
        and letter_ratio >= 0.8
        and 1 <= len(words) <= 8
        and 6 <= len(stripped) < 60
        and "=" not in stripped
    )


def _is_page_number(text: str, rect: fitz.Rect, page_height: float, margin: float = 50) -> bool:
    """차트의 축 눈금(0, 1, 2 ...)도 짧은 숫자라서, 페이지 위/아래 여백 근처에 있을
    때만 쪽 번호로 인정한다. 이 위치 조건이 없으면 차트 한가운데의 눈금 숫자에서
    스캔이 멈춰버린다."""
    stripped = text.strip()
    if not (stripped.isdigit() and len(stripped) <= 3):
        return False
    return rect.y0 < margin or rect.y1 > page_height - margin


def _hard_stop(text: str, rect: fitz.Rect, page_height: float, line_groups: list[dict]) -> bool:
    """캡션/섹션 제목/쪽 번호처럼, 표 내부 텍스트가 아무리 문단처럼 보여도 절대 넘지 말아야 할 경계.

    단, 표 구분선 안쪽의 텍스트는 섹션 제목이 될 수 없다. 표 셀의 "QWEN-CHAT", "LLAMA 2"
    같은 대문자 모델명이 제목으로 오인되면 표가 중간에서 잘린다.
    """
    if CAPTION_RE.match(text.strip()) or _is_page_number(text, rect, page_height):
        return True
    return _is_heading(text) and not _inside_ruled_table(rect, line_groups)


def _horizontal_overlap(a: fitz.Rect, b: fitz.Rect) -> float:
    left, right = max(a.x0, b.x0), min(a.x1, b.x1)
    if right <= left:
        return 0.0
    narrower = min(a.x1 - a.x0, b.x1 - b.x0)
    return (right - left) / narrower if narrower > 0 else 0.0


def _line_groups(
    drawings: list, caption_ys: list[float], page_height: float, min_width: float = 60, tol: float = 5
) -> list[dict]:
    """비슷한 가로 폭을 가진 얇은 수평선(표 구분선)들을 같은 표의 선으로 묶는다.

    같은 페이지에 폭이 같은 표가 위아래로 두 개 있으면 선들이 한 그룹으로 묶여, 두 표
    사이의 본문까지 "표 안쪽"으로 보이게 된다. 표마다 캡션이 하나씩 있으므로, 연속한 두
    선 사이에 캡션이 끼어 있으면 거기서 그룹을 나눈다.

    머리글/바닥글 구분선(페이지 위아래 여백의 선)은 표 구분선이 아니다. 본문 폭과 같은
    머리글 선이 그림 안의 선과 묶이면 페이지 윗부분 전체가 "표 안쪽"이 되어 버린다
    (Qwen3 Technical Report의 Figure 1).
    """
    groups: list[dict] = []
    for d in drawings:
        r = d["rect"]
        if r.y1 - r.y0 >= 1 or (r.x1 - r.x0) < min_width or _in_margin(r, page_height):
            continue
        for g in groups:
            if abs(g["x0"] - r.x0) <= tol and abs(g["x1"] - r.x1) <= tol:
                g["ys"].append(r.y0)
                break
        else:
            groups.append({"x0": r.x0, "x1": r.x1, "ys": [r.y0]})

    split_groups = []
    for g in groups:
        ys = sorted(g["ys"])
        current = [ys[0]]
        for y in ys[1:]:
            if any(current[-1] < cy < y for cy in caption_ys):
                split_groups.append({"x0": g["x0"], "x1": g["x1"], "ys": current})
                current = []
            current.append(y)
        split_groups.append({"x0": g["x0"], "x1": g["x1"], "ys": current})
    return split_groups


def _inside_ruled_table(rect: fitz.Rect, groups: list[dict]) -> bool:
    """표의 맨 위 구분선과 맨 아래 구분선 사이에 있으면, 내부 텍스트가 길게 이어져도 표 안으로 본다."""
    for g in groups:
        col = fitz.Rect(g["x0"], rect.y0, g["x1"], rect.y1)
        if _horizontal_overlap(rect, col) < 0.5:
            continue
        y0, y1 = min(g["ys"]), max(g["ys"])
        if y0 - 3 <= rect.y0 and rect.y1 <= y1 + 3:
            return True
    return False


def _union_rect(rects: list[fitz.Rect]) -> fitz.Rect:
    x0 = min(r.x0 for r in rects)
    y0 = min(r.y0 for r in rects)
    x1 = max(r.x1 for r in rects)
    y1 = max(r.y1 for r in rects)
    return fitz.Rect(x0, y0, x1, y1)


def _visible_drawing_rects(drawings: list) -> list[fitz.Rect]:
    """실제로 눈에 보이는 잉크(채우기/선)가 있는 드로잉만 남긴다.

    배경/클리핑용으로 그려진, 흰색으로 채워지고 테두리선이 없는 사각형은 시각적으로는
    빈 여백과 구분이 안 되지만 bbox만 아주 크게 잡히는 경우가 있어(예: 카드 배경 박스),
    이런 것까지 포함하면 크롭 영역이 근거 없이 확 넓어질 수 있다.
    """
    rects = []
    for d in drawings:
        fill = d.get("fill")
        is_white_fill = fill is not None and all(abs(c - 1.0) < 0.01 for c in fill)
        has_stroke = bool(d.get("stroke_opacity")) and d.get("width")
        if is_white_fill and not has_stroke:
            continue
        rects.append(d["rect"])
    return rects


def _merge_touching(region: fitz.Rect, candidates: list[fitz.Rect], tol: float = 3) -> fitz.Rect:
    """region에 맞닿거나 겹치는 사각형들을 연쇄적으로(flood-fill 방식) 합친다.

    "캡션에서 몇 pt 이내"처럼 고정된 여백을 두면, 실제로는 하나로 이어진 차트(막대/선 등
    작은 드로잉 수백 개로 구성)인데도 폭이 넓거나 높이가 크면 잘려나간다. 대신 서로
    맞닿아 있는지만 보고 계속 이어붙이면, 실제로 연결된 그림은 크기와 상관없이 전부
    모이고, 동떨어진 드로잉은 아무리 커도 섞여 들어오지 않는다.
    """
    remaining = list(candidates)
    changed = True
    while changed:
        changed = False
        expanded = fitz.Rect(region.x0 - tol, region.y0 - tol, region.x1 + tol, region.y1 + tol)
        still_remaining = []
        for r in remaining:
            if expanded.intersects(r):
                region = _union_rect([region, r])
                changed = True
            else:
                still_remaining.append(r)
        remaining = still_remaining
    return region


def _content_area(found: list) -> float:
    return _union_rect([c["rect"] for c in found]).get_area() if found else 0.0


def _caption_conventions(pending: list[dict]) -> dict:
    """그림/표 종류별로 이 문서가 캡션을 내용의 위에 두는지 아래에 두는지 다수결로 정한다.

    학회 양식마다 관례가 달라서(NeurIPS·arXiv 템플릿은 표 캡션이 위, ACL·CVPR은 아래가
    흔하다) 고정값을 쓸 수 없다. 한쪽에만 내용이 확연히 많은 "명확한" 캡션들만 표로
    세고, 표가 부족하거나 엇갈리면 None(관례 불명)을 돌려준다.

    반환값은 내용이 있는 방향이다: "up"이면 내용이 캡션 위(= 캡션이 아래)에 있다.
    """
    votes = {"Figure": {"up": 0, "down": 0}, "Table": {"up": 0, "down": 0}}
    for p in pending:
        up, down = p["area"]["up"], p["area"]["down"]
        if up > 0 and up >= 3 * down:
            votes[p["kind"]]["up"] += 1
        elif down > 0 and down >= 3 * up:
            votes[p["kind"]]["down"] += 1

    conventions = {}
    for kind, v in votes.items():
        if v["up"] >= 2 and v["up"] >= 2 * v["down"]:
            conventions[kind] = "up"
        elif v["down"] >= 2 and v["down"] >= 2 * v["up"]:
            conventions[kind] = "down"
        else:
            conventions[kind] = None
    return conventions


def _nearest_drawing(cap_rect: fitz.Rect, drawings: list[fitz.Rect], direction: str, max_gap: float = 20):
    """캡션 바로 위(또는 아래) max_gap 이내에서 같은 컬럼에 있는 가장 가까운 드로잉을 찾는다.

    LaTeX 기본 캡션 여백은 10pt 안팎이라 20pt면 충분하고, 그보다 멀리 있는 드로잉은
    다른 요소(옆 표의 구분선 등)일 가능성이 커서 잡지 않는다.
    """
    best, best_gap = None, max_gap
    for r in drawings:
        if _horizontal_overlap(cap_rect, r) < 0.3:
            continue
        gap = cap_rect.y0 - r.y1 if direction == "up" else r.y0 - cap_rect.y1
        if -1 <= gap <= best_gap:
            best, best_gap = r, gap
    return best


def _drawings_in_band(cap_rect: fitz.Rect, drawings: list[fitz.Rect], direction: str, limit: float) -> list[fitz.Rect]:
    """캡션과 limit(스캔이 멈춘 경계) 사이에 완전히 들어가는, 같은 컬럼의 드로잉들.

    페이지 밖까지 뻗은 클리핑용 사각형처럼 경계를 넘는 드로잉은 그림 조각이 아니므로 뺀다.
    """
    if direction == "up":
        y0, y1 = limit, cap_rect.y0
    else:
        y0, y1 = cap_rect.y1, limit
    return [
        r for r in drawings
        if _horizontal_overlap(cap_rect, r) >= 0.3 and r.y0 >= y0 - 1 and r.y1 <= y1 + 1
    ]


def _text_blocks(page: fitz.Page) -> list[dict]:
    """텍스트 블록마다 위치·텍스트와 함께 대표 글자 크기(글자 수 기준 최빈값)를 구한다.

    수식 추출에서 블록 안의 일부 줄만 잘라야 할 때가 있어 줄 단위 위치·텍스트도 남긴다.
    """
    blocks = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        lines, size_chars = [], {}
        for line in b["lines"]:
            lines.append(
                {
                    "rect": fitz.Rect(line["bbox"]),
                    "text": "".join(span["text"] for span in line["spans"]),
                    "fonts": {span["font"] for span in line["spans"] if span["text"].strip()},
                    "spans": [(span["font"], span["text"]) for span in line["spans"]],
                }
            )
            for span in line["spans"]:
                size = round(span["size"] * 2) / 2
                size_chars[size] = size_chars.get(size, 0) + len(span["text"].strip())
        text = "\n".join(line["text"] for line in lines) + "\n"
        if not text.strip():
            continue
        size = max(size_chars, key=size_chars.get) if size_chars else 0.0
        blocks.append({"rect": fitz.Rect(b["bbox"]), "text": text, "size": size, "lines": lines})
    return blocks


def _body_font_size(page_blocks: list[list[dict]]) -> float:
    """문서 전체에서 가장 많은 글자가 쓰인 크기를 본문 글자 크기로 본다."""
    size_chars: dict = {}
    for blocks in page_blocks:
        for b in blocks:
            size_chars[b["size"]] = size_chars.get(b["size"], 0) + len(b["text"])
    return max(size_chars, key=size_chars.get) if size_chars else 0.0


def _in_margin(rect: fitz.Rect, page_height: float, ratio: float = 0.1) -> bool:
    return rect.y1 < page_height * ratio or rect.y0 > page_height * (1 - ratio)


def _running_texts(page_blocks: list[list[dict]], page_heights: list[float], min_pages: int = 3) -> set:
    """페이지 위/아래 여백에 3쪽 이상 반복해서 나오는 텍스트(머리글/바닥글)를 찾는다.

    그림이 페이지 맨 위에 있으면 위로 스캔하다 "논문 제목"이나 "저자명" 머리글까지
    그림에 포함된다. 숫자(쪽 번호 등)를 지운 뒤 같은 문구가 여러 쪽에 반복되는지 본다.
    """
    pages_by_text: dict = {}
    for page_index, (blocks, height) in enumerate(zip(page_blocks, page_heights)):
        for b in blocks:
            if _in_margin(b["rect"], height):
                key = _normalize_running(b["text"])
                if key:
                    pages_by_text.setdefault(key, set()).add(page_index)
    return {key for key, pages in pages_by_text.items() if len(pages) >= min_pages}


def _normalize_running(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "", text)).strip().lower()


def extract_figures_and_tables(doc: fitz.Document, out_dir: Path) -> list[dict]:
    figures_dir = out_dir / "figures"
    tables_dir = out_dir / "tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    # 1차: 캡션마다 위/아래 양쪽 후보 내용을 모아만 둔다. 어느 쪽을 쓸지는 문서 전체의
    # 캡션 배치 관례를 본 뒤(2차) 정한다.
    pending = []
    page_blocks = [_text_blocks(page) for page in doc]
    body_size = _body_font_size(page_blocks)
    running = _running_texts(page_blocks, [page.rect.height for page in doc])
    for page_index, page in enumerate(doc, start=1):
        blocks = [
            b for b in page_blocks[page_index - 1]
            if not (_in_margin(b["rect"], page.rect.height) and _normalize_running(b["text"]) in running)
        ]
        drawings = page.get_drawings()
        images = page.get_image_info()
        caption_ys = [(b["rect"].y0 + b["rect"].y1) / 2 for b in blocks if CAPTION_RE.match(b["text"].strip())]
        line_groups = _line_groups(drawings, caption_ys, page.rect.height)
        visible_drawing_rects = _visible_drawing_rects(drawings)

        # 텍스트 블록과 임베딩 이미지를 하나의 "요소" 목록으로 합쳐서 위/아래로 스캔한다.
        # 표지(figure) 그림 자체가 raster 이미지라 주변에 텍스트가 거의 없는 경우(예: 이
        # 논문의 Figure 3~7)에도 이미지가 스캔 대상에 포함되어야 캡션과 함께 묶인다.
        elements = [{**b, "is_image": False} for b in blocks]
        elements += [{"rect": fitz.Rect(info["bbox"]), "text": None, "size": 0.0, "is_image": True} for info in images]
        elements.sort(key=lambda e: e["rect"].y0)

        for i, elem in enumerate(elements):
            if elem["is_image"]:
                continue
            text = elem["text"].strip()
            match = CAPTION_RE.match(text)
            if not match:
                continue
            kind = "Figure" if match.group(1).lower().startswith("fig") else "Table"
            num = int(match.group(2))
            cap_rect = fitz.Rect(elem["rect"])
            cap_top = cap_rect.y0

            # 캡션 둘째 줄부터 들여쓰기(hanging indent)가 있으면 캡션이 블록 여러 개로 쪼개진다.
            # 캡션 바로 아래 줄 간격(4pt) 이내로 붙어 있는 같은 컬럼 블록은 캡션의 연속으로 본다.
            continuation = set()
            for j in range(i + 1, len(elements)):
                cand = elements[j]
                if cand["is_image"] or _horizontal_overlap(cap_rect, cand["rect"]) < 0.3:
                    if cand["rect"].y0 > cap_rect.y1 + 4:
                        break
                    continue
                if cand["rect"].y0 - cap_rect.y1 > 4 or CAPTION_RE.match(cand["text"].strip()):
                    break
                # 캡션 옆으로 본문이 흐르는 배치(wrapfigure, QLoRA Table 1)에서는 옆 단 문단이 캡션 높이에서
                # 시작한다. 캡션보다 왼쪽에서 시작하는 블록은 옆 단이므로 캡션의 연속이 아니다. 캡션 첫 줄이
                # 위첨자 때문에 두 블록으로 쪼개진 경우(환각 논문 Figure 20)는 오른쪽에서 시작하므로 이어 붙인다.
                if cand["rect"].x0 < cap_rect.x0 - 5:
                    continue
                continuation.add(j)
                cap_rect |= cand["rect"]
                text += " " + cand["text"].strip()

            def scan(step: int) -> tuple[list, float, bool]:
                """내용 후보 목록, 스캔을 멈추게 한 요소의 경계 y좌표(없으면 페이지 끝), 다른 캡션에서
                멈췄는지를 돌려준다."""
                found = []
                limit = page.rect.y0 if step < 0 else page.rect.y1
                at_caption = False
                j = i + step
                while 0 <= j < len(elements):
                    cand = elements[j]
                    if j in continuation:
                        j += step
                        continue
                    # 캡션 옆 단에서 시작한 본문 블록(wrapfigure 옆으로 흐르는 문단, QLoRA Table 1)은
                    # 아래쪽 전폭 줄 때문에 캡션 열과 겹쳐 보여도 그림/표의 경계가 아니므로 건너뛴다.
                    beside = (
                        not cand["is_image"] and cand["rect"].x0 < cap_rect.x0 - 20
                        and cand["rect"].y0 < cap_rect.y1 and cand["rect"].y1 > cap_top
                    )
                    if not beside and _horizontal_overlap(cap_rect, cand["rect"]) >= 0.3:
                        if cand["is_image"]:
                            found.append(cand)
                        else:
                            cand_text = cand["text"]
                            # 셀 안의 서술형 텍스트(예: 사례 비교 박스)는 문단처럼 보이더라도
                            # 표 구분선 안쪽에 있으면 본문 문단으로 오인해 멈추지 않는다.
                            if _hard_stop(cand_text, cand["rect"], page.rect.height, line_groups) or (
                                _is_body_paragraph(cand_text, cand["rect"], cap_rect, cand["size"], body_size)
                                and not _inside_ruled_table(cand["rect"], line_groups)
                            ):
                                limit = cand["rect"].y1 if step < 0 else cand["rect"].y0
                                at_caption = bool(CAPTION_RE.match(cand_text.strip()))
                                break
                            found.append(cand)
                    j += step
                return found, limit, at_caption

            # 같은 컬럼(가로 겹침)에 있는 요소만 후보로 삼아 2단(2-column) 레이아웃에서
            # 다른 컬럼 내용이 섞이지 않게 한다.
            up_found, up_limit, up_at_caption = scan(-1)
            down_found, down_limit, down_at_caption = scan(1)
            pending.append(
                {
                    "kind": kind,
                    "num": num,
                    "page": page_index,
                    "page_rect": page.rect,
                    "caption": text,
                    "cap_rect": cap_rect,
                    "elem": {"rect": cap_rect, "is_image": False},
                    "found": {"up": up_found, "down": down_found},
                    "area": {"up": _content_area(up_found), "down": _content_area(down_found)},
                    "limit": {"up": up_limit, "down": down_limit},
                    "at_caption": {"up": up_at_caption, "down": down_at_caption},
                    "drawings": visible_drawing_rects,
                }
            )

    conventions = _caption_conventions(pending)

    # 2차: 문서 관례 방향을 우선으로 내용 쪽을 고르고, 맞닿은 벡터 드로잉까지 합친다.
    candidates = []
    for p in pending:
        preferred = conventions[p["kind"]]
        if preferred is None:
            # 관례를 알 수 없으면(그림/표가 한두 개뿐인 문서 등) 내용 면적이 큰 쪽을 쓴다.
            side = "up" if p["area"]["up"] >= p["area"]["down"] else "down"
        else:
            other = "down" if preferred == "up" else "up"
            # 관례 쪽 내용이 반대쪽보다 확연히 작을 때만 반대쪽을 쓴다. 캡션 위치가 문서
            # 안에서 섞여 있는 경우(예: LightRAG의 Figure 2)를 위한 예외다. 면적만으로
            # 고르면, 바로 옆 표의 본문이 더 큰 경우 그 표의 내용을 가져와 버린다.
            # 단, 반대쪽 스캔이 다른 캡션에서 멈췄다면 그 내용은 관례상 그 캡션의 것이다(QLoRA 6쪽:
            # Figure 2 아래쪽 차트는 Figure 3의 것). 관례 쪽 차트가 글자 없는 벡터 그림이라 면적이
            # 작게 잡혀도 반대쪽으로 넘어가지 않는다.
            if p["area"][preferred] < 0.3 * p["area"][other] and not p["at_caption"][other]:
                side = other
            else:
                side = preferred
        collected = [p["elem"]] + p["found"][side]

        region = _union_rect([c["rect"] for c in collected])
        # 이미지 없이 글자 조각만 조금 잡힌 경우(축 라벨 "Model" 하나, QLoRA Figure 2)도 벡터 차트일 수 있다.
        content_area = _content_area(p["found"][side])
        sparse = not any(c["is_image"] for c in collected) and content_area < 0.1 * p["cap_rect"].width ** 2
        if len(collected) == 1 or sparse:
            # 캡션 외에 텍스트·이미지가 하나도 없으면, 글자까지 선으로 그려진 벡터 차트일 수
            # 있다(예: Qwen의 Figure 2 레이더 차트). 이런 차트는 조각(축 라벨, 눈금, 선)
            # 사이가 떨어져 있어 "맞닿은 것만 합치기"로는 다 모이지 않는다. 캡션 바로 옆
            # 여백 너머에 드로잉이 있으면, 캡션과 스캔이 멈춘 경계(앞 문단 등) 사이에 있는
            # 같은 컬럼의 드로잉을 전부 그림으로 본다.
            for direction in (side, "down" if side == "up" else "up"):
                if _nearest_drawing(p["cap_rect"], p["drawings"], direction) is None:
                    continue
                band = _drawings_in_band(p["cap_rect"], p["drawings"], direction, p["limit"][direction])
                region = _union_rect([region] + band)
                break
        region = _merge_touching(region, p["drawings"]) & p["page_rect"]

        # 본문 문장이 우연히 "Table 4 presents ..."처럼 번호로 시작하는 경우도 캡션으로
        # 잡힌다. 같은 번호의 후보가 여럿이면, 실제 이미지·벡터 드로잉이 더 많이 딸려온
        # 쪽(진짜 그림/표일 가능성이 높은 쪽)을 고르기 위한 점수를 매겨둔다.
        # 본문 언급 형태의 후보는 이미지 근처에 있더라도 진짜 캡션 후보가 있으면 항상 진다.
        has_image = any(c["is_image"] for c in collected)
        drawing_area = sum(r.get_area() for r in p["drawings"] if region.intersects(r))
        score = (1e9 if has_image else 0) + drawing_area - (1e10 if _looks_like_mention(p["caption"]) else 0)

        candidates.append(
            {
                "kind": p["kind"],
                "num": p["num"],
                "page": p["page"],
                "caption": p["caption"],
                "region": region,
                "score": score,
            }
        )

    # (kind, num)이 같은 후보가 여럿이면 점수가 가장 높은 것 하나만 남긴다.
    best_by_key: dict[tuple, dict] = {}
    for cand in candidates:
        key = (cand["kind"], cand["num"])
        if key not in best_by_key or cand["score"] > best_by_key[key]["score"]:
            best_by_key[key] = cand

    manifest = []
    for cand in best_by_key.values():
        page = doc[cand["page"] - 1]
        region = cand["region"]
        pad = 4
        clip = fitz.Rect(region.x0 - pad, region.y0 - pad, region.x1 + pad, region.y1 + pad) & page.rect
        pix = page.get_pixmap(clip=clip, dpi=200)

        target_dir = figures_dir if cand["kind"] == "Figure" else tables_dir
        prefix = "figure" if cand["kind"] == "Figure" else "table"
        filename = f"{prefix}_{cand['num']:02d}_page{cand['page']:03d}.png"
        pix.save(target_dir / filename)
        manifest.append(
            {
                "kind": cand["kind"],
                "num": cand["num"],
                "page": cand["page"],
                "file": filename,
                "caption": cand["caption"],
                "region": clip,  # 수식 추출에서 그림/표 안의 텍스트를 수식으로 오인하지 않도록 넘긴다.
            }
        )

    n_figures = sum(1 for m in manifest if m["kind"] == "Figure")
    n_tables = sum(1 for m in manifest if m["kind"] == "Table")
    print(f"[figures] 그림 {n_figures}개 추출 완료 -> {figures_dir}")
    print(f"[tables] 표 {n_tables}개 추출 완료 -> {tables_dir}")
    return manifest


# 정리/예제 등의 머리("Example 4. Given", "Theorem 2.")는 수식이 아니라 본문 구조다.
THEOREM_HEAD_RE = re.compile(
    r"^(theorem|lemma|definition|example|proof|corollary|proposition|remark|assumption)\b", re.IGNORECASE
)
# 수식 바로 앞 줄을 끝맺는 연결어("... for each n, so", "... together with ... gives").
LEAD_IN_RE = re.compile(r"(\b(so|gives|that|where|yields|hence|thus|obtain|have|get|with|follows)|:)\s*$")


def _is_prose(text: str) -> bool:
    """수식 사이에 끼어 있는 설명 문장("With trained matrices:", "Then the resulting
    response r is creatively bounded:")인지 본다.

    수식에도 "for all", "arg max", "cost(f)" 같은 단어가 들어가지만, 4글자 이상 영어
    단어가 3개 이상이고 그 단어들이 글자의 30% 이상을 차지하면 문장으로 본다. 이론
    논문의 본문은 줄마다 기호가 많이 섞여 있어 기준을 그보다 높이면 본문을 놓친다.
    """
    stripped = text.strip()
    if THEOREM_HEAD_RE.match(stripped) or (LEAD_IN_RE.search(stripped) and re.search(r"[A-Za-z]{4,}", stripped)):
        return True
    visible = len(re.sub(r"\s", "", stripped))
    words = re.findall(r"[A-Za-z]{4,}", stripped)
    return visible > 0 and len(words) >= 3 and sum(len(w) for w in words) >= 0.3 * visible


def _column_span(paragraph_rects: list[fitz.Rect], x: float, text_area: fitz.Rect) -> tuple[float, float]:
    """x좌표(수식 번호 위치)가 속한 본문 컬럼의 좌우 범위. 2단 양식에서 옆 단의 블록이 같은
    높이에 있다는 이유로 수식에 섞이지 않게 한다. 근처 본문 문단이 없으면 페이지의 글자 영역 전체."""
    spans = sorted((r.x0, r.x1) for r in paragraph_rects if r.x0 - 5 <= x <= r.x1 + 5)
    if not spans:
        return text_area.x0 - 5, text_area.x1 + 5
    mid = spans[len(spans) // 2]
    return mid[0] - 5, mid[1] + 5


def _equation_numbers(text: str) -> list[int]:
    """줄 끝의 수식 번호들. 본문 문장이 "... as shown in (3)"처럼 줄 끝에서 번호를 언급하는
    경우는 번호 앞부분이 문장이므로 제외한다."""
    numbers = []
    for line in text.split("\n"):
        m = EQUATION_NUM_RE.search(line)
        if m and not _is_prose(line[: m.start()]):
            numbers.append(int(m.group(1)))
    return numbers


def _in_span(rect: fitz.Rect, x0: float, x1: float) -> bool:
    return rect.width > 0 and min(rect.x1, x1) - max(rect.x0, x0) >= 0.5 * rect.width


def _rows(lines: list[tuple[dict, int]]) -> list[dict]:
    """(줄, 블록 번호) 목록을 세로로 겹치는 것끼리 화면상의 한 줄(row)로 묶는다.

    수식 번호 줄과 같은 높이의 수식 본체도 같은 row가 되므로, 수식 본체에 "(initial
    knowledge state)" 같은 설명이 붙어 있어도 번호와 함께 항상 포함된다(환각 논문 수식 (29)).
    """
    rows: list[dict] = []
    for line, k in sorted(lines, key=lambda t: (t[0]["rect"].y0 + t[0]["rect"].y1) / 2):
        r = line["rect"]
        for row in reversed(rows[-3:]):
            rr = row["rect"]
            if min(r.y1, rr.y1) - max(r.y0, rr.y0) > 0.5 * min(r.height, rr.height):
                row["lines"].append((line, k))
                row["rect"] = rr | r
                break
        else:
            rows.append({"rect": fitz.Rect(r), "lines": [(line, k)]})
    rows.sort(key=lambda row: row["rect"].y0)
    for row in rows:
        row["text"] = " ".join(line["text"] for line, _ in sorted(row["lines"], key=lambda t: t[0]["rect"].x0))
    return rows


# TeX 수식 글꼴(cmmi 이탤릭, cmsy 기호, cmex 큰 기호, AMS msbm/msam)과 유니코드 수식 글꼴.
MATH_FONT_RE = re.compile(r"CMMI|CMSY|CMEX|CMBSY|MSBM|MSAM|EUFM|RSFS|Math|STIX|Symbol", re.IGNORECASE)
MONO_FONT_RE = re.compile(r"TT\d|Mono|Courier|Typewriter", re.IGNORECASE)
MATH_CHARS = set("=<>≤≥≠≈∈∉⊂⊆⊃⊇∑∏∫√∞→←↦⇒⇔∀∃∧∨⋃⋂∪∩±×·∂∇−")


def _center(rect: fitz.Rect) -> fitz.Point:
    return fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)


def _has_math(row: dict) -> bool:
    """수식 글꼴로 쓰인 글자가 있는 줄인지. "=" 같은 기호만으로 판단하면 본문 글꼴로 조판한
    코드 목록("tmp = []", Qwen 부록)까지 수식이 되므로 글꼴로 본다."""
    return any(MATH_FONT_RE.search(font) for line, _ in row["lines"] for font in line.get("fonts", ()))


def _visible_len(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def _row_is_prose(row: dict, text_fonts: set) -> bool:
    """본문 글꼴 글자가 줄의 절반 이상이고 그 글자들이 문장일 때만 문장으로 본다. 수식 안의
    "logit", "log" 같은 연산자 이름이 본문 글꼴로 조판돼도(Boogu 42쪽) 수식 줄로 남는다."""
    text_part = " ".join(t for line, _ in row["lines"] for f, t in line.get("spans", ()) if f in text_fonts)
    return _visible_len(text_part) >= 0.5 * _visible_len(row["text"]) and _is_prose(text_part)


def _math_dominant(row: dict) -> bool:
    """수식 기호가 있거나 수식 글꼴 글자가 절반 이상인 줄. 들여쓴 짧은 이탤릭 문구("token Xt.")처럼
    아래첨자 하나만 수식 글꼴인 줄을 거른다."""
    if any(c in MATH_CHARS for c in row["text"]):
        return True
    # 고정폭(코드) 글꼴로 쓴 함수 호출("submit(R∗)", Anemoi 6쪽)도 수식 쪽으로 센다.
    math = sum(
        _visible_len(t) for line, _ in row["lines"] for f, t in line.get("spans", ())
        if MATH_FONT_RE.search(f) or MONO_FONT_RE.search(f)
    )
    return math >= 0.5 * _visible_len(row["text"])


def _text_fonts(doc: fitz.Document, min_share: float = 0.02) -> set:
    """본문 문장에 쓰이는 글꼴들(기본·이탤릭·굵은 글씨 등). 본문 문단 글자의 2% 이상을 차지하는
    수식 글꼴이 아닌 글꼴로 본다. 본문 문단 속 짧은 수식의 숫자·괄호에 쓰인 CMR(Anemoi 1% 미만)은
    빠지고, 이론 논문의 이탤릭 본문 CMTI(약 10%)는 들어간다."""
    counts: dict = {}
    total = 0
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            lines = b.get("lines", [])
            text = "\n".join("".join(s["text"] for s in line["spans"]) for line in lines)
            if not (_is_paragraph(text) and _is_prose(text)):
                continue
            for line in lines:
                for span in line["spans"]:
                    n = len(span["text"].strip())
                    counts[span["font"]] = counts.get(span["font"], 0) + n
                    total += n
    return {f for f, n in counts.items() if total and n / total >= min_share and not MATH_FONT_RE.search(f)}


def _equation_clip(
    page: fitz.Page, rows: list[dict], members: list[int], drawings: list[fitz.Rect], x0: float, x1: float
) -> fitz.Rect:
    """수식 줄(members)의 크롭 영역. 번호 있는 수식과 번호 없는 수식이 같은 규칙을 쓴다."""
    region = _union_rect([rows[r]["rect"] for r in members])
    # 분수선·근호처럼 선으로 그려진 수식 기호는 붙여 넣되, 표 테두리 같은 큰 선이
    # 딸려 오지 않도록 같은 컬럼 안의 작은 드로잉만 쓴다.
    small = [d for d in drawings if d.height <= 40 and d.x0 >= x0 - 1 and d.x1 <= x1 + 1]
    region = _merge_touching(region, small)

    # 수식 위아래 본문 줄과 간격이 좁아서, 그림/표처럼 4pt 여백을 주면 이웃 줄 윗부분이 걸린다.
    pad = 2
    clip = fitz.Rect(region.x0 - pad, region.y0 - pad, region.x1 + pad, region.y1 + pad) & page.rect
    # 분수·합 기호 조각의 경계가 다음 문단 시작 높이까지 닿는 경우가 있어서, 같은 컬럼의
    # 수식 밖 줄 경계를 넘지 않게 위아래를 자른다(환각 논문 수식 (150)).
    for r, row in enumerate(rows):
        if r in members:
            continue
        if row["rect"].y0 >= region.y1 - 2:
            clip.y1 = min(clip.y1, max(row["rect"].y0, region.y1))
        elif row["rect"].y1 <= region.y0 + 2:
            clip.y0 = max(clip.y0, min(row["rect"].y1, region.y0))
    return clip


def _nearest_numbered(rows: list[dict], numbered_rows: set, r: int) -> int:
    center = (rows[r]["rect"].y0 + rows[r]["rect"].y1) / 2
    return min(numbered_rows, key=lambda n: abs((rows[n]["rect"].y0 + rows[n]["rect"].y1) / 2 - center))


def extract_equations(doc: fitz.Document, out_dir: Path, figures_and_tables: list[dict] | None = None) -> list[dict]:
    """번호가 붙은 수식("(1)")을 찾아 수식 하나(또는 번호가 여러 개 붙은 수식 덩어리 하나)당
    이미지 한 장으로 저장한다.

    수식은 같은 줄에서도 기호별 블록 여러 개로 쪼개져 있어서, 번호 블록(앵커)에서 위아래로
    문장이 아닌 블록을 모은다. 위아래 수식 사이의 조각은 양쪽 앵커가 모두 모으므로, 수직
    거리가 더 가까운 앵커 하나에만 배정해 같은 수식이 여러 장으로 중복 저장되지 않게 한다.
    """
    eq_dir = out_dir / "equations"
    eq_dir.mkdir(parents=True, exist_ok=True)
    excluded_by_page: dict = {}
    for item in figures_and_tables or []:
        excluded_by_page.setdefault(item["page"], []).append(item["region"])

    page_blocks = [_text_blocks(page) for page in doc]
    running = _running_texts(page_blocks, [page.rect.height for page in doc])
    text_fonts = _text_fonts(doc)

    manifest = []
    numbered_count = 0
    for page_index, page in enumerate(doc, start=1):
        height = page.rect.height
        excluded = excluded_by_page.get(page_index, [])
        blocks = []
        for b in page_blocks[page_index - 1]:
            if _in_margin(b["rect"], height) and (
                _normalize_running(b["text"]) in running or b["text"].strip().isdigit()
            ):
                continue  # 머리글/바닥글, 쪽 번호
            if any(region.contains(b["rect"]) or (region & b["rect"]).get_area() > 0.5 * b["rect"].get_area()
                   for region in excluded):
                continue  # 그림/표 안의 텍스트(축 라벨 "π(1)" 등)
            blocks.append(b)
        paragraph_rects = [b["rect"] for b in blocks if _is_paragraph(b["text"])]
        # 본문 문단 블록(줄이 길고 문장인 블록)의 줄은 수식 경계로 쓴다. 기호가 많아 줄 하나만
        # 보면 문장 같지 않은 이론 논문 본문 줄도 블록 전체로는 문장으로 판정된다.
        prose_blocks = {k for k, b in enumerate(blocks) if _is_paragraph(b["text"]) and _is_prose(b["text"])}
        lines = [(line, k) for k, b in enumerate(blocks) for line in b["lines"] if line["text"].strip()]
        if not lines:
            continue
        numbered = [(line, k) for line, k in lines if _equation_numbers(line["text"])]

        drawings = _visible_drawing_rects(page.get_drawings())
        text_area = _union_rect([b["rect"] for b in blocks])
        done_rows = set()
        page_clips: list[fitz.Rect] = []
        for number_line, _ in sorted(numbered, key=lambda t: t[0]["rect"].y0):
            # 번호가 있는 컬럼의 줄들을 화면상의 한 줄(row) 단위로 묶는다. 한 문장이 블록 여러
            # 개로 쪼개져 있어도("where s∗" + "i(θi) represents ..."), 줄 단위로 합쳐야 문장으로 보인다.
            x0, x1 = _column_span(paragraph_rects, number_line["rect"].x1 - 1, text_area)
            # 수식 번호는 컬럼 오른쪽 끝에 붙는다. 코드 목록의 "G.unsqueeze (0)"처럼 줄 중간에서
            # 끝나는 괄호 숫자는 번호가 아니다(Boogu 70쪽).
            if x1 - number_line["rect"].x1 > max(15, 0.08 * (x1 - x0)):
                continue
            rows = _rows([(line, k) for line, k in lines if _in_span(line["rect"], x0, x1)])
            k_anchor = next(r for r, row in enumerate(rows) if any(line is number_line for line, _ in row["lines"]))
            key = (x0, x1, k_anchor)
            if key in done_rows:
                continue  # 같은 줄에 번호가 둘 이상 붙은 경우
            numbered_rows = {
                r for r, row in enumerate(rows) if any(_equation_numbers(line["text"]) for line, _ in row["lines"])
            }
            done_rows.add(key)

            # 위아래로 문장 줄, 본문 문단, 제목/캡션, 다른 수식 번호 줄을 만날 때까지 넓힌다.
            members = [k_anchor]
            for step in (-1, 1):
                r = k_anchor + step
                while 0 <= r < len(rows):
                    row = rows[r]
                    if (
                        r in numbered_rows
                        or _is_prose(row["text"])
                        or _hard_stop(row["text"], row["rect"], height, [])
                        or any(k in prose_blocks for _, k in row["lines"])
                    ):
                        break
                    # 두 수식 사이의 줄은 더 가까운 번호 쪽 수식에 속한다.
                    if _nearest_numbered(rows, numbered_rows, r) != k_anchor:
                        break
                    members.append(r)
                    r += step

            clip = _equation_clip(page, rows, members, drawings, x0, x1)
            numbers = [n for line, _ in rows[k_anchor]["lines"] for n in _equation_numbers(line["text"])]
            numbered_count += 1
            filename = f"equation_{numbered_count:03d}_page{page_index:03d}.png"
            page.get_pixmap(clip=clip, dpi=200).save(eq_dir / filename)
            label = ", ".join(f"({n})" for n in numbers)
            text = " ".join(rows[r]["text"] for r in sorted(members))
            manifest.append(
                {"page": page_index, "file": filename, "numbers": numbers, "caption": f"{label} {text}", "region": clip}
            )
            page_clips.append(clip)

        # 번호 없는 수식: 본문 줄보다 안쪽에서 시작하고, 문장이 아니며, 수식 글꼴이나 수식 기호로
        # 이루어진 줄. 본문 문장 속의 짧은 수식("ai ∈ A")은 문장과 같은 줄이라 대상이 아니다.
        # 1쪽의 제목·저자·소속은 위첨자 기호(∗, ‡) 때문에 수식처럼 보이므로 "Abstract" 제목
        # (없으면 첫 본문 문단) 위쪽은 보지 않는다.
        front_end = 0.0
        if page_index == 1:
            abstract = [b["rect"].y0 for b in blocks if b["text"].strip().lower().startswith("abstract")]
            front_end = min(abstract) if abstract else min((r.y0 for r in paragraph_rects), default=0.0)
        free_lines = [
            (line, k) for line, k in lines
            if not any(c.contains(_center(line["rect"])) for c in page_clips) and line["rect"].y0 >= front_end
        ]
        spans: dict = {}
        for line, k in free_lines:
            span = _column_span(paragraph_rects, _center(line["rect"]).x, text_area)
            spans.setdefault(span, []).append((line, k))
        unnumbered = []
        for (x0, x1), span_lines in spans.items():
            rows = _rows(span_lines)
            # 문장 판정은 본문 글꼴로 쓰인 글자만 본다. 수식 글꼴로 쓰인 "list_agents", "namej"(Anemoi),
            # "logit", "tshift"(Boogu) 같은 식별자는 영어 단어가 아니다.
            display = [
                r for r, row in enumerate(rows)
                if row["rect"].x0 - x0 >= 0.15 * (x1 - x0)
                and not _row_is_prose(row, text_fonts)
                and not _hard_stop(row["text"], row["rect"], height, [])
                and _has_math(row)
            ]
            # 위아래로 붙은 줄(여러 줄 수식, 따로 떨어진 위·아래 첨자)은 한 수식으로 묶는다.
            groups: list[list[int]] = []
            for r in display:
                if groups and r == groups[-1][-1] + 1 and rows[r]["rect"].y0 - rows[groups[-1][-1]]["rect"].y1 <= 6:
                    groups[-1].append(r)
                else:
                    groups.append([r])
            for members in groups:
                text = " ".join(rows[r]["text"] for r in members)
                # "( 1", "∫ x"처럼 큰 기호가 본문 줄에서 떨어져 나온 조각은 수식이 아니다.
                if len(re.sub(r"\s", "", text)) < 4:
                    continue
                # 수식 비중은 묶은 수식 전체로 본다. 분자 줄의 "t_shift"처럼 아래첨자만 본문 글꼴인
                # 줄도 같은 수식의 일부로 남는다(Boogu 42쪽).
                if not _math_dominant({"text": text, "lines": [lt for r in members for lt in rows[r]["lines"]]}):
                    continue
                clip = _equation_clip(page, rows, members, drawings, x0, x1)
                unnumbered.append((clip, text))

        for k, (clip, text) in enumerate(sorted(unnumbered, key=lambda t: (t[0].y0, t[0].x0)), start=1):
            filename = f"equation_page{page_index:03d}_{k:02d}.png"
            page.get_pixmap(clip=clip, dpi=200).save(eq_dir / filename)
            label = f"p{page_index}-{k}"
            manifest.append(
                {"page": page_index, "file": filename, "numbers": [], "label": label, "caption": f"[{label}] {text}", "region": clip}
            )

    n_unnumbered = sum(1 for m in manifest if not m["numbers"])
    print(f"[equations] 수식 {len(manifest)}개(번호 없는 수식 {n_unnumbered}개 포함) 추출 완료 -> {eq_dir}")
    return manifest


def write_report(
    out_dir: Path, pdf_path: Path, page_count: int, manifest: list[dict], equations: list[dict]
) -> None:
    figures = sorted((m for m in manifest if m["kind"] == "Figure"), key=lambda m: m["num"])
    tables = sorted((m for m in manifest if m["kind"] == "Table"), key=lambda m: m["num"])

    lines = [
        f"# 추출 리포트: {pdf_path.name}",
        "",
        f"- 처리 일시: {date.today().isoformat()}",
        f"- 총 페이지 수: {page_count}",
        f"- 추출된 그림 수: {len(figures)}",
        f"- 추출된 표 수: {len(tables)}",
        f"- 추출된 수식 수: {len(equations)}",
        "",
        "## 그림 목록",
        "",
    ]
    for fig in figures:
        lines.append(f"- page {fig['page']}: `{fig['file']}` — {fig['caption']}")

    lines += ["", "## 표 목록", ""]
    for tbl in tables:
        lines.append(f"- page {tbl['page']}: `{tbl['file']}` — {tbl['caption']}")

    lines += ["", "## 수식 목록", ""]
    for eq in equations:
        lines.append(f"- page {eq['page']}: `{eq['file']}` — {eq['caption']}")

    # PDF 글꼴에 따라 캡션 텍스트에 제어 문자("\x00" 등)가 섞여 나오면 리포트가 바이너리
    # 파일로 취급되므로, 줄바꿈 외의 제어 문자는 지운다.
    report = re.sub(r"[\x00-\x09\x0b-\x1f]", "", "\n".join(lines))
    (out_dir / "extraction_report.md").write_text(report, encoding="utf-8")
    print(f"[report] 리포트 저장 완료 -> {out_dir / 'extraction_report.md'}")


def output_path(pdf_path: Path) -> Path:
    """기존 CLI와 실행기가 공유하는 기본 추출 경로."""
    stem = pdf_path.stem
    if len(stem) > 60:
        stem = stem[:60].rsplit(" ", 1)[0].rstrip(" -_")
    return PROJECT_DIR / "output" / f"{stem}_extract_{date.today().isoformat()}"


def main(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description="PDF에서 텍스트/그림/표를 추출한다.")
    parser.add_argument("--pdf", default=str(PROJECT_DIR / "input" / "LIGHTRAG.pdf"), help="입력 PDF 경로")
    parser.add_argument("--output-dir", help="추출 폴더 (생략하면 기존 날짜별 경로)")
    args = parser.parse_args(argv)

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF를 찾을 수 없습니다: {pdf_path}")

    # 논문 제목이 긴 파일명은 결과 폴더 경로가 Windows 경로 길이 제한(260자)을 넘길 수 있어서
    # 폴더 이름에는 앞 60자(단어 경계)까지만 쓴다.
    out_dir = Path(args.output_dir).resolve() if args.output_dir else output_path(pdf_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    # 텍스트 정리에 그림/표/수식 영역이 필요하므로 텍스트는 마지막에 추출한다.
    manifest = extract_figures_and_tables(doc, out_dir)
    equations = extract_equations(doc, out_dir, manifest)
    extract_text(doc, out_dir, manifest, equations)
    write_report(out_dir, pdf_path, len(doc), manifest, equations)
    doc.close()

    print(f"\n완료. 결과 폴더: {out_dir}")
    return out_dir


if __name__ == "__main__":
    main()
