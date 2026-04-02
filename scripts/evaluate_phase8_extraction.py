from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app.services.rule_extraction as rule_extraction_module
from app.ai.providers import StructuredOutputProviderTransportError
from app.core.config import Settings, reset_settings_cache
from app.db import create_all_tables, session_scope
from app.db.session import reset_engine_cache
from app.models import DocumentKind
from app.repositories import CanonicalDocumentRepository, ScholarshipNoticeRepository, ScholarshipRuleRepository
from app.schemas import (
    CanonicalBlock,
    CanonicalDocumentUpsert,
    NoticeAttachmentUpsert,
    ScholarshipNoticeUpsert,
)
from app.services import ScholarshipRuleExtractionService


@dataclass(frozen=True)
class GoldExpectedRule:
    """fixture가 기대하는 gold qualification과 evidence block 집합입니다."""

    scholarship_name: str
    qualification: Dict[str, Any]
    evidence_block_ids: List[str]


@dataclass(frozen=True)
class GoldProviderCase:
    """fixture가 LLM path에 대해 어떤 응답이나 실패를 내야 하는지 정의합니다."""

    behavior: str
    payload_template: Optional[Dict[str, Any]]


@dataclass(frozen=True)
class GoldSample:
    """phase 8.6 synthetic evaluation에 사용하는 단일 gold sample입니다."""

    sample_id: str
    notice: Dict[str, Any]
    attachments: List[Dict[str, Any]]
    documents: List[Dict[str, Any]]
    expected: GoldExpectedRule
    provider_case: GoldProviderCase


@dataclass(frozen=True)
class SeededGoldSample:
    """DB에 materialize된 sample과 문서 id, block id 맵을 함께 보관합니다."""

    sample: GoldSample
    notice_id: int
    document_ids_by_ref: Dict[str, int]
    all_block_ids: List[str]
    provider_case: GoldProviderCase


@dataclass(frozen=True)
class ExtractionLogRecord:
    """서비스 로그에서 복원한 extraction outcome 구조입니다."""

    notice_id: int
    requested_mode: str
    extractor_used: str
    success: bool
    fallback_used: bool
    latency_ms: float
    error_type: Optional[str]
    error_message: Optional[str]


@dataclass(frozen=True)
class SampleEvaluationResult:
    """sample 하나를 특정 mode로 실행했을 때의 측정 결과입니다."""

    sample_id: str
    success: bool
    field_matches: int
    field_total: int
    evidence_valid_count: int
    evidence_total: int
    evidence_coverage_count: int
    evidence_coverage_total: int
    latency_ms: float
    fallback_used: bool
    fallback_expected: bool
    error_type: Optional[str]


@dataclass(frozen=True)
class ModeEvaluationSummary:
    """mode 단위 aggregated metric을 담는 결과 객체입니다."""

    mode: str
    sample_count: int
    success_count: int
    field_match_count: int
    field_total_count: int
    evidence_valid_count: int
    evidence_total_count: int
    evidence_coverage_count: int
    evidence_coverage_total: int
    fallback_expected_count: int
    fallback_success_count: int
    average_latency_ms: float
    p95_latency_ms: float

    @property
    def extraction_success_rate(self) -> float:
        return self.success_count / self.sample_count if self.sample_count else 0.0

    @property
    def field_exact_match_rate(self) -> float:
        return self.field_match_count / self.field_total_count if self.field_total_count else 0.0

    @property
    def evidence_valid_rate(self) -> float:
        return self.evidence_valid_count / self.evidence_total_count if self.evidence_total_count else 0.0

    @property
    def evidence_coverage_rate(self) -> float:
        return (
            self.evidence_coverage_count / self.evidence_coverage_total
            if self.evidence_coverage_total
            else 0.0
        )

    @property
    def fallback_recovery_rate(self) -> float:
        return (
            self.fallback_success_count / self.fallback_expected_count
            if self.fallback_expected_count
            else 0.0
        )


class EvaluationLogCapture(logging.Handler):
    """추출 결과 로그를 구조화해서 evaluation metric 집계에 재사용합니다."""

    def __init__(self):
        super().__init__()
        self.records: List[ExtractionLogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        """rule extraction outcome 로그만 받아 구조화된 dataclass로 변환합니다."""

        if not isinstance(record.args, tuple) or len(record.args) != 8:
            return

        self.records.append(
            ExtractionLogRecord(
                notice_id=int(record.args[0]),
                requested_mode=str(record.args[1]),
                extractor_used=str(record.args[2]),
                success=bool(record.args[3]),
                fallback_used=bool(record.args[4]),
                latency_ms=float(record.args[5]),
                error_type=None if record.args[6] == "-" else str(record.args[6]),
                error_message=None if record.args[7] == "-" else str(record.args[7]),
            )
        )

    def latest_for_notice(self, notice_id: int) -> Optional[ExtractionLogRecord]:
        """특정 notice에 대해 가장 최근에 남은 extraction outcome 로그를 가져옵니다."""

        for record in reversed(self.records):
            if record.notice_id == notice_id:
                return record
        return None


class FixtureDrivenStructuredOutputProvider:
    """notice title 기준으로 fixture별 success, invalid evidence, transport error를 재현합니다."""

    def __init__(self, cases_by_title: Dict[str, GoldProviderCase]):
        self._cases_by_title = cases_by_title
        self.recorded_prompts: List[str] = []

    def extract_rule(self, *, prompt_text: str):
        """prompt에 포함된 notice title을 기준으로 fixture provider case를 선택합니다."""

        self.recorded_prompts.append(prompt_text)
        for notice_title, provider_case in self._cases_by_title.items():
            if notice_title not in prompt_text:
                continue

            if provider_case.behavior == "transport_error":
                raise StructuredOutputProviderTransportError(
                    "synthetic transport error for {0}".format(notice_title)
                )
            if provider_case.payload_template is None:
                raise ValueError("Provider payload is missing for sample: {0}".format(notice_title))
            from app.schemas import LLMExtractionResponse

            return LLMExtractionResponse.model_validate(provider_case.payload_template)

        raise ValueError("No provider case matched the given prompt")

    def close(self) -> None:
        """fixture provider는 외부 리소스를 소유하지 않으므로 정리 동작이 없습니다."""


def load_gold_set(fixtures_dir: Path) -> List[GoldSample]:
    """JSON fixture 디렉터리에서 phase 8.6 gold sample 목록을 읽어옵니다."""

    samples: List[GoldSample] = []
    for path in sorted(fixtures_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        samples.append(
            GoldSample(
                sample_id=payload["sample_id"],
                notice=payload["notice"],
                attachments=payload.get("attachments", []),
                documents=payload["documents"],
                expected=GoldExpectedRule(
                    scholarship_name=payload["expected"]["scholarship_name"],
                    qualification=payload["expected"]["qualification"],
                    evidence_block_ids=payload["expected"]["evidence_block_ids"],
                ),
                provider_case=GoldProviderCase(
                    behavior=payload["provider_case"]["behavior"],
                    payload_template=payload["provider_case"] if payload["provider_case"]["behavior"] != "transport_error" else None,
                ),
            )
        )
    return samples


def evaluate_all_modes(fixtures_dir: Path) -> Dict[str, ModeEvaluationSummary]:
    """gold set을 기준으로 heuristic, llm, hybrid 세 모드를 모두 평가합니다."""

    gold_set = load_gold_set(fixtures_dir)
    return {
        mode: evaluate_mode(mode=mode, gold_set=gold_set)
        for mode in ("heuristic", "llm", "hybrid")
    }


def evaluate_mode(mode: str, gold_set: List[GoldSample]) -> ModeEvaluationSummary:
    """단일 extractor mode를 gold set 전체에 대해 실행하고 metric을 집계합니다."""

    with tempfile.TemporaryDirectory(prefix="jbnu-phase8-eval-") as temp_dir:
        database_path = Path(temp_dir) / "{0}.sqlite3".format(mode)
        database_url = "sqlite+pysqlite:///{0}".format(database_path)

        with temporary_database_url(database_url):
            create_all_tables()
            seeded_samples = seed_gold_set(gold_set)
            provider = FixtureDrivenStructuredOutputProvider(
                {
                    seeded.sample.notice["title"]: seeded.provider_case
                    for seeded in seeded_samples
                }
            )
            settings = Settings(
                database_url=database_url,
                extractor_mode=mode,
                llm_provider="fake",
                llm_retry_attempts=2,
                llm_max_context_characters=4000,
            )

            original_builder = rule_extraction_module.build_structured_output_provider
            log_capture = EvaluationLogCapture()
            logger = logging.getLogger("app.services.extraction_logging")
            logger.addHandler(log_capture)
            logger.setLevel(logging.INFO)
            try:
                if mode in {"llm", "hybrid"}:
                    rule_extraction_module.build_structured_output_provider = lambda active_settings: provider

                service = ScholarshipRuleExtractionService(settings=settings)
                results = [
                    evaluate_seeded_sample(
                        service=service,
                        seeded_sample=seeded_sample,
                        log_capture=log_capture,
                    )
                    for seeded_sample in seeded_samples
                ]
            finally:
                rule_extraction_module.build_structured_output_provider = original_builder
                logger.removeHandler(log_capture)
                provider.close()

    return summarize_mode(mode=mode, results=results)


def seed_gold_set(gold_set: Iterable[GoldSample]) -> List[SeededGoldSample]:
    """gold sample 전체를 현재 DB에 적재하고 provider payload를 실문서 id 기준으로 materialize합니다."""

    return [seed_gold_sample(sample) for sample in gold_set]


def seed_gold_sample(sample: GoldSample) -> SeededGoldSample:
    """단일 gold sample을 notice, attachment, canonical document까지 현재 DB에 적재합니다."""

    with session_scope() as session:
        notice_repository = ScholarshipNoticeRepository(session)
        document_repository = CanonicalDocumentRepository(session)

        notice = notice_repository.upsert_notice(
            ScholarshipNoticeUpsert(
                source_board=sample.notice["source_board"],
                source_notice_id=sample.notice["source_notice_id"],
                title=sample.notice["title"],
                notice_url=sample.notice["notice_url"],
                published_at=parse_datetime(sample.notice["published_at"]),
                application_started_at=parse_datetime(sample.notice["application_started_at"]),
                application_ended_at=parse_datetime(sample.notice["application_ended_at"]),
                summary=sample.notice["summary"],
            )
        )

        attachment_ids_by_ref: Dict[str, int] = {}
        for attachment in sample.attachments:
            saved_attachment = notice_repository.add_or_update_attachment(
                notice.id,
                NoticeAttachmentUpsert(
                    source_url=attachment["source_url"],
                    file_name=attachment["file_name"],
                    media_type=attachment["media_type"],
                ),
            )
            attachment_ids_by_ref[attachment["attachment_ref"]] = saved_attachment.id

        document_ids_by_ref: Dict[str, int] = {}
        all_block_ids: List[str] = []
        for document in sample.documents:
            saved_document = document_repository.upsert_document(
                CanonicalDocumentUpsert(
                    notice_id=notice.id,
                    attachment_id=attachment_ids_by_ref.get(document.get("attachment_ref")),
                    document_kind=DocumentKind(document["document_kind"]),
                    source_label=document["source_label"],
                    canonical_text=document["canonical_text"],
                    blocks=[
                        CanonicalBlock(
                            block_id=block["block_id"],
                            text=block["text"],
                            page_number=block.get("page_number"),
                        )
                        for block in document["blocks"]
                    ],
                )
            )
            document_ids_by_ref[document["document_ref"]] = saved_document.id
            all_block_ids.extend(block["block_id"] for block in document["blocks"])

    return SeededGoldSample(
        sample=sample,
        notice_id=notice.id,
        document_ids_by_ref=document_ids_by_ref,
        all_block_ids=all_block_ids,
        provider_case=materialize_provider_case(sample.provider_case, document_ids_by_ref),
    )


def materialize_provider_case(
    provider_case: GoldProviderCase, document_ids_by_ref: Dict[str, int]
) -> GoldProviderCase:
    """fixture payload 안의 document_ref를 실제 seeded document_id로 치환합니다."""

    if provider_case.payload_template is None:
        return provider_case

    payload_template = provider_case.payload_template or {}
    payload = {
        "scholarship_name": payload_template["scholarship_name"],
        "summary_text": payload_template.get("summary_text"),
        "qualification": payload_template["qualification"],
    }
    evidence_items = payload_template.get("evidence", [])
    materialized_evidence = []
    for evidence in evidence_items:
        materialized_evidence.append(
            {
                "field_name": evidence["field_name"],
                "document_id": document_ids_by_ref[evidence["document_ref"]],
                "block_id": evidence["block_id"],
                "page_number": evidence.get("page_number"),
                "quote_text": evidence["quote_text"],
            }
        )

    payload["evidence"] = materialized_evidence
    return GoldProviderCase(
        behavior=provider_case.behavior,
        payload_template=payload,
    )


def evaluate_seeded_sample(
    *,
    service: ScholarshipRuleExtractionService,
    seeded_sample: SeededGoldSample,
    log_capture: EvaluationLogCapture,
) -> SampleEvaluationResult:
    """seeded sample 하나를 실행하고 field/evidence/fallback/latency metric을 계산합니다."""

    success = False
    error_type: Optional[str] = None
    try:
        service.extract_notice(seeded_sample.notice_id)
        success = True
    except Exception as exc:
        error_type = type(exc).__name__

    log_record = log_capture.latest_for_notice(seeded_sample.notice_id)
    fallback_used = log_record.fallback_used if log_record is not None else False
    latency_ms = log_record.latency_ms if log_record is not None else 0.0
    if log_record is not None and error_type is None:
        error_type = log_record.error_type

    field_matches = 0
    field_total = 0
    evidence_valid_count = 0
    evidence_total = 0
    evidence_coverage_count = 0
    evidence_coverage_total = len(seeded_sample.sample.expected.evidence_block_ids)

    if success:
        predicted_rule, predicted_anchor_block_ids = load_predicted_rule(seeded_sample.notice_id)
        field_matches, field_total = compute_field_accuracy(
            expected=seeded_sample.sample.expected,
            predicted_rule=predicted_rule,
        )
        evidence_valid_count, evidence_total, evidence_coverage_count = compute_evidence_validity(
            expected_block_ids=seeded_sample.sample.expected.evidence_block_ids,
            predicted_anchor_block_ids=predicted_anchor_block_ids,
            known_block_ids=seeded_sample.all_block_ids,
        )
    else:
        field_total = len(build_expected_field_map(seeded_sample.sample.expected))

    return SampleEvaluationResult(
        sample_id=seeded_sample.sample.sample_id,
        success=success,
        field_matches=field_matches,
        field_total=field_total,
        evidence_valid_count=evidence_valid_count,
        evidence_total=evidence_total,
        evidence_coverage_count=evidence_coverage_count,
        evidence_coverage_total=evidence_coverage_total,
        latency_ms=latency_ms,
        fallback_used=fallback_used,
        fallback_expected=seeded_sample.provider_case.behavior != "success",
        error_type=error_type,
    )


def load_predicted_rule(notice_id: int) -> tuple[Dict[str, Any], List[str]]:
    """service 실행 후 저장된 rule과 provenance anchor block id를 읽어 metric 계산용으로 정리합니다."""

    with session_scope() as session:
        rule_repository = ScholarshipRuleRepository(session)
        document_repository = CanonicalDocumentRepository(session)

        saved_rule = rule_repository.list_rules_for_notice(notice_id)[0]
        documents = document_repository.list_documents_for_notice(notice_id)
        anchors = []
        for document in documents:
            anchors.extend(document_repository.list_anchors(document.id))

    predicted_rule = {
        "scholarship_name": saved_rule.scholarship_name,
        "qualification": saved_rule.qualification_json,
    }
    predicted_anchor_block_ids = [anchor.block_id for anchor in anchors]
    return predicted_rule, predicted_anchor_block_ids


def compute_field_accuracy(expected: GoldExpectedRule, predicted_rule: Dict[str, Any]) -> tuple[int, int]:
    """gold expected field map과 predicted field map을 exact match 기준으로 비교합니다."""

    expected_fields = build_expected_field_map(expected)
    predicted_fields = build_predicted_field_map(predicted_rule)

    matches = 0
    for field_name, expected_value in expected_fields.items():
        predicted_value = predicted_fields.get(field_name)
        if normalize_value(predicted_value) == normalize_value(expected_value):
            matches += 1
    return matches, len(expected_fields)


def compute_evidence_validity(
    *,
    expected_block_ids: List[str],
    predicted_anchor_block_ids: List[str],
    known_block_ids: List[str],
) -> tuple[int, int, int]:
    """예상된 근거 block과 실제 anchor block을 비교해 validity와 coverage를 계산합니다."""

    known_block_set = set(known_block_ids)
    predicted_block_set = set(predicted_anchor_block_ids)
    expected_block_set = set(expected_block_ids)

    valid_count = sum(1 for block_id in predicted_anchor_block_ids if block_id in known_block_set)
    coverage_count = len(predicted_block_set & expected_block_set)
    return valid_count, len(predicted_anchor_block_ids), coverage_count


def summarize_mode(mode: str, results: List[SampleEvaluationResult]) -> ModeEvaluationSummary:
    """sample 단위 결과를 mode summary로 집계합니다."""

    latency_values = [result.latency_ms for result in results]
    return ModeEvaluationSummary(
        mode=mode,
        sample_count=len(results),
        success_count=sum(1 for result in results if result.success),
        field_match_count=sum(result.field_matches for result in results),
        field_total_count=sum(result.field_total for result in results),
        evidence_valid_count=sum(result.evidence_valid_count for result in results),
        evidence_total_count=sum(result.evidence_total for result in results),
        evidence_coverage_count=sum(result.evidence_coverage_count for result in results),
        evidence_coverage_total=sum(result.evidence_coverage_total for result in results),
        fallback_expected_count=sum(1 for result in results if result.fallback_expected),
        fallback_success_count=sum(
            1
            for result in results
            if result.fallback_expected and result.success and result.fallback_used
        ),
        average_latency_ms=sum(latency_values) / len(latency_values) if latency_values else 0.0,
        p95_latency_ms=compute_p95(latency_values),
    )


def build_expected_field_map(expected: GoldExpectedRule) -> Dict[str, Any]:
    """gold rule을 field-level exact match 계산용 flat map으로 변환합니다."""

    field_map = {"scholarship_name": expected.scholarship_name}
    for key, value in expected.qualification.items():
        field_map["qualification.{0}".format(key)] = value
    return field_map


def build_predicted_field_map(predicted_rule: Dict[str, Any]) -> Dict[str, Any]:
    """저장된 predicted rule을 expected와 같은 flat field map으로 변환합니다."""

    field_map = {"scholarship_name": predicted_rule.get("scholarship_name")}
    for key, value in predicted_rule.get("qualification", {}).items():
        field_map["qualification.{0}".format(key)] = value
    return field_map


def normalize_value(value: Any) -> Any:
    """list ordering 차이 같은 비교 노이즈를 줄이기 위해 값을 정규화합니다."""

    if isinstance(value, list):
        return sorted(normalize_value(item) for item in value)
    return value


def compute_p95(values: List[float]) -> float:
    """소규모 sample에서도 재현 가능한 inclusive 방식의 p95를 계산합니다."""

    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]

    position = (len(sorted_values) - 1) * 0.95
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    weight = position - lower_index
    return lower_value + (upper_value - lower_value) * weight


def format_summary_markdown(summaries: Dict[str, ModeEvaluationSummary]) -> str:
    """README와 benchmark 문서에 붙여넣기 쉬운 markdown 표를 만듭니다."""

    rows = [
        "| Mode | Success Rate | Field Exact Match | Evidence Validity | Evidence Coverage | Fallback Recovery | Avg Latency | p95 Latency |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode in ("heuristic", "llm", "hybrid"):
        summary = summaries[mode]
        rows.append(
            "| {mode} | {success:.2%} | {field:.2%} | {valid:.2%} | {coverage:.2%} | {recovery:.2%} | {avg:.2f}ms | {p95:.2f}ms |".format(
                mode=summary.mode,
                success=summary.extraction_success_rate,
                field=summary.field_exact_match_rate,
                valid=summary.evidence_valid_rate,
                coverage=summary.evidence_coverage_rate,
                recovery=summary.fallback_recovery_rate,
                avg=summary.average_latency_ms,
                p95=summary.p95_latency_ms,
            )
        )
    return "\n".join(rows)


def parse_datetime(value: str) -> datetime:
    """fixture에 들어 있는 ISO datetime 문자열을 naive datetime으로 변환합니다."""

    return datetime.fromisoformat(value)


@contextmanager
def temporary_database_url(database_url: str) -> Iterator[None]:
    """evaluation 중에만 전역 세션 팩토리가 임시 SQLite를 보도록 환경 변수를 덮어씁니다."""

    previous_database_url = os.environ.get("JBNU_DATABASE_URL")
    os.environ["JBNU_DATABASE_URL"] = database_url
    reset_settings_cache()
    reset_engine_cache()
    try:
        yield
    finally:
        if previous_database_url is None:
            os.environ.pop("JBNU_DATABASE_URL", None)
        else:
            os.environ["JBNU_DATABASE_URL"] = previous_database_url
        reset_settings_cache()
        reset_engine_cache()


def main() -> None:
    """phase 8.6 synthetic extraction evaluation CLI entrypoint입니다."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixtures-dir",
        default="tests/fixtures/phase8_gold_set",
        help="gold evaluation fixture directory",
    )
    args = parser.parse_args()

    fixtures_dir = Path(args.fixtures_dir)
    summaries = evaluate_all_modes(fixtures_dir)

    print(format_summary_markdown(summaries))
    print()
    print(
        json.dumps(
            {
                mode: {
                    "sample_count": summary.sample_count,
                    "success_rate": summary.extraction_success_rate,
                    "field_exact_match_rate": summary.field_exact_match_rate,
                    "evidence_valid_rate": summary.evidence_valid_rate,
                    "evidence_coverage_rate": summary.evidence_coverage_rate,
                    "fallback_recovery_rate": summary.fallback_recovery_rate,
                    "average_latency_ms": summary.average_latency_ms,
                    "p95_latency_ms": summary.p95_latency_ms,
                }
                for mode, summary in summaries.items()
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
