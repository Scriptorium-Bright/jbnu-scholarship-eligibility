from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, Optional, Protocol, runtime_checkable

from app.models import RuleStatus


@dataclass(frozen=True)
class ExtractedProvenanceAnchor:
    """Structured provenance candidate produced by any extraction backend."""

    document_id: int
    anchor_key: str
    block_id: str
    quote_text: str
    page_number: Optional[int] = None
    locator: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractedScholarshipRule:
    """Structured scholarship rule contract shared by heuristic and LLM extractors."""

    scholarship_name: str
    qualification: Dict[str, object]
    provenance_anchors: list[ExtractedProvenanceAnchor]
    source_document_id: Optional[int]
    application_started_at: Optional[datetime]
    application_ended_at: Optional[datetime]
    summary_text: Optional[str]
    status: RuleStatus = RuleStatus.PUBLISHED


@runtime_checkable
class StructuredRuleExtractor(Protocol):
    """Common extraction contract that phase 8 implementations must satisfy."""

    def extract_notice_rule(
        self,
        notice_title: str,
        canonical_documents: Iterable[object],
        application_started_at: Optional[datetime] = None,
        application_ended_at: Optional[datetime] = None,
        fallback_summary: Optional[str] = None,
    ) -> ExtractedScholarshipRule:
        """Extract one structured scholarship rule from canonical notice documents."""

