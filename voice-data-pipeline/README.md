# voice-data-pipeline

통화 녹음 파일을 STT(faster-whisper)로 전사하고, 로컬 LLM(Ollama)으로 통화를 분류·요약한 뒤,
분류 결과를 집계·시각화하는 파이프라인입니다. 수신 통화(상담/비상담)와 발신 통화(고객콜백/공급업체/기타)를 나눠서 다룹니다.

> 학습·실험용입니다. 실제 통화 녹음·전사문·분류 결과는 커밋되지 않습니다(아래 참고).

## 폴더 구조

```
voice-data-pipeline/
├─ notebooks/
│  ├─ 01_analyze_inbound_calls.ipynb           # 수신 통화 STT + 상담/비상담 분류 (소량 테스트용)
│  ├─ 02_visualize_inbound_call_analysis.ipynb # 01 결과 시각화
│  ├─ 03_analyze_outbound_calls.ipynb          # 발신 통화 STT + 유형분류(고객콜백/공급업체/기타)
│  ├─ 04_verify_outbound_classification.ipynb  # 03 분류 품질 점검(번호별 혼재 확인) + "기타" 재분류
│  └─ 05_visualize_outbound_call_analysis.ipynb# 03 결과 시각화 (유형기반 + 목적/수신빈도 기반)
├─ scripts/
│  ├─ analyze_inbound_calls.py                 # 01과 같은 로직의 전체 배치용 (체크포인트로 중단/재개)
│  └─ analyze_outbound_calls.py                # 03과 같은 로직의 전체 배치용
├─ data/    # 파일명 메타데이터·분류결과(csv/json/checkpoint) — 실행 시 생성, 커밋 제외
└─ output/  # 시각화 결과 이미지 — 실행 시 생성, 커밋 제외
```

## 실행 방법

1. 저장소 루트 `.env.example`을 복사해 `.env` 생성 후 `VOICE_NAS_PATH`(통화 녹음이 있는 폴더 경로)를 채웁니다.
2. 로컬에 Ollama가 설치되어 있고 `qwen2.5:3b` 모델이 pull되어 있어야 합니다 (`ollama pull qwen2.5:3b`).
3. `pip install faster-whisper python-dotenv pandas requests matplotlib seaborn` (한글 폰트로 `Malgun Gothic` 등 필요).
4. **소량 테스트(수신)**: `notebooks/01_analyze_inbound_calls.ipynb` 실행 → `data/inbound/`에 결과 생성. `TEST_N`(개수) / `TEST_DATE`(예: `"20260601"`)로 범위를 좁힐 수 있습니다.
5. **전체 배치(수신)**: `scripts/` 폴더에서 `python analyze_inbound_calls.py` (야간 실행 권장, 체크포인트로 재개 가능).
6. `notebooks/02_visualize_inbound_call_analysis.ipynb` 실행 → `output/inbound/`에 이미지 생성.
7. **소량 테스트(발신)**: `notebooks/03_analyze_outbound_calls.ipynb` 실행 → 발신 통화를 고객콜백/공급업체/기타로 분류하고, 유형별 항목(고객콜백: QA/해결여부, 공급업체: 상품·발주·이슈)을 추출합니다.
8. **전체 배치(발신)**: `scripts/` 폴더에서 `python analyze_outbound_calls.py`.
9. **분류 품질 점검(발신)**: `notebooks/04_verify_outbound_classification.ipynb` — 같은 번호가 고객콜백/공급업체로 혼재 분류됐는지 확인하고, "기타"로 분류된 통화를 재분류해 체크포인트에 반영합니다.
10. `notebooks/05_visualize_outbound_call_analysis.ipynb` 실행 → `output/outbound/`에 이미지 생성.

## STT / LLM 선택

- STT: `faster-whisper` (`small` 기본, 로컬 GPU 있으면 자동 활용).
- 분류·요약: 로컬 `Ollama` (`qwen2.5:3b`). API 키 불필요, 통화 내용이 외부로 나가지 않습니다.
- 통화 유형 분류 프롬프트는 "판촉물 쇼핑몰 상담" 시나리오 기준으로 작성돼 있습니다 — 다른 도메인이면 `build_*_prompt()` 함수의 설명 문구를 바꿔서 쓰면 됩니다.

## 참고 — 통화 데이터는 커밋되지 않습니다

`data/`, `output/` 폴더는 `.gitignore` 대상입니다. 통화 전사문·요약·분류 결과가 담기기 때문입니다.
로컬에서 실행하면 폴더가 자동 생성되며, 커밋 대상이 아닙니다. 노트북 출력 셀도 비운 상태로 커밋합니다.
