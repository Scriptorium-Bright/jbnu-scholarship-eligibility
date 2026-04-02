from __future__ import annotations

from typing import Any, Dict, List, Optional

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
