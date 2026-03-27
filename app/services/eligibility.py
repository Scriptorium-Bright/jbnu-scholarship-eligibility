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
        """
        특정 장학금의 자격 조건 체계(Rule)와 개별 학생 프로필을 1:1로 비교 검증합니다.
        상세한 조건 통과/실패 내역을 취합하여 상태 판정과 누락된 정보 항목들을 반환합니다.
        """

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
        """
        조건 불충족, 정보 수집 누락, 기간 마감 등의 다양한 요인들을 논리적으로 종합하여 최종 결과 상태를 도출합니다.
        'eligible', 'ineligible', 'expired', 'insufficient_info' 네 가지 키워드 중 하나를 반환합니다.
        """

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
        """
        내부적으로 판정된 상태 코드와 사유들을 조합하여, 사람이 읽고 이해하기 쉬운 문장 형태(Explanation)를 생성합니다.
        클라이언트용 API 응답에 얹어서 사용자에게 안내 목적으로 표출됩니다.
        """

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
        """
        영문으로 된 프로필 필드명(예: gpa)을 UI 노출에 적합한 한글 명칭(예: 평점)으로 단순 매핑합니다.
        누락 정보 안내 문구 내에 자연스럽게 필드 이름을 삽입하기 위한 번역 헬퍼입니다.
        """

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
        """
        검색어나 전체 목록에서 대상 장학물들을 수집한 후, 학생 프로필과 각각 대조 평가를 수행합니다.
        최종 판정 결과와 출처 데이터들을 우선순위에 맞게 정렬하여 일괄 응답용 객체(Response)로 반환합니다.
        """

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
        self.search_service.populate_provenance(evaluated_items)

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
        """
        검색어가 있을 경우 검색 API 계층을 거치고, 없을 경우 기준 시간에 유효하게 열린 모든 규정 목록을 불러옵니다.
        이후 판정 엔진의 For 루프에 투입될 기초 장학금 후보군(Candidate List)을 준비합니다.
        """

        if query:
            return self.search_service.search(
                query,
                reference_time=reference_time,
                limit=50,
                include_provenance=False,
            ).items
        return self.search_service.list_published_scholarships(
            reference_time=reference_time,
            include_provenance=False,
        )

    def _evaluate_item(
        self,
        item: ScholarshipSearchItem,
        profile: StudentProfile,
    ) -> ScholarshipEligibilityItem:
        """
        단일 검색 항목(Item)에 대해서 실제 프로필 비교 검증 및 안내 문구 생성 로직을 차례대로 적용합니다.
        평가 과정에서 도출된 상세한 Condition Check 값들을 모두 통합한 뒤 DTO 모델로 감싸 반환합니다.
        """

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
        """
        클라이언트 우선순위(지원 가능 > 정보 부족 > 지원 불가 등)와 기간 등을 기준으로 다중 정렬 튜플을 부여합니다.
        최대한 사용자에게 Actionable(행동 가능)한 정보가 상단에 노출되도록 결과를 정렬할 때 쓰입니다.
        """

        return (
            self._decision_rank(item.decision),
            self.search_service._application_status_rank(item.application_status),
            -item.score,
            -item.published_at.timestamp(),
        )

    def _decision_rank(self, decision: str) -> int:
        """
        문자열 형태의 판정 결과를 내부 기준 0부터 시작하는 숫자 랭크 파라미터로 사상(치환)합니다.
        다중 정렬 알고리즘에서 상위에 위치해야 할 항목일수록 더 낮은 숫자를 가지게 설계되어 있습니다.
        """

        return {
            "eligible": 0,
            "insufficient_info": 1,
            "ineligible": 2,
            "expired": 3,
        }.get(decision, 99)
