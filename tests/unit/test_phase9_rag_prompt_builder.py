from typing import Optional

from app.models import DocumentKind
from app.schemas import RagRetrievedChunk
from app.services import RagPromptBuilder


def _build_chunk(
    *,
    chunk_id: int,
    chunk_text: str,
    page_number: Optional[int] = 1,
) -> RagRetrievedChunk:
    return RagRetrievedChunk(
        chunk_id=chunk_id,
        chunk_key="notice:1:document:1:block:block-{0}".format(chunk_id),
        notice_id=1,
        document_id=1,
        rule_id=1,
        block_id="block-{0}".format(chunk_id),
        chunk_text=chunk_text,
        scholarship_name="통합장학금",
        source_label="notice-html",
        document_kind=DocumentKind.NOTICE_HTML,
        page_number=page_number,
        anchor_keys=["eligibility-gpa"],
        metadata={"block_metadata": {"section": "지원자격"}},
        keyword_score=6.0,
        vector_score=0.95,
        final_score=0.25,
        matched_retrieval_kinds=["keyword", "vector"],
    )


def test_phase9_rag_prompt_builder_serializes_citation_metadata():
    builder = RagPromptBuilder(max_characters=400)

    serialized = builder.serialize_chunk(
        _build_chunk(
            chunk_id=7,
            chunk_text="직전학기 평점평균 3.80 이상인 재학생",
            page_number=2,
        )
    )

    assert "[chunk_id=7]" in serialized
    assert "[source_label=notice-html]" in serialized
    assert "[page_number=2]" in serialized
    assert "[anchor_keys=eligibility-gpa]" in serialized
    assert "[section=지원자격]" in serialized
    assert "직전학기 평점평균 3.80 이상인 재학생" in serialized


def test_phase9_rag_prompt_builder_truncates_chunks_by_budget():
    builder = RagPromptBuilder(max_characters=220)
    first_chunk = _build_chunk(
        chunk_id=1,
        chunk_text="직전학기 평점평균 3.80 이상인 재학생",
    )
    second_chunk = _build_chunk(
        chunk_id=2,
        chunk_text="소득분위 8분위 이하 학생",
    )

    context = builder.build_context(
        query="성적 우수 장학금 기준이 뭐야?",
        retrieved_chunks=[first_chunk, second_chunk],
    )

    assert context.has_evidence is True
    assert context.truncated is True
    assert [chunk.chunk_id for chunk in context.selected_chunks] == [1]
    assert "성적 우수 장학금 기준이 뭐야?" in context.prompt_text
    assert "직전학기 평점평균 3.80 이상인 재학생" in context.prompt_text
    assert "소득분위 8분위 이하 학생" not in context.prompt_text
