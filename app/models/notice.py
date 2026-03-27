from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import now_in_seoul
from app.models.base import Base
from app.models.common import TimestampMixin


class ScholarshipNotice(TimestampMixin, Base):
    """
    전북대학교 외부 장학게시판으로부터 1차 수집기를 통해 긁어온 원본 공지 메타데이터(수집물)를 저장하는 베이스 ORM 엔티티입니다.
    신청 시작/종료일 및 작성일 등의 거시적 정보와 함께, 모든 정규화 문서 및 추출 룰의 논리적 최상위 부모 모델로 기능합니다.
    """

    __tablename__ = "scholarship_notices"
    __table_args__ = (
        UniqueConstraint(
            "source_board",
            "source_notice_id",
            name="uq_scholarship_notice_source_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_board: Mapped[str] = mapped_column(String(100), nullable=False)
    source_notice_id: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    notice_url: Mapped[str] = mapped_column(String(500), nullable=False)
    department_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    application_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    application_ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_html_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_in_seoul,
        nullable=False,
    )

    attachments: Mapped[List["NoticeAttachment"]] = relationship(
        back_populates="notice",
        cascade="all, delete-orphan",
    )
    canonical_documents: Mapped[List["CanonicalDocument"]] = relationship(
        back_populates="notice",
        cascade="all, delete-orphan",
    )
    scholarship_rules: Mapped[List["ScholarshipRule"]] = relationship(
        back_populates="notice",
        cascade="all, delete-orphan",
    )


class NoticeAttachment(TimestampMixin, Base):
    """
    공지사항 하나에 딸려 들어온 PDF, HWP, 텍스트 등 개별 원격 첨부파일 정보들을 담는 자식 ORM 엔티티입니다.
    차후 다운로드되어 내부 스토리지에 병합된 파일 경로(Raw Storage Path) 및 무결성 검증을 위한 메타 체인 정보를 관리합니다.
    """

    __tablename__ = "notice_attachments"
    __table_args__ = (
        UniqueConstraint(
            "notice_id",
            "source_url",
            name="uq_notice_attachment_source_url",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    notice_id: Mapped[int] = mapped_column(
        ForeignKey("scholarship_notices.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_storage_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    notice: Mapped[ScholarshipNotice] = relationship(back_populates="attachments")
    canonical_documents: Mapped[List["CanonicalDocument"]] = relationship(
        back_populates="attachment",
    )

if TYPE_CHECKING:
    from app.models.document import CanonicalDocument
    from app.models.rule import ScholarshipRule
