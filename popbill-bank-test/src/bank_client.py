"""노트북에서 사용하는 설정 검증 및 팝빌 조회 도우미."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import calendar
import math
import re
import time

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))


def load_config(values=None, today=None):
    if values is None:
        from dotenv import dotenv_values
        # 루트 저장소의 .env와 혼동하지 않도록 프로젝트 파일만 읽는다.
        values = dotenv_values(ROOT / '.env', encoding='utf-8-sig', interpolate=False)
    def required(key):
        value = (values.get(key) or '').strip()
        if not value:
            raise ValueError(f'.env에 {key} 값을 입력하세요.')
        return value
    def digits(key, pattern):
        value = re.sub(r'[-\s]', '', required(key))
        if not re.fullmatch(pattern, value):
            raise ValueError(f'{key} 형식을 확인하세요.')
        return value
    def seconds(key, default):
        try:
            value = float(values.get(key) or default)
        except ValueError:
            raise ValueError(f'{key}는 숫자로 입력하세요.') from None
        if not math.isfinite(value) or not 1 <= value <= 3600:
            raise ValueError(f'{key}는 1~3600초 범위여야 합니다.')
        return value
    is_test = (values.get('POPBILL_IS_TEST') or 'true').strip()
    if is_test not in ('true', 'false'):
        raise ValueError('POPBILL_IS_TEST는 true 또는 false여야 합니다.')
    today = today or datetime.now(KST).date()
    start = (values.get('QUERY_START_DATE') or (today - timedelta(days=1)).strftime('%Y%m%d')).strip()
    end = (values.get('QUERY_END_DATE') or today.strftime('%Y%m%d')).strip()
    try:
        if not all(re.fullmatch(r'\d{8}', d) for d in (start, end)):
            raise ValueError()
        sd, ed = (datetime.strptime(d, '%Y%m%d').date() for d in (start, end))
    except ValueError:
        raise ValueError('조회 날짜는 유효한 yyyyMMdd 형식이어야 합니다.') from None
    month_index = today.year * 12 + today.month - 1 - 3
    year, month = divmod(month_index, 12)
    earliest = today.replace(year=year, month=month+1, day=min(today.day, calendar.monthrange(year, month+1)[1]))
    if not earliest <= sd <= ed <= today or (ed - sd).days > 30:
        raise ValueError('최근 3개월 내 날짜로 시작일≤종료일≤오늘, 최대 31일을 설정하세요. 은행별 조회 제한은 별도 적용됩니다.')
    return dict(link_id=required('POPBILL_LINK_ID'), secret_key=required('POPBILL_SECRET_KEY'),
                corp_num=digits('POPBILL_CORP_NUM', r'\d{10}'),
                bank_code=digits('POPBILL_BANK_CODE', r'\d{4}'),
                account_number=digits('POPBILL_ACCOUNT_NUMBER', r'\d{1,30}'),
                user_id=(values.get('POPBILL_USER_ID') or '').strip(),
                is_test=is_test == 'true', start_date=start, end_date=end,
                poll_timeout=seconds('POLL_TIMEOUT_SECONDS', 180),
                poll_interval=seconds('POLL_INTERVAL_SECONDS', 3))


def plain(value):
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if hasattr(value, '__dict__'):
        return plain(vars(value))
    return value


class BankClient:
    def __init__(self, config, service=None):
        self.config = config
        if service is None:
            from popbill import EasyFinBankService
            service = EasyFinBankService(config['link_id'], config['secret_key'])
            service.IsTest = config['is_test']
            service.IPRestrictOnOff = True
            service.UseStaticIP = False
            service.UseLocalTimeYN = True
        self.service = service

    def call(self, method, *args):
        try:
            return plain(getattr(self.service, method)(*args))
        except Exception as exc:
            message = f'{method} 실패 [{getattr(exc, "code", "오류")}]: {getattr(exc, "message", str(exc))}'
            for key in ('secret_key', 'link_id', 'corp_num', 'account_number', 'user_id'):
                if self.config[key]:
                    message = message.replace(self.config[key], '[숨김]')
            raise RuntimeError(message) from None

    def account_info(self):
        c = self.config
        return self.call('getBankAccountInfo', c['corp_num'], c['bank_code'], c['account_number'], c['user_id'])

    def request_job(self):
        c = self.config
        return self.call('requestJob', c['corp_num'], c['bank_code'], c['account_number'], c['start_date'], c['end_date'], c['user_id'])

    def wait_for_job(self, job_id, *, sleep=time.sleep, clock=time.monotonic):
        c = self.config
        deadline = clock() + c['poll_timeout']
        while clock() < deadline:
            state = self.call('getJobState', c['corp_num'], job_id, c['user_id'])
            if int(state['jobState']) == 3:
                if int(state['errorCode']) != 1:
                    raise RuntimeError(f'수집 실패 [{state["errorCode"]}]. 은행 빠른조회 및 팝빌 계좌 등록정보를 확인하세요.')
                return state
            sleep(max(0, min(c['poll_interval'], deadline - clock())))
        raise TimeoutError(f'수집 대기시간 초과. 기존 작업 ID {job_id}로 완료 대기 셀을 다시 실행하세요.')

    def transactions(self, job_id, per_page=1000):
        if not isinstance(per_page, int) or not 1 <= per_page <= 1000:
            raise ValueError('per_page는 1~1000이어야 합니다.')
        c = self.config
        rows, page = [], 1
        while True:
            result = self.call('search', c['corp_num'], job_id, ['I', 'O'], '', page, per_page, 'A', c['user_id'])
            if int(result.get('code', 1)) < 0:
                raise RuntimeError(f'거래내역 조회 실패 [{result["code"]}]')
            batch = result.get('list')
            if not isinstance(batch, list):
                raise RuntimeError('거래내역 응답에 list가 없습니다.')
            rows.extend(batch)
            if len(batch) < per_page:
                return rows
            page += 1

    def summary(self, job_id):
        c = self.config
        return self.call('summary', c['corp_num'], job_id, ['I', 'O'], '', c['user_id'])
