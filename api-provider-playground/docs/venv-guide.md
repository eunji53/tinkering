# `venv` 간단 가이드

`venv`는 Python에 기본으로 포함된 가상환경 기능입니다. 프로젝트마다 Python 패키지를 분리해서 설치할 수 있습니다.

## 환경 생성

프로젝트 폴더에서 다음 명령을 실행합니다.

```powershell
python -m venv .venv
```

마지막의 `.venv`는 환경 폴더 이름입니다. 원하는 이름으로 바꿀 수 있습니다.

```powershell
python -m venv api-env
```

프로젝트마다 `.venv`라는 이름을 사용하는 것이 일반적입니다. 서로 다른 프로젝트에 같은 이름의 `.venv`가 있어도 실제로는 완전히 독립된 환경입니다.

## 환경 활성화와 종료

`.venv`라는 이름으로 만들었다면 다음과 같이 활성화합니다.

```powershell
.\.venv\Scripts\Activate.ps1
```

다른 이름을 사용했다면 경로도 같은 이름으로 바꿉니다.

```powershell
.\api-env\Scripts\Activate.ps1
```

활성화되면 PowerShell 프롬프트 앞에 보통 `(.venv)` 또는 `(api-env)`가 표시됩니다. 환경에서 빠져나올 때는 다음을 실행합니다.

```powershell
deactivate
```

## 현재 사용 중인 Python 확인

```powershell
python -c "import sys; print(sys.executable)"
```

이 프로젝트의 `.venv`가 활성화됐다면 출력 경로에 다음 부분이 포함됩니다.

```text
api-provider-playground\.venv\Scripts\python.exe
```

PowerShell에서 실행 파일 위치만 빠르게 확인할 수도 있습니다.

```powershell
Get-Command python
```

## `venv` 환경 조회

Conda와 달리 `venv`에는 중앙 환경 목록이 없습니다. 각 환경은 `pyvenv.cfg`를 포함한 하나의 폴더입니다.

현재 프로젝트와 하위 폴더에서 환경을 찾으려면 다음을 실행합니다.

```powershell
Get-ChildItem -Filter pyvenv.cfg -Recurse -Force |
    ForEach-Object { $_.Directory.FullName }
```

특정 상위 폴더 아래의 여러 프로젝트를 조회하려면 그 폴더로 이동한 뒤 같은 명령을 실행합니다. 검색 범위가 넓으면 시간이 오래 걸릴 수 있습니다.

Conda 환경은 Conda가 활성화된 PowerShell이나 Anaconda Prompt에서 별도로 조회합니다.

```powershell
conda env list
```

## 환경 삭제

환경이 활성화되어 있다면 먼저 종료합니다.

```powershell
deactivate
```

삭제 전에 대상이 현재 프로젝트의 환경인지 확인합니다.

```powershell
Resolve-Path .\.venv
```

확인한 다음 환경 폴더를 삭제합니다.

```powershell
Remove-Item -LiteralPath .\.venv -Recurse -Force
```

`venv` 환경은 폴더 자체가 환경이므로 별도의 삭제 명령은 필요하지 않습니다. 환경을 삭제해도 프로젝트 코드, 노트북, `requirements.txt`, 시스템 Python은 삭제되지 않습니다.

## 환경 다시 만들기

문제가 생기거나 환경을 삭제한 후에는 동일한 명령으로 다시 구성할 수 있습니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

가상환경 폴더는 용량이 크고 다른 PC에서도 다시 만들 수 있으므로 Git에 커밋하지 않습니다. 이 저장소의 `.gitignore`에는 `.venv/`와 `venv/`가 제외 대상으로 등록되어 있습니다.
