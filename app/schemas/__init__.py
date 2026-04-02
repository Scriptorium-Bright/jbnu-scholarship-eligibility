"""스키마 패키지입니다."""

from app.schemas.domain import (
    CanonicalBlock,
    CanonicalDocumentUpsert,
    NoticeAttachmentUpsert,
    ProvenanceAnchorCreate,
    ScholarshipNoticeUpsert,
    ScholarshipRuleCreate,
)
from app.schemas.eligibility import (
    EligibilityCheckRequest,
    EligibilityConditionCheck,
    ScholarshipEligibilityItem,
    ScholarshipEligibilityResponse,
    StudentProfile,
)
from app.schemas.llm_extraction import (
    LLMExtractionEvidence,
    LLMExtractionQualification,
    LLMExtractionResponse,
)
from app.schemas.rag import (
    RagPromptContext,
    RagRetrievalCandidate,
    RagRetrievalResult,
    RagRetrievedChunk,
    ScholarshipRagChunkUpsert,
)
from app.schemas.search import (
    OpenScholarshipListResponse,
    ScholarshipProvenanceAnchorResponse,
    ScholarshipSearchItem,
    ScholarshipSearchResponse,
)

__all__ = [
    "CanonicalBlock",
    "CanonicalDocumentUpsert",
    "EligibilityCheckRequest",
    "EligibilityConditionCheck",
    "LLMExtractionEvidence",
    "LLMExtractionQualification",
    "LLMExtractionResponse",
    "NoticeAttachmentUpsert",
    "OpenScholarshipListResponse",
    "ProvenanceAnchorCreate",
    "RagPromptContext",
    "RagRetrievalCandidate",
    "RagRetrievalResult",
    "RagRetrievedChunk",
    "ScholarshipEligibilityItem",
    "ScholarshipEligibilityResponse",
    "ScholarshipProvenanceAnchorResponse",
    "ScholarshipRagChunkUpsert",
    "ScholarshipNoticeUpsert",
    "ScholarshipRuleCreate",
    "ScholarshipSearchItem",
    "ScholarshipSearchResponse",
    "StudentProfile",
]
