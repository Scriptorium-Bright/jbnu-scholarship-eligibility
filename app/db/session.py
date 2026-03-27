from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Dict, Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.models.base import Base


@lru_cache(maxsize=4)
def build_engine(database_url: str):
    """
    애플리케이션 설정에 선언된 DB URL을 바탕으로 캐시된 SQLAlchemy 커넥션 엔진 객체를 생성합니다.
    초당 수많은 요청에도 인스턴스 재생성을 방지하여 오버헤드와 물리적인 자원 소모를 감소시킵니다.
    """

    connect_args = {}
    engine_kwargs = {
        "future": True,
        "pool_pre_ping": True,
        "connect_args": connect_args,
    }
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if database_url.endswith(":memory:"):
            engine_kwargs["poolclass"] = StaticPool

    return create_engine(database_url, **engine_kwargs)


@lru_cache(maxsize=4)
def build_session_factory(database_url: str):
    """
    설정된 캐시 엔진에 연결된 데이터베이스 세션 팩토리를 구성하여 트랜잭션 단위 작업을 통제합니다.
    안전한 연결을 위해 Autoflush를 방지하고 Commit 시 객체 만료(Expire) 옵션을 꺼둡니다.
    """

    return sessionmaker(
        bind=build_engine(database_url),
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )


def get_engine():
    """
    현재 구동 중인 애플리케이션의 설정값(Config)을 읽어들여 전역적으로 재사용 가능한 DB 엔진을 반환합니다.
    주로 DDL(테이블 생성)이나 헬스체크 등 순수 커넥션 단위 작업이 필요할 때 호출됩니다.
    """

    return build_engine(get_settings().database_url)


def get_session_factory():
    """
    현재 구동 중인 애플리케이션 설정값(Config)을 통해 생성된 전역 유지형 DB 세션 팩토리를 리턴합니다.
    개별 트랜잭션을 일관되게 열어주는 기초 토대 객체로 동작합니다.
    """

    return build_session_factory(get_settings().database_url)


def get_session() -> Session:
    """
    캐시되어 있는 내부 라이프사이클 세션 팩토리로부터 실제 데이터베이스와 소통할 단일 세션 객체를 뽑아냅니다.
    주입(DI)나 개별 명령 생명주기 블록 등에서 호출해 작업 시작점으로 쓰입니다.
    """

    return get_session_factory()()


@contextmanager
def session_scope() -> Iterator[Session]:
    """
    하나의 작업 단위(Unit of Work)를 독립된 로컬 트랜잭션 컨텍스트 범위로 안전하게 감싸 보호합니다.
    정상 종료 시 자동 커밋을, 예외 발생 시 에러 롤백 처리를 자동화하여 DB 무결성을 유지합니다.
    """

    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all_tables() -> None:
    """
    로컬 테스트 구동이나 초기 데이터베이스 앱 부트스트랩 시점에 선언된 모든 테이블 DDL을 전송합니다.
    의존되는 모든 모델들을 먼저 임포트시켜 메타데이터 맵핑이 누락되지 않도록 방어합니다.
    """

    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def reset_engine_cache() -> None:
    """
    pytest 등을 통한 단위/통합 테스트 환경 간의 상태 데이터 격리와 완전한 독립성 보장을 수행합니다.
    캐싱된 구 엔진 및 세션 팩토리 인스턴스를 메모리상에서 모두 비워내고 새로 짓도록 유도합니다.
    """

    build_engine.cache_clear()
    build_session_factory.cache_clear()


def database_healthcheck() -> Dict[str, Any]:
    """
    데이터베이스 커넥션이 정상적으로 수립되고 가벼운 단위 쿼리(SELECT 1)가 동작하는지 점검합니다.
    외부 로드밸런서의 레디니스 프로브(Readiness Probe)나 서버 헬스체크 라우터 API에서 확인용으로 반환합니다.
    """

    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "detail": "database connection succeeded"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
