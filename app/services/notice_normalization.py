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
        """Prepare the raw storage adapter and HTML normalizer used by the service."""

        self._raw_storage = raw_storage or LocalRawStorage()
        self._normalizer = normalizer or HtmlNoticeNormalizer()

    def normalize_notice(self, notice_id: int):
        """Normalize one stored notice HTML file into a canonical document."""

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
