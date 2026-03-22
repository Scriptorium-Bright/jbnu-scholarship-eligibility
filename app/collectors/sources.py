from __future__ import annotations

from app.collectors.types import CollectorSource

JBNU_MAIN_NOTICE_SOURCE = CollectorSource(
    source_board="jbnu-main",
    list_url="https://www.jbnu.ac.kr/web/news/notice/sub01.do",
    list_parser_kind="jbnu-main",
    default_department_name="전북대학교 본부",
    include_keywords=("장학", "근로장학생"),
)

JBNU_SOFTWARE_NOTICE_SOURCE = CollectorSource(
    source_board="jbnu-software",
    list_url="https://software.jbnu.ac.kr/software/3348/subview.do",
    list_parser_kind="k2web",
    default_department_name="소프트웨어공학과",
    include_keywords=("장학", "장학생"),
)

DEFAULT_COLLECTOR_SOURCES = (
    JBNU_MAIN_NOTICE_SOURCE,
    JBNU_SOFTWARE_NOTICE_SOURCE,
)
