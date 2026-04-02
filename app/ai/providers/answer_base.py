from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas import GroundedAnswerOutput


class GroundedAnswerProviderError(RuntimeError):
    """grounded answer 공급자가 답변 생성을 완료하지 못했을 때 쓰는 공통 예외입니다."""


class GroundedAnswerProviderTransportError(GroundedAnswerProviderError):
    """상위 answer generation 공급자에 연결할 수 없거나 HTTP 오류가 반환될 때 발생합니다."""


class GroundedAnswerProviderResponseError(GroundedAnswerProviderError):
    """상위 공급자가 answer response 형식을 지키지 못했을 때 발생합니다."""


@runtime_checkable
class GroundedAnswerProvider(Protocol):
    """RAG answer generation 단계가 공통으로 따를 공급자 계약입니다."""

    def generate_answer(self, *, question: str, prompt_text: str) -> GroundedAnswerOutput:
        """질문과 grounded context를 받아 answer payload를 반환합니다."""

    def close(self) -> None:
        """공유 HTTP 클라이언트 같은 공급자 리소스를 정리합니다."""
