# paper-review-notion

논문 PDF를 넣으면 텍스트/이미지/표를 추출하고, 이를 바탕으로 리뷰 초안을 만들어
Notion에 정리하는 자동화 파이프라인. (`papers-digest`와 달리 논문 한 편을 깊이 있게
리뷰하는 용도)

## 빠른 실행 — PowerShell 한 줄 (`review.ps1`)

PDF 추출 → 선택한 모델로 요약 → Notion 변환을 한 번에 실행한다. **기본은 로컬 미리보기**이고,
`-Publish`를 붙여야 Notion에 새 페이지를 만든다. 프로젝트 폴더에서 실행한다고 가정한다.

```powershell
cd C:\Users\USER\Desktop\workspace\tinkering\paper-review-notion
```

**제공자별 (PDF부터 시작)**

```powershell
.\review.ps1 -Pdf '.\input\<논문>.pdf' -Provider claude    # OpenRouter anthropic/claude-sonnet-5.5 (기본 제공자)
.\review.ps1 -Pdf '.\input\<논문>.pdf' -Provider gpt       # OpenAI gpt-5.4-mini
.\review.ps1 -Pdf '.\input\<논문>.pdf' -Provider ollama    # 로컬 Ollama gemma3:12b
```

**모델 바꾸기** — `-Model`에 제공자의 모델 ID를 그대로 쓴다.

```powershell
.\review.ps1 -Pdf '.\input\<논문>.pdf' -Provider ollama -Model 'qwen3.5:9b'
.\review.ps1 -Pdf '.\input\<논문>.pdf' -Provider claude -Model 'anthropic/<다른 모델 ID>'
```

**시작 지점 고르기**

| 시작 | 명령 | 하는 일 |
|---|---|---|
| PDF | `.\review.ps1 -Pdf '.\input\<논문>.pdf' -Provider gpt` | 새 추출 → 요약 생성(모델 호출) → 미리보기 |
| 기존 추출물 | `.\review.ps1 -Extract '.\output\<논문>_extract_<날짜>' -Provider gpt` | 재추출 없이 요약 생성(모델 호출) → 미리보기 |
| 기존 요약 | `.\review.ps1 -Summary '.\output\<논문>_summary_<…>.md'` | **모델을 호출하지 않는다.** 미리보기만 (`-Provider`·`-Model`은 무시) |

**확인·발행 옵션**

| 옵션 | 동작 |
|---|---|
| (없음) | 로컬 미리보기. `<요약>_notion_preview.json`을 만들고 Notion은 호출하지 않는다 |
| `-DryRun` | 입력·모델 설정만 출력. **모델·Notion 호출과 파일 생성이 모두 없다.** `-Publish`와 함께 쓸 수 없다 |
| `-Publish` | Notion "논문 리뷰"에 새 페이지 발행. 같은 제목이 있으면 멈춘다 (기존 페이지를 고치지 않음) |
| `-Compare` | Notion 제목 뒤에 `[비교본: OpenAI gpt-5.4-mini]`처럼 모델 이름을 붙인다. 요약 옆 `.json` 실행 기록에서 읽으므로 수동 요약에는 쓸 수 없다. 원본 md는 바뀌지 않는다 |
| `-MaxTokens`, `-NumCtx`, `-Think` | `generate_summary.py`의 `--max-tokens`(기본 40000), `--num-ctx`(기본 16384), `--think`와 같다 |
| `-Python` | 사용할 python.exe 경로 |

```powershell
# 호출 없이 설정 확인
.\review.ps1 -Extract '.\output\<논문>_extract_<날짜>' -Provider ollama -Model 'qwen3.5:9b' -DryRun
# 이미 만든 요약을 모델 이름을 붙여 발행
.\review.ps1 -Summary '.\output\<논문>_summary_openai-gpt-5.4-mini_<날짜>.md' -Compare -Publish
# 다른 폴더에서 절대 경로로 호출
& 'C:\Users\USER\Desktop\workspace\tinkering\paper-review-notion\review.ps1' -Summary 'D:\papers\[논문] 요약.md' -DryRun
```

**동작 규칙**

- 경로는 작은따옴표로 감싸면 공백·한글·대괄호(`[QLORA]…`)가 그대로 전달된다. 상대 경로는 PowerShell의 현재 폴더 기준이다.
- 한 단계가 실패하면 다음 단계로 넘어가지 않고 0이 아닌 종료 코드로 끝난다. API 키는 추출·요약 **전에** 확인한다
  (`-Publish`면 Notion 키까지). `finish_reason=length`(출력 한도에서 잘림)인 요약은 발행하지 않는다.
- 기존 결과를 덮어쓰지 않는다. PDF에서 시작할 때 같은 날짜 추출 폴더가 있으면 `_2`, `_3` 폴더를 새로 만들고,
  같은 날 같은 모델 요약이 있으면 `_2.md`/`_2.json`으로 저장한다. 미리보기 json은 요약 파일마다 다시 쓴다.
- Ollama 모델이 `## 3 줄 요약` 제목이나 목록 기호 없는 세 줄로 써도 3줄 요약 속성과 본문 줄을 인식한다.
- 정확한 단계별 동작은 아래 방법 2·3의 개별 스크립트와 같다. 개별 스크립트도 그대로 쓸 수 있다.

**준비**

- **Python**: 이 PC는 `C:\Users\USER\Anaconda3\python.exe`가 자동으로 선택된다. 찾는 순서는 `-Python` →
  환경변수 `PAPER_REVIEW_PYTHON` → `paper-review-notion\.venv` → `tinkering\.venv` → `%USERPROFILE%\Anaconda3` →
  `%USERPROFILE%\miniconda3` → PATH의 `python`. 다른 PC는 `-Python 'C:\path\to\python.exe'`로 지정한다.
- **의존성**: `& '<python.exe>' -m pip install -r requirements.txt` (pymupdf, requests, python-dotenv)
- **API 키**: 저장소 최상위 `tinkering\.env`에 넣는다 (Git 제외). 필요한 이름만 적으면 아래와 같다. 값은 문서·로그에 남기지 않는다.

  | 사용 | 변수 |
  |---|---|
  | `-Provider claude` | `OPENROUTER_API_KEY` |
  | `-Provider gpt` | `OPENAI_API_KEY` |
  | `-Publish` | `NOTION_TOKEN`, `NOTION_DATABASE_ID` (아래 방법 3 준비 참고) |

- **Ollama**: 키가 필요 없고 로컬 서버가 켜져 있어야 한다. `ollama list`로 설치된 모델 이름을 확인해 `-Model`에 그대로 쓰고,
  없으면 `ollama pull <모델>`로 받는다. 서버가 꺼져 있으면 트레이의 Ollama 앱을 켜거나 `ollama serve`를 실행한다.
  다른 주소는 `OLLAMA_HOST`로 지정한다. QLoRA(21쪽) 기준 약 25~30분 걸렸다.
- **실행 정책**: 스크립트 실행이 막힌 PC에서는 `powershell -ExecutionPolicy Bypass -File .\review.ps1 -Pdf '…' -Provider gpt`처럼 실행한다.

여기서 Claude는 **OpenRouter API로 호출하는 Claude 모델**(유료, `OPENROUTER_API_KEY`)이다. Claude Code 대화로 요약을 쓰는 아래 방법 1과는 다른 실행 방식이다.

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
2. **요약 생성** (구현): Claude Code(방법 1) 또는 `generate_summary.py`(방법 2, OpenRouter·OpenAI·Ollama)로 요약 md를 만든다.
3. **Notion 발행** (진행 중): 방법 1은 Claude의 Notion 연결로, 방법 3은 `publish_notion.py`로 "논문 리뷰"에 올린다.

## 실행 방법

PyMuPDF가 설치된 Python이 필요하다(`pip install pymupdf`). 이 PC에서는 Anaconda Python에 설치되어 있다.

```powershell
cd paper-review-notion\src
$env:PYTHONIOENCODING = "utf-8"
C:\Users\USER\Anaconda3\python.exe extract_pdf.py --pdf "..\input\<논문>.pdf"
```

결과는 `output/<논문 제목 앞 60자>_extract_<날짜>/`에 저장된다. 이 스크립트를 같은 날 다시 실행하면 같은 폴더에 덮어쓴다
(`--output-dir`로 다른 폴더 지정 가능). `review.ps1`은 기존 폴더가 있으면 `_2` 폴더를 새로 만든다.

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

### 방법 2. 스크립트로 요약 생성 (`src/generate_summary.py`)

Claude Code 없이 명령 한 줄로 요약 md를 만든다. 요약 형식 문서(`prompts/summary_format.md`)를 그대로 LLM에 넘긴다.

**제공자**

| `--provider` | 기본 모델 | 필요한 것 | 입력 방식 |
|---|---|---|---|
| `openrouter` (기본) | `anthropic/claude-sonnet-5.5` | `OPENROUTER_API_KEY` | 본문 전체 + 번호 있는 수식 이미지(최대 40개)를 한 번에 |
| `openai` | `gpt-5.4-mini` | `OPENAI_API_KEY` | 위와 같음 |
| `ollama` | `gemma3:12b` | 로컬 Ollama 서버 (`OLLAMA_HOST`, 기본 `http://localhost:11434`) | 몇 쪽씩 나눠 메모를 만든 뒤(map) 모아서 최종 요약(reduce). 이미지는 넘기지 않음 |

- 키는 **저장소 최상위 `tinkering/.env`** 에 넣는다 (`.gitignore` 대상). 스크립트 위치에서 위로 올라가며 `.env`를 찾고
  git 저장소 최상위에서 멈추므로, 어느 폴더에서 실행해도 다른 저장소의 `.env`를 읽지 않는다. 이미 설정된 환경변수가 우선한다.
- 모델 이름과 가격은 바뀌므로 다른 모델은 `--model`로 지정한다.
- 참고문헌 목록은 빼고 부록은 남긴다. 번호 인용(`[12] …`)이 대부분인 쪽을 참고문헌으로 보고, 그 쪽 중간에
  부록 제목(`A`, `A Case Study`, `Appendix …`)이 나오면 그 줄부터 남긴다. 저자-연도식 참고문헌은 걸러지지 않고 남는다(토큰만 더 씀).

**실행**

```powershell
cd paper-review-notion\src
$env:PYTHONIOENCODING = "utf-8"
# 입력 크기만 확인 (LLM 호출 없음)
C:\Users\USER\Anaconda3\python.exe generate_summary.py --extract "..\output\<논문>_extract_<날짜>" --dry-run
# OpenRouter(기본)
C:\Users\USER\Anaconda3\python.exe generate_summary.py --extract "..\output\<논문>_extract_<날짜>"
# 로컬 Ollama
C:\Users\USER\Anaconda3\python.exe generate_summary.py --extract "..\output\<논문>_extract_<날짜>" --provider ollama --model qwen3.5:9b
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--max-tokens` | 40000 | API 최종 요약의 최대 출력 토큰 (생각 토큰 포함). 16000에서는 요약이 잘렸다 |
| `--num-ctx` | 16384 | Ollama 입력 길이(토큰) |
| `--think` | 꺼짐 | Ollama 모델의 생각 기능 |

**결과**: `output/<논문>_summary_<provider>-<모델>_<날짜>.md`와 같은 이름의 `.json`(걸린 시간, 토큰, `finish_reason`,
목록에 없는 이미지 경로). 같은 이름이 이미 있으면 `_2`, `_3`을 붙여 기존 결과를 보존한다. `finish_reason=length`면 요약이 잘린 것이고, `missing_images`가 비어 있어도 이미지가 충분히
들어갔다는 뜻은 아니다.

모델별 비교 결과는 [docs/model_comparison_2026-10-27.md](docs/model_comparison_2026-10-27.md)에 정리했다.

### 방법 3. Notion 자동 발행 (`src/publish_notion.py`)

요약 md(방법 1·2 어느 쪽 결과든)를 Notion "논문 리뷰"에 페이지로 올린다. Claude의 Notion 연결과 별개로
**Notion API를 직접 호출**하므로 내부 통합 토큰이 따로 필요하다.

**준비 (처음 한 번)**

1. https://www.notion.so/profile/integrations 에서 내부 통합(Internal integration)을 만든다. 기능(Capabilities)은
   콘텐츠 읽기·업데이트·삽입을 켠다. 발급된 토큰(`ntn_…`)을 복사한다.
2. Notion "논문 리뷰" 데이터베이스 오른쪽 위 `…` → 연결(Connections)에서 위 통합을 추가한다.
3. `tinkering/.env`에 넣는다.

   ```
   NOTION_TOKEN=ntn_...
   NOTION_DATABASE_ID=43884d81b1e643dc8a02ee2807f496b2
   ```

**실행**

```powershell
cd paper-review-notion\src
$env:PYTHONIOENCODING = "utf-8"
# 1) 미리보기 (기본, Notion 호출 없음): 블록 개요 출력 + output/<요약 파일>_notion_preview.json 저장
C:\Users\USER\Anaconda3\python.exe publish_notion.py --summary "..\output\<논문>_summary_<날짜>.md"
# 2) 발행
C:\Users\USER\Anaconda3\python.exe publish_notion.py --summary "..\output\<논문>_summary_<날짜>.md" --publish
```

| 요약 md | Notion |
|---|---|
| `# 제목`, `- 저자/기관/공개/링크/태그` | 속성 제목·링크(첫 URL)·연도(공개의 연도)·기관(없으면 저자 줄 괄호)·태그. 저자·공개·링크 줄은 본문 맨 위 목록으로 |
| `## 3줄 요약`의 세 줄 (`## 3 줄 요약`, 목록 기호 없는 줄도 인식) | 본문(줄마다 따로) + 속성 "3줄 요약"(각 줄의 첫 문장) |
| `<details><summary>용어 정리</summary>` | 접히는 제목(H2) |
| `<details><summary>자세히 보기</summary>` | 접히는 제목(H3) |
| 표, `$$ … $$`, `$…$`, `![캡션](경로)` | 표, 수식 블록, 인라인 수식, 이미지(파일 업로드) + 캡션 |
| - | 상태 `읽을 예정`, 정리일 = 실행한 날 |

- **같은 제목 페이지가 있으면 새로 만들지 않고 멈춘다.** `--update-existing`을 붙이면 '내 메모' 제목 앞의 본문을
  지우고 새 내용으로 바꾼다. '내 메모' 이하와 '상태' 속성은 유지한다. 다른 속성은 요약 md 값으로 바뀐다.
- 이미지 파일이 없거나 20MB를 넘는 등 문제가 있으면 발행하지 않는다.
- 태그는 요약 md의 값이 그대로 들어간다. 데이터베이스에 없는 태그는 새로 생긴다.
- `--title-suffix "[비교본: …]"`는 원본 md를 바꾸지 않고 Notion 제목 뒤에만 문구를 붙인다 (`review.ps1 -Compare`가 사용).

`input/`(논문 PDF)과 `output/`(추출 결과)은 저작권·용량 때문에 Git에 올리지 않는다.
