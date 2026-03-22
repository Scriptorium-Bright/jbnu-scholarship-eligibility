from pathlib import Path

from app.collectors.sources import JBNU_MAIN_NOTICE_SOURCE
from app.db import create_all_tables, session_scope
from app.models import DocumentKind
from app.repositories import CanonicalDocumentRepository
from app.services import NoticeCollectionService, NoticeHtmlNormalizationService
from app.storage import LocalRawStorage

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "collector"


def _load_fixture(name: str) -> str:
    """Read one collector HTML fixture from disk."""

    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_phase4_notice_normalization_service_persists_canonical_document(monkeypatch, tmp_path):
    database_path = tmp_path / "phase4_normalize.sqlite3"
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

    collection_service = NoticeCollectionService(
        fetch_html=fixture_map.__getitem__,
        fetch_binary=binary_map.__getitem__,
        raw_storage=storage,
    )
    collection_result = collection_service.collect_source(
        source=JBNU_MAIN_NOTICE_SOURCE,
        limit=10,
    )

    normalization_service = NoticeHtmlNormalizationService(raw_storage=storage)
    document = normalization_service.normalize_notice(collection_result.persisted_notice_ids[0])

    with session_scope() as session:
        document_repository = CanonicalDocumentRepository(session)
        stored_document = document_repository.get_document(
            notice_id=document.notice_id,
            attachment_id=None,
            document_kind=DocumentKind.NOTICE_HTML,
        )

        assert stored_document is not None
        assert stored_document.document_kind == DocumentKind.NOTICE_HTML
        assert stored_document.blocks_json[0]["text"].startswith("2026학년도 1학기 국가근로장학생")
