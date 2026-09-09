"""Read-only VAN notebook helpers. Uses Python standard library for HTTP."""
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def _read_env(name):
    """이 파일에서 상위로 올라가며 첫 .env를 찾아 name 값을 읽는다 (없으면 None)."""
    for parent in Path(__file__).resolve().parents:
        env_path = parent / '.env'
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.strip().removeprefix('export ').partition('=')
            if not sep or key.strip() != name:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
                return value[1:-1]
            return value.split(' #', 1)[0].strip()
    return None


def load_key():
    key = os.environ.get('SMARTRO_VAN_API_KEY', '').strip() or (_read_env('SMARTRO_VAN_API_KEY') or '').strip()
    if not key:
        raise RuntimeError('SMARTRO_VAN_API_KEY를 저장소 .env 또는 환경변수에 설정하세요.')
    return key


def env_value(name, default=''):
    """os 환경변수 우선, 없으면 상위 .env에서 읽는다. 둘 다 없으면 default."""
    found = os.environ.get(name, '').strip()
    if found:
        return found
    value = _read_env(name)
    return value if value not in (None, '') else default


def van_get(path, params=None):
    key = load_key()
    url = 'https://extvan.smilebiz.co.kr' + path
    if params:
        url += '?' + urlencode(params)
    request = Request(url, headers={'Accept': 'application/json', 'Authorization': 'Bearer ' + key})
    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f'HTTP {error.code}: 인증·권한·요청 필드를 확인하세요.') from None
    except (URLError, TimeoutError):
        raise RuntimeError('서버 연결 실패 또는 시간 초과입니다.') from None
    except ValueError:
        raise RuntimeError('JSON 형식이 아닌 응답입니다.') from None
    if not isinstance(data, dict):
        raise RuntimeError('응답 객체 형식이 잘못되었습니다.')
    empty_sales = (path.startswith('/V1/sales/') and data.get('CODE') == 'VAN_SALE-1001'
                   and data.get('DATA') in (None, []))
    if data.get('CODE') != '0000' and not empty_sales:
        message = str(data.get('MESSAGE', '')).replace(key, '[인증키 숨김]')
        raise RuntimeError(f"API 오류 {data.get('CODE')}: {message}")
    return data


def rows_of(data):
    rows = data.get('DATA')
    if rows is None:
        return []
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError('DATA 거래 목록 형식 오류')
    return rows


def fetch_pages(path, params, max_pages=1000):
    """Use total count when available; otherwise request until empty. Fail on repeats."""
    rows, responses, fingerprints = [], [], set()
    expected_total = None
    for page in range(max_pages):
        data = van_get(path, {**params, 'CURRPAGE': page})
        batch = rows_of(data)
        responses.append(data)
        total = data.get('TOT_CNT', batch[0].get('TOT_CNT') if batch else None)
        if total is not None:
            total = int(total)
            if total < 0 or (expected_total is not None and expected_total != total):
                raise RuntimeError('조회 중 총 건수가 변경되었습니다. 다시 조회하세요.')
            expected_total = total
        if not batch:
            if expected_total is not None and len(rows) != expected_total:
                raise RuntimeError('전체 건수를 받기 전에 빈 페이지가 반환되었습니다.')
            return rows, responses
        for row in batch:
            for name in ('TERMID', 'GBN', 'AUTHNO'):
                if params.get(name) and row.get(name) not in (None, '') and str(row[name]).strip() != str(params[name]).strip():
                    raise RuntimeError(f'요청과 다른 {name}이 반환되었습니다.')
        # Exclude page metadata so a server ignoring CURRPAGE cannot loop forever.
        fingerprint = json.dumps([{k: v for k, v in r.items() if k not in ('CURRPAGE', 'TOTPAGE', 'TOT_CNT', 'TOT_AMT')} for r in batch], sort_keys=True)
        if fingerprint in fingerprints:
            raise RuntimeError('동일한 거래 페이지가 반복되어 전체 조회를 중단했습니다.')
        fingerprints.add(fingerprint)
        rows.extend(batch)
        if expected_total is not None:
            if len(rows) > expected_total:
                raise RuntimeError('수신 건수가 총 건수를 초과했습니다.')
            if len(rows) == expected_total:
                return rows, responses
    raise RuntimeError('최대 페이지 수에 도달했습니다. 전체 조회 완료가 아닙니다.')


def sales_params(start, end, termid='', gbn='2', authno='', comp_no='', comp_idx=''):
    return dict(SDATE=start, EDATE=end, STIME='', ETIME='', COMP_NO=comp_no,
                COMP_IDX=comp_idx, TERMID=termid, GBN=gbn, CDNO='', AUTHNO=authno,
                HID_GBN='', ORGCOD='', REJEC_TYPE='1')
