# paper-review-notion

논문 PDF를 넣으면 텍스트/이미지/표를 추출하고, 이를 바탕으로 리뷰 초안을 만들어
Notion에 정리하는 자동화 파이프라인. (`papers-digest`와 달리 논문 한 편을 깊이 있게
리뷰하는 용도)

## 폴더 구조

```
paper-review-notion/
  input/          # 리뷰할 논문 PDF 원본을 넣는 곳
  src/            # 추출·생성 스크립트
  output/         # 추출된 텍스트/이미지, 생성된 리뷰 결과물
  tests/          # 테스트용 스크립트
  docs/           # 설계 문서
```

## 진행 단계

1. **PDF 추출** (완료, 2026-10-26 일반화): `input/`의 논문 PDF에서 텍스트·그림·표·수식을 추출해
   `output/`에 저장한다. 양식이 다른 논문 12편으로 검증했다.
2. 리뷰 초안 생성 (다음 작업): 추출 결과를 바탕으로 요약(용어 / 3줄 / 상세)을 만든다.
3. Notion 발행: 실제 페이지 생성 (사용자 승인 후 진행).

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

`input/`(논문 PDF)과 `output/`(추출 결과)은 저작권·용량 때문에 Git에 올리지 않는다.
