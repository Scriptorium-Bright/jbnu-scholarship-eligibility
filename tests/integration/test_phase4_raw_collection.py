from pathlib import Path

from app.collectors.sources import JBNU_MAIN_NOTICE_SOURCE
from app.db import create_all_tables, session_scope
from app.repositories import ScholarshipNoticeRepository
from app.services import NoticeCollectionService
from app.storage import LocalRawStorage

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "collector"


def _load_fixture(name: str) -> str:
    """Read one collector HTML fixture from disk."""

    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_phase4_collection_service_stores_raw_notice_html_and_attachments(monkeypatch, tmp_path):
    database_path = tmp_path / "phase4_raw.sqlite3"
    monkeypatch.setenv("JBNU_DATABASE_URL", "sqlite+pysqlite:///{0}".format(database_path))
    create_all_tables()

    storage = LocalRawStorage(base_path=str(tmp_path / "raw"))
    fixture_map = {
        "https://www.jbnu.ac.kr/web/news/notice/sub01.do": _load_fixture("jbnu_main_notice_list.html"),
        "https://www.jbnu.ac.kr/web/news/notice/sub01.do?mode=view&articleNo=402100": _load_fixture(
            "jbnu_main_notice_detail.html"
        ),
    }
    binary_map = {
        "https://www.jbnu.ac.kr/files/work-study-guide.pdf": b"fake-pdf-binary",
    }

    service = NoticeCollectionService(
        fetch_html=fixture_map.__getitem__,
        fetch_binary=binary_map.__getitem__,
        raw_storage=storage,
    )
    result = service.collect_source(JBNU_MAIN_NOTICE_SOURCE, limit=10)

    assert result.persisted_count == 1

    with session_scope() as session:
        notice_repository = ScholarshipNoticeRepository(session)
        notice = notice_repository.get_by_source_identity("jbnu-main", "402100")

        assert notice is not None
        assert notice.raw_html_path is not None
        assert storage.exists(notice.raw_html_path)
        assert len(notice.attachments) == 1
        assert notice.attachments[0].raw_storage_path is not None
        assert storage.read_bytes(notice.attachments[0].raw_storage_path) == b"fake-pdf-binary"
