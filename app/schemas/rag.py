from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from app.models.common import DocumentKind
from app.schemas.domain import StrictSchema


class ScholarshipRagChunkUpsert(StrictSchema):
    """RAG corpus row를 삽입하거나 갱신할 때 사용하는 생성 전용 DTO입니다."""

    notice_id: int
    document_id: int
    rule_id: Optional[int] = None
    chunk_key: str
    block_id: str
    chunk_text: str
    search_text: str
    scholarship_name: Optional[str] = None
    source_label: str
    document_kind: DocumentKind
    page_number: Optional[int] = None
    anchor_keys: List[str] = Field(default_factory=list)
    embedding_vector: List[float] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RagRetrievalCandidate(StrictSchema):
    """keyword/vector retrieval이 반환하는 내부 후보 DTO입니다."""

    chunk_id: int
    chunk_key: str
    notice_id: int
    document_id: int
    rule_id: Optional[int] = None
    block_id: str
    chunk_text: str
    search_text: str
    scholarship_name: Optional[str] = None
    source_label: str
    document_kind: DocumentKind
    page_number: Optional[int] = None
    anchor_keys: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0
    retrieval_kind: str


class RagRetrievedChunk(StrictSchema):
    """hybrid retrieval과 dedup을 거친 뒤 generation에 넘길 최종 근거 DTO입니다."""

    chunk_id: int
    chunk_key: str
    notice_id: int
    document_id: int
    rule_id: Optional[int] = None
    block_id: str
    chunk_text: str
    scholarship_name: Optional[str] = None
    source_label: str
    document_kind: DocumentKind
    page_number: Optional[int] = None
    anchor_keys: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    keyword_score: float = 0.0
    vector_score: float = 0.0
    final_score: float = 0.0
    matched_retrieval_kinds: List[str] = Field(default_factory=list)


class RagRetrievalResult(StrictSchema):
    """retrieve 단계 전체 결과와 fallback 상태를 담는 DTO입니다."""

    query: str
    count: int
    has_evidence: bool
    retrieval_mode: str
    keyword_fallback_used: bool = False
    failure_reason: Optional[str] = None
    chunks: List[RagRetrievedChunk] = Field(default_factory=list)


class RagPromptContext(StrictSchema):
    """retrieved chunk를 prompt budget 안에서 직렬화한 augment 결과 DTO입니다."""

    query: str
    prompt_text: str
    selected_chunks: List[RagRetrievedChunk] = Field(default_factory=list)
    truncated: bool
    has_evidence: bool


class GroundedAnswerOutput(StrictSchema):
    """LLM answer provider가 반환하는 최소 답변 payload입니다."""

    answer_text: str = Field(min_length=1)


class ScholarshipRagQuestionRequest(StrictSchema):
    """RAG 질의응답 endpoint가 입력받는 질문 payload입니다."""

    question: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=10)


class ScholarshipRagCitationResponse(StrictSchema):
    """grounded answer와 함께 노출할 citation 응답 DTO입니다."""

    chunk_id: int
    chunk_key: str
    notice_id: int
    document_id: int
    rule_id: Optional[int] = None
    block_id: str
    quote_text: str
    scholarship_name: Optional[str] = None
    source_label: str
    document_kind: DocumentKind
    page_number: Optional[int] = None
    anchor_keys: List[str] = Field(default_factory=list)
    matched_retrieval_kinds: List[str] = Field(default_factory=list)
    final_score: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScholarshipRagAnswerResponse(StrictSchema):
    """question/answer API가 반환하는 grounded answer 응답 DTO입니다."""

    question: str
    answer_text: str
    answer_mode: Literal["grounded", "no_evidence", "guardrail"]
    has_evidence: bool
    retrieval_mode: str
    prompt_truncated: bool = False
    keyword_fallback_used: bool = False
    failure_reason: Optional[str] = None
    recommended_endpoint: Optional[str] = None
    citations: List[ScholarshipRagCitationResponse] = Field(default_factory=list)
