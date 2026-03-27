from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from app.db import session_scope
from app.models import NoticeAttachment
from app.normalizers import AttachmentDocumentNormalizer
from app.repositories import CanonicalDocumentRepository
from app.storage import LocalRawStorage


class AttachmentNormalizationService:
    """Read stored attachment binaries and persist canonical attachment documents."""

    def __init__(
        self,
        raw_storage: Optional[LocalRawStorage] = None,
        normalizer: Optional[AttachmentDocumentNormalizer] = None,
    ):
        """
        원시(Raw) 저장소 어댑터와 첨부파일 정규화기(Normalizer)를 주입받아 초기화합니다.
        파일 시스템과 파일 파싱 로직의 의존성을 설정합니다.
        """

        self._raw_storage = raw_storage or LocalRawStorage()
        self._normalizer = normalizer or AttachmentDocumentNormalizer()

    def normalize_attachment(self, attachment_id: int):
        """
        주어지는 첨부파일 ID를 바탕으로 DB에서 메타데이터를 찾고, 원시 파일을 읽어 정규화합니다.
        PDF나 HWP의 텍스트를 파싱하여 규격화된 문서 형태로 DB에 적재(Upsert)합니다.
        """

        with session_scope() as session:
            attachment = session.scalar(
                select(NoticeAttachment).where(NoticeAttachment.id == attachment_id)
            )
            if attachment is None:
                raise ValueError("Attachment does not exist: {0}".format(attachment_id))
            if not attachment.raw_storage_path:
                raise ValueError("Attachment does not have stored raw content: {0}".format(attachment_id))

            raw_bytes = self._raw_storage.read_bytes(attachment.raw_storage_path)
            payload = self._normalizer.normalize_attachment(
                notice_id=attachment.notice_id,
                attachment_id=attachment.id,
                file_name=attachment.file_name,
                media_type=attachment.media_type,
                raw_bytes=raw_bytes,
            )

            repository = CanonicalDocumentRepository(session)
            return repository.upsert_document(payload)
