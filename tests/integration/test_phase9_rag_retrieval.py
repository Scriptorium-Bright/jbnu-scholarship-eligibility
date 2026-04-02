from datetime import datetime

from app.ai.providers import EmbeddingProviderTransportError, FakeEmbeddingProvider
from app.core.time import ASIA_SEOUL
from app.db import create_all_tables, session_scope
from app.models import DocumentKind
from app.repositories import (
    CanonicalDocumentRepository,
    ScholarshipNoticeRepository,
    ScholarshipRagChunkRepository,
    ScholarshipRuleRepository,
)
from app.schemas import (
    CanonicalBlock,
    CanonicalDocumentUpsert,
    NoticeAttachmentUpsert,
    ProvenanceAnchorCreate,
    ScholarshipNoticeUpsert,
    ScholarshipRagChunkUpsert,
    ScholarshipRuleCreate,
)
from app.services import ScholarshipRagRetrievalService


class FailingEmbeddingProvider:
    def embed_documents(self, *, texts):
        raise NotImplementedError

    def embed_query(self, *, text):
        raise EmbeddingProviderTransportError("embedding backend unavailable")

    def close(self) -> None:
        return None


def _seed_notice_for_phase9_retrieval():
    with session_scope() as session:
        notice_repository = ScholarshipNoticeRepository(session)
        document_repository = CanonicalDocumentRepository(session)
        rule_repository = ScholarshipRuleRepository(session)
        rag_repository = ScholarshipRagChunkRepository(session)

        notice = notice_repository.upsert_notice(
            ScholarshipNoticeUpsert(
                source_board="jbnu-main",
                source_notice_id="2026-011",
                title="2026학년도 1학기 통합장학금 선발 안내",
                notice_url="https://example.test/notices/2026-011",
                published_at=datetime(2026, 4, 3, 9, 0, tzinfo=ASIA_SEOUL),
                application_started_at=datetime(2026, 4, 4, 9, 0, tzinfo=ASIA_SEOUL),
                application_ended_at=datetime(2026, 4, 10, 18, 0, tzinfo=ASIA_SEOUL),
                summary="성적과 소득 기준을 함께 보는 장학금",
            )
        )
        attachment = notice_repository.add_or_update_attachment(
            notice.id,
            NoticeAttachmentUpsert(
                source_url="https://example.test/notices/2026-011/guide.txt",
                file_name="guide.txt",
                media_type="text/plain",
            ),
        )

        notice_document = document_repository.upsert_document(
            CanonicalDocumentUpsert(
                notice_id=notice.id,
                document_kind=DocumentKind.NOTICE_HTML,
                source_label="notice-html",
                canonical_text="\n".join(
                    [
                        "직전학기 평점평균 3.80 이상인 재학생",
                        "소득분위 8분위 이하 학생",
                    ]
                ),
                blocks=[
                    CanonicalBlock(
                        block_id="notice-block-1",
                        text="직전학기 평점평균 3.80 이상인 재학생",
                        page_number=1,
                        metadata={"section": "지원자격"},
                    ),
                    CanonicalBlock(
                        block_id="notice-block-2",
                        text="소득분위 8분위 이하 학생",
                        page_number=1,
                        metadata={"section": "지원자격"},
                    ),
                ],
            )
        )
        attachment_document = document_repository.upsert_document(
            CanonicalDocumentUpsert(
                notice_id=notice.id,
                attachment_id=attachment.id,
                document_kind=DocumentKind.ATTACHMENT_TEXT,
                source_label="attachment-text",
                canonical_text="제출서류: 장학금지원서 및 성적증명서",
                blocks=[
                    CanonicalBlock(
                        block_id="attachment-block-1",
                        text="제출서류: 장학금지원서 및 성적증명서",
                        page_number=2,
                        metadata={"section": "제출서류"},
                    )
                ],
            )
        )

        document_repository.replace_anchors(
            document_id=notice_document.id,
            anchors=[
                ProvenanceAnchorCreate(
                    document_id=notice_document.id,
                    anchor_key="eligibility-gpa",
                    block_id="notice-block-1",
                    quote_text="직전학기 평점평균 3.80 이상인 재학생",
                    page_number=1,
                    locator={"section": "지원자격"},
                ),
                ProvenanceAnchorCreate(
                    document_id=notice_document.id,
                    anchor_key="eligibility-income",
                    block_id="notice-block-2",
                    quote_text="소득분위 8분위 이하 학생",
                    page_number=1,
                    locator={"section": "지원자격"},
                ),
            ],
        )
        document_repository.replace_anchors(
            document_id=attachment_document.id,
            anchors=[
                ProvenanceAnchorCreate(
                    document_id=attachment_document.id,
                    anchor_key="required-documents",
                    block_id="attachment-block-1",
                    quote_text="제출서류: 장학금지원서 및 성적증명서",
                    page_number=2,
                    locator={"section": "제출서류"},
                )
            ],
        )

        saved_rules = rule_repository.replace_rules(
            notice_id=notice.id,
            rules=[
                ScholarshipRuleCreate(
                    notice_id=notice.id,
                    document_id=notice_document.id,
                    scholarship_name="통합장학금",
                    application_started_at=datetime(2026, 4, 4, 9, 0, tzinfo=ASIA_SEOUL),
                    application_ended_at=datetime(2026, 4, 10, 18, 0, tzinfo=ASIA_SEOUL),
                    summary_text="성적과 소득 기준을 함께 보는 장학금",
                    qualification={"gpa_min": 3.8, "income_bracket_max": 8},
                    provenance_keys=["eligibility-gpa", "eligibility-income"],
                ),
                ScholarshipRuleCreate(
                    notice_id=notice.id,
                    document_id=notice_document.id,
                    scholarship_name="성적우수장학금",
                    application_started_at=datetime(2026, 4, 4, 9, 0, tzinfo=ASIA_SEOUL),
                    application_ended_at=datetime(2026, 4, 10, 18, 0, tzinfo=ASIA_SEOUL),
                    summary_text="우수 성적 재학생 대상 장학금",
                    qualification={"gpa_min": 3.8},
                    provenance_keys=["eligibility-gpa"],
                ),
            ],
        )

        rag_repository.upsert_chunks(
            [
                ScholarshipRagChunkUpsert(
                    notice_id=notice.id,
                    document_id=notice_document.id,
                    rule_id=saved_rules[0].id,
                    chunk_key="notice:1:document:1:block:notice-block-1:rule:1",
                    block_id="notice-block-1",
                    chunk_text="직전학기 평점평균 3.80 이상인 재학생",
                    search_text="통합장학금 성적우수 평점 3.80 이상 재학생",
                    scholarship_name="통합장학금",
                    source_label="notice-html",
                    document_kind=DocumentKind.NOTICE_HTML,
                    page_number=1,
                    anchor_keys=["eligibility-gpa"],
                    embedding_vector=[1.0, 0.0, 0.0],
                    metadata={
                        "notice_title": notice.title,
                        "notice_url": notice.notice_url,
                        "block_metadata": {"section": "지원자격"},
                    },
                ),
                ScholarshipRagChunkUpsert(
                    notice_id=notice.id,
                    document_id=notice_document.id,
                    rule_id=saved_rules[1].id,
                    chunk_key="notice:1:document:1:block:notice-block-1:rule:2",
                    block_id="notice-block-1",
                    chunk_text="직전학기 평점평균 3.80 이상인 재학생",
                    search_text="성적우수장학금 성적우수 평점 3.80 이상 재학생",
                    scholarship_name="성적우수장학금",
                    source_label="notice-html",
                    document_kind=DocumentKind.NOTICE_HTML,
                    page_number=1,
                    anchor_keys=["eligibility-gpa"],
                    embedding_vector=[1.0, 0.0, 0.0],
                    metadata={
                        "notice_title": notice.title,
                        "notice_url": notice.notice_url,
                        "block_metadata": {"section": "지원자격"},
                    },
                ),
                ScholarshipRagChunkUpsert(
                    notice_id=notice.id,
                    document_id=notice_document.id,
                    rule_id=saved_rules[0].id,
                    chunk_key="notice:1:document:1:block:notice-block-2:rule:1",
                    block_id="notice-block-2",
                    chunk_text="소득분위 8분위 이하 학생",
                    search_text="통합장학금 소득분위 8분위 이하 학생",
                    scholarship_name="통합장학금",
                    source_label="notice-html",
                    document_kind=DocumentKind.NOTICE_HTML,
                    page_number=1,
                    anchor_keys=["eligibility-income"],
                    embedding_vector=[0.0, 1.0, 0.0],
                    metadata={
                        "notice_title": notice.title,
                        "notice_url": notice.notice_url,
                        "block_metadata": {"section": "지원자격"},
                    },
                ),
                ScholarshipRagChunkUpsert(
                    notice_id=notice.id,
                    document_id=attachment_document.id,
                    rule_id=saved_rules[0].id,
                    chunk_key="notice:1:document:2:block:attachment-block-1:rule:1",
                    block_id="attachment-block-1",
                    chunk_text="제출서류: 장학금지원서 및 성적증명서",
                    search_text="통합장학금 제출서류 장학금지원서 성적증명서",
                    scholarship_name="통합장학금",
                    source_label="attachment-text",
                    document_kind=DocumentKind.ATTACHMENT_TEXT,
                    page_number=2,
                    anchor_keys=["required-documents"],
                    embedding_vector=[0.0, 0.0, 1.0],
                    metadata={
                        "notice_title": notice.title,
                        "notice_url": notice.notice_url,
                        "block_metadata": {"section": "제출서류"},
                    },
                ),
            ]
        )

        return notice.id


def test_phase9_rag_retrieval_service_merges_hybrid_candidates(monkeypatch, tmp_path):
    database_path = tmp_path / "phase9_retrieval.sqlite3"
    monkeypatch.setenv("JBNU_DATABASE_URL", "sqlite+pysqlite:///{0}".format(database_path))
    create_all_tables()
    _seed_notice_for_phase9_retrieval()

    provider = FakeEmbeddingProvider(
        dimensions=3,
        predefined_vectors={"통합장학금 성적 우수": [1.0, 0.0, 0.0]},
    )
    service = ScholarshipRagRetrievalService(embedding_provider=provider)

    result = service.retrieve("통합장학금 성적 우수", limit=3)

    assert result.has_evidence is True
    assert result.retrieval_mode == "hybrid"
    assert result.count == 3
    assert [chunk.block_id for chunk in result.chunks].count("notice-block-1") == 1
    assert result.chunks[0].block_id == "notice-block-1"
    assert result.chunks[0].matched_retrieval_kinds == ["keyword", "vector"]
    assert result.chunks[0].anchor_keys == ["eligibility-gpa"]


def test_phase9_rag_retrieval_service_returns_no_evidence_when_query_is_unmatched(
    monkeypatch,
    tmp_path,
):
    database_path = tmp_path / "phase9_retrieval_empty.sqlite3"
    monkeypatch.setenv("JBNU_DATABASE_URL", "sqlite+pysqlite:///{0}".format(database_path))
    create_all_tables()
    _seed_notice_for_phase9_retrieval()

    provider = FakeEmbeddingProvider(
        dimensions=3,
        predefined_vectors={"기숙사 입주 가능한가": [0.0, 0.0, 0.0]},
    )
    service = ScholarshipRagRetrievalService(embedding_provider=provider)

    result = service.retrieve("기숙사 입주 가능한가", limit=2)

    assert result.has_evidence is False
    assert result.retrieval_mode == "no_evidence"
    assert result.count == 0
    assert result.chunks == []


def test_phase9_rag_retrieval_service_falls_back_to_keyword_candidates(monkeypatch, tmp_path):
    database_path = tmp_path / "phase9_retrieval_fallback.sqlite3"
    monkeypatch.setenv("JBNU_DATABASE_URL", "sqlite+pysqlite:///{0}".format(database_path))
    create_all_tables()
    _seed_notice_for_phase9_retrieval()

    service = ScholarshipRagRetrievalService(embedding_provider=FailingEmbeddingProvider())

    result = service.retrieve("평점 3.80", limit=2)

    assert result.has_evidence is True
    assert result.retrieval_mode == "keyword_fallback"
    assert result.keyword_fallback_used is True
    assert result.failure_reason == "EmbeddingProviderTransportError"
    assert result.chunks[0].block_id == "notice-block-1"
