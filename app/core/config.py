from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    애플리케이션 전반에 적용될 데이터베이스 연결 정보, 로그 레벨, 스토리지 경로 등의 전역 상수와 환경 변수를 매핑합니다.
    Pydantic을 이용하여 `.env` 파일과 시스템 환경 변수 중 우선 순위를 해석하여 안전한 정적 타입으로 바인딩합니다.
    """
    app_name: str = "JBNU Scholarship Regulation Search & Eligibility Decision System"
    environment: str = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://jbnu:jbnu@localhost:54329/jbnu_scholarship"
    raw_storage_path: str = "./data/raw"

    model_config = SettingsConfigDict(
        env_prefix="JBNU_",
        case_sensitive=False,
        env_file=".env",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    동적인 Pydantic 설정 객체를 애플리케이션 라이프사이클 구동 시점에 싱글톤 캐싱(lru_cache)으로 인스턴스화해 가져옵니다.
    반복적인 I/O 파일 읽기 및 파싱 오버헤드를 없애고 빠르고 쾌적하게 설정을 조회하도록 돕습니다.
    """
    return Settings()


def reset_settings_cache() -> None:
    """
    Pytest 같은 자동화 테스트 환경에서 임의로 환경 변수를 갈아끼운 뒤 설정을 새로 밀어넣어야 할 때 호출합니다.
    보호되어 있던 기존 세팅 객체 캐시를 날림으로써 변경된 픽스처(Fixture)가 새롭게 씌워지도록 유도합니다.
    """
    get_settings.cache_clear()
