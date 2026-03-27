from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import Field

from app.schemas.domain import StrictSchema
from app.schemas.search import ScholarshipSearchItem


class StudentProfile(StrictSchema):
    """
    결정론적 판정 엔진(Eligibility Engine)이 장학금 조건을 검사하기 위해 참조하는 핵심 유저 프로필 스키마입니다.
    사용자 화면 등에서 넘겨받은 학적 상태, 학년, 학점, 소득분위 속성을 정제된 타입으로 모델링합니다.
    """

    grade_level: Optional[int] = Field(default=None, ge=1, le=8)
    enrollment_status: Optional[str] = None
    gpa: Optional[float] = Field(default=None, ge=0.0, le=4.5)
    income_bracket: Optional[int] = Field(default=None, ge=0, le=10)


class EligibilityCheckRequest(StrictSchema):
    """
    특정 학생의 스펙(StudentProfile)으로 전체 장학금 규칙 중 수혜 가능한 항목들을 심사해달라는 요청 규격(Payload)입니다.
    키워드 검색어와 페이징 리미트 등의 보조 필드를 같이 받아 판정 결과 필터링에 참여할 수 있습니다.
    """

    profile: StudentProfile
    query: Optional[str] = None
    limit: int = Field(default=10, ge=1, le=50)


class EligibilityConditionCheck(StrictSchema):
    """
    장학금 규정 중 단 하나의 단위 조건(예: 소득 3분위 이하)과 내 프로필 데이터가 만났을 때 도출된 비교 결괏값의 기록입니다.
    결과 상태(통과/미달), 기대 수치, 실제 사용자 수치, 그리고 UI에 출력될 상세한 사유(Reason) 메시지를 포함합니다.
    """

    field_name: str
    status: str
    expected_value: str
    actual_value: Optional[str] = None
    reason: str


class ScholarshipEligibilityItem(ScholarshipSearchItem):
    """
    일반적인 장학금 검색 반환 모델 위에, 특정 사용자 기반의 '조건 부합 여부(합격/탈락/미확인)' 관점을 오버라이드한 모델입니다.
    세부 조건별 패스 여부 리스트(Condition Checks)와 추천/반려 사유(Explanation)를 추가로 렌더링할 때 씁니다.
    """

    decision: str
    explanation: str
    missing_fields: List[str] = Field(default_factory=list)
    unmet_conditions: List[str] = Field(default_factory=list)
    required_documents: List[str] = Field(default_factory=list)
    condition_checks: List[EligibilityConditionCheck] = Field(default_factory=list)


class ScholarshipEligibilityResponse(StrictSchema):
    """
    적격성 검사 API 라우터가 클라이언트에게 답변하는 최종 JSON 뭉치 스키마입니다.
    심사 대상이 된 원본 프로필, 기준 평가 시간, 그리고 심사를 통과했거나 관련 있는 항목 목록 등을 포함합니다.
    """

    profile: StudentProfile
    query: Optional[str] = None
    reference_time: datetime
    count: int
    items: List[ScholarshipEligibilityItem]
