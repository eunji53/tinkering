# 회의록 md 파일을 회사 표준 서식(docx)으로 변환하는 PowerShell 래퍼 스크립트
#
# 사용법:
#   .\scripts\make_docx.ps1 <회의록.md> [--template 템플릿경로] [--output 출력경로]
#
# 예시:
#   .\scripts\make_docx.ps1 "회의록\250101\회의록.md"

$ErrorActionPreference = "Stop"

if ($args.Count -eq 0) {
    Write-Output "사용법: .\scripts\make_docx.ps1 <회의록.md> [--template 템플릿경로] [--output 출력경로]"
    exit 1
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot

python "$ProjectRoot\src\md_to_docx.py" @args
