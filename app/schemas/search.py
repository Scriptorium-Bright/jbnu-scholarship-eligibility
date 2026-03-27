from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from app.models.common import DocumentKind
from app.schemas.domain import StrictSchema


class ScholarshipProvenanceAnchorResponse(StrictSchema):
    """
    사용자에게 장학 조건의 '도출 근거'를 육안으로 납득시킬 때 쓰이는 API 응답 전용 출처 파편화 모델입니다.
    해당 규칙이 파생된 실제 원문 문구(Quote)와 페이지 번호, 안내 텍스트 등의 하이라이팅 정보를 노출합니다.
    """

    anchor_key: str
    block_id: str
    quote_text: str
    page_number: Optional[int] = None
    source_label: Optional[str] = None
    document_kind: Optional[DocumentKind] = None
    locator: Dict[str, Any] = Field(default_factory=dict)


class ScholarshipSearchItem(StrictSchema):
    """
    장학 게시글 정보와 룰(Rule) 정보, 그리고 연결된 출처들까지 한 줄의 응답으로 섞고 변환시킨 통합 조회 읽기 모델(Read Model)입니다.
    날짜 비교를 통한 활성 상태값 및 스코어 랭킹 등 복합 계산 결과가 프론트엔드가 편하도록 모두 미리 세팅됩니다.
    """

    notice_id: int
    rule_id: int
    scholarship_name: str
    notice_title: str
    source_board: str
    department_name: Optional[str] = None
    notice_url: str
    published_at: datetime
    application_started_at: Optional[datetime] = None
    application_ended_at: Optional[datetime] = None
    application_status: str
    summary_text: Optional[str] = None
    qualification: Dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0
    matched_fields: List[str] = Field(default_factory=list)
    provenance: List[ScholarshipProvenanceAnchorResponse] = Field(default_factory=list)


class ScholarshipSearchResponse(StrictSchema):
    """
    검색 화면 라우터가 입력 문장(Query)에 따라 필터링과 스코어링을 거친 응답 객체들을 목록으로 모아 내려주는 DTO입니다.
    단순 조회부터 텍스트 기반 매치업 랭킹까지 모두 이 형태의 통일된 리스폰스로 서빙됩니다.
    """

    query: str
    open_only: bool = False
    count: int
    items: List[ScholarshipSearchItem]


class OpenScholarshipListResponse(StrictSchema):
    """
    현재 지원 기간이 열려 있는(Open) 장학 고속 조회용 API(배너/추천 섹션 등)가 클라이언트에게 건네는 전용 응답 객체입니다.
    서버의 측정 기준 시간(Reference Time) 정보를 포함해 클라이언트 시간 차이로 발생하는 오해를 차단합니다.
    """

    reference_time: datetime
    count: int
    items: List[ScholarshipSearchItem]
