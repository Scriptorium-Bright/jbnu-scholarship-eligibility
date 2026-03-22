from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence, Tuple

from app.core.time import now_in_seoul
from app.schemas import (
    EligibilityConditionCheck,
    ScholarshipEligibilityItem,
    ScholarshipEligibilityResponse,
    ScholarshipSearchItem,
    StudentProfile,
)
from app.services.search import ScholarshipSearchService


class EligibilityDecisionEngine:
    """Compare one scholarship rule read model against one student profile."""

    def evaluate(
        self,
        item: ScholarshipSearchItem,
        profile: StudentProfile,
    ) -> Tuple[str, List[EligibilityConditionCheck], List[str], List[str]]:
        """Return a deterministic decision with detailed condition checks."""

        condition_checks: List[EligibilityConditionCheck] = []
        missing_fields: List[str] = []
        unmet_conditions: List[str] = []
        qualification = item.qualification

        gpa_min = qualification.get("gpa_min")
        if gpa_min is not None:
            if profile.gpa is None:
                missing_fields.append("gpa")
                condition_checks.append(
                    EligibilityConditionCheck(
                        field_name="gpa",
                        status="missing",
                        expected_value=">= {0:.2f}".format(float(gpa_min)),
                        actual_value=None,
                        reason="학점 정보가 없어 최소 평점 기준을 확인할 수 없습니다.",
                    )
                )
            elif float(profile.gpa) >= float(gpa_min):
                condition_checks.append(
                    EligibilityConditionCheck(
                        field_name="gpa",
                        status="passed",
                        expected_value=">= {0:.2f}".format(float(gpa_min)),
                        actual_value="{0:.2f}".format(float(profile.gpa)),
                        reason="최소 평점 기준을 충족합니다.",
                    )
                )
            else:
                reason = "평점 {0:.2f}가 최소 기준 {1:.2f}보다 낮습니다.".format(
                    float(profile.gpa),
                    float(gpa_min),
                )
                unmet_conditions.append(reason)
                condition_checks.append(
                    EligibilityConditionCheck(
                        field_name="gpa",
                        status="failed",
                        expected_value=">= {0:.2f}".format(float(gpa_min)),
                        actual_value="{0:.2f}".format(float(profile.gpa)),
                        reason=reason,
                    )
                )

        income_bracket_max = qualification.get("income_bracket_max")
        if income_bracket_max is not None:
            if profile.income_bracket is None:
                missing_fields.append("income_bracket")
                condition_checks.append(
                    EligibilityConditionCheck(
                        field_name="income_bracket",
                        status="missing",
                        expected_value="<= {0}".format(int(income_bracket_max)),
                        actual_value=None,
                        reason="소득분위 정보가 없어 소득 기준을 확인할 수 없습니다.",
                    )
                )
            elif int(profile.income_bracket) <= int(income_bracket_max):
                condition_checks.append(
                    EligibilityConditionCheck(
                        field_name="income_bracket",
                        status="passed",
                        expected_value="<= {0}".format(int(income_bracket_max)),
                        actual_value=str(int(profile.income_bracket)),
                        reason="소득분위 기준을 충족합니다.",
                    )
                )
            else:
                reason = "소득분위 {0}가 허용 기준 {1}보다 높습니다.".format(
                    int(profile.income_bracket),
                    int(income_bracket_max),
                )
                unmet_conditions.append(reason)
                condition_checks.append(
                    EligibilityConditionCheck(
                        field_name="income_bracket",
                        status="failed",
                        expected_value="<= {0}".format(int(income_bracket_max)),
                        actual_value=str(int(profile.income_bracket)),
                        reason=reason,
                    )
                )

        grade_levels = qualification.get("grade_levels")
        if grade_levels:
            normalized_levels = sorted(int(level) for level in grade_levels)
            if profile.grade_level is None:
                missing_fields.append("grade_level")
                condition_checks.append(
                    EligibilityConditionCheck(
                        field_name="grade_level",
                        status="missing",
                        expected_value=", ".join(str(level) for level in normalized_levels),
                        actual_value=None,
                        reason="학년 정보가 없어 대상 학년 여부를 확인할 수 없습니다.",
                    )
                )
            elif int(profile.grade_level) in normalized_levels:
                condition_checks.append(
                    EligibilityConditionCheck(
                        field_name="grade_level",
                        status="passed",
                        expected_value=", ".join(str(level) for level in normalized_levels),
                        actual_value=str(int(profile.grade_level)),
                        reason="대상 학년 기준을 충족합니다.",
                    )
                )
            else:
                reason = "학년 {0}는 허용 학년 {1}에 포함되지 않습니다.".format(
                    int(profile.grade_level),
                    ", ".join(str(level) for level in normalized_levels),
                )
                unmet_conditions.append(reason)
                condition_checks.append(
                    EligibilityConditionCheck(
                        field_name="grade_level",
                        status="failed",
                        expected_value=", ".join(str(level) for level in normalized_levels),
                        actual_value=str(int(profile.grade_level)),
                        reason=reason,
                    )
                )

        enrollment_statuses = qualification.get("enrollment_status")
        if enrollment_statuses:
            normalized_statuses = [str(status).strip() for status in enrollment_statuses]
            normalized_profile_status = (
                str(profile.enrollment_status).strip() if profile.enrollment_status is not None else None
            )
            if normalized_profile_status is None:
                missing_fields.append("enrollment_status")
                condition_checks.append(
                    EligibilityConditionCheck(
                        field_name="enrollment_status",
                        status="missing",
                        expected_value=", ".join(normalized_statuses),
                        actual_value=None,
                        reason="학적 상태 정보가 없어 대상 여부를 확인할 수 없습니다.",
                    )
                )
            elif normalized_profile_status in normalized_statuses:
                condition_checks.append(
                    EligibilityConditionCheck(
                        field_name="enrollment_status",
                        status="passed",
                        expected_value=", ".join(normalized_statuses),
                        actual_value=normalized_profile_status,
                        reason="학적 상태 기준을 충족합니다.",
                    )
                )
            else:
                reason = "학적 상태 {0}는 허용 상태 {1}에 포함되지 않습니다.".format(
                    normalized_profile_status,
                    ", ".join(normalized_statuses),
                )
                unmet_conditions.append(reason)
                condition_checks.append(
                    EligibilityConditionCheck(
                        field_name="enrollment_status",
                        status="failed",
                        expected_value=", ".join(normalized_statuses),
                        actual_value=normalized_profile_status,
                        reason=reason,
                    )
                )

        decision = self._decide(
            application_status=item.application_status,
            missing_fields=missing_fields,
            unmet_conditions=unmet_conditions,
        )
        return decision, condition_checks, sorted(set(missing_fields)), unmet_conditions

    def _decide(
        self,
        *,
        application_status: str,
        missing_fields: Sequence[str],
        unmet_conditions: Sequence[str],
    ) -> str:
        """Reduce window status and condition results into one final decision."""

        if application_status == "closed":
            return "expired"
        if unmet_conditions:
            return "ineligible"
        if missing_fields or application_status == "unknown":
            return "insufficient_info"
        return "eligible"


class EligibilityAnswerBuilder:
    """Build a short deterministic explanation for one eligibility decision."""

    def build(
        self,
        item: ScholarshipSearchItem,
        decision: str,
        missing_fields: Sequence[str],
        unmet_conditions: Sequence[str],
    ) -> str:
        """Translate one decision into a concise human-readable explanation."""

        if decision == "eligible":
            if item.application_status == "upcoming":
                return "지원 자격을 충족하지만 아직 신청 시작 전입니다."
            return "현재 확인 가능한 기준으로는 지원 자격을 충족합니다."

        if decision == "expired":
            return "신청 기간이 종료되어 현재는 지원할 수 없습니다."

        if decision == "ineligible":
            return "지원 조건을 충족하지 않습니다: {0}".format(" / ".join(unmet_conditions))

        if missing_fields:
            translated = ", ".join(self._translate_field_name(field_name) for field_name in missing_fields)
            return "{0} 정보가 없어 지원 가능 여부를 확정할 수 없습니다.".format(translated)

        return "신청 기간 정보가 부족해 지원 가능 여부를 확정할 수 없습니다."

    def _translate_field_name(self, field_name: str) -> str:
        """Map internal profile field names to concise Korean labels."""

        return {
            "gpa": "평점",
            "income_bracket": "소득분위",
            "grade_level": "학년",
            "enrollment_status": "학적 상태",
        }.get(field_name, field_name)


class ScholarshipEligibilityService:
    """Evaluate a student profile against scholarship rules and build answers."""

    def __init__(
        self,
        *,
        search_service: Optional[ScholarshipSearchService] = None,
        decision_engine: Optional[EligibilityDecisionEngine] = None,
        answer_builder: Optional[EligibilityAnswerBuilder] = None,
    ):
        self.search_service = search_service or ScholarshipSearchService()
        self.decision_engine = decision_engine or EligibilityDecisionEngine()
        self.answer_builder = answer_builder or EligibilityAnswerBuilder()

    def evaluate_profile(
        self,
        profile: StudentProfile,
        *,
        query: Optional[str] = None,
        limit: int = 10,
        reference_time: Optional[datetime] = None,
    ) -> ScholarshipEligibilityResponse:
        """Return eligibility decisions for scholarships matched against one profile."""

        reference_time = reference_time or now_in_seoul()
        candidate_items = self._load_candidate_items(
            query=query,
            reference_time=reference_time,
        )

        evaluated_items = [
            self._evaluate_item(item, profile)
            for item in candidate_items
        ]
        evaluated_items = sorted(evaluated_items, key=self._decision_sort_key)[:limit]

        return ScholarshipEligibilityResponse(
            profile=profile,
            query=query,
            reference_time=reference_time,
            count=len(evaluated_items),
            items=evaluated_items,
        )

    def _load_candidate_items(
        self,
        *,
        query: Optional[str],
        reference_time: datetime,
    ) -> List[ScholarshipSearchItem]:
        """Load candidate scholarships from either the search API path or all published rules."""

        if query:
            return self.search_service.search(
                query,
                reference_time=reference_time,
                limit=50,
            ).items
        return self.search_service.list_published_scholarships(reference_time=reference_time)

    def _evaluate_item(
        self,
        item: ScholarshipSearchItem,
        profile: StudentProfile,
    ) -> ScholarshipEligibilityItem:
        """Attach decision, explanation, and condition diagnostics to one scholarship item."""

        decision, condition_checks, missing_fields, unmet_conditions = self.decision_engine.evaluate(
            item,
            profile,
        )
        explanation = self.answer_builder.build(
            item,
            decision,
            missing_fields,
            unmet_conditions,
        )
        required_documents = [
            str(document_name)
            for document_name in item.qualification.get("required_documents", [])
        ]

        return ScholarshipEligibilityItem(
            **item.model_dump(),
            decision=decision,
            explanation=explanation,
            missing_fields=list(missing_fields),
            unmet_conditions=list(unmet_conditions),
            required_documents=required_documents,
            condition_checks=condition_checks,
        )

    def _decision_sort_key(self, item: ScholarshipEligibilityItem) -> Tuple[int, int, float, float]:
        """Prefer actionable decisions first while keeping stronger matches near the top."""

        return (
            self._decision_rank(item.decision),
            self.search_service._application_status_rank(item.application_status),
            -item.score,
            -item.published_at.timestamp(),
        )

    def _decision_rank(self, decision: str) -> int:
        """Convert decision text into a stable response ordering priority."""

        return {
            "eligible": 0,
            "insufficient_info": 1,
            "ineligible": 2,
            "expired": 3,
        }.get(decision, 99)
