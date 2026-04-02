from __future__ import annotations

from typing import List, Optional

from app.ai.providers import GroundedAnswerProvider, build_grounded_answer_provider
from app.core.config import Settings, get_settings
from app.schemas import (
    RagPromptContext,
    RagRetrievalResult,
    RagRetrievedChunk,
    ScholarshipRagAnswerResponse,
    ScholarshipRagCitationResponse,
)
from app.services.rag_prompt_builder import RagPromptBuilder
from app.services.rag_retrieval import ScholarshipRagRetrievalService

ELIGIBILITY_ENDPOINT = "/api/v1/scholarships/eligibility"


class ScholarshipRagAnswerService:
    """retrieve -> augment -> generate를 실제 grounded answer로 연결하는 서비스입니다."""

    def __init__(
        self,
        *,
        answer_provider: Optional[GroundedAnswerProvider] = None,
        retrieval_service: Optional[ScholarshipRagRetrievalService] = None,
        prompt_builder: Optional[RagPromptBuilder] = None,
        settings: Optional[Settings] = None,
    ):
        """answer provider, retrieval service, prompt builder를 주입받아 초기화합니다."""

        self._settings = settings or get_settings()
        self._answer_provider = answer_provider or build_grounded_answer_provider(self._settings)
        self._retrieval_service = retrieval_service or ScholarshipRagRetrievalService(
            settings=self._settings
        )
        self._prompt_builder = prompt_builder or RagPromptBuilder(
            max_characters=self._settings.llm_max_context_characters
        )

    def answer(
        self,
        question: str,
        *,
        limit: int = 5,
    ) -> ScholarshipRagAnswerResponse:
        """질문을 retrieval -> prompt assembly -> answer generation으로 연결합니다."""

        normalized_question = self._normalize_question(question)
        if self._enforce_guardrail(normalized_question):
            return self._build_guardrail_response(question=normalized_question)

        retrieval_result = self._retrieval_service.retrieve(normalized_question, limit=limit)
        prompt_context = self._prompt_builder.build_context(
            query=normalized_question,
            retrieved_chunks=retrieval_result.chunks,
        )
        if not retrieval_result.has_evidence or not prompt_context.has_evidence:
            return self._build_no_evidence_response(
                question=normalized_question,
                retrieval_result=retrieval_result,
                prompt_context=prompt_context,
            )

        provider_response = self._answer_provider.generate_answer(
            question=normalized_question,
            prompt_text=prompt_context.prompt_text,
        )
        return ScholarshipRagAnswerResponse(
            question=normalized_question,
            answer_text=provider_response.answer_text,
            answer_mode="grounded",
            has_evidence=True,
            retrieval_mode=retrieval_result.retrieval_mode,
            prompt_truncated=prompt_context.truncated,
            keyword_fallback_used=retrieval_result.keyword_fallback_used,
            failure_reason=retrieval_result.failure_reason,
            citations=self._build_citations(prompt_context.selected_chunks),
        )

    def _build_no_evidence_response(
        self,
        *,
        question: str,
        retrieval_result: RagRetrievalResult,
        prompt_context: RagPromptContext,
    ) -> ScholarshipRagAnswerResponse:
        """retrieval 근거가 부족할 때 안전한 refusal 응답을 만듭니다."""

        return ScholarshipRagAnswerResponse(
            question=question,
            answer_text=(
                "전북대 공식 공지에서 바로 인용할 수 있는 근거를 찾지 못했습니다. "
                "장학금명, 지원자격, 제출서류처럼 질문을 더 구체적으로 입력해 주세요."
            ),
            answer_mode="no_evidence",
            has_evidence=False,
            retrieval_mode=retrieval_result.retrieval_mode,
            prompt_truncated=prompt_context.truncated,
            keyword_fallback_used=retrieval_result.keyword_fallback_used,
            failure_reason=retrieval_result.failure_reason,
            citations=[],
        )

    def _build_guardrail_response(self, *, question: str) -> ScholarshipRagAnswerResponse:
        """프로필 기반 최종 eligibility 판정 요청은 deterministic endpoint로 안내합니다."""

        return ScholarshipRagAnswerResponse(
            question=question,
            answer_text=(
                "최종 지원 가능 여부는 질의응답이 아니라 학생 프로필 기반 판정 경로에서 확인해야 합니다. "
                "학점, 소득분위, 학적 상태를 함께 보내 `/api/v1/scholarships/eligibility`를 사용해 주세요."
            ),
            answer_mode="guardrail",
            has_evidence=False,
            retrieval_mode="guardrail",
            recommended_endpoint=ELIGIBILITY_ENDPOINT,
            citations=[],
        )

    def _enforce_guardrail(self, question: str) -> bool:
        """프로필 기반 최종 판정 질문인지 간단한 휴리스틱으로 판별합니다."""

        normalized_question = question.lower()
        decision_markers = [
            "지원 가능",
            "신청 가능",
            "가능해",
            "가능할까",
            "될까",
            "eligible",
            "자격",
        ]
        profile_markers = [
            "내가",
            "제가",
            "저는",
            "내 ",
            "제 ",
            "프로필",
            "학점",
            "gpa",
            "소득분위",
            "income",
            "재학",
            "휴학",
        ]
        return any(marker in normalized_question for marker in decision_markers) and any(
            marker in normalized_question for marker in profile_markers
        )

    def _build_citations(
        self,
        chunks: List[RagRetrievedChunk],
    ) -> List[ScholarshipRagCitationResponse]:
        """prompt에 포함된 chunk들을 API 응답용 citation DTO로 변환합니다."""

        return [
            ScholarshipRagCitationResponse(
                chunk_id=chunk.chunk_id,
                chunk_key=chunk.chunk_key,
                notice_id=chunk.notice_id,
                document_id=chunk.document_id,
                rule_id=chunk.rule_id,
                block_id=chunk.block_id,
                quote_text=chunk.chunk_text,
                scholarship_name=chunk.scholarship_name,
                source_label=chunk.source_label,
                document_kind=chunk.document_kind,
                page_number=chunk.page_number,
                anchor_keys=list(chunk.anchor_keys),
                matched_retrieval_kinds=list(chunk.matched_retrieval_kinds),
                final_score=chunk.final_score,
                metadata=dict(chunk.metadata),
            )
            for chunk in chunks
        ]

    def _normalize_question(self, question: str) -> str:
        """공백과 줄바꿈을 정리한 질문 문자열을 반환합니다."""

        return " ".join(str(question).strip().split())
