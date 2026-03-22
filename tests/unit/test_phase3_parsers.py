from pathlib import Path

from app.collectors.parsers import GenericNoticeDetailParser, JbnuMainNoticeListParser, K2WebNoticeListParser
from app.collectors.sources import JBNU_MAIN_NOTICE_SOURCE, JBNU_SOFTWARE_NOTICE_SOURCE

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "collector"


def _load_fixture(name: str) -> str:
    """Read one collector HTML fixture from disk."""

    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_phase3_main_list_parser_extracts_notice_summaries():
    parser = JbnuMainNoticeListParser()

    summaries = parser.parse(_load_fixture("jbnu_main_notice_list.html"), JBNU_MAIN_NOTICE_SOURCE)

    assert len(summaries) == 2
    assert summaries[0].source_notice_id == "402100"
    assert summaries[0].category == "장학"


def test_phase3_k2web_list_parser_extracts_notice_summaries():
    parser = K2WebNoticeListParser()

    summaries = parser.parse(_load_fixture("software_notice_list.html"), JBNU_SOFTWARE_NOTICE_SOURCE)

    assert len(summaries) == 2
    assert summaries[0].source_notice_id == "384006"
    assert summaries[0].department_name == "소프트웨어공학과"


def test_phase3_detail_parser_extracts_body_window_and_attachments():
    summary = JbnuMainNoticeListParser().parse(
        _load_fixture("jbnu_main_notice_list.html"),
        JBNU_MAIN_NOTICE_SOURCE,
    )[0]
    parser = GenericNoticeDetailParser()

    detail = parser.parse(
        _load_fixture("jbnu_main_notice_detail.html"),
        summary,
        JBNU_MAIN_NOTICE_SOURCE,
    )

    assert detail.application_started_at is not None
    assert detail.application_ended_at is not None
    assert detail.attachments[0].file_name == "국가근로 교육자료.pdf"
