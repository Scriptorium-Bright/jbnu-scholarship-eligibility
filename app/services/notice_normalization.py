from __future__ import annotations

from typing import Optional

from app.db import session_scope
from app.normalizers import HtmlNoticeNormalizer
from app.repositories import CanonicalDocumentRepository, ScholarshipNoticeRepository
from app.storage import LocalRawStorage


class NoticeHtmlNormalizationService:
    """Read stored raw HTML and persist canonical notice documents."""

    def __init__(
        self,
        raw_storage: Optional[LocalRawStorage] = None,
        normalizer: Optional[HtmlNoticeNormalizer] = None,
    ):
        """
        저장된 원본 HTML을 불러오는 로컬 스토리지 애드온과 정규화기(Normalizer)를 주입합니다.
        파일 시스템과 파이프라인 컴포넌트 간의 의존성을 구축합니다.
        """

        self._raw_storage = raw_storage or LocalRawStorage()
        self._normalizer = normalizer or HtmlNoticeNormalizer()

    def normalize_notice(self, notice_id: int):
        """
        특정 공지사항 ID를 기준으로 저장된 Raw HTML을 읽어들여 공통 형식으로 정규화합니다.
        이후 추출기가 처리할 수 있는 Canonical Document 형태로 변환되어 DB에 적재됩니다.
        """

        with session_scope() as session:
            notice_repository = ScholarshipNoticeRepository(session)
            document_repository = CanonicalDocumentRepository(session)

            notice = notice_repository.get_by_id(notice_id)
            if notice is None:
                raise ValueError("Notice does not exist: {0}".format(notice_id))
            if not notice.raw_html_path:
                raise ValueError("Notice does not have stored raw HTML: {0}".format(notice_id))

            raw_html = self._raw_storage.read_text(notice.raw_html_path)
            payload = self._normalizer.normalize_notice_html(notice.id, raw_html)
            return document_repository.upsert_document(payload)
