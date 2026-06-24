from __future__ import annotations

import argparse
import sys
from pathlib import Path
from time import perf_counter
from typing import Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import get_settings
from app.db import session_scope
from app.repositories import CanonicalDocumentRepository, ScholarshipNoticeRepository, ScholarshipRuleRepository
from app.services import ScholarshipRagAnswerService, ScholarshipRagIndexingService, ScholarshipRuleExtractionService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Real provider를 사용해 RAG retrieval + answer smoke test를 실행합니다."
    )
    parser.add_argument(
        "--notice-id",
        type=int,
        default=None,
        help="검증할 notice id. 생략하면 rule/canonical document가 있는 최신 notice를 자동 선택합니다.",
    )
    parser.add_argument(
        "--question",
        type=str,
        default=None,
        help="질문 문자열. 생략하면 선택된 장학금명 기준 기본 질문을 생성합니다.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="RAG evidence chunk limit",
    )
    return parser.parse_args()


def ensure_real_rag_config() -> int:
    settings = get_settings()
    errors = []

    if settings.llm_provider != "openai_compatible":
        errors.append(
            "JBNU_LLM_PROVIDER=openai_compatible 로 설정해야 real RAG smoke test를 실행할 수 있습니다."
        )
    if not settings.llm_api_key:
        errors.append(
            "JBNU_LLM_API_KEY가 비어 있습니다. .env를 확인하세요. .env.example은 자동 로드되지 않습니다."
        )
    if settings.embedding_provider != "openai_compatible":
        errors.append(
            "JBNU_EMBEDDING_PROVIDER=openai_compatible 로 설정해야 real RAG smoke test를 실행할 수 있습니다."
        )
    if not settings.embedding_api_key:
        errors.append(
            "JBNU_EMBEDDING_API_KEY가 비어 있습니다. .env를 확인하세요. .env.example은 자동 로드되지 않습니다."
        )

    if errors:
        for message in errors:
            print("[config error] {0}".format(message), file=sys.stderr)
        return 1

    print(
        "[config] llm_provider={llm_provider} llm_model={llm_model} embedding_provider={emb_provider} embedding_model={emb_model}".format(
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            emb_provider=settings.embedding_provider,
            emb_model=settings.embedding_model,
        )
    )
    return 0


def resolve_notice(notice_id: Optional[int]) -> Tuple[int, str, Optional[str], int]:
    with session_scope() as session:
        notice_repository = ScholarshipNoticeRepository(session)
        document_repository = CanonicalDocumentRepository(session)
        rule_repository = ScholarshipRuleRepository(session)

        if notice_id is not None:
            notice = notice_repository.get_by_id(notice_id)
            if notice is None:
                raise ValueError("Notice does not exist: {0}".format(notice_id))
            documents = document_repository.list_documents_for_notice(notice.id)
            if not documents:
                raise ValueError(
                    "Notice does not have canonical documents: {0}".format(notice.id)
                )
            rules = rule_repository.list_rules_for_notice(notice.id)
            scholarship_name = rules[0].scholarship_name if rules else None
            return notice.id, notice.title, scholarship_name, len(documents)

        seen_notice_ids = set()
        for rule in rule_repository.list_published_rules(limit=50, include_provenance_anchors=False):
            if rule.notice_id in seen_notice_ids:
                continue
            seen_notice_ids.add(rule.notice_id)
            documents = document_repository.list_documents_for_notice(rule.notice_id)
            if documents:
                return rule.notice_id, rule.notice.title, rule.scholarship_name, len(documents)

        for notice in notice_repository.list_recent_notices(limit=50):
            if notice.id in seen_notice_ids:
                continue
            documents = document_repository.list_documents_for_notice(notice.id)
            if documents:
                rules = rule_repository.list_rules_for_notice(notice.id)
                scholarship_name = rules[0].scholarship_name if rules else None
                return notice.id, notice.title, scholarship_name, len(documents)

    raise ValueError(
        "RAG smoke test에 사용할 notice를 찾지 못했습니다. canonical document와 rule 데이터를 확인하세요."
    )


def ensure_rule_exists(notice_id: int) -> None:
    with session_scope() as session:
        rule_repository = ScholarshipRuleRepository(session)
        rules = rule_repository.list_rules_for_notice(notice_id)
        if rules:
            return

    print("[preflight] published rule이 없어 extraction을 먼저 실행합니다.")
    ScholarshipRuleExtractionService().extract_notice(notice_id)


def build_default_question(
    *,
    scholarship_name: Optional[str],
    notice_title: str,
) -> str:
    base_name = scholarship_name or notice_title
    return "{0} 지원 자격이 뭐야?".format(base_name)


def print_response_summary(response) -> None:
    print(
        "[response] answer_mode={mode} retrieval_mode={retrieval_mode} citations={citation_count} prompt_truncated={truncated} keyword_fallback_used={fallback}".format(
            mode=response.answer_mode,
            retrieval_mode=response.retrieval_mode,
            citation_count=len(response.citations),
            truncated=response.prompt_truncated,
            fallback=response.keyword_fallback_used,
        )
    )
    if response.recommended_endpoint:
        print("[response] recommended_endpoint={0}".format(response.recommended_endpoint))
    if response.failure_reason:
        print("[response] failure_reason={0}".format(response.failure_reason))
    print("[answer]")
    print(response.answer_text)

    for index, citation in enumerate(response.citations[:3], start=1):
        print(
            "[citation {index}] notice_id={notice_id} source_label={source_label} block_id={block_id} score={score:.6f}".format(
                index=index,
                notice_id=citation.notice_id,
                source_label=citation.source_label,
                block_id=citation.block_id,
                score=citation.final_score,
            )
        )
        print(citation.quote_text)


def main() -> int:
    args = parse_args()
    config_result = ensure_real_rag_config()
    if config_result != 0:
        return config_result

    try:
        selected_notice_id, selected_notice_title, scholarship_name, document_count = resolve_notice(
            args.notice_id
        )
    except Exception as exc:
        print("[selection error] {0}".format(exc), file=sys.stderr)
        return 1

    print(
        "[notice] id={id} title={title} document_count={count} scholarship_name={scholarship_name}".format(
            id=selected_notice_id,
            title=selected_notice_title,
            count=document_count,
            scholarship_name=scholarship_name or "-",
        )
    )

    try:
        ensure_rule_exists(selected_notice_id)
    except Exception as exc:
        print("[preflight error] {0}: {1}".format(type(exc).__name__, exc), file=sys.stderr)
        return 1

    indexing_started_at = perf_counter()
    try:
        chunk_rows = ScholarshipRagIndexingService().rebuild_notice(selected_notice_id)
    except Exception as exc:
        print("[indexing error] {0}: {1}".format(type(exc).__name__, exc), file=sys.stderr)
        return 1
    indexing_elapsed_ms = (perf_counter() - indexing_started_at) * 1000

    question = args.question or build_default_question(
        scholarship_name=scholarship_name,
        notice_title=selected_notice_title,
    )
    print("[question] {0}".format(question))
    print(
        "[indexing] rebuilt_chunk_count={count} elapsed_ms={elapsed:.2f}".format(
            count=len(chunk_rows),
            elapsed=indexing_elapsed_ms,
        )
    )

    answer_started_at = perf_counter()
    try:
        response = ScholarshipRagAnswerService().answer(question, limit=max(args.limit, 1))
    except Exception as exc:
        print("[answer error] {0}: {1}".format(type(exc).__name__, exc), file=sys.stderr)
        return 1
    answer_elapsed_ms = (perf_counter() - answer_started_at) * 1000

    print("[timing] answer_elapsed_ms={0:.2f}".format(answer_elapsed_ms))
    print_response_summary(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
