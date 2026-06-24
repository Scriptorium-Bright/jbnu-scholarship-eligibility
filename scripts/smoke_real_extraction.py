from __future__ import annotations

import argparse
import json
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
from app.services import ScholarshipRuleExtractionService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Real provider를 사용해 notice 1건의 structured extraction smoke test를 실행합니다."
    )
    parser.add_argument(
        "--notice-id",
        type=int,
        default=None,
        help="검증할 notice id. 생략하면 canonical document가 있는 최신 notice를 자동 선택합니다.",
    )
    return parser.parse_args()


def ensure_real_llm_config() -> int:
    settings = get_settings()
    errors = []

    if settings.llm_provider != "openai_compatible":
        errors.append(
            "JBNU_LLM_PROVIDER=openai_compatible 로 설정해야 real extraction smoke test를 실행할 수 있습니다."
        )
    if not settings.llm_api_key:
        errors.append(
            "JBNU_LLM_API_KEY가 비어 있습니다. .env를 확인하세요. .env.example은 자동 로드되지 않습니다."
        )

    if errors:
        for message in errors:
            print("[config error] {0}".format(message), file=sys.stderr)
        return 1

    print(
        "[config] llm_provider={provider} model={model}".format(
            provider=settings.llm_provider,
            model=settings.llm_model,
        )
    )
    return 0


def resolve_notice(notice_id: Optional[int]) -> Tuple[int, str, int]:
    with session_scope() as session:
        notice_repository = ScholarshipNoticeRepository(session)
        document_repository = CanonicalDocumentRepository(session)

        if notice_id is not None:
            notice = notice_repository.get_by_id(notice_id)
            if notice is None:
                raise ValueError("Notice does not exist: {0}".format(notice_id))

            document_count = len(document_repository.list_documents_for_notice(notice.id))
            if document_count == 0:
                raise ValueError(
                    "Notice does not have canonical documents: {0}".format(notice.id)
                )
            return notice.id, notice.title, document_count

        for notice in notice_repository.list_recent_notices(limit=50):
            document_count = len(document_repository.list_documents_for_notice(notice.id))
            if document_count > 0:
                return notice.id, notice.title, document_count

    raise ValueError(
        "Canonical document가 있는 notice를 찾지 못했습니다. 먼저 수집/정규화 데이터를 확인하세요."
    )


def print_rules(notice_id: int) -> None:
    with session_scope() as session:
        rule_repository = ScholarshipRuleRepository(session)
        rules = rule_repository.list_rules_for_notice(notice_id)

    print("[result] extracted_rule_count={0}".format(len(rules)))
    for index, rule in enumerate(rules, start=1):
        qualification = dict(rule.qualification_json)
        qualification_keys = sorted(qualification.keys())
        preview = {
            "scholarship_name": rule.scholarship_name,
            "status": str(rule.status.value),
            "qualification_keys": qualification_keys,
            "qualification": qualification,
            "provenance_key_count": len(rule.provenance_keys_json),
        }
        print("[rule {0}]".format(index))
        print(json.dumps(preview, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    config_result = ensure_real_llm_config()
    if config_result != 0:
        return config_result

    try:
        selected_notice_id, selected_notice_title, document_count = resolve_notice(args.notice_id)
    except Exception as exc:
        print("[selection error] {0}".format(exc), file=sys.stderr)
        return 1

    print(
        "[notice] id={id} title={title} document_count={count}".format(
            id=selected_notice_id,
            title=selected_notice_title,
            count=document_count,
        )
    )

    started_at = perf_counter()
    try:
        ScholarshipRuleExtractionService().extract_notice(selected_notice_id)
    except Exception as exc:
        print("[extraction error] {0}: {1}".format(type(exc).__name__, exc), file=sys.stderr)
        return 1
    elapsed_ms = (perf_counter() - started_at) * 1000

    print("[timing] extraction_elapsed_ms={0:.2f}".format(elapsed_ms))
    print_rules(selected_notice_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
