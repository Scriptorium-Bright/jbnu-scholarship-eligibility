from __future__ import annotations

from typing import List, Sequence, Tuple

from app.schemas import RagPromptContext, RagRetrievedChunk


class RagPromptBuilder:
    """retrieved chunk를 generation-friendly prompt context로 직렬화하는 빌더입니다."""

    def __init__(self, *, max_characters: int = 6000):
        """질의응답 단계에서 근거 chunk에 배정할 최대 문자 예산을 설정합니다."""

        self.max_characters = max_characters

    def build_context(
        self,
        *,
        query: str,
        retrieved_chunks: Sequence[RagRetrievedChunk],
    ) -> RagPromptContext:
        """질의와 선택된 chunk들을 하나의 augment prompt payload로 조립합니다."""

        selected_chunks, truncated = self.truncate_chunks(retrieved_chunks)
        prompt_lines = [
            "당신은 전북대 장학금 질의응답용 근거 컨텍스트 조립기다.",
            "아래 근거에서 확인 가능한 사실만 사용하고 추정하지 않는다.",
            "근거가 부족하면 근거 없음으로 판단할 수 있어야 한다.",
            "",
            "[user query]",
            str(query).strip(),
            "",
            "[retrieved chunks]",
        ]
        if selected_chunks:
            prompt_lines.extend(self.serialize_chunk(chunk) for chunk in selected_chunks)
        else:
            prompt_lines.append("(no evidence)")

        return RagPromptContext(
            query=query,
            prompt_text="\n".join(prompt_lines).strip(),
            selected_chunks=list(selected_chunks),
            truncated=truncated,
            has_evidence=bool(selected_chunks),
        )

    def serialize_chunk(self, chunk: RagRetrievedChunk) -> str:
        """citation에 필요한 핵심 식별자와 메타데이터를 한 줄 근거 표현으로 직렬화합니다."""

        document_kind = getattr(chunk.document_kind, "value", str(chunk.document_kind))
        parts = [
            "[chunk_id={0}]".format(chunk.chunk_id),
            "[chunk_key={0}]".format(chunk.chunk_key),
            "[notice_id={0}]".format(chunk.notice_id),
            "[document_id={0}]".format(chunk.document_id),
            "[block_id={0}]".format(chunk.block_id),
            "[source_label={0}]".format(chunk.source_label),
            "[document_kind={0}]".format(document_kind),
        ]
        if chunk.page_number is not None:
            parts.append("[page_number={0}]".format(chunk.page_number))
        if chunk.scholarship_name:
            parts.append("[scholarship_name={0}]".format(chunk.scholarship_name))
        if chunk.anchor_keys:
            parts.append("[anchor_keys={0}]".format(",".join(chunk.anchor_keys)))

        block_metadata = chunk.metadata.get("block_metadata", {})
        if isinstance(block_metadata, dict):
            section = block_metadata.get("section")
            if section:
                parts.append("[section={0}]".format(section))
        return "{0} {1}".format("".join(parts), chunk.chunk_text)

    def truncate_chunks(
        self,
        chunks: Sequence[RagRetrievedChunk],
    ) -> Tuple[List[RagRetrievedChunk], bool]:
        """retrieval 순서를 유지한 채 prompt budget에 맞춰 chunk를 자릅니다."""

        if not chunks:
            return [], False

        selected: List[RagRetrievedChunk] = []
        used_characters = 0
        truncated = False

        for chunk in chunks:
            serialized = self.serialize_chunk(chunk)
            chunk_cost = len(serialized) + 1
            if selected and used_characters + chunk_cost > self.max_characters:
                truncated = True
                break
            if not selected and chunk_cost > self.max_characters:
                selected.append(chunk)
                truncated = True
                break

            selected.append(chunk)
            used_characters += chunk_cost

        return selected, truncated
