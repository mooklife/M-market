from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def get_kst_now() -> datetime:
    return datetime.now(tz=KST)


def get_kst_now_str() -> str:
    return get_kst_now().isoformat()
