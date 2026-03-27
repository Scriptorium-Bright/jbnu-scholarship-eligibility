import logging


def configure_logging(log_level: str) -> None:
    """
    애플리케이션 부트스트랩 시점에 표준 라이브러리(logging)의 글로벌 포맷과 로깅 레벨 제한을 초기화하는 공용 설정기입니다.
    API 라우터, 콘솔 등에서 출력되는 텍스트 기록이 균일한 메타데이터 형식을 따를 수 있게 세팅합니다.
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
