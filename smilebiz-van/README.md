# smilebiz-van 실행 가이드

스마일비즈(SMARTRO)에서 제공하는 VAN API(가맹점 매출/입금 정보 조회)를 테스트하기 위한 프로젝트입니다.

API 가이드 문서: https://exttran.smilebiz.co.kr/ (좌측 메뉴에서 `VAN` 탭 선택)
실제 API 호출 주소: `https://extvan.smilebiz.co.kr` (문서 사이트와 도메인이 다릅니다 — `exttran`은 가이드, `extvan`이 실제 서버입니다)

## 폴더 구조

```
smilebiz-van/
└─ van-api/
   ├─ van_test_helpers.py          # 공용 요청 함수 (Bearer 인증·페이지네이션·응답 검증). 표준 라이브러리만 사용, 노트북들이 import
   ├─ 01_test_van_api.ipynb        # VAN 탭 8개 API 전부 GET 테스트 (서버체크·공통코드·매출집계·매출내역·입금 4종) + 결과 요약
   ├─ 02_cash_receipt_lookup.ipynb # 현금영수증 1건을 골라 반환 필드 전체 / 명세 대비 누락 필드 / 원본 JSON 확인
   ├─ 03_cash_receipt_fields.ipynb # 승인번호 여러 개의 현금영수증 반환 필드를 가로·세로로 비교
   └─ 04_cash_receipt_audit.ipynb  # 기간 전체 페이지 조회 + 지정 승인번호의 기대값 vs 실제 승인·취소 대사
```

`02`~`04` 노트북은 `van_test_helpers.py`의 `van_get()`/`fetch_pages()`를 그대로 씁니다.
`getSalesSum`에는 `GBN` 요청 필드가 없어 집계를 받은 뒤 현금영수증 행만 필터링하는 점,
카드 공통 필드가 현금영수증 응답에서 빈 값으로 오는 점 등을 확인합니다.

## 0. 환경 준비

```bash
pip install pandas jupyter
```

HTTP 요청은 `van_test_helpers.py`가 표준 라이브러리(`urllib`)로 처리하므로 `requests`/`python-dotenv`는 필요 없습니다.

저장소 루트의 `.env.example`을 참고해 `.env`에 아래 값을 채웁니다.

```
# .env
SMARTRO_VAN_API_KEY=발급받은_Bearer_키
SMARTRO_VAN_TERMID=조회할_단말기번호_10자리   # 02·03·04 노트북에서 사용 (01은 없어도 됨)
SMARTRO_VAN_COMP_NO=사업자번호                # (선택) 특정 가맹점만 좁혀 조회할 때. 비우면 사업자 전체 범위
```

키는 API 가이드 사이트에서 발급/확인하셔야 합니다 (이 저장소나 노트북이 발급을 대신 해주지 않습니다).

## 1. 인증 방식

모든 요청 헤더에 아래 두 값을 포함해야 합니다.

| Header | Value |
|---|---|
| `Accept` | `application/json` |
| `Authorization` | `Bearer {SMARTRO_VAN_API_KEY}` |

응답은 공통적으로 `CODE`(결과코드, `"0000"`이면 성공)와 `MESSAGE`(결과메시지)를 포함합니다.

## 2. 확인된 API (VAN 탭 기준)

| 분류 | 이름 | Method | 경로 | 필수 파라미터 |
|---|---|---|---|---|
| 공통 | 서버연결 상태체크 | GET | `/V1/common/serverChecks` | 없음 |
| 공통 | 공통코드정보조회 | GET | `/V1/common/getCommCodeInfo` | 없음 |
| 매출 | 매출집계 조회 | GET | `/V1/sales/getSalesSum` | `SDATE`, `EDATE` (YYYYMMDD) |
| 매출 | 매출내역 조회 | GET | `/V1/sales/getSalesList` | `SDATE`, `EDATE` (+ `STIME`/`ETIME`/`CURRPAGE` 등 옵션) |
| 입금 | 입금내역 조회(집계/상세), 입금보류내역, 청구내역 | GET | (가이드 사이트 참고) | 노트북에서 파라미터를 직접 확인하지 않았습니다 — 실제 사용 전 가이드 사이트에서 확인하세요 |

`SDATE`/`EDATE`는 승인일자 기준이며, `COMP_NO`(사업자번호)/`COMP_IDX`/`TERMID`(단말기번호)로 특정 가맹점만 좁혀 조회할 수 있습니다(옵션).

⚠️ **문서와 실제 서버 동작이 다른 부분 (실행해서 확인함)** — `매출내역 조회`(`getSalesList`) 기준:
- 문서엔 `STIME` 등이 Optional이라고 나오지만, 실제로는 **파라미터 키가 요청에 아예 없으면 400 에러**가 납니다
  (값은 빈 문자열이어도 되지만, 키 자체는 요청 표에 있는 모든 필드를 다 보내야 합니다).
- `GBN`(소계구분)은 문서엔 Optional이지만 실제로는 **비어 있으면 500 에러**가 나는 사실상 필수값입니다.
  결제수단 하나만 지정하는 값이라, 전체 매출을 보려면 공통코드조회로 얻은 `GBN` 코드(1~8)를 순회 호출해야 합니다.
- 일부 `GBN` 값은 응답이 `CODE: "VAN_SALE-9999"`(예기치 못한 오류)로 올 수 있습니다 — HTTP 상태는 200이라
  예외가 나지 않으니, `CODE`가 `"0000"`인지 반드시 확인하고 쓰세요.

## 3. 실행

`van-api/` 안의 노트북을 열어 셀을 하나씩 실행하면 됩니다. 노트북 폴더나 저장소 루트 어디에서 실행해도 `van_test_helpers.py`를 찾습니다.
`.env`의 `SMARTRO_VAN_API_KEY`를 불러오지 못하면 이후 요청이 모두 인증 오류(401 등)로 실패합니다.
`02`~`04` 노트북은 `SMARTRO_VAN_TERMID`(단말기번호 10자리)도 필요합니다.

GET 조회만 수행하며 현금영수증 발급·취소 요청은 하지 않습니다.

## 4. 흔한 오류

| 증상 | 원인 | 조치 |
|---|---|---|
| `.env에 SMARTRO_VAN_API_KEY가 설정되지 않았습니다` | `.env` 파일이 없거나 값이 비어있음 | 위 "0. 환경 준비" 참고 |
| 응답 `CODE`가 `"0000"`이 아님 | 키 만료/오류, 파라미터 형식(날짜 등) 오류 | `MESSAGE` 필드 내용 확인, 가이드 사이트에서 파라미터 재확인 |
| 401 Unauthorized | Bearer 키가 비어있거나 잘못됨 | `.env`의 `SMARTRO_VAN_API_KEY` 값 재확인 |
| 400 `Required String parameter 'XXX' is not present` | 문서에 Optional이라고 나온 파라미터를 아예 안 보냄 | 값이 없어도 빈 문자열로 그 키를 요청에 포함시킬 것 |
| 500 `GBN(소계구분) 은 필수값입니다` | `getSalesList` 호출 시 `GBN`을 빈 값으로 보냄 | `GBN`에 1~8 중 값을 채워서 보낼 것 (전체 조회는 순회 필요) |
