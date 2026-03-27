from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.common import RuleStatus, TimestampMixin


class ScholarshipRule(TimestampMixin, Base):
    """
    가공된 정규화 문서들 속에서 자격(성적, 소득분위, 학년 등) 요건만을 구체적으로 추출해낸 핵심 비즈니스 도메인 ORM 엔티티입니다.
    실질적인 학생 엘리지빌리티(Eligibility) 판정 엔진이 이 구조화된 Qualification JSON 데이터를 기반으로 합불 검사를 실행합니다.
    """

    __tablename__ = "scholarship_rules"
    __table_args__ = (
        UniqueConstraint(
            "notice_id",
            "scholarship_name",
            "rule_version",
            name="uq_scholarship_rule_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    notice_id: Mapped[int] = mapped_column(
        ForeignKey("scholarship_notices.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("canonical_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    scholarship_name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(50), default="v1", nullable=False)
    application_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    application_ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    summary_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qualification_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    provenance_keys_json: Mapped[List[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    status: Mapped[RuleStatus] = mapped_column(
        Enum(RuleStatus, native_enum=False, length=24),
        default=RuleStatus.PUBLISHED,
        nullable=False,
    )

    notice: Mapped["ScholarshipNotice"] = relationship(back_populates="scholarship_rules")
    document: Mapped[Optional["CanonicalDocument"]] = relationship(back_populates="scholarship_rules")

if TYPE_CHECKING:
    from app.models.document import CanonicalDocument
    from app.models.notice import ScholarshipNotice
