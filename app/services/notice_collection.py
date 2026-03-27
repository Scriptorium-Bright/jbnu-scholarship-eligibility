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
        """
        게시물 수집기(Fetcher)와 본문/요약/첨부 파싱 객체들을 주입하여 준비합니다.
        HTTP 통신 및 디스크 I/O 저장을 위한 외부 인프라 의존성을 세팅합니다.
        """

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
        """
        서비스가 자체 생성한 HTTP 연결 클라이언트 객체가 있다면 명시적으로 해제합니다.
        스케줄러 작업 등에서 발생할 수 있는 소켓(Socket) 리소스 누수를 근본적으로 억제합니다.
        """

        if self._owned_fetcher is not None:
            self._owned_fetcher.close()

    def collect_default_sources(self, limit_per_source: int = 20) -> List[CollectionRunResult]:
        """
        사전에 기본 정의된 JBNU 핵심 대상 게시판 소스들을 전체 순회하며 크롤링을 수행합니다.
        각 출처별 수집 내역 횟수와 상세 결과를 리스트 모음으로 한 번에 반환합니다.
        """

        return [
            self.collect_source(source, limit=limit_per_source)
            for source in DEFAULT_COLLECTOR_SOURCES
        ]

    def collect_source(self, source: CollectorSource, limit: int = 20) -> CollectionRunResult:
        """
        특정 게시판 하나에서 요약 리스트를 받고, 키워드로 단일 필터링한 뒤 상세 내용을 수집해 DB에 반영(Upsert)합니다.
        원시 HTML 파편 데이터 저장부터 첨부파일 보존 작업까지 한 사이클의 프로세스를 묶어서 처리합니다.
        """

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
        """
        대상 게시판의 목록(List) 웹 페이지를 내려받아 설정된 전용 파서로 구문 분석합니다.
        제목과 게시일자 같이 간략하게 요약된 데이터 구조체 리스트를 1차적으로 도출해냅니다.
        """

        parser = self._select_list_parser(source)
        list_html = self._fetch_html(source.list_url)
        return parser.parse(list_html, source)

    def _collect_detail(self, source: CollectorSource, summary: CollectedNoticeSummary):
        """
        초기에 파악된 링크 URL을 방문하여 공지사항 내 장문의 HTML 텍스트를 불러오고 내용을 해독합니다.
        DB 삽입을 위해 정돈된 데이터 모델과, 추후 기록 차원에서 남길 수 있는 원본(Raw) HTML을 튜플로 반환합니다.
        """

        detail_html = self._fetch_html(summary.notice_url)
        return detail_html, self._detail_parser.parse(detail_html, summary, source)

    def _select_list_parser(self, source: CollectorSource):
        """
        소스 환경(K2Web, JBNU Main 등)에 호환되는 적합한 리스트 파서 구현체를 맵(Dictionary)에서 찾아 꺼내옵니다.
        매치되는 타입이 설정되어 있지 않은 경우 런타임 에러(KeyError)를 발생시킵니다.
        """

        if source.list_parser_kind not in self._list_parsers:
            raise KeyError("Unsupported list parser kind: {0}".format(source.list_parser_kind))
        return self._list_parsers[source.list_parser_kind]

    def _filter_summaries(
        self,
        source: CollectorSource,
        summaries: Iterable[CollectedNoticeSummary],
    ) -> List[CollectedNoticeSummary]:
        """
        초기 크롤링된 다량의 요약 공지사항 중 지정된 검색 키워드(예: 장학)가 등장하는 데이터만 선별합니다.
        무관한 일반 게시글들로 인해 무의미하게 상세 페이지들을 더 수집하는 트래픽 낭비 문제를 방지합니다.
        """

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
