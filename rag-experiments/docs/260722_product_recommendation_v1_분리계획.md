# product_recommendation 노트북 v1 분리 계획 (내일 할일)

작성일: 2026-07-22
대상 폴더: `projects/rag-experiments/notebooks/product_recommendation/`

## 지금 상태

- `product_recommendation_v0.ipynb`: TF-IDF 베이스라인. 그대로 둠.
- `product_recommendation_v1.ipynb`: 아래 내용이 전부 한 파일(56셀)에 합쳐져 있음.
  - 0~14번 섹션: Ollama bge-m3 임베딩 + LLM 질문구조화 + 날짜 리드타임 + 거래데이터 **row 단위** 검색
  - 15번 섹션: 거래데이터를 **profile 단위**로 집계해서 검색 (원래 patch 노트북이었던 내용)
  - 16번 섹션: 상품데이터 임베딩 **모델 비교** (TF-IDF vs Ollama bge-m3 vs 한국어 SBERT 2종 jhgan/KR-SBERT). FAQ 프로젝트의 `faq_rag_v1_embedding.ipynb` 6번 섹션 패턴을 참고해서 만듦.
  - 17번 섹션: 보완하면 좋을 점 메모
- `product_recommendation_v1_1.ipynb`: 위 파일의 백업 사본 (사용자가 직접 복사해둔 것, 건드리지 않음).

## 왜 나누기로 했나

기술적으로는 profile(거래데이터 준비 방식)과 임베딩 모델 비교(상품데이터 쪽 실험)가 서로 의존 관계 없는 독립적인 축이라 굳이 나눌 필요는 없다고 판단했었음. 하지만 사용자는 "기술적 의존관계"가 아니라 **실제로 시도해본 순서(학습 기록)** 를 남기고 싶어해서, 아래처럼 시간순으로 파일을 분리하기로 함.

## 내일 할일: 4개 파일로 분리

| 파일 | 내용 | 비고 |
|---|---|---|
| `v0.ipynb` | TF-IDF 베이스라인 | 기존 그대로, 변경 없음 |
| `v1.ipynb` (재구성) | 현재 v1.ipynb의 0~14번 섹션만 — Ollama 임베딩 + LLM 질문구조화 + 날짜 리드타임 + row 단위 거래 검색 | 공통 준비 과정 포함, 독립 실행 가능해야 함 |
| `v2.ipynb` (신규) | 현재 v1.ipynb의 15번 섹션 — 거래데이터 profile 단위 집계 임베딩 | 공통 준비 과정(데이터 로드/정규화/상품임베딩/질문구조화/날짜리드타임)을 복사해서 넣어야 독립 실행 가능 |
| `v3.ipynb` (신규) | 현재 v1.ipynb의 16번 섹션 — 임베딩 모델 비교 (TF-IDF/bge-m3/SBERT 2종) | 마찬가지로 공통 준비 과정 필요 |

- 분리 기준(v1=row, v2=profile, v3=임베딩비교)은 사용자에게 확인 요청했으나, "일단 퇴근해야 해서 정리만 해달라"고 해서 **분리 기준 자체는 아직 확정 답변을 못 받은 상태**임. 내일 다시 확인 후 진행할 것.
- 현재 통합본 `v1.ipynb`(56셀)는 분리 후 **삭제하지 않고 파일명을 바꿔서 보관**하기로 결정됨 (예: `product_recommendation_v1_all_in_one.ipynb` 등 — 정확한 새 이름은 내일 정할 것).
- 각 노트북 분리 시 공통 준비 셀을 복사해 넣는 과정에서 코드 중복이 발생하는 건 감수하기로 함 (각 파일이 독립적으로 실행 가능해야 하므로).

## 참고

- Ollama, sentence-transformers, torch 모두 이 환경에 설치되어 있어 바로 실행 가능함 (bge-m3, gemma3:4b 등 모델 다운로드 완료 상태).
- FAQ 프로젝트(`notebooks/faq/faq_rag_v1_embedding.ipynb`)가 "TF-IDF → 임베딩 여러 모델 비교" 패턴의 참고 예시임.
