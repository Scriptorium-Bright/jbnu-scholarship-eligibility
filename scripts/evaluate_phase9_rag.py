from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.ai.providers import FakeEmbeddingProvider
from app.core.config import reset_settings_cache
from app.core.time import ASIA_SEOUL
from app.db import create_all_tables, session_scope
from app.db.session import reset_engine_cache
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
    ScholarshipNoticeUpsert,
    ScholarshipRagChunkUpsert,
    ScholarshipRuleCreate,
)
from app.schemas import GroundedAnswerOutput
from app.services import RagPromptBuilder, ScholarshipRagAnswerService, ScholarshipRagRetrievalService


@dataclass(frozen=True)
class RagQuestionExpectation:
    """평가 fixture가 기대하는 answer mode와 citation/grounding 기준입니다."""

    answer_mode: str
    citation_block_ids: List[str]
    grounded_phrases: List[str]
    recommended_endpoint: Optional[str] = None


@dataclass(frozen=True)
class RagQuestionSample:
    """phase 9.4 synthetic evaluation에 사용하는 단일 질문 fixture입니다."""

    sample_id: str
    question: str
    query_embedding: List[float]
    answer_payload: Optional[Dict[str, Any]]
    expected: RagQuestionExpectation


@dataclass(frozen=True)
class RagQuestionEvaluationResult:
    """질문 하나를 실행했을 때의 평가 결과입니다."""

    sample_id: str
    expected_answer_mode: str
    actual_answer_mode: str
    grounded: bool
    citation_coverage_count: int
    citation_coverage_total: int
    refusal_expected: bool
    refusal_correct: bool
    latency_ms: float


@dataclass(frozen=True)
class RagEvaluationSummary:
    """phase 9.4 RAG answer evaluation의 집계 결과입니다."""

    sample_count: int
    grounded_sample_count: int
    grounded_success_count: int
    citation_coverage_count: int
    citation_coverage_total: int
    refusal_expected_count: int
    refusal_correct_count: int
    average_latency_ms: float
    p95_latency_ms: float

    @property
    def groundedness_rate(self) -> float:
        return (
            self.grounded_success_count / self.grounded_sample_count
            if self.grounded_sample_count
            else 0.0
        )

    @property
    def citation_coverage_rate(self) -> float:
        return (
            self.citation_coverage_count / self.citation_coverage_total
            if self.citation_coverage_total
            else 0.0
        )

    @property
    def refusal_precision(self) -> float:
        return (
            self.refusal_correct_count / self.refusal_expected_count
            if self.refusal_expected_count
            else 0.0
        )


@dataclass(frozen=True)
class RagEvaluationRun:
    """평가 fixture, sample 결과, 요약을 함께 담는 결과 객체입니다."""

    samples: List[RagQuestionSample]
    results: List[RagQuestionEvaluationResult]
    summary: RagEvaluationSummary


class FixtureDrivenGroundedAnswerProvider:
    """질문별 고정 answer payload를 반환하는 fixture 기반 grounded answer provider입니다."""

    def __init__(self, payloads_by_question: Dict[str, Dict[str, Any]]):
        self._payloads_by_question = dict(payloads_by_question)
        self.recorded_questions: List[str] = []
        self.recorded_prompts: List[str] = []

    def generate_answer(self, *, question: str, prompt_text: str) -> GroundedAnswerOutput:
        """질문에 대응하는 fixture payload를 반환합니다."""

        self.recorded_questions.append(question)
        self.recorded_prompts.append(prompt_text)

        payload = self._payloads_by_question.get(question)
        if payload is None:
            raise ValueError("No grounded answer payload configured for question: {0}".format(question))
        return GroundedAnswerOutput.model_validate(payload)

    def close(self) -> None:
        """fixture provider는 외부 리소스를 소유하지 않으므로 정리 동작이 없습니다."""


def load_question_set(fixtures_dir: Path) -> List[RagQuestionSample]:
    """JSON fixture 디렉터리에서 phase 9.4 질문 집합을 읽어옵니다."""

    samples: List[RagQuestionSample] = []
    for path in sorted(fixtures_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        expected_payload = payload["expected"]
        samples.append(
            RagQuestionSample(
                sample_id=payload["sample_id"],
                question=payload["question"],
                query_embedding=[float(value) for value in payload["query_embedding"]],
                answer_payload=payload.get("answer_payload"),
                expected=RagQuestionExpectation(
                    answer_mode=expected_payload["answer_mode"],
                    citation_block_ids=list(expected_payload.get("citation_block_ids", [])),
                    grounded_phrases=list(expected_payload.get("grounded_phrases", [])),
                    recommended_endpoint=expected_payload.get("recommended_endpoint"),
                ),
            )
        )
    return samples


def evaluate_rag_answers(fixtures_dir: Path) -> RagEvaluationRun:
    """question fixture를 기반으로 RAG answer 전체 경로를 평가합니다."""

    samples = load_question_set(fixtures_dir)

    with tempfile.TemporaryDirectory(prefix="jbnu-phase9-rag-eval-") as temp_dir:
        database_path = Path(temp_dir) / "phase9_rag_eval.sqlite3"
        database_url = "sqlite+pysqlite:///{0}".format(database_path)

        with temporary_database_url(database_url):
            create_all_tables()
            seed_rag_corpus()
            retrieval_service = ScholarshipRagRetrievalService(
                embedding_provider=FakeEmbeddingProvider(
                    dimensions=3,
                    predefined_vectors={
                        sample.question: sample.query_embedding
                        for sample in samples
                    },
                )
            )
            answer_provider = FixtureDrivenGroundedAnswerProvider(
                payloads_by_question={
                    sample.question: sample.answer_payload
                    for sample in samples
                    if sample.answer_payload is not None
                }
            )
            service = ScholarshipRagAnswerService(
                answer_provider=answer_provider,
                retrieval_service=retrieval_service,
                prompt_builder=RagPromptBuilder(max_characters=6000),
            )
            results = [
                evaluate_question_sample(service=service, sample=sample)
                for sample in samples
            ]

    return RagEvaluationRun(
        samples=samples,
        results=results,
        summary=summarize_results(results),
    )


def evaluate_question_sample(
    *,
    service: ScholarshipRagAnswerService,
    sample: RagQuestionSample,
) -> RagQuestionEvaluationResult:
    """질문 하나를 실행하고 groundedness, citation coverage, refusal 품질을 계산합니다."""

    started_at = perf_counter()
    response = service.answer(sample.question, limit=2)
    latency_ms = (perf_counter() - started_at) * 1000

    grounded = compute_groundedness(
        expected_grounded_phrases=sample.expected.grounded_phrases,
        answer_text=response.answer_text,
        citation_quotes=[citation.quote_text for citation in response.citations],
        answer_mode=response.answer_mode,
    )
    citation_coverage_count, citation_coverage_total = compute_citation_coverage(
        expected_block_ids=sample.expected.citation_block_ids,
        actual_block_ids=[citation.block_id for citation in response.citations],
    )
    refusal_correct = compute_refusal_precision(
        expected_mode=sample.expected.answer_mode,
        actual_mode=response.answer_mode,
        has_evidence=response.has_evidence,
        citation_count=len(response.citations),
        recommended_endpoint=response.recommended_endpoint,
        expected_endpoint=sample.expected.recommended_endpoint,
    )

    return RagQuestionEvaluationResult(
        sample_id=sample.sample_id,
        expected_answer_mode=sample.expected.answer_mode,
        actual_answer_mode=response.answer_mode,
        grounded=grounded,
        citation_coverage_count=citation_coverage_count,
        citation_coverage_total=citation_coverage_total,
        refusal_expected=sample.expected.answer_mode != "grounded",
        refusal_correct=refusal_correct,
        latency_ms=latency_ms,
    )


def compute_groundedness(
    *,
    expected_grounded_phrases: Sequence[str],
    answer_text: str,
    citation_quotes: Sequence[str],
    answer_mode: str,
) -> bool:
    """답변 핵심 문구가 실제 citation quote 안에서도 확인되는지 평가합니다."""

    if answer_mode != "grounded":
        return False
    if not expected_grounded_phrases:
        return False

    combined_citations = " ".join(citation_quotes)
    return all(
        phrase in answer_text and phrase in combined_citations
        for phrase in expected_grounded_phrases
    )


def compute_citation_coverage(
    *,
    expected_block_ids: Sequence[str],
    actual_block_ids: Sequence[str],
) -> tuple[int, int]:
    """기대한 citation block id가 실제 응답 citations에 얼마나 포함됐는지 계산합니다."""

    expected = [str(block_id) for block_id in expected_block_ids]
    if not expected:
        return 0, 0

    actual_set = {str(block_id) for block_id in actual_block_ids}
    covered = sum(1 for block_id in expected if block_id in actual_set)
    return covered, len(expected)


def compute_refusal_precision(
    *,
    expected_mode: str,
    actual_mode: str,
    has_evidence: bool,
    citation_count: int,
    recommended_endpoint: Optional[str],
    expected_endpoint: Optional[str],
) -> bool:
    """근거 부족 또는 guardrail 상황에서 안전한 refusal이 반환됐는지 계산합니다."""

    if expected_mode == "grounded":
        return False
    if actual_mode != expected_mode:
        return False
    if has_evidence:
        return False
    if citation_count != 0:
        return False
    if expected_endpoint is not None and recommended_endpoint != expected_endpoint:
        return False
    return True


def summarize_results(results: Iterable[RagQuestionEvaluationResult]) -> RagEvaluationSummary:
    """질문별 결과를 aggregate metric으로 요약합니다."""

    result_list = list(results)
    latencies = sorted(result.latency_ms for result in result_list)
    grounded_results = [result for result in result_list if result.expected_answer_mode == "grounded"]
    refusal_results = [result for result in result_list if result.refusal_expected]

    return RagEvaluationSummary(
        sample_count=len(result_list),
        grounded_sample_count=len(grounded_results),
        grounded_success_count=sum(1 for result in grounded_results if result.grounded),
        citation_coverage_count=sum(result.citation_coverage_count for result in grounded_results),
        citation_coverage_total=sum(result.citation_coverage_total for result in grounded_results),
        refusal_expected_count=len(refusal_results),
        refusal_correct_count=sum(1 for result in refusal_results if result.refusal_correct),
        average_latency_ms=(sum(latencies) / len(latencies)) if latencies else 0.0,
        p95_latency_ms=percentile(latencies, 0.95),
    )


def format_rag_summary_markdown(summary: RagEvaluationSummary) -> str:
    """README와 benchmark 문서에 붙일 RAG evaluation markdown 표를 생성합니다."""

    return "\n".join(
        [
            "| Sample Count | Groundedness | Citation Coverage | Refusal Precision | Avg Latency | p95 Latency |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
            "| {0} | {1:.2%} | {2:.2%} | {3:.2%} | {4:.2f}ms | {5:.2f}ms |".format(
                summary.sample_count,
                summary.groundedness_rate,
                summary.citation_coverage_rate,
                summary.refusal_precision,
                summary.average_latency_ms,
                summary.p95_latency_ms,
            ),
        ]
    )


def percentile(values: Sequence[float], ratio: float) -> float:
    """작은 샘플 수에서도 안정적으로 동작하는 nearest-rank percentile을 계산합니다."""

    if not values:
        return 0.0
    rank = max(int(math.ceil(len(values) * ratio)) - 1, 0)
    return float(values[min(rank, len(values) - 1)])


def seed_rag_corpus() -> Dict[str, int]:
    """phase 9.4 synthetic question set이 공통으로 사용할 RAG corpus를 적재합니다."""

    with session_scope() as session:
        notice_repository = ScholarshipNoticeRepository(session)
        document_repository = CanonicalDocumentRepository(session)
        rule_repository = ScholarshipRuleRepository(session)
        rag_repository = ScholarshipRagChunkRepository(session)

        notice = notice_repository.upsert_notice(
            ScholarshipNoticeUpsert(
                source_board="jbnu-main",
                source_notice_id="2026-012",
                title="2026학년도 1학기 통합장학금 선발 안내",
                notice_url="https://example.test/notices/2026-012",
                published_at=datetime(2026, 4, 3, 9, 0, tzinfo=ASIA_SEOUL),
                application_started_at=datetime(2026, 4, 4, 9, 0, tzinfo=ASIA_SEOUL),
                application_ended_at=datetime(2026, 4, 10, 18, 0, tzinfo=ASIA_SEOUL),
                summary="성적과 소득 기준을 함께 보는 장학금",
            )
        )
        attachment = notice_repository.add_or_update_attachment(
            notice.id,
            NoticeAttachmentUpsert(
                source_url="https://example.test/notices/2026-012/guide.txt",
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
                    provenance_keys=["eligibility-gpa", "eligibility-income", "required-documents"],
                )
            ],
        )

        rag_repository.upsert_chunks(
            [
                ScholarshipRagChunkUpsert(
                    notice_id=notice.id,
                    document_id=notice_document.id,
                    rule_id=saved_rules[0].id,
                    chunk_key="notice:{0}:document:{1}:block:notice-block-1:rule:{2}".format(
                        notice.id,
                        notice_document.id,
                        saved_rules[0].id,
                    ),
                    block_id="notice-block-1",
                    chunk_text="직전학기 평점평균 3.80 이상인 재학생",
                    search_text="통합장학금 성적 기준 평점 3.80 이상 재학생",
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
                    rule_id=saved_rules[0].id,
                    chunk_key="notice:{0}:document:{1}:block:notice-block-2:rule:{2}".format(
                        notice.id,
                        notice_document.id,
                        saved_rules[0].id,
                    ),
                    block_id="notice-block-2",
                    chunk_text="소득분위 8분위 이하 학생",
                    search_text="통합장학금 소득 기준 소득분위 8분위 이하 학생",
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
                    chunk_key="notice:{0}:document:{1}:block:attachment-block-1:rule:{2}".format(
                        notice.id,
                        attachment_document.id,
                        saved_rules[0].id,
                    ),
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

        return {
            "notice_id": notice.id,
            "rule_id": saved_rules[0].id,
        }


@contextmanager
def temporary_database_url(database_url: str) -> Iterator[None]:
    """evaluation 동안에만 앱 설정과 session factory가 임시 SQLite를 바라보게 합니다."""

    previous_value = os.environ.get("JBNU_DATABASE_URL")
    os.environ["JBNU_DATABASE_URL"] = database_url
    reset_settings_cache()
    reset_engine_cache()
    try:
        yield
    finally:
        if previous_value is None:
            os.environ.pop("JBNU_DATABASE_URL", None)
        else:
            os.environ["JBNU_DATABASE_URL"] = previous_value
        reset_settings_cache()
        reset_engine_cache()


def main() -> int:
    """phase 9.4 평가를 실행하고 markdown summary를 stdout에 출력합니다."""

    parser = argparse.ArgumentParser(description="Evaluate phase 9 RAG answers")
    parser.add_argument(
        "--fixtures-dir",
        default="tests/fixtures/phase9_rag_questions",
        help="Path to phase 9 RAG question fixtures",
    )
    args = parser.parse_args()

    evaluation_run = evaluate_rag_answers(Path(args.fixtures_dir))
    print(format_rag_summary_markdown(evaluation_run.summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
