# tinkering

데이터 분석 업무를 하면서 궁금했던 주제들(LLM API, RAG, 외부 API 연동,
음성·논문 처리 파이프라인, 프론트엔드)을 작게 구현해보며 공부한 개인 프로젝트 모음입니다.
프로덕션 코드가 아니라 학습·실험 목적이라 완성도는 프로젝트마다 다릅니다.

## 프로젝트

| 폴더 | 내용 | 상태 |
|---|---|---|
| [api-provider-playground](./api-provider-playground) | 같은 프롬프트를 OpenAI·OpenRouter에 보내며 API 호출 구조·응답·토큰 사용량 비교 | 초안 (노트북 1개) |
| [data-analysis-digest](./data-analysis-digest) | 데이터분석/AI 블로그·Hacker News·Reddit 인기글 본문을 가져와 요약·번역해 마크다운 다이제스트로 저장 | 초안 (실행 테스트 전) |
| [papers-digest](./papers-digest) | Hugging Face Trending / sotapapers 논문을 훑어 상위 N개만 다이제스트로 저장 | 초안 |
| [paper-review-notion](./paper-review-notion) | 논문 PDF에서 텍스트·그림·표·수식을 추출 → 리뷰 초안 작성 → Notion 발행 파이프라인 | 진행 중 (1~2단계) |
| [rag-experiments](./rag-experiments) | FAQ 검색·상품 추천에 RAG를 적용해보는 실습. TF-IDF → 임베딩(SBERT) → BM25+임베딩 하이브리드 순으로 발전 | 실습 노트북 (v0~v3) |
| [frontend-learning](./frontend-learning) | React + TypeScript + Tailwind + shadcn/ui + React Flow 단계별 학습. 노드/엣지 다이어그램 뷰어 만들기가 최종 목표 | 진행 중 (2/7단계) |
| [smilebiz-van](./smilebiz-van) | SMARTRO VAN API(가맹점 매출/입금 조회) 호출 테스트. 공식 문서와 다른 실제 동작(필수 파라미터, 에러 조건) 정리 | 테스트 노트북 |
| [popbill-bank-test](./popbill-bank-test) | 팝빌 EasyFinBank(계좌 거래내역 조회) API 연동 테스트. 수집요청 → 상태 폴링 → 거래내역 조회 흐름, 응답 마스킹 유닛테스트 포함 | 테스트 노트북 + 유닛테스트 |
| [meeting-stt](./meeting-stt) | 회의 녹음(m4a 등)을 faster-whisper로 STT → 정해진 구조의 회의록 md 작성 → docx 템플릿에 채워 변환 | 도구 (사용 중) |

## 공통 참고

- 각 프로젝트 실행 방법은 해당 폴더의 `README.md` 참고.
- API 키가 필요한 프로젝트는 저장소 루트에 `.env`를 만들어 채웁니다 (`.env.example` 참고). `.env`는 커밋하지 않습니다.
- 노트북이 읽는 데이터 파일(`data/`), 실행 결과(`output/`), 임베딩 캐시(`cache/`)는 커밋에서 제외됩니다. 각자 준비하거나 실행 시 생성됩니다.
- Python 프로젝트는 3.10+ 기준. 프로젝트별 `requirements.txt`가 있으면 그걸 따릅니다.
