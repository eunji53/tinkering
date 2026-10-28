"""PDF/기존 추출물/요약에서 시작하는 단일 실행 진입점. 기본 결과는 Notion 미리보기다."""

import argparse
import json
import os
from pathlib import Path

import generate_summary as generate
import publish_notion as publish

PROVIDER_ALIASES = {"gpt": "openai", "claude": "openrouter", "ollama": "ollama"}
PROVIDER_LABELS = {"openai": "OpenAI", "openrouter": "Claude", "ollama": "Ollama"}


def available_extract_path(path: Path) -> Path:
    candidate, number = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}_{number}")
        number += 1
    return candidate


def execution_record(summary: Path) -> dict:
    path = summary.with_suffix(".json")
    if not path.is_file():
        return {}
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError(f"실행 기록이 JSON 객체가 아닙니다: {path}")
    return record


def comparison_suffix(summary: Path) -> str:
    record = execution_record(summary)
    provider, model = record.get("provider"), record.get("model")
    if provider not in PROVIDER_LABELS or not isinstance(model, str) or not model.strip():
        raise ValueError("비교 제목에는 요약 옆 .json의 provider/model 기록이 필요합니다.")
    label = PROVIDER_LABELS[provider]
    model_label = model.removeprefix("anthropic/") if provider == "openrouter" else model
    return f"[비교본: {label} {model_label}]"


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GPT·Claude·Ollama 선택 → 논문 요약 → Notion 미리보기/발행")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path, help="새로 추출할 PDF")
    source.add_argument("--extract", type=Path, help="이미 추출한 폴더 (재추출하지 않음)")
    source.add_argument("--summary", type=Path, help="이미 만든 요약 md (모델을 호출하지 않음)")
    parser.add_argument("--provider", choices=PROVIDER_ALIASES, default="claude")
    parser.add_argument("--model", help="모델 ID; 생략하면 기존 제공자 기본값")
    parser.add_argument("--max-tokens", type=int, default=40000)
    parser.add_argument("--num-ctx", type=int, default=16384)
    parser.add_argument("--think", action="store_true", help="Ollama 생각 기능")
    parser.add_argument("--publish", action="store_true", help="미리보기 대신 Notion에 새 페이지 발행")
    parser.add_argument("--compare", action="store_true", help="Notion 제목에 실행 기록의 모델 이름 추가")
    parser.add_argument("--dry-run", action="store_true", help="설정/입력 확인만; 모델·Notion 호출 및 파일 생성 없음")
    return parser


def main(argv: list[str] | None = None) -> Path | None:
    parser = make_parser()
    args = parser.parse_args(argv)
    if args.dry_run and args.publish:
        parser.error("--dry-run과 --publish는 함께 사용할 수 없습니다.")
    if args.max_tokens <= 0 or args.num_ctx <= 0:
        parser.error("토큰 한도와 컨텍스트 길이는 양수여야 합니다.")

    provider = PROVIDER_ALIASES[args.provider]
    model = args.model or generate.PROVIDERS[provider]["default_model"]
    source = (args.pdf or args.extract or args.summary).resolve()
    if args.extract:
        for name in ("full_text.md", "extraction_report.md"):
            if not (source / name).is_file():
                parser.error(f"추출 폴더에 {name}이 없습니다: {source}")
    elif not source.is_file():
        parser.error(f"입력 파일을 찾을 수 없습니다: {source}")
    if args.pdf and source.suffix.lower() != ".pdf":
        parser.error("--pdf에는 PDF 파일을 지정하세요.")
    if args.compare and args.summary:
        try:
            comparison_suffix(source)
        except ValueError as err:
            parser.error(str(err))

    generate.load_env()
    if not args.dry_run:
        required = []
        if not args.summary and provider != "ollama":
            required.append(generate.PROVIDERS[provider]["key_env"])
        if args.publish:
            required += ["NOTION_TOKEN", "NOTION_DATABASE_ID"]
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            parser.error(f"환경변수가 없습니다: {', '.join(missing)}. tinkering/.env를 확인하세요.")

    print(f"[source] {source}")
    if args.summary:
        print("[model] 기존 요약 재사용; 모델 호출 없음")
    else:
        print(f"[model] {args.provider} → {provider} / {model}")
    print(f"[notion] {'새 페이지 발행' if args.publish else '로컬 미리보기'}")

    extract_dir = source
    if args.pdf:
        import extract_pdf

        extract_dir = available_extract_path(extract_pdf.output_path(source))
        print(f"[extract] {extract_dir}")
        if not args.dry_run:
            extract_pdf.main(["--pdf", str(source), "--output-dir", str(extract_dir)])

    if args.dry_run:
        if args.extract:
            generate.main(["--extract", str(source), "--provider", provider, "--model", model, "--dry-run"])
        elif args.summary:
            _, header, body = publish.parse_summary(source)
            blocks = publish.markdown_to_blocks(header + [""] + body, source.parent)
            print(f"[preview] 블록 {sum(1 for _ in publish.walk(blocks))}개, 문제 {publish.validate(blocks)}")
            if args.compare:
                print(f"[title] {comparison_suffix(source)}")
        print("[dry-run] 모델·Notion 호출과 파일 생성 없이 확인했습니다.")
        return None

    if args.summary:
        summary = source
    else:
        generate_args = [
            "--extract", str(extract_dir), "--provider", provider, "--model", model,
            "--max-tokens", str(args.max_tokens), "--num-ctx", str(args.num_ctx),
        ]
        if args.think:
            generate_args.append("--think")
        summary = generate.main(generate_args)
        if summary is None:
            raise RuntimeError("요약 파일이 생성되지 않았습니다.")

    # 잘린 답을 자동으로 원격 발행하지 않는다. 생성된 파일은 검토용으로 남긴다.
    record = execution_record(summary)
    if args.publish and record.get("finish_reason") == "length":
        parser.error(f"출력 한도에 걸린 요약이라 발행하지 않았습니다. 저장된 파일: {summary}")
    publish_args = ["--summary", str(summary)]
    if args.compare:
        publish_args += ["--title-suffix", comparison_suffix(summary)]
    if args.publish:
        publish_args.append("--publish")
    publish.main(publish_args)
    print(f"[summary] {summary}")
    return summary


if __name__ == "__main__":
    main()
