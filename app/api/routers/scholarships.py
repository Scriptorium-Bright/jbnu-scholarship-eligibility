from fastapi import APIRouter, Query

from app.schemas import (
    EligibilityCheckRequest,
    OpenScholarshipListResponse,
    ScholarshipEligibilityResponse,
    ScholarshipRagAnswerResponse,
    ScholarshipRagQuestionRequest,
    ScholarshipSearchResponse,
)
from app.services import (
    ScholarshipEligibilityService,
    ScholarshipRagAnswerService,
    ScholarshipSearchService,
)

router = APIRouter(prefix="/scholarships", tags=["scholarships"])


@router.get("/search", response_model=ScholarshipSearchResponse)
def search_scholarships(
    query: str = Query(..., min_length=1, description="Scholarship keyword query"),
    open_only: bool = False,
    limit: int = Query(10, ge=1, le=50),
) -> ScholarshipSearchResponse:
    """
    검색어에 맞는 장학금 규정과 출처 정보를 조회하여 반환합니다.
    기간이 열려있는 공고만 필터링하거나 결과 개수를 제한할 수 있습니다.
    """

    return ScholarshipSearchService().search(query, open_only=open_only, limit=limit)


@router.get("/open", response_model=OpenScholarshipListResponse)
def list_open_scholarships(
    limit: int = Query(10, ge=1, le=50),
) -> OpenScholarshipListResponse:
    """
    현재 신청 기간이 열려 있는 활성 장학금 목록만 필터링하여 제공합니다.
    마감되지 않은 장학금 공고들을 빠르게 탐색할 때 사용됩니다.
    """

    return ScholarshipSearchService().list_open_scholarships(limit=limit)


@router.post("/eligibility", response_model=ScholarshipEligibilityResponse)
def check_scholarship_eligibility(
    payload: EligibilityCheckRequest,
) -> ScholarshipEligibilityResponse:
    """
    입력된 학생 프로필을 바탕으로 특정/전체 장학금의 신청 자격을 선제척으로 판정합니다.
    각 장학금 항목별로 자격 충족/미달 조건을 상세 분석하여 결과를 응답합니다.
    """

    return ScholarshipEligibilityService().evaluate_profile(
        payload.profile,
        query=payload.query,
        limit=payload.limit,
    )


@router.post("/ask", response_model=ScholarshipRagAnswerResponse)
def ask_scholarship_question(
    payload: ScholarshipRagQuestionRequest,
) -> ScholarshipRagAnswerResponse:
    """
    자연어 질문에 대해 grounded answer와 citation 목록을 반환합니다.
    최종 eligibility 판정 질문은 deterministic eligibility endpoint로 안내합니다.
    """

    return ScholarshipRagAnswerService().answer(payload.question, limit=payload.limit)
