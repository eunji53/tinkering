# paper-review-notion

논문 PDF를 넣으면 텍스트/이미지/표를 추출하고, 이를 바탕으로 리뷰 초안을 만들어
Notion에 정리하는 자동화 파이프라인. (`papers-digest`와 달리 논문 한 편을 깊이 있게
리뷰하는 용도)

## 폴더 구조

```
paper-review-notion/
  input/          # 리뷰할 논문 PDF 원본을 넣는 곳
  src/            # 추출·생성 스크립트
  prompts/        # 요약 형식 (Claude Code·API 공통)
  output/         # 추출된 텍스트/이미지, 생성된 리뷰 결과물
  tests/          # 테스트용 스크립트
  docs/           # 설계 문서
```

## 진행 단계

1. **PDF 추출** (완료, 2026-10-26 일반화): `input/`의 논문 PDF에서 텍스트·그림·표·수식을 추출해
   `output/`에 저장한다. 양식이 다른 논문 12편으로 검증했다.
2. **요약 → Notion** (진행 중): Claude Code로 요약을 만들어 Notion "논문 리뷰"에 올린다. 형식 확정 후 API 스크립트로 자동화 예정.

## 실행 방법

PyMuPDF가 설치된 Python이 필요하다(`pip install pymupdf`). 이 PC에서는 Anaconda Python에 설치되어 있다.

```powershell
cd paper-review-notion\src
$env:PYTHONIOENCODING = "utf-8"
C:\Users\USER\Anaconda3\python.exe extract_pdf.py --pdf "..\input\<논문>.pdf"
```

결과는 `output/<논문 제목 앞 60자>_extract_<날짜>/`에 저장된다. 같은 날 다시 실행하면 같은 폴더에 덮어쓴다.

## 추출 결과

| 경로 | 내용 |
|---|---|
| `figures/figure_NN_pageNNN.png` | 그림 (캡션 포함) |
| `tables/table_NN_pageNNN.png` | 표 (캡션 포함) |
| `equations/equation_NNN_pageNNN.png` | 번호 있는 수식 — `(1)` 등 |
| `equations/equation_pageNNN_kk.png` | 번호 없는 따로 떨어진 수식 — 해당 쪽의 kk번째 |
| `text/page_NNN.txt`, `full_text.md` | 정리된 본문. 그림 → `[Figure N: 캡션 → 이미지 경로]`, 표 → 표시 줄 + `\|`로 나눈 행, 따로 떨어진 수식 → `[수식 … → 이미지 경로]`, 문장 속 수식 → `$...$` LaTeX |
| `text_raw/page_NNN.txt` | PDF에서 꺼낸 원본 텍스트 (제어 문자만 제거) |
| `extraction_report.md` | 그림·표·수식 목록과 캡션 |

판단 기준, 수정 이력, 알려진 한계는 [추출 일반화 테스트 기록](docs/test_extract_generalization_2026-10-26.md)에 정리했다.

## 요약 → Notion 정리

요약 형식(섹션 구성, Notion 속성)은 [prompts/summary_format.md](prompts/summary_format.md)에 정해 두었다.
아래 두 방법 모두 이 형식을 따른다.

### 방법 1. Claude Code(CLI)로 정리 — 현재 사용 중

API 키 없이 쓸 수 있다. Claude가 추출 결과를 직접 읽고 요약을 쓴 뒤, Claude에 연결된 Notion으로 페이지를 만든다.

**준비 (처음 한 번)**

- claude.ai 설정에서 **Notion 커넥터**가 연결되어 있어야 한다. Claude Code에서 Notion 도구가 보이지 않으면 `/mcp`로 연결 상태를 확인한다.
- Notion에 "논문 리뷰" 데이터베이스가 있다 (2026-10-26 생성, 비공개).

**사용 순서**

1. 논문 PDF를 `input/`에 넣는다.
2. 이 폴더에서 Claude Code를 연다.

   ```powershell
   cd C:\Users\USER\Desktop\workspace\tinkering\paper-review-notion
   claude
   ```

3. 아래처럼 요청한다. 추출부터 Notion 발행까지 한 번에 맡겨도 되고, 단계별로 나눠도 된다.

   ```text
   input/<논문>.pdf 추출하고, prompts/summary_format.md 형식으로 요약해서
   Notion "논문 리뷰" 데이터베이스에 올려줘.
   ```

   이미 추출한 논문이면:

   ```text
   output/<논문>_extract_<날짜>/ 결과로 prompts/summary_format.md 형식 요약을 만들어서
   Notion "논문 리뷰"에 올려줘.
   ```

4. Claude가 만든 결과
   - 로컬 사본: `output/<논문>_summary_<날짜>.md`
   - Notion "논문 리뷰" 데이터베이스에 한 행 (그림·표 이미지와 LaTeX 수식 포함)

여러 편을 한 번에 하려면 "input/에 있는 논문 중 아직 Notion에 없는 것 전부"처럼 요청하면 된다.
요약 품질은 Claude가 논문 전체를 읽고 쓰는 만큼 좋지만, 대화마다 사용량이 들고 Claude Code를 열어서 시켜야 한다.

### 방법 2. API로 자동 정리 — 예정 (아직 구현 전)

Claude Code 없이 명령 한 줄(또는 예약 실행)로 돌리는 방식이다. 아래는 구현할 때의 계획이다.

**필요한 것**

| 항목 | 설명 |
|---|---|
| LLM API 키 | Anthropic(Claude), OpenAI, Google(Gemini) 중 하나. 환경변수 `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` |
| Notion 통합 토큰 | Notion 설정의 통합(Integrations) 메뉴에서 내부 통합을 만들고 받은 토큰. 환경변수 `NOTION_TOKEN` |
| 데이터베이스 공유 | "논문 리뷰" 데이터베이스 오른쪽 위 메뉴의 연결(Connections)에서 위 통합을 추가해야 쓸 수 있다 |
| 데이터베이스 ID | "논문 리뷰" 주소의 마지막 32자리. 환경변수 `NOTION_DATABASE_ID` |

키와 토큰은 코드나 파일에 적지 않고 환경변수로만 넣는다. PowerShell에서 사용자 환경변수로 저장하는 예:

```powershell
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "<키>", "User")
[Environment]::SetEnvironmentVariable("NOTION_TOKEN", "<토큰>", "User")
[Environment]::SetEnvironmentVariable("NOTION_DATABASE_ID", "<데이터베이스 ID>", "User")
```

저장한 뒤에는 터미널을 새로 열어야 적용된다.

**예정된 실행 방법**

```powershell
cd src
# 1) PDF 추출 (지금과 같음)
C:\Users\USER\Anaconda3\python.exe extract_pdf.py --pdf "..\input\<논문>.pdf"
# 2) 요약 생성: prompts/summary_format.md 형식으로 output/<논문>_summary_<날짜>.md 생성
C:\Users\USER\Anaconda3\python.exe generate_summary.py --extract "..\output\<논문>_extract_<날짜>" --provider anthropic
# 3) Notion 발행: 요약 md와 그림·표 이미지를 "논문 리뷰"에 올림
C:\Users\USER\Anaconda3\python.exe publish_notion.py --summary "..\output\<논문>_summary_<날짜>.md"
```

- `--provider`를 생략하면 설정된 API 키를 찾아 자동으로 고른다.
- 비용을 줄이려고 기본값은 각 회사의 저렴한 모델로 할 예정이다. 모델 이름과 가격은 구현할 때 최신 정보를 확인한다.
- 수식 이미지는 LLM에 이미지로 같이 넘겨 LaTeX로 옮기게 한다.

`input/`(논문 PDF)과 `output/`(추출 결과)은 저작권·용량 때문에 Git에 올리지 않는다.
