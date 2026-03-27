from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.common import DocumentKind, RuleStatus


class StrictSchema(BaseModel):
    """
    정의되지 않은 스키마 속성값이 들어올 경우(Extra Fields) Pydantic 레벨에서 가차없이 에러를 뱉게 하여 오타나 페이로드 오염을 방지합니다.
    모든 도메인 핵심 스키마들이 공통으로 상속받는 데이터 파이프라인의 문지기 모델입니다.
    """

    model_config = ConfigDict(extra="forbid")


class CanonicalBlock(StrictSchema):
    """
    정규화 문서 본문을 형성하는 최소 단위의 텍스트 한 문단(Block)에 대한 Pydantic 페이로드 스키마입니다.
    어떤 태그(h1, p, li 등)에서 파생되었는지, 원문 몇 페이지에 존재하는지 등의 추가 메타데이터도 딕셔너리로 품을 수 있습니다.
    """

    block_id: str
    block_type: str = "paragraph"
    text: str
    page_number: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NoticeAttachmentUpsert(StrictSchema):
    """
    데이터베이스 레포지토리에 특정 첨부파일 레코드를 삽입(Insert) 혹은 갱신(Update)하고자 할 때 사용하는 중간 데이터 전송 객체(DTO)입니다.
    어플리케이션이 ORM에 종속되지 않고 순수 파이썬 타입만으로 데이터를 주고받게 만듭니다.
    """

    source_url: str
    file_name: str
    media_type: str
    raw_storage_path: Optional[str] = None
    checksum: Optional[str] = None


class ScholarshipNoticeUpsert(StrictSchema):
    """
    1차 데이터 수집기(Collector)에 의해 공지 게시판의 메타정보가 추출 완료된 시점에 만들어지는 등록 전용 데이터 컨테이너(DTO)입니다.
    새로운 장학금 글이 DB에 세이브(Upsert)되는 순간의 무결성 룰이 이 스키마 객체에 정의됩니다.
    """

    source_board: str
    source_notice_id: str
    title: str
    notice_url: str
    published_at: datetime
    department_name: Optional[str] = None
    application_started_at: Optional[datetime] = None
    application_ended_at: Optional[datetime] = None
    summary: Optional[str] = None
    raw_html_path: Optional[str] = None


class CanonicalDocumentUpsert(StrictSchema):
    """
    HTML 본문 파서 및 첨부파일 텍스트 추출기 등 Normalizer 파이프라인을 거친 후 DB에 전달하기 위해 조립되는 중간 산출물 지갑(DTO)입니다.
    안쪽에 다발의 CanonicalBlock 객체들을 품고 있으며, 이는 JSON 형태로 직렬화되어 한 번에 모델에 들어갑니다.
    """

    notice_id: int
    attachment_id: Optional[int] = None
    document_kind: DocumentKind
    source_label: str
    canonical_text: str
    blocks: List[CanonicalBlock]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProvenanceAnchorCreate(StrictSchema):
    """
    장학금 규칙 추출기 엔진이 자신이 뽑아낸 특정 규칙(예: 학점 3.0)의 출처 문장(Quote Text) 정보를 남기기 위해 인스턴스화 하는 생성용 DTO입니다.
    근거 영역의 위치 식별 키와 로케이터 좌표값 등을 안전하게 캐스팅해 전달합니다.
    """

    document_id: int
    anchor_key: str
    block_id: str
    quote_text: str
    page_number: Optional[int] = None
    locator: Dict[str, Any] = Field(default_factory=dict)


class ScholarshipRuleCreate(StrictSchema):
    """
    장학 조건 룰 파이프라인의 완성 단계에서 도출되는 '단일 조건' 덩어리에 대응하는 Pydantic 생성 전용 DTO 스키마 모델입니다.
    내부적으로 생성된 고유 Qualification (JSON) 자격 항목과 연관 출처 식별자(Provenance Keys) 집합을 담고 있습니다.
    """

    notice_id: int
    document_id: Optional[int] = None
    scholarship_name: str
    rule_version: str = "v1"
    application_started_at: Optional[datetime] = None
    application_ended_at: Optional[datetime] = None
    summary_text: Optional[str] = None
    qualification: Dict[str, Any] = Field(default_factory=dict)
    provenance_keys: List[str] = Field(default_factory=list)
    status: RuleStatus = RuleStatus.PUBLISHED
