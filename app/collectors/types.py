from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class CollectorSource:
    """Configuration for one external notice board."""

    source_board: str
    list_url: str
    list_parser_kind: str
    default_department_name: Optional[str] = None
    include_keywords: Tuple[str, ...] = ("장학",)


@dataclass(frozen=True)
class CollectedAttachment:
    """Attachment metadata extracted from a detail page."""

    source_url: str
    file_name: str
    media_type: str


@dataclass(frozen=True)
class CollectedNoticeSummary:
    """List-page summary used to decide which detail pages to fetch."""

    source_notice_id: str
    title: str
    notice_url: str
    published_at: datetime
    department_name: Optional[str] = None
    category: Optional[str] = None


@dataclass(frozen=True)
class CollectedNotice:
    """Fully collected notice payload ready for persistence."""

    source_notice_id: str
    title: str
    notice_url: str
    published_at: datetime
    department_name: Optional[str]
    summary: Optional[str]
    application_started_at: Optional[datetime]
    application_ended_at: Optional[datetime]
    attachments: List[CollectedAttachment] = field(default_factory=list)


@dataclass(frozen=True)
class CollectionRunResult:
    """Collector run summary returned to tests or future schedulers."""

    source_board: str
    fetched_count: int
    matched_count: int
    persisted_count: int
    persisted_notice_ids: Tuple[int, ...] = ()
