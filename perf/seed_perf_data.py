from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import reset_settings_cache
from app.core.time import ASIA_SEOUL
from app.db import create_all_tables, reset_engine_cache, session_scope
from app.models import CanonicalDocument, DocumentKind, ProvenanceAnchor, RuleStatus, ScholarshipNotice, ScholarshipRule


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed scholarship performance benchmark data.")
    parser.add_argument("--count", type=int, default=1200, help="Number of published rules to seed.")
    parser.add_argument("--anchors", type=int, default=6, help="Number of provenance anchors per rule.")
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("/tmp/jbnu-scholarship-perf.sqlite3"),
        help="SQLite database path used for perf runs.",
    )
    return parser.parse_args()


def build_long_quote(index: int, anchor_index: int) -> str:
    return (
        f"{index}번 장학금 규정 요약 {anchor_index}. "
        "직전학기 평점 평균 3.20 이상인 재학생을 대상으로 하며, "
        "소득분위 8분위 이하 학생에게 우선 선발 기회를 제공합니다. "
        "신청 시 장학금 지원서, 성적증명서, 통장사본을 제출해야 합니다."
    )


def main() -> None:
    args = parse_args()
    if args.database_path.exists():
        args.database_path.unlink()

    import os

    os.environ["JBNU_DATABASE_URL"] = f"sqlite+pysqlite:///{args.database_path}"
    reset_settings_cache()
    reset_engine_cache()
    create_all_tables()

    reference_time = datetime(2026, 3, 22, 12, 0, tzinfo=ASIA_SEOUL)

    with session_scope() as session:
        for index in range(1, args.count + 1):
            notice = ScholarshipNotice(
                source_board="perf-board-main" if index % 2 else "perf-board-software",
                source_notice_id=f"perf-{index}",
                title=f"2026학년도 장학금 통합 안내 {index}",
                notice_url=f"https://perf.local/notices/{index}",
                department_name="학생지원과" if index % 2 else "소프트웨어공학과",
                published_at=reference_time - timedelta(days=index % 30),
                application_started_at=reference_time - timedelta(days=2),
                application_ended_at=reference_time + timedelta(days=(index % 9) + 1),
                summary="성적, 근로, 복지 장학 제도를 통합 정리한 공지입니다.",
                raw_html_path=None,
            )
            session.add(notice)
            session.flush()

            blocks = []
            anchors = []
            provenance_keys = []
            canonical_lines = []
            for anchor_index in range(1, args.anchors + 1):
                block_id = f"block-{anchor_index}"
                quote_text = build_long_quote(index, anchor_index)
                canonical_lines.append(quote_text)
                blocks.append(
                    {
                        "block_id": block_id,
                        "block_type": "p",
                        "text": quote_text,
                    }
                )
                anchor_key = f"anchor-{anchor_index}"
                provenance_keys.append(anchor_key)
                anchors.append(
                    ProvenanceAnchor(
                        anchor_key=anchor_key,
                        block_id=block_id,
                        quote_text=quote_text,
                        page_number=1,
                        locator_json={"block_id": block_id},
                    )
                )

            document = CanonicalDocument(
                notice_id=notice.id,
                attachment_id=None,
                document_kind=DocumentKind.NOTICE_HTML,
                source_label=f"perf-doc-{index}",
                canonical_text="\n".join(canonical_lines),
                blocks_json=blocks,
                metadata_json={"seed": "perf", "anchor_count": args.anchors},
                provenance_anchors=anchors,
            )
            session.add(document)
            session.flush()

            scholarship_name = (
                f"성적우수장학금 {index}" if index % 3 else f"국가근로장학금 {index}"
            )
            qualification = {
                "gpa_min": 3.2 if index % 3 else 2.8,
                "income_bracket_max": 8 if index % 4 else 6,
                "grade_levels": [1, 2, 3, 4] if index % 5 else [2, 3, 4],
                "enrollment_status": ["재학생"],
                "required_documents": ["장학금지원서", "성적증명서", "통장사본"],
            }
            rule = ScholarshipRule(
                notice_id=notice.id,
                document_id=document.id,
                scholarship_name=scholarship_name,
                rule_version="v1",
                application_started_at=notice.application_started_at,
                application_ended_at=notice.application_ended_at,
                summary_text=(
                    "성적 기준과 소득 기준을 함께 확인하는 장학금 공지"
                    if index % 3
                    else "근로 유형과 신청 기간을 함께 확인하는 장학금 공지"
                ),
                qualification_json=qualification,
                provenance_keys_json=provenance_keys,
                status=RuleStatus.PUBLISHED,
            )
            session.add(rule)

    print(
        "seeded",
        {
            "database_path": str(args.database_path),
            "rule_count": args.count,
            "anchors_per_rule": args.anchors,
        },
    )


if __name__ == "__main__":
    main()
