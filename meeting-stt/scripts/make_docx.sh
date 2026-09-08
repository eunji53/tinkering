#!/usr/bin/env bash
# 회의록 md 파일을 회사 표준 서식(docx)으로 변환하는 래퍼 스크립트
#
# 사용법:
#   ./scripts/make_docx.sh <회의록.md> [--template 템플릿경로] [--output 출력경로]
#
# 예시:
#   ./scripts/make_docx.sh "회의록/250101/회의록.md"
#
# --template을 생략하면 현재 폴더의 template.docx를 사용합니다.
# --output을 생략하면 입력 md와 같은 폴더/이름으로 .docx 확장자만 바꿔 저장합니다.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ "$#" -eq 0 ]; then
  echo "사용법: $0 <회의록.md> [--template 템플릿경로] [--output 출력경로]"
  exit 1
fi

PYTHON_BIN="python"
if ! command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" "$PROJECT_ROOT/src/md_to_docx.py" "$@"
