from datetime import datetime, timedelta, timezone

ASIA_SEOUL = timezone(timedelta(hours=9), name="Asia/Seoul")


def now_in_seoul() -> datetime:
    """
    전북대학교 학사 시스템의 타임존(Asia/Seoul, UTC+9)에 기반을 둔 명확한 타임스탬프(Aware Datetime) 객체를 반환합니다.
    DB 저장 시간 보정 및 현재 날짜 대비 장학금 마감 산출(Status 계산) 등 치밀한 일정 관리에 범용적으로 쓰입니다.
    """
    return datetime.now(tz=ASIA_SEOUL)
