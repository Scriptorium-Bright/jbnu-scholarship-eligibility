from datetime import datetime, timedelta, timezone

ASIA_SEOUL = timezone(timedelta(hours=9), name="Asia/Seoul")


def now_in_seoul() -> datetime:
    return datetime.now(tz=ASIA_SEOUL)
