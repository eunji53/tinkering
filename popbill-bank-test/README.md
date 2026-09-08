# 팝빌 계좌조회 노트북 테스트

Python 3.10 이상에서 `notebooks/01_popbill_bank_test.ipynb`를 실행합니다.

## 빠른 시작

1. 프로젝트 폴더의 `.env.example`을 `.env`로 복사한 뒤 인증정보와 계좌정보를 입력합니다. `.env`는 Git에 커밋되지 않습니다.
2. VS Code에서 노트북을 열고 Python 커널을 선택합니다.
3. 첫 경로 확인 셀과 패키지 설치 셀을 실행합니다.
4. 이후 설정 확인 → 등록계좌 확인 → 수집 요청 → 완료 대기 → 거래내역 조회 셀을 순서대로 실행합니다.

JupyterLab을 사용하는 경우 프로젝트 폴더 터미널에서:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m jupyterlab notebooks/01_popbill_bank_test.ipynb
```

Python이 설치되어 있지 않다면 먼저 Python을 설치하고, VS Code에서는 Python/Jupyter 확장을 활성화하세요.

## .env 항목

| 변수 | 입력 내용 |
|---|---|
| `POPBILL_LINK_ID` | 팝빌 발급 링크아이디 |
| `POPBILL_SECRET_KEY` | 팝빌 발급 비밀키(API 인증키) |
| `POPBILL_CORP_NUM` | 팝빌 회원 사업자번호 10자리 |
| `POPBILL_USER_ID` | 팝빌 회원 아이디, 선택 |
| `POPBILL_IS_TEST` | 기본 `true`, 운영은 `false` |
| `POPBILL_BANK_CODE` | 팝빌 은행 기관코드 4자리 |
| `POPBILL_ACCOUNT_NUMBER` | 팝빌에 등록한 계좌번호 |
| `QUERY_START_DATE`, `QUERY_END_DATE` | `yyyyMMdd`, 빈 값이면 한국시간 어제~오늘 |
| `POLL_TIMEOUT_SECONDS` | 수집 상태 대기시간, 기본 180초 |
| `POLL_INTERVAL_SECONDS` | 수집 상태 확인 간격, 기본 3초 |

프로젝트 `.env`만 읽습니다. 상위 저장소의 `.env`와 시스템 환경변수는 사용하지 않습니다. `.env` 변경 후 설정 셀부터 다시 실행하세요. 인증정보 전체를 출력하지 마세요.

## 실제 조회 전 준비

팝빌 API 인증은 단일 키 대신 LinkID와 SecretKey를 사용합니다. 은행 빠른조회 신청, 팝빌 회원 준비, 계좌조회 정액제 신청 및 계좌등록이 선행되어야 합니다. 테스트/운영은 독립된 환경이므로 테스트 사이트에서 준비한 회원과 계좌를 사용하세요. 은행 로그인 정보·계좌 비밀번호는 은행/팝빌 계좌등록 화면에서 입력하고 이 프로젝트에는 넣지 않습니다.

이 프로젝트는 등록된 계좌를 조회하며 계좌 등록·결제를 자동 실행하지 않습니다. 관련 안내:

- [서비스 소개](https://developers.popbill.com/guide/easyfinbank/introduction/easy-intro)
- [빠른조회 및 정액제·계좌등록 준비](https://developers.popbill.com/guide/easyfinbank/introduction/check-bank-account)
- [Python SDK 설정](https://developers.popbill.com/reference/easyfinbank/python/getting-started/sdk-configration)
- [수집 요청과 상태 확인](https://developers.popbill.com/reference/easyfinbank/python/api/job)
- [거래내역과 합계 조회](https://developers.popbill.com/reference/easyfinbank/python/api/search)

수집 작업 ID는 1시간 동안 유효합니다. 수집이 늦어지면 요청 셀 대신 완료 대기 셀만 다시 실행하세요. 기간은 최근 3개월 내 최대 1개월 단위이며 은행 정책에 따라 달라질 수 있습니다. 기본은 어제~오늘의 짧은 기간입니다. SDK 내부 통신 대기는 별도로 적용되므로 실제 대기시간이 설정값을 초과할 수 있습니다.

잔액은 거래내역의 `balance` 등 은행에서 반환하는 항목으로 확인합니다. 마지막 거래 시점 잔액을 현재 잔액으로 간주하지 않습니다. 거래가 없으면 잔액을 추정하지 않습니다.

## 저장 및 검증

선택 저장 셀의 `SAVE_RESULTS = True`로 JSON을 `output`에 저장합니다. `.env`, 가상환경, 결과 폴더는 Git에서 제외합니다. 실행 후 노트북 출력에는 금융정보가 포함될 수 있으므로 공유/커밋 전에 **Clear All Outputs**를 실행하세요.

```powershell
python -m unittest discover -s tests -v
```

테스트는 가짜 응답으로 설정 검증, 수집 성공/실패/시간초과, 페이지 처리 및 오류 메시지 마스킹을 확인합니다. 실제 API 인증과 계좌 조회 성공 여부는 본인의 `.env`를 입력한 후 노트북에서 확인해야 합니다.
