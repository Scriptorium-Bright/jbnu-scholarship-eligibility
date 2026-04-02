from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.schemas import GroundedAnswerOutput


class FakeGroundedAnswerProvider:
    """네트워크 호출 없이 grounded answer 흐름을 검증하는 결정론적 공급자입니다."""

    def __init__(self, response_payload: Optional[Dict[str, Any]] = None):
        """테스트에서 재사용할 고정 grounded answer payload를 미리 검증해 보관합니다."""

        self._response = GroundedAnswerOutput.model_validate(
            response_payload or self._default_payload()
        )
        self.recorded_questions: List[str] = []
        self.recorded_prompts: List[str] = []

    def generate_answer(self, *, question: str, prompt_text: str) -> GroundedAnswerOutput:
        """항상 같은 스키마 유효 답변을 반환하고 질문/프롬프트를 기록합니다."""

        self.recorded_questions.append(question)
        self.recorded_prompts.append(prompt_text)
        return self._response.model_copy(deep=True)

    def close(self) -> None:
        """fake provider는 외부 리소스를 소유하지 않으므로 close는 아무 동작도 하지 않습니다."""

    @staticmethod
    def _default_payload() -> Dict[str, Any]:
        """baseline 테스트에 사용할 최소한의 grounded answer를 제공합니다."""

        return {
            "answer_text": "공식 공지 기준으로 확인 가능한 장학 조건을 요약한 테스트 답변입니다.",
        }
