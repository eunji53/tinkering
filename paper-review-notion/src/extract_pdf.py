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
# 4자리인 경우는 제외해 본문 인용과 헷갈리지 않게 한다.
EQUATION_END_RE = re.compile(r"\(\d{1,3}\)\s*$")


def extract_text(doc: fitz.Document, out_dir: Path) -> None:
    text_dir = out_dir / "text"
    text_dir.mkdir(parents=True, exist_ok=True)

    full_text_parts = []
    for page_index, page in enumerate(doc, start=1):
        page_text = page.get_text()
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


def _is_heading(text: str) -> bool:
    stripped = text.strip()
    if HEADING_RE.match(stripped):
        return True
    words = stripped.split()
    # "M =" 같은 짧은 수식 조각이 대문자 한 글자 때문에 헤딩으로 오인되지 않도록
    # 최소 길이와 '=' 미포함 조건을 둔다. 실제 섹션 제목(ABSTRACT 등)은 이 조건을 만족한다.
    return stripped.isupper() and 1 <= len(words) <= 8 and 6 <= len(stripped) < 60 and "=" not in stripped


def _is_page_number(text: str, rect: fitz.Rect, page_height: float, margin: float = 50) -> bool:
    """차트의 축 눈금(0, 1, 2 ...)도 짧은 숫자라서, 페이지 위/아래 여백 근처에 있을
    때만 쪽 번호로 인정한다. 이 위치 조건이 없으면 차트 한가운데의 눈금 숫자에서
    스캔이 멈춰버린다."""
    stripped = text.strip()
    if not (stripped.isdigit() and len(stripped) <= 3):
        return False
    return rect.y0 < margin or rect.y1 > page_height - margin


def _hard_stop(text: str, rect: fitz.Rect, page_height: float) -> bool:
    """캡션/섹션 제목/쪽 번호처럼, 표 내부 텍스트가 아무리 문단처럼 보여도 절대 넘지 말아야 할 경계."""
    return bool(CAPTION_RE.match(text.strip())) or _is_heading(text) or _is_page_number(text, rect, page_height)


def _horizontal_overlap(a: fitz.Rect, b: fitz.Rect) -> float:
    left, right = max(a.x0, b.x0), min(a.x1, b.x1)
    if right <= left:
        return 0.0
    narrower = min(a.x1 - a.x0, b.x1 - b.x0)
    return (right - left) / narrower if narrower > 0 else 0.0


def _line_groups(drawings: list, min_width: float = 60, tol: float = 5) -> list[dict]:
    """비슷한 가로 폭을 가진 얇은 수평선(표 구분선)들을 같은 표의 선으로 묶는다."""
    groups: list[dict] = []
    for d in drawings:
        r = d["rect"]
        if r.y1 - r.y0 >= 1 or (r.x1 - r.x0) < min_width:
            continue
        for g in groups:
            if abs(g["x0"] - r.x0) <= tol and abs(g["x1"] - r.x1) <= tol:
                g["ys"].append(r.y0)
                break
        else:
            groups.append({"x0": r.x0, "x1": r.x1, "ys": [r.y0]})
    return groups


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


def extract_figures_and_tables(doc: fitz.Document, out_dir: Path) -> list[dict]:
    figures_dir = out_dir / "figures"
    tables_dir = out_dir / "tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    candidates = []
    for page_index, page in enumerate(doc, start=1):
        blocks = [b for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]
        drawings = page.get_drawings()
        images = page.get_image_info()
        line_groups = _line_groups(drawings)
        visible_drawing_rects = _visible_drawing_rects(drawings)

        # 텍스트 블록과 임베딩 이미지를 하나의 "요소" 목록으로 합쳐서 위/아래로 스캔한다.
        # 표지(figure) 그림 자체가 raster 이미지라 주변에 텍스트가 거의 없는 경우(예: 이
        # 논문의 Figure 3~7)에도 이미지가 스캔 대상에 포함되어야 캡션과 함께 묶인다.
        elements = [
            {"rect": fitz.Rect(b[0], b[1], b[2], b[3]), "text": b[4], "is_image": False} for b in blocks
        ]
        elements += [{"rect": fitz.Rect(info["bbox"]), "text": None, "is_image": True} for info in images]
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
            cap_rect = elem["rect"]

            def scan(step: int) -> list:
                found = []
                j = i + step
                while 0 <= j < len(elements):
                    cand = elements[j]
                    if _horizontal_overlap(cap_rect, cand["rect"]) >= 0.3:
                        if cand["is_image"]:
                            found.append(cand)
                        else:
                            cand_text = cand["text"]
                            if _hard_stop(cand_text, cand["rect"], page.rect.height):
                                break
                            # 셀 안의 서술형 텍스트(예: 사례 비교 박스)는 문단처럼 보이더라도
                            # 표 구분선 안쪽에 있으면 본문 문단으로 오인해 멈추지 않는다.
                            if _is_paragraph(cand_text) and not _inside_ruled_table(cand["rect"], line_groups):
                                break
                            found.append(cand)
                    j += step
                return found

            # 캡션이 그림/표 "위"에 있는 경우와 "아래"에 있는 경우가 문서 안에 섞여
            # 있을 수 있어(예: 이 논문의 Figure 2), 위/아래를 모두 스캔해 실제 내용이
            # 있는 쪽을 선택한다. 같은 컬럼(가로 겹침)에 있는 요소만 후보로 삼아
            # 2단(2-column) 레이아웃에서 다른 컬럼 내용이 섞이지 않게 한다.
            # 판단 기준은 "블록 개수"가 아니라 "차지하는 면적"이다. 실제 그림(이미지
            # 1~2개)이 옆 그림의 축 눈금·범례처럼 작은 텍스트 조각 여러 개보다 개수는
            # 적어도 훨씬 더 의미 있는 내용이기 때문이다.
            up_found = scan(-1)
            down_found = scan(1)
            up_area = _union_rect([cap_rect] + [c["rect"] for c in up_found]).get_area() if up_found else 0
            down_area = _union_rect([cap_rect] + [c["rect"] for c in down_found]).get_area() if down_found else 0
            collected = [elem] + (up_found if up_area >= down_area else down_found)

            region = _union_rect([c["rect"] for c in collected])
            region = _merge_touching(region, visible_drawing_rects)

            # 본문 문장이 우연히 "Table 4 presents ..."처럼 번호로 시작하는 경우도 캡션으로
            # 잡힌다. 같은 번호의 후보가 여럿이면, 실제 이미지·벡터 드로잉이 더 많이 딸려온
            # 쪽(진짜 그림/표일 가능성이 높은 쪽)을 고르기 위한 점수를 매겨둔다.
            has_image = any(c["is_image"] for c in collected)
            drawing_area = sum(r.get_area() for r in visible_drawing_rects if region.intersects(r))
            score = (1e9 if has_image else 0) + drawing_area - (1e6 if _is_paragraph(text) else 0)

            candidates.append(
                {
                    "kind": kind,
                    "num": num,
                    "page": page_index,
                    "caption": text,
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
            {"kind": cand["kind"], "num": cand["num"], "page": cand["page"], "file": filename, "caption": cand["caption"]}
        )

    n_figures = sum(1 for m in manifest if m["kind"] == "Figure")
    n_tables = sum(1 for m in manifest if m["kind"] == "Table")
    print(f"[figures] 그림 {n_figures}개 추출 완료 -> {figures_dir}")
    print(f"[tables] 표 {n_tables}개 추출 완료 -> {tables_dir}")
    return manifest


def extract_equations(doc: fitz.Document, out_dir: Path) -> list[dict]:
    eq_dir = out_dir / "equations"
    eq_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    eq_num = 0
    for page_index, page in enumerate(doc, start=1):
        blocks = [b for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]
        blocks.sort(key=lambda b: b[1])
        drawings = page.get_drawings()
        visible_drawing_rects = _visible_drawing_rects(drawings)

        for i, block in enumerate(blocks):
            text = block[4].strip()
            if not EQUATION_END_RE.search(text) or _is_paragraph(text):
                continue

            # 수식은 같은 줄(y좌표가 거의 같음)에 여러 조각(기호별 블록)으로 쪼개져 있고,
            # 그 조각들이 꼭 앵커(번호가 붙은 블록) "위"에만 있다고 보장할 수 없다(같은
            # y좌표를 가진 블록끼리는 원본 PDF 내부 순서대로 정렬되기 때문). 그래서 위/아래
            # 양쪽으로 스캔해 문단이 아닌 조각들을 모두 모은다.
            collected = [block]
            for step in (-1, 1):
                j = i + step
                while 0 <= j < len(blocks):
                    cand_text = blocks[j][4].strip()
                    cand_rect = fitz.Rect(blocks[j][0], blocks[j][1], blocks[j][2], blocks[j][3])
                    if _hard_stop(cand_text, cand_rect, page.rect.height) or _is_paragraph(cand_text):
                        break
                    collected.append(blocks[j])
                    j += step

            region = _union_rect([fitz.Rect(c[0], c[1], c[2], c[3]) for c in collected])
            region = _merge_touching(region, visible_drawing_rects)

            pad = 4
            clip = fitz.Rect(region.x0 - pad, region.y0 - pad, region.x1 + pad, region.y1 + pad) & page.rect
            eq_num += 1
            pix = page.get_pixmap(clip=clip, dpi=200)
            filename = f"equation_{eq_num:02d}_page{page_index:03d}.png"
            pix.save(eq_dir / filename)
            manifest.append({"page": page_index, "file": filename, "caption": text})

    print(f"[equations] 수식 {len(manifest)}개 추출 완료 -> {eq_dir}")
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

    (out_dir / "extraction_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[report] 리포트 저장 완료 -> {out_dir / 'extraction_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF에서 텍스트/그림/표를 추출한다.")
    parser.add_argument("--pdf", default=str(PROJECT_DIR / "input" / "LIGHTRAG.pdf"), help="입력 PDF 경로")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF를 찾을 수 없습니다: {pdf_path}")

    stem = pdf_path.stem
    out_dir = PROJECT_DIR / "output" / f"{stem}_extract_{date.today().isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    extract_text(doc, out_dir)
    manifest = extract_figures_and_tables(doc, out_dir)
    equations = extract_equations(doc, out_dir)
    write_report(out_dir, pdf_path, len(doc), manifest, equations)
    doc.close()

    print(f"\n완료. 결과 폴더: {out_dir}")


if __name__ == "__main__":
    main()
