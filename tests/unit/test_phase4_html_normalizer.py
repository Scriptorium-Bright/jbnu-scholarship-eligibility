from pathlib import Path

from app.models import DocumentKind
from app.normalizers import HtmlNoticeNormalizer

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "collector"


def _load_fixture(name: str) -> str:
    """Read one collector HTML fixture from disk."""

    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_phase4_html_normalizer_builds_canonical_blocks():
    normalizer = HtmlNoticeNormalizer()

    payload = normalizer.normalize_notice_html(
        notice_id=1,
        raw_html=_load_fixture("jbnu_main_notice_detail.html"),
    )

    assert payload.document_kind == DocumentKind.NOTICE_HTML
    assert payload.blocks[0].block_type == "p"
    assert "국가근로장학생 선발 대상자 교육" in payload.canonical_text
    assert payload.metadata["block_count"] >= 2
