# OpenAI · OpenRouter API 입문 실험실

같은 프롬프트를 OpenAI와 OpenRouter에 보내면서 API 호출 구조, 응답, 토큰 사용량을 비교하는 작은 학습 프로젝트입니다.

## 파일

- `notebooks/01_openai_openrouter_api_test.ipynb`: 설명과 실행 코드가 포함된 테스트 노트북
- `requirements.txt`: 노트북 실행에 필요한 최소 패키지

## 시작하기: 가상환경 권장

PowerShell에서 이 폴더로 이동한 뒤 Python 기본 기능인 `venv`로 프로젝트 전용 가상환경을 만들고 패키지를 설치하는 방법을 권장합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
jupyter lab
```

가상환경을 종료할 때는 다음 명령을 사용합니다.

```powershell
deactivate
```

base 환경에 바로 설치해도 실행은 가능하지만 권장하지 않습니다. 다른 프로젝트가 요구하는 패키지 버전과 충돌하거나, 나중에 이 프로젝트의 패키지만 정리하기 어려울 수 있습니다. 일회성 테스트라도 `.venv`를 사용하면 프로젝트 폴더만으로 의존성을 분리할 수 있습니다. 이미 별도로 관리하는 Conda 환경이나 전용 Python 환경이 있다면 그 환경을 사용해도 됩니다.

환경 이름 변경, 현재 환경 확인, 저장소 안의 `venv` 조회 및 삭제 방법은 [venv 간단 가이드](docs/venv-guide.md)를 참고하세요.

## API 키 불러오기

### 방법 1: 저장소 루트의 `.env` 사용

노트북은 현재 폴더부터 상위 폴더를 탐색해 `.env`를 찾고 다음 변수를 자동으로 읽습니다.

```dotenv
OPENAI_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-v1-...
```

저장소 루트에 `.env` 파일을 만들고 위 두 변수를 채우세요 (`.env.example` 참고). `.env`는 Git에 커밋하지 않습니다.

### 방법 2: `.env`가 없을 때 PowerShell 환경변수 사용

`.env`가 없는 환경에서는 노트북을 실행할 PowerShell 창에 API 키를 임시로 지정할 수 있습니다.

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:OPENROUTER_API_KEY="sk-or-v1-..."
jupyter lab
```

이 방식으로 설정한 값은 현재 PowerShell 세션과 그 세션에서 실행한 Jupyter에만 전달됩니다. 테스트 후 PowerShell 창을 닫거나 다음 명령으로 제거할 수 있습니다.

```powershell
Remove-Item Env:OPENAI_API_KEY
Remove-Item Env:OPENROUTER_API_KEY
```

`.env`와 PowerShell 환경변수가 모두 있으면 이미 설정된 PowerShell 환경변수를 우선하고 `.env` 값으로 덮어쓰지 않습니다. 두 방법 모두 키 값을 노트북 코드에 직접 적지 않습니다.

## API 호출 실행

그다음 노트북의 안내에 따라 `RUN_OPENAI` 또는 `RUN_OPENROUTER` 값을 `True`로 바꿉니다. 기본값은 모두 `False`이므로 실수로 전체 셀을 실행해도 API 비용이 발생하지 않습니다.

## 기본 모델

- OpenAI: `gpt-5.6-luna` — 비용에 민감한 작업용 저가 모델
- OpenRouter: `openrouter/free` — 사용 가능한 무료 모델을 자동 선택하는 라우터

모델명과 가격, 무료 모델 제공 여부는 변경될 수 있으므로 실제 테스트 전 각 서비스의 모델 페이지를 확인하세요.

## 보안 주의사항

- 저장소 루트의 `.env`는 Git에서 제외된 상태를 유지합니다.
- API 키를 노트북, 스크린샷, 출력 결과에 포함하지 않습니다.
- 출력 토큰 제한을 크게 올리기 전에 가격을 확인합니다.
