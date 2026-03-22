from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import Field

from app.schemas.domain import StrictSchema
from app.schemas.search import ScholarshipSearchItem


class StudentProfile(StrictSchema):
    """Student attributes used by the deterministic eligibility engine."""

    grade_level: Optional[int] = Field(default=None, ge=1, le=8)
    enrollment_status: Optional[str] = None
    gpa: Optional[float] = Field(default=None, ge=0.0, le=4.5)
    income_bracket: Optional[int] = Field(default=None, ge=0, le=10)


class EligibilityCheckRequest(StrictSchema):
    """Request payload for evaluating one student profile against scholarship rules."""

    profile: StudentProfile
    query: Optional[str] = None
    limit: int = Field(default=10, ge=1, le=50)


class EligibilityConditionCheck(StrictSchema):
    """One deterministic comparison between a rule requirement and profile data."""

    field_name: str
    status: str
    expected_value: str
    actual_value: Optional[str] = None
    reason: str


class ScholarshipEligibilityItem(ScholarshipSearchItem):
    """Eligibility decision view that extends the search read model."""

    decision: str
    explanation: str
    missing_fields: List[str] = Field(default_factory=list)
    unmet_conditions: List[str] = Field(default_factory=list)
    required_documents: List[str] = Field(default_factory=list)
    condition_checks: List[EligibilityConditionCheck] = Field(default_factory=list)


class ScholarshipEligibilityResponse(StrictSchema):
    """Response returned by the scholarship eligibility API."""

    profile: StudentProfile
    query: Optional[str] = None
    reference_time: datetime
    count: int
    items: List[ScholarshipEligibilityItem]
