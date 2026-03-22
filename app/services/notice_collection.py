from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional

from app.collectors.fetchers import HttpTextFetcher
from app.collectors.parsers import (
    GenericNoticeDetailParser,
    JbnuMainNoticeListParser,
    K2WebNoticeListParser,
)
from app.collectors.sources import DEFAULT_COLLECTOR_SOURCES
from app.collectors.types import CollectedNoticeSummary, CollectionRunResult, CollectorSource
from app.db import session_scope
from app.repositories import ScholarshipNoticeRepository
from app.schemas import NoticeAttachmentUpsert, ScholarshipNoticeUpsert
from app.storage import LocalRawStorage


class NoticeCollectionService:
    """Collect notice metadata from configured JBNU boards and persist it."""

    def __init__(
        self,
        fetch_html: Optional[Callable[[str], str]] = None,
        fetch_binary: Optional[Callable[[str], bytes]] = None,
        raw_storage: Optional[LocalRawStorage] = None,
    ):
        """Prepare fetchers plus optional raw storage for archival runs."""

        self._owned_fetcher = HttpTextFetcher() if fetch_html is None else None
        self._fetch_html = fetch_html or self._owned_fetcher.fetch_text
        self._fetch_binary = fetch_binary or (
            self._owned_fetcher.fetch_bytes if self._owned_fetcher is not None else None
        )
        self._raw_storage = raw_storage
        self._list_parsers: Dict[str, object] = {
            "jbnu-main": JbnuMainNoticeListParser(),
            "k2web": K2WebNoticeListParser(),
        }
        self._detail_parser = GenericNoticeDetailParser()

    def close(self) -> None:
        """Close the owned HTTP client when the service created it internally."""

        if self._owned_fetcher is not None:
            self._owned_fetcher.close()

    def collect_default_sources(self, limit_per_source: int = 20) -> List[CollectionRunResult]:
        """Collect all default sources defined for the MVP."""

        return [
            self.collect_source(source, limit=limit_per_source)
            for source in DEFAULT_COLLECTOR_SOURCES
        ]

    def collect_source(self, source: CollectorSource, limit: int = 20) -> CollectionRunResult:
        """Collect one source board and persist matched scholarship notices."""

        summaries = self._collect_summaries(source)
        matched_summaries = self._filter_summaries(source, summaries)[:limit]
        persisted_notice_ids = []

        with session_scope() as session:
            notice_repository = ScholarshipNoticeRepository(session)
            for summary in matched_summaries:
                detail_html, detail = self._collect_detail(source, summary)
                raw_html_path = None
                if self._raw_storage is not None:
                    raw_html_path = self._raw_storage.save_notice_html(
                        source.source_board,
                        detail.source_notice_id,
                        detail_html,
                    )
                notice = notice_repository.upsert_notice(
                    ScholarshipNoticeUpsert(
                        source_board=source.source_board,
                        source_notice_id=detail.source_notice_id,
                        title=detail.title,
                        notice_url=detail.notice_url,
                        published_at=detail.published_at,
                        department_name=detail.department_name,
                        application_started_at=detail.application_started_at,
                        application_ended_at=detail.application_ended_at,
                        summary=detail.summary,
                        raw_html_path=raw_html_path,
                    )
                )
                for attachment in detail.attachments:
                    raw_storage_path = None
                    if self._raw_storage is not None and self._fetch_binary is not None:
                        raw_storage_path = self._raw_storage.save_attachment(
                            source.source_board,
                            detail.source_notice_id,
                            attachment.file_name,
                            self._fetch_binary(attachment.source_url),
                        )
                    notice_repository.add_or_update_attachment(
                        notice_id=notice.id,
                        payload=NoticeAttachmentUpsert(
                            source_url=attachment.source_url,
                            file_name=attachment.file_name,
                            media_type=attachment.media_type,
                            raw_storage_path=raw_storage_path,
                        ),
                    )
                persisted_notice_ids.append(notice.id)

        return CollectionRunResult(
            source_board=source.source_board,
            fetched_count=len(summaries),
            matched_count=len(matched_summaries),
            persisted_count=len(persisted_notice_ids),
            persisted_notice_ids=tuple(persisted_notice_ids),
        )

    def _collect_summaries(self, source: CollectorSource) -> List[CollectedNoticeSummary]:
        """Fetch and parse one list page into notice summaries."""

        parser = self._select_list_parser(source)
        list_html = self._fetch_html(source.list_url)
        return parser.parse(list_html, source)

    def _collect_detail(self, source: CollectorSource, summary: CollectedNoticeSummary):
        """Fetch raw detail HTML and parse it into a persistence-ready notice payload."""

        detail_html = self._fetch_html(summary.notice_url)
        return detail_html, self._detail_parser.parse(detail_html, summary, source)

    def _select_list_parser(self, source: CollectorSource):
        """Pick the parser implementation that matches the source type."""

        if source.list_parser_kind not in self._list_parsers:
            raise KeyError("Unsupported list parser kind: {0}".format(source.list_parser_kind))
        return self._list_parsers[source.list_parser_kind]

    def _filter_summaries(
        self,
        source: CollectorSource,
        summaries: Iterable[CollectedNoticeSummary],
    ) -> List[CollectedNoticeSummary]:
        """Keep only summaries that look scholarship-related for the current source."""

        keywords = [keyword.lower() for keyword in source.include_keywords]
        matched = []
        for summary in summaries:
            search_fields = [
                summary.title.lower(),
                (summary.category or "").lower(),
            ]
            if any(keyword in field for keyword in keywords for field in search_fields):
                matched.append(summary)
        return matched
