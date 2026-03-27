from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Dict, Optional, Tuple

import olefile
from pypdf import PdfReader

from app.models import DocumentKind
from app.schemas import CanonicalBlock, CanonicalDocumentUpsert


class UnsupportedAttachmentError(ValueError):
    """Raised when no extractor is available for the attachment payload."""


def _clean_text(text: str) -> str:
    """
    여러 줄바꿈과 연속된 공백 문자를 단일 띄어쓰기로 압축하여 파싱된 텍스트 크기를 최적화합니다.
    검색 시 공백 차이로 인한 매칭 실패를 예방하고 출처 문장을 정돈합니다.
    """

    return " ".join((text or "").split())


class PdfAttachmentTextExtractor:
    """Extract text from PDF attachments using pypdf."""

    def extract(self, raw_bytes: bytes) -> str:
        """
        바이너리로 전달된 PDF 파일 내용에서 pypdf를 이용하여 모든 페이지의 텍스트를 추출합니다.
        각 페이지별 텍스트를 정돈(_clean_text)한 후 하나의 긴 문자열로 병합합니다.
        """

        reader = PdfReader(BytesIO(raw_bytes))
        page_texts = []
        for page in reader.pages:
            extracted = _clean_text(page.extract_text() or "")
            if extracted:
                page_texts.append(extracted)
        return "\n".join(page_texts).strip()


class HwpPreviewTextExtractor:
    """Extract preview text from HWP attachments through the OLE `PrvText` stream."""

    def extract(self, raw_bytes: bytes) -> str:
        """
        구형 HWP 파일 포맷의 OLE 구조에 접근하여 'PrvText' 부분(미리보기 텍스트)만 가볍게 읽어냅니다.
        이를 파이썬이 해석 가능한 UTF-16LE 기반 텍스트로 안전하게 디코딩합니다.
        """

        ole = olefile.OleFileIO(BytesIO(raw_bytes))
        try:
            if not ole.exists("PrvText"):
                raise UnsupportedAttachmentError("HWP preview text stream is missing")
            preview_stream = ole.openstream("PrvText")
            preview_bytes = preview_stream.read()
        finally:
            ole.close()

        extracted = _clean_text(preview_bytes.decode("utf-16le", errors="ignore"))
        if not extracted:
            raise UnsupportedAttachmentError("HWP preview text is empty")
        return extracted


class PlainTextAttachmentTextExtractor:
    """Decode text-like attachment bytes as UTF-8."""

    def extract(self, raw_bytes: bytes) -> str:
        """
        메모장 파일(.txt)이나 마크다운 형식 등의 일반 텍스트 바이트 배열을 UTF-8로 디코딩합니다.
        디코딩된 내용이 비어있을 경우 부적합 예외(UnsupportedAttachmentError)를 발생시킵니다.
        """

        extracted = _clean_text(raw_bytes.decode("utf-8"))
        if not extracted:
            raise UnsupportedAttachmentError("Plain text attachment is empty")
        return extracted


class AttachmentDocumentNormalizer:
    """Convert raw attachment bytes into canonical document payloads."""

    def __init__(
        self,
        pdf_extractor: Optional[PdfAttachmentTextExtractor] = None,
        hwp_extractor: Optional[HwpPreviewTextExtractor] = None,
        text_extractor: Optional[PlainTextAttachmentTextExtractor] = None,
    ):
        """
        PDF, HWP, 텍스트 형태의 확장자별 전용 파싱 객체(Extractor) 타입들을 각각 주입받아 준비합니다.
        추후 분기 처리(Strategy)를 통해 파일 타입에 알맞은 파서를 호출합니다.
        """

        self._pdf_extractor = pdf_extractor or PdfAttachmentTextExtractor()
        self._hwp_extractor = hwp_extractor or HwpPreviewTextExtractor()
        self._text_extractor = text_extractor or PlainTextAttachmentTextExtractor()

    def normalize_attachment(
        self,
        notice_id: int,
        attachment_id: int,
        file_name: str,
        media_type: str,
        raw_bytes: bytes,
    ) -> CanonicalDocumentUpsert:
        """
        각종 첨부파일 포맷을 자동으로 인식 및 텍스트화 한 뒤, 단락을 나누어 통일된 블록셋(Blocks) 구조체로 래핑합니다.
        이를 DB에 즉시 삽입(Upsert) 가능한 형태인 CanonicalDocumentUpsert 형태로 리턴해 줍니다.
        """

        document_kind, extracted_text = self._extract_text(file_name, media_type, raw_bytes)
        lines = [line.strip() for line in extracted_text.splitlines() if line.strip()]
        block_texts = lines or [extracted_text]
        blocks = [
            CanonicalBlock(
                block_id="block-{0}".format(index + 1),
                block_type="attachment_text",
                text=block_text,
                metadata={"file_name": file_name},
            )
            for index, block_text in enumerate(block_texts)
        ]

        return CanonicalDocumentUpsert(
            notice_id=notice_id,
            attachment_id=attachment_id,
            document_kind=document_kind,
            source_label="attachment:{0}".format(file_name),
            canonical_text="\n".join(block.text for block in blocks),
            blocks=blocks,
            metadata={
                "file_name": file_name,
                "media_type": media_type,
                "attachment_id": attachment_id,
            },
        )

    def _extract_text(
        self,
        file_name: str,
        media_type: str,
        raw_bytes: bytes,
    ) -> Tuple[DocumentKind, str]:
        """
        파일의 영문 확장자 및 MIME 미디어 타입을 분석하여 어떤 추출기(PDF/HWP/TXT)를 사용할지 판단합니다.
        선택된 추출기를 통해 뽑힌 문자열 원문과 식별된 파일 종류(DocumentKind)를 넘겨줍니다.
        """

        extension = Path(file_name).suffix.lower()
        if extension == ".pdf" or media_type == "application/pdf":
            extracted = self._pdf_extractor.extract(raw_bytes)
            if not extracted:
                raise UnsupportedAttachmentError("PDF attachment does not contain extractable text")
            return DocumentKind.ATTACHMENT_PDF, extracted

        if extension == ".hwp" or media_type == "application/x-hwp":
            return DocumentKind.ATTACHMENT_TEXT, self._hwp_extractor.extract(raw_bytes)

        if media_type.startswith("text/") or extension in {".txt", ".md"}:
            return DocumentKind.ATTACHMENT_TEXT, self._text_extractor.extract(raw_bytes)

        raise UnsupportedAttachmentError(
            "Unsupported attachment type: {0} ({1})".format(file_name, media_type)
        )
