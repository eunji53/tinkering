"""추출 결과(output/<논문>_extract_<날짜>/)로 논문 요약 마크다운을 만든다.

요약 형식은 prompts/summary_format.md를 그대로 LLM에 넘긴다. Claude Code로 정리할 때와 같은 형식이다.

제공자(provider)
- openrouter: OpenRouter 경유 (Claude 등). 환경변수 OPENROUTER_API_KEY
- openai: OpenAI API. 환경변수 OPENAI_API_KEY
- ollama: 로컬 Ollama 서버 (키 필요 없음). 환경변수 OLLAMA_HOST (기본 http://localhost:11434)

API 키는 저장소 최상위 .env(예: tinkering/.env)에서 읽는다. .env는 git에 올라가지 않는다.

긴 입력을 한 번에 다루는 API 모델은 논문 전체를 한 번에 넘긴다. 입력 길이가 짧은 로컬 모델(ollama)은
몇 쪽씩 나눠 먼저 메모를 만들고(map), 메모를 모아 최종 요약을 쓴다(reduce).

실행 예:
    python generate_summary.py --extract "../output/<논문>_extract_<날짜>" --provider openrouter
    python generate_summary.py --extract "../output/<논문>_extract_<날짜>" --provider ollama --model gemma3:12b
    python generate_summary.py --extract "../output/<논문>_extract_<날짜>" --provider openai --dry-run
"""

import argparse
import base64
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

SRC_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SRC_DIR.parent
FORMAT_PATH = PROJECT_DIR / "prompts" / "summary_format.md"

PROVIDERS = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "default_model": "anthropic/claude-sonnet-5.5",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "default_model": "gpt-5.4-mini",
    },
    "ollama": {"base_url": None, "key_env": None, "default_model": "gemma3:12b"},
}

# 수식 이미지를 LLM에 같이 넘겨 LaTeX로 옮기게 한다. 이론 논문은 수식이 100개를 넘어 비용이
# 커지므로 앞에서부터 이 개수까지만 넘기고, 나머지는 추출 텍스트의 수식을 쓴다.
MAX_EQUATION_IMAGES = 40
# ollama 메모 단계에서 한 번에 넘기는 본문 길이(글자). 한국어 메모까지 합쳐 num_ctx 안에 들어가게 잡는다.
CHUNK_CHARS = 14000
CITATION_LINE_RE = re.compile(r"^\[\d{1,3}\]\s")
# 부록 제목: "Appendix …"/"Supplementary …" 또는 "A", "A.1", "A Case Study" 처럼 대문자 하나로 시작하는 짧은 줄
APPENDIX_NAMED_RE = re.compile(r"^(Appendix|Appendices|Supplementary Material)\b", re.I)
APPENDIX_LETTER_RE = re.compile(r"^[A-H](\.\d+)?(\s+[A-Z][^.]{2,80})?$")
REFERENCE_TAIL_RE = re.compile(r"\b(19|20)\d\d[a-z]?\.\s*$|arXiv|^In\s", re.I)

SYSTEM_PROMPT = """당신은 연구 논문을 한국어로 정리하는 연구 보조자다.
아래 '요약 형식' 문서의 규칙을 그대로 따라 논문 요약을 마크다운으로 쓴다.

출력 규칙 (로컬 마크다운 파일용):
- 맨 앞은 다음 메타데이터 목록으로 시작한다. 모르면 '확인 필요'라고 쓴다.
  # <논문 원제>
  - 저자: ...
  - 기관: ...
  - 공개: YYYY-MM, <arXiv 번호 등>
  - 링크: <논문 주소>
  - 태그: 태그1, 태그2, ...
- 그다음 '## 3줄 요약'부터 형식 문서의 섹션 순서대로 쓴다.
- 접기 블록은 <details><summary>자세히 보기</summary> ... </details> 로 쓴다. 용어 정리는 <details><summary><b>용어 정리</b></summary> 로 감싼다.
- 그림·표는 '사용 가능한 이미지' 목록에 있는 경로만 써서 ![설명](figures/파일명.png) 처럼 넣는다. 목록에 없는 경로를 만들지 않는다.
- 수식은 $$ 로 시작하고 끝나는 줄로 감싼 LaTeX 블록으로 쓰고, 끝에 \\quad (번호)를 붙인다. 문장 속 수식은 $...$.
- 마크다운 본문만 출력한다. 앞뒤에 설명이나 코드 펜스를 붙이지 않는다.
"""

MAP_PROMPT = """다음은 논문의 일부(쪽 {first}~{last})다. 나중에 전체 요약을 쓰기 위한 메모를 한국어로 만든다.

빠짐없이 적을 것:
- 핵심 주장과 결론, 저자가 강조하는 교훈
- 방법의 세부(구성 요소, 학습 방식, 하이퍼파라미터)
- 수치 결과 (어느 표·그림에서 나왔는지 번호와 함께)
- 수식 (LaTeX로, 원래 번호와 함께)
- 그림·표 번호와 무엇을 보여주는지
- 한계, 의의, 공개 자료
- 메타데이터(제목, 저자, 기관, 공개 시기, arXiv 번호)가 보이면 그대로

본문에 없는 내용은 쓰지 않는다. 메모는 항목별 목록으로 간결하게.

--- 본문 ---
{text}
"""


def find_env_file(start: Path = SRC_DIR) -> Path | None:
    """이 파일 위치에서 위쪽 폴더로 올라가며 처음 만나는 .env를 찾는다.

    git 저장소 최상위(.git이 있는 폴더)에서 멈춘다. 실행 위치(cwd)는 보지 않으므로
    다른 폴더에서 실행해도 다른 저장소의 .env를 읽지 않는다.
    """
    for folder in [start, *start.parents]:
        if (folder / ".env").is_file():
            return folder / ".env"
        if (folder / ".git").exists():
            return None
    return None


def load_env() -> None:
    """저장소 안의 .env를 읽는다. 이미 설정된 환경변수가 우선한다."""
    path = find_env_file()
    if path:
        load_dotenv(path, override=False)


def read_pages(extract_dir: Path) -> list[tuple[int, str]]:
    """full_text.md를 (쪽 번호, 본문) 목록으로 나누고 참고문헌을 뺀다.

    "References" 제목 이후로 인용 줄("[12] ...")이 대부분인 쪽은 버린다. 부록은 참고문헌 뒤에
    오는 경우가 많아, 인용 줄이 적은 쪽이 다시 나오면 그때부터는 남긴다. 참고문헌 쪽 중간에서
    부록 제목("A" / "A Case Study" / "Appendix")이 시작하면 그 줄부터 남긴다.
    """
    text = (extract_dir / "full_text.md").read_text(encoding="utf-8")
    parts = re.split(r"^## Page (\d+)\s*$", text, flags=re.M)
    pages = [(int(parts[i]), parts[i + 1].strip()) for i in range(1, len(parts) - 1, 2)]

    kept, in_refs = [], False
    for num, body in pages:
        lines = [l for l in body.splitlines() if l.strip()]
        cites = sum(1 for l in lines if CITATION_LINE_RE.match(l))
        heading = next((i for i, l in enumerate(lines) if l.strip().lower() in ("references", "bibliography")), None)
        if heading is not None:
            in_refs = True
            before = "\n".join(lines[:heading]).strip()
            if before:
                kept.append((num, before))
            start = appendix_start(lines, heading + 1)
            if start is not None:
                in_refs = False
                kept.append((num, "\n".join(lines[start:])))
            continue
        if in_refs and (cites >= 5 or (lines and cites / len(lines) > 0.2)):
            start = appendix_start(lines, 0)
            if start is not None:
                in_refs = False
                kept.append((num, "\n".join(lines[start:])))
            continue
        in_refs = False
        kept.append((num, body))
    return kept


def appendix_start(lines: list[str], begin: int) -> int | None:
    """참고문헌 줄들 사이에서 부록이 시작하는 줄 번호. 마지막 인용 줄 이후에서만 찾는다.

    "A Survey of …"처럼 참고문헌 제목이 줄바꿈된 경우와 헷갈리지 않도록, 바로 앞줄이 마침표로
    끝나고(참고문헌 항목이 끝남) 뒤따르는 두 줄이 참고문헌 꼴(연도·arXiv·"In …")이 아닐 때만 부록 제목으로 본다.
    """
    last_cite = max((i for i, l in enumerate(lines) if CITATION_LINE_RE.match(l)), default=-1)
    for i in range(max(begin, last_cite + 1), len(lines)):
        line = lines[i].strip()
        if APPENDIX_NAMED_RE.match(line):
            return i
        prev_done = i == 0 or lines[i - 1].rstrip().endswith(".")
        next_is_ref = any(REFERENCE_TAIL_RE.search(l) for l in lines[i + 1 : i + 3])
        if prev_done and not next_is_ref and APPENDIX_LETTER_RE.match(line):
            return i
    return None


def read_assets(extract_dir: Path) -> list[dict]:
    """extraction_report.md의 그림·표·수식 목록을 읽는다."""
    report = (extract_dir / "extraction_report.md").read_text(encoding="utf-8")
    assets = []
    for m in re.finditer(r"^- page (\d+): `([^`]+)` — (.*)$", report, flags=re.M):
        page, file, caption = int(m.group(1)), m.group(2), m.group(3).strip()
        folder = "figures" if file.startswith("figure") else "tables" if file.startswith("table") else "equations"
        assets.append({"page": page, "path": f"{folder}/{file}", "caption": caption})
    return assets


def asset_list_text(assets: list[dict]) -> str:
    lines = [
        f"- {a['path']} (p.{a['page']}): {a['caption'][:160]}"
        for a in assets if not a["path"].startswith("equations/")
    ]
    return "\n".join(lines) or "(없음)"


def equation_images(extract_dir: Path, assets: list[dict]) -> list[dict]:
    """번호 있는 수식 이미지(equation_NNN_pageNNN.png)를 앞에서부터 MAX_EQUATION_IMAGES개까지."""
    eqs = [a for a in assets if re.match(r"equations/equation_\d{3}_page", a["path"])]
    return eqs[:MAX_EQUATION_IMAGES]


def image_part(path: Path) -> dict:
    data = base64.b64encode(path.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}


def chat_openai_compatible(provider: str, model: str, system: str, content: list, max_tokens: int) -> tuple[str, dict]:
    """OpenAI 호환 Chat Completions 호출 (OpenAI, OpenRouter)."""
    import os

    cfg = PROVIDERS[provider]
    key = os.environ.get(cfg["key_env"])
    if not key:
        sys.exit(f"{cfg['key_env']}가 없습니다. 저장소 최상위 .env에 넣어 주세요.")
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
    }
    # OpenAI의 최신 모델은 max_tokens 대신 max_completion_tokens만 받는다.
    body["max_completion_tokens" if provider == "openai" else "max_tokens"] = max_tokens
    r = requests.post(
        f"{cfg['base_url']}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=body,
        timeout=900,
    )
    if not r.ok:
        sys.exit(f"API 오류 {r.status_code}: {r.text[:500]}")
    data = r.json()
    choice = data["choices"][0]
    usage = dict(data.get("usage", {}))
    usage["finish_reason"] = choice.get("finish_reason")
    # 생각(reasoning) 기능이 있는 모델은 답을 쓰기 전 생각에도 출력 토큰을 쓴다. 출력 한도에 걸려
    # 요약이 잘렸는지 알 수 있도록 생각 토큰 수를 따로 남긴다.
    details = usage.get("completion_tokens_details") or {}
    usage["reasoning_tokens"] = details.get("reasoning_tokens", 0)
    return choice["message"]["content"] or "", usage


def chat_ollama(model: str, system: str, user: str, num_ctx: int, think: bool) -> tuple[str, dict]:
    import os

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "think": think,
        "options": {"num_ctx": num_ctx, "temperature": 0.2},
    }
    try:
        r = requests.post(f"{host}/api/chat", json=body, timeout=3600)
    except requests.ConnectionError:
        sys.exit(f"Ollama 서버({host})에 연결할 수 없습니다. 'ollama serve'로 서버를 먼저 실행하세요.")
    if not r.ok:
        sys.exit(f"Ollama 오류 {r.status_code}: {r.text[:500]}")
    data = r.json()
    # 생각(think) 기능이 있는 모델이 think=False를 무시하면 본문에 <think>…</think>가 섞여 나온다.
    text = re.sub(r"<think>.*?</think>", "", data["message"]["content"], flags=re.S).strip()
    usage = {"prompt_tokens": data.get("prompt_eval_count", 0), "completion_tokens": data.get("eval_count", 0)}
    return text, usage


def chunk_pages(pages: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    chunks, current, size = [], [], 0
    for num, body in pages:
        if current and size + len(body) > CHUNK_CHARS:
            chunks.append(current)
            current, size = [], 0
        current.append((num, body))
        size += len(body)
    if current:
        chunks.append(current)
    return chunks


def fix_image_paths(markdown: str, extract_dir: Path) -> tuple[str, list[str]]:
    """요약 md는 output/에 저장되므로 'figures/…' 경로 앞에 추출 폴더 이름을 붙인다. 없는 파일은 경고."""
    missing = []

    def repl(m: re.Match) -> str:
        rel = m.group(2)
        if not (extract_dir / rel).exists():
            missing.append(rel)
        return f"{m.group(1)}(<{extract_dir.name}/{rel}>)"

    fixed = re.sub(r"(!\[[^\]]*\])\(<?((?:figures|tables|equations)/[^)>\s]+)>?\)", repl, markdown)
    return fixed, missing


def available_summary_path(path: Path) -> Path:
    """같은 날 같은 모델을 재실행해도 기존 요약과 실행 기록을 보존한다."""
    candidate, number = path, 2
    while candidate.exists() or candidate.with_suffix(".json").exists():
        candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
        number += 1
    return candidate


def main(argv: list[str] | None = None) -> Path | None:
    parser = argparse.ArgumentParser(description="추출 결과로 논문 요약 마크다운을 만든다.")
    parser.add_argument("--extract", required=True, help="output/<논문>_extract_<날짜> 폴더")
    parser.add_argument("--provider", choices=list(PROVIDERS), default="openrouter")
    parser.add_argument("--model", help="모델 이름 (생략하면 제공자별 기본값)")
    parser.add_argument(
        "--max-tokens", type=int, default=40000, help="최종 요약의 최대 출력 토큰 (생각 토큰 포함, 실제 쓴 만큼만 과금)"
    )
    parser.add_argument("--num-ctx", type=int, default=16384, help="ollama 입력 길이(토큰)")
    parser.add_argument("--think", action="store_true", help="ollama 모델의 생각(think) 기능 켜기 (느려짐)")
    parser.add_argument("--dry-run", action="store_true", help="LLM을 호출하지 않고 입력 크기만 확인")
    args = parser.parse_args(argv)

    load_env()
    extract_dir = Path(args.extract).resolve()
    if not (extract_dir / "full_text.md").exists():
        sys.exit(f"추출 결과가 아닙니다: {extract_dir}")
    model = args.model or PROVIDERS[args.provider]["default_model"]
    if args.max_tokens <= 0 or args.num_ctx <= 0:
        parser.error("--max-tokens와 --num-ctx는 양수여야 합니다.")

    format_doc = FORMAT_PATH.read_text(encoding="utf-8")
    pages = read_pages(extract_dir)
    assets = read_assets(extract_dir)
    body = "\n\n".join(f"## Page {n}\n\n{t}" for n, t in pages)
    system = SYSTEM_PROMPT + "\n\n--- 요약 형식 ---\n" + format_doc
    assets_text = asset_list_text(assets)
    eq_imgs = equation_images(extract_dir, assets) if args.provider != "ollama" else []

    print(f"[input] {extract_dir.name}")
    print(f"[input] 본문 {len(pages)}쪽 (참고문헌 제외), {len(body):,}자 ≈ {len(body) // 4:,} 토큰, 이미지 목록 {len(assets)}개, 수식 이미지 첨부 {len(eq_imgs)}개")
    if args.provider == "ollama":
        print(f"[input] ollama 메모 단계 {len(chunk_pages(pages))}회 + 최종 1회, num_ctx={args.num_ctx}")
    if args.dry_run:
        return

    started = time.time()
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
    finish_reason = None

    def add_usage(u: dict) -> None:
        nonlocal finish_reason
        for k in usage_total:
            usage_total[k] += int(u.get(k) or 0)
        finish_reason = u.get("finish_reason", finish_reason)

    if args.provider == "ollama":
        notes = []
        for i, chunk in enumerate(chunk_pages(pages), start=1):
            text = "\n\n".join(f"## Page {n}\n\n{t}" for n, t in chunk)
            prompt = MAP_PROMPT.format(first=chunk[0][0], last=chunk[-1][0], text=text)
            note, u = chat_ollama(model, "논문 메모를 정확하게 작성하는 연구 보조자다.", prompt, args.num_ctx, args.think)
            add_usage(u)
            notes.append(f"### 쪽 {chunk[0][0]}~{chunk[-1][0]} 메모\n{note}")
            print(f"[map] {i}: 쪽 {chunk[0][0]}~{chunk[-1][0]} 완료 ({time.time() - started:.0f}초)")
        user = (
            "아래는 논문 전체를 쪽별로 읽고 만든 메모다. 이 메모만 근거로 요약을 써라.\n\n"
            f"--- 사용 가능한 이미지 ---\n{assets_text}\n\n--- 메모 ---\n" + "\n\n".join(notes)
        )
        summary, u = chat_ollama(model, system, user, args.num_ctx, args.think)
        add_usage(u)
    else:
        content = [
            {
                "type": "text",
                "text": f"--- 사용 가능한 이미지 ---\n{assets_text}\n\n--- 논문 본문 (추출 텍스트) ---\n{body}",
            }
        ]
        if eq_imgs:
            content.append({"type": "text", "text": "--- 번호 있는 수식 이미지 (LaTeX로 옮길 때 참고) ---"})
            for a in eq_imgs:
                content.append({"type": "text", "text": f"{a['path']}: {a['caption'][:80]}"})
                content.append(image_part(extract_dir / a["path"]))
        summary, u = chat_openai_compatible(args.provider, model, system, content, args.max_tokens)
        add_usage(u)

    summary = re.sub(r"^```(?:markdown|md)?\s*\n|\n```\s*$", "", summary.strip())
    if not summary.strip():
        sys.exit("모델이 빈 요약을 반환했습니다. 결과를 저장하거나 발행하지 않았습니다.")
    summary, missing = fix_image_paths(summary, extract_dir)

    stem = extract_dir.name.split("_extract_")[0]
    model_slug = re.sub(r"[^A-Za-z0-9.]+", "-", model).strip("-")
    out_path = available_summary_path(
        extract_dir.parent / f"{stem}_summary_{args.provider}-{model_slug}_{date.today().isoformat()}.md"
    )
    out_path.write_text(summary + "\n", encoding="utf-8")

    elapsed = time.time() - started
    meta = {
        "provider": args.provider,
        "model": model,
        "extract": extract_dir.name,
        "seconds": round(elapsed),
        "usage": usage_total,
        "finish_reason": finish_reason,
        "missing_images": missing,
    }
    out_path.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    print(
        f"[done] {out_path.name} ({elapsed:.0f}초, 입력 {usage_total['prompt_tokens']:,} / "
        f"출력 {usage_total['completion_tokens']:,} 토큰, 그중 생각 {usage_total['reasoning_tokens']:,})"
    )
    if finish_reason == "length":
        print(f"[warn] 출력 한도({args.max_tokens:,} 토큰)에 걸려 요약이 중간에 잘렸습니다. --max-tokens를 늘려 다시 실행하세요.")
    if missing:
        print(f"[warn] 목록에 없는 이미지 경로 {len(missing)}개: {missing[:5]}")
    return out_path


if __name__ == "__main__":
    main()
