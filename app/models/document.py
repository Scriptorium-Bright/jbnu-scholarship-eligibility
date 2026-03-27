from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import Enum, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.common import DocumentKind, TimestampMixin


class CanonicalDocument(TimestampMixin, Base):
    """
    공지사항 본문이나 첨부파일 구별 없이 순수 텍스트를 추출하여 저장하는 정규화 문서(Canonical Document) ORM 엔티티입니다.
    룰 조각(Rule) 추출 과정에서 스크래핑 엔진이 통일된 알고리즘으로 문서를 스캔할 수 있도록 일관된 JSON 블록 구조를 제공합니다.
    """

    __tablename__ = "canonical_documents"
    __table_args__ = (
        UniqueConstraint(
            "notice_id",
            "attachment_id",
            "document_kind",
            name="uq_canonical_document_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    notice_id: Mapped[int] = mapped_column(
        ForeignKey("scholarship_notices.id", ondelete="CASCADE"),
        nullable=False,
    )
    attachment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("notice_attachments.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_kind: Mapped[DocumentKind] = mapped_column(
        Enum(DocumentKind, native_enum=False, length=32),
        nullable=False,
    )
    source_label: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_text: Mapped[str] = mapped_column(Text, nullable=False)
    blocks_json: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    notice: Mapped["ScholarshipNotice"] = relationship(back_populates="canonical_documents")
    attachment: Mapped[Optional["NoticeAttachment"]] = relationship(
        back_populates="canonical_documents",
    )
    provenance_anchors: Mapped[List["ProvenanceAnchor"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    scholarship_rules: Mapped[List["ScholarshipRule"]] = relationship(
        back_populates="document",
    )


class ProvenanceAnchor(TimestampMixin, Base):
    """
    특정 장학 조건이 정규화 문서의 어느 단락(블록)에서 파생되었는지를 시각적으로 추적 가능하게 돕는 출처 핀(Anchor) ORM 엔티티입니다.
    AI의 응답 근거나 사용자에게 보여줄 하이라이팅 기준(Quote, Locator) 메타데이터를 보관합니다.
    """

    __tablename__ = "provenance_anchors"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "anchor_key",
            name="uq_provenance_anchor_document_key",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    anchor_key: Mapped[str] = mapped_column(String(120), nullable=False)
    block_id: Mapped[str] = mapped_column(String(120), nullable=False)
    quote_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(nullable=True)
    locator_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    document: Mapped[CanonicalDocument] = relationship(back_populates="provenance_anchors")

if TYPE_CHECKING:
    from app.models.notice import NoticeAttachment, ScholarshipNotice
    from app.models.rule import ScholarshipRule
