from __future__ import annotations

import re
from datetime import datetime
from typing import Any, List, Optional, Sequence, Tuple

from app.core.time import now_in_seoul
from app.db import session_scope
from app.models import ScholarshipRule
from app.repositories import ScholarshipRuleRepository
from app.schemas import (
    OpenScholarshipListResponse,
    ScholarshipProvenanceAnchorResponse,
    ScholarshipSearchItem,
    ScholarshipSearchResponse,
)

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")


class ScholarshipSearchService:
    """Assemble scholarship search and open-list responses from stored rules."""

    def list_published_scholarships(
        self,
        *,
        limit: Optional[int] = None,
        reference_time: Optional[datetime] = None,
    ) -> List[ScholarshipSearchItem]:
        """Return published scholarship read models without applying a search query."""

        reference_time = reference_time or now_in_seoul()
        with session_scope() as session:
            rules = ScholarshipRuleRepository(session).list_published_rules()
            items = [self._build_item(rule, reference_time) for rule in rules]

        items = sorted(items, key=self._published_sort_key)
        if limit is not None:
            items = items[:limit]
        return items

    def search(
        self,
        query: str,
        *,
        open_only: bool = False,
        limit: int = 10,
        reference_time: Optional[datetime] = None,
    ) -> ScholarshipSearchResponse:
        """Search published scholarship rules with lexical scoring and provenance."""

        reference_time = reference_time or now_in_seoul()
        normalized_query = self._normalize_text(query)
        if not normalized_query:
            return ScholarshipSearchResponse(query=query, open_only=open_only, count=0, items=[])

        tokens = self._extract_tokens(query)
        with session_scope() as session:
            rules = ScholarshipRuleRepository(session).list_published_rules()
            items = self._search_rules(rules, normalized_query, tokens, reference_time, open_only)

        items = sorted(items, key=self._search_sort_key)[:limit]
        return ScholarshipSearchResponse(
            query=query,
            open_only=open_only,
            count=len(items),
            items=items,
        )

    def list_open_scholarships(
        self,
        *,
        limit: int = 10,
        reference_time: Optional[datetime] = None,
    ) -> OpenScholarshipListResponse:
        """Return rules whose application window is currently open."""

        reference_time = reference_time or now_in_seoul()
        items = [
            item
            for item in self.list_published_scholarships(reference_time=reference_time)
            if item.application_status == "open"
        ]
        items = sorted(items, key=self._open_list_sort_key)[:limit]
        return OpenScholarshipListResponse(
            reference_time=reference_time,
            count=len(items),
            items=items,
        )

    def _search_rules(
        self,
        rules: Sequence[ScholarshipRule],
        normalized_query: str,
        tokens: Sequence[str],
        reference_time: datetime,
        open_only: bool,
    ) -> List[ScholarshipSearchItem]:
        """Score loaded rules and keep only matching candidates."""

        matched_items: List[ScholarshipSearchItem] = []
        for rule in rules:
            item = self._build_item(rule, reference_time)
            if open_only and item.application_status != "open":
                continue

            score, matched_fields = self._score_item(item, normalized_query, tokens)
            if score <= 0:
                continue

            item.score = round(score, 2)
            item.matched_fields = matched_fields
            matched_items.append(item)

        return matched_items

    def _build_item(
        self,
        rule: ScholarshipRule,
        reference_time: datetime,
    ) -> ScholarshipSearchItem:
        """Build one API response item from a rule and its related entities."""

        application_started_at, application_ended_at = self._resolve_application_window(rule)
        application_started_at = self._coerce_datetime(application_started_at, reference_time)
        application_ended_at = self._coerce_datetime(application_ended_at, reference_time)
        published_at = self._coerce_datetime(rule.notice.published_at, reference_time) or reference_time
        return ScholarshipSearchItem(
            notice_id=rule.notice_id,
            rule_id=rule.id,
            scholarship_name=rule.scholarship_name,
            notice_title=rule.notice.title,
            source_board=rule.notice.source_board,
            department_name=rule.notice.department_name,
            notice_url=rule.notice.notice_url,
            published_at=published_at,
            application_started_at=application_started_at,
            application_ended_at=application_ended_at,
            application_status=self._compute_application_status(
                application_started_at,
                application_ended_at,
                reference_time,
            ),
            summary_text=rule.summary_text or rule.notice.summary,
            qualification=rule.qualification_json,
            provenance=self._build_provenance(rule),
        )

    def _resolve_application_window(
        self,
        rule: ScholarshipRule,
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Prefer rule-level dates and fall back to collected notice dates."""

        return (
            rule.application_started_at or rule.notice.application_started_at,
            rule.application_ended_at or rule.notice.application_ended_at,
        )

    def _compute_application_status(
        self,
        application_started_at: Optional[datetime],
        application_ended_at: Optional[datetime],
        reference_time: datetime,
    ) -> str:
        """Derive a coarse application status used by search ordering and filters."""

        if application_started_at and reference_time < application_started_at:
            return "upcoming"
        if application_ended_at and reference_time > application_ended_at:
            return "closed"
        if application_started_at is None and application_ended_at is None:
            return "unknown"
        return "open"

    def _coerce_datetime(
        self,
        value: Optional[datetime],
        reference_time: datetime,
    ) -> Optional[datetime]:
        """Attach the reference timezone to naive datetimes returned by SQLite."""

        if value is None:
            return None
        if value.tzinfo is not None:
            return value
        return value.replace(tzinfo=reference_time.tzinfo)

    def _build_provenance(self, rule: ScholarshipRule) -> List[ScholarshipProvenanceAnchorResponse]:
        """Expose only the anchors referenced by the extracted rule."""

        if rule.document is None:
            return []

        anchors_by_key = {
            anchor.anchor_key: anchor for anchor in rule.document.provenance_anchors
        }
        ordered_anchors: List[ScholarshipProvenanceAnchorResponse] = []
        for anchor_key in rule.provenance_keys_json:
            anchor = anchors_by_key.get(anchor_key)
            if anchor is None:
                continue
            ordered_anchors.append(
                ScholarshipProvenanceAnchorResponse(
                    anchor_key=anchor.anchor_key,
                    block_id=anchor.block_id,
                    quote_text=anchor.quote_text,
                    page_number=anchor.page_number,
                    source_label=rule.document.source_label,
                    document_kind=rule.document.document_kind,
                    locator=anchor.locator_json,
                )
            )
        return ordered_anchors

    def _score_item(
        self,
        item: ScholarshipSearchItem,
        normalized_query: str,
        tokens: Sequence[str],
    ) -> Tuple[float, List[str]]:
        """Combine title, rule, and provenance matches into one score."""

        document_text = ""
        if item.provenance:
            document_text = " ".join(anchor.quote_text for anchor in item.provenance)

        search_fields = [
            ("scholarship_name", item.scholarship_name, 6.0),
            ("notice_title", item.notice_title, 4.0),
            ("summary_text", item.summary_text or "", 3.0),
            ("qualification", self._flatten_value(item.qualification), 4.0),
            ("provenance", document_text, 2.5),
        ]

        score = 0.0
        matched_fields = set()
        for field_name, value, field_weight in search_fields:
            field_score = self._score_text(value, normalized_query, tokens, field_weight)
            if field_score <= 0:
                continue
            score += field_score
            matched_fields.add(field_name)

        if item.application_status == "open":
            score += 1.0
        elif item.application_status == "upcoming":
            score += 0.25

        return score, sorted(matched_fields)

    def _score_text(
        self,
        value: str,
        normalized_query: str,
        tokens: Sequence[str],
        field_weight: float,
    ) -> float:
        """Score one searchable text field against a normalized query and tokens."""

        normalized_value = self._normalize_text(value)
        if not normalized_value:
            return 0.0

        score = 0.0
        if normalized_query in normalized_value:
            score += field_weight

        token_hits = sum(1 for token in tokens if token in normalized_value)
        if token_hits:
            score += min(token_hits, 4) * (field_weight * 0.45)

        return score

    def _extract_tokens(self, query: str) -> List[str]:
        """Split a query into searchable lexical tokens."""

        tokens = {
            self._normalize_text(match.group(0))
            for match in TOKEN_PATTERN.finditer(query)
            if len(match.group(0).strip()) >= 2
        }
        return sorted(token for token in tokens if token)

    def _normalize_text(self, value: str) -> str:
        """Normalize text for simple deterministic substring matching."""

        collapsed = " ".join(value.lower().split())
        return collapsed.strip()

    def _flatten_value(self, value: Any) -> str:
        """Flatten nested qualification payloads into one searchable text blob."""

        if isinstance(value, dict):
            return " ".join(
                f"{key} {self._flatten_value(nested_value)}"
                for key, nested_value in value.items()
            )
        if isinstance(value, list):
            return " ".join(self._flatten_value(item) for item in value)
        return str(value)

    def _search_sort_key(self, item: ScholarshipSearchItem) -> Tuple[float, int, float]:
        """Prefer higher score, then more actionable status, then newer notices."""

        return (
            -item.score,
            self._application_status_rank(item.application_status),
            -item.published_at.timestamp(),
        )

    def _open_list_sort_key(self, item: ScholarshipSearchItem) -> Tuple[bool, datetime, float]:
        """Prefer scholarships that close sooner while keeping recent notices first."""

        fallback_end = datetime.max.replace(tzinfo=item.published_at.tzinfo)
        return (
            item.application_ended_at is None,
            item.application_ended_at or fallback_end,
            -item.published_at.timestamp(),
        )

    def _application_status_rank(self, status: str) -> int:
        """Convert status text into a stable search ordering priority."""

        return {
            "open": 0,
            "upcoming": 1,
            "unknown": 2,
            "closed": 3,
        }.get(status, 99)

    def _published_sort_key(self, item: ScholarshipSearchItem) -> Tuple[int, float]:
        """Prefer actionable notices first while keeping recently published rules near the top."""

        return (
            self._application_status_rank(item.application_status),
            -item.published_at.timestamp(),
        )
