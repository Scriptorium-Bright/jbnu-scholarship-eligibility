from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db import create_all_tables, session_scope
from app.models import CanonicalDocument, ScholarshipNotice, ScholarshipRule
from app.repositories import CanonicalDocumentRepository, ScholarshipNoticeRepository
from app.schemas import CanonicalBlock, CanonicalDocumentUpsert, NoticeAttachmentUpsert, ScholarshipNoticeUpsert


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="phase8 gold fixture를 이용해 local DB에 샘플 장학 공지와 canonical document를 적재합니다."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=2,
        help="적재할 fixture 개수. 기본값은 2건입니다.",
    )
    return parser.parse_args()


def load_fixture_payloads(limit: int) -> List[dict]:
    fixtures_dir = ROOT_DIR / "tests" / "fixtures" / "phase8_gold_set"
    payloads: List[dict] = []
    for path in sorted(fixtures_dir.glob("*.json"))[: max(int(limit), 1)]:
        payloads.append(json.loads(path.read_text(encoding="utf-8")))
    if not payloads:
        raise ValueError("phase8 gold fixture를 찾지 못했습니다.")
    return payloads


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def seed_payload(payload: dict) -> int:
    with session_scope() as session:
        notice_repository = ScholarshipNoticeRepository(session)
        document_repository = CanonicalDocumentRepository(session)

        notice_payload = payload["notice"]
        notice = notice_repository.upsert_notice(
            ScholarshipNoticeUpsert(
                source_board=notice_payload["source_board"],
                source_notice_id=notice_payload["source_notice_id"],
                title=notice_payload["title"],
                notice_url=notice_payload["notice_url"],
                published_at=parse_datetime(notice_payload["published_at"]),
                application_started_at=parse_datetime(notice_payload["application_started_at"]),
                application_ended_at=parse_datetime(notice_payload["application_ended_at"]),
                summary=notice_payload.get("summary"),
            )
        )

        attachment_ids_by_ref = {}
        for attachment in payload.get("attachments", []):
            saved_attachment = notice_repository.add_or_update_attachment(
                notice.id,
                NoticeAttachmentUpsert(
                    source_url=attachment["source_url"],
                    file_name=attachment["file_name"],
                    media_type=attachment["media_type"],
                ),
            )
            attachment_ids_by_ref[attachment["attachment_ref"]] = saved_attachment.id

        for document in payload["documents"]:
            document_repository.upsert_document(
                CanonicalDocumentUpsert(
                    notice_id=notice.id,
                    attachment_id=attachment_ids_by_ref.get(document.get("attachment_ref")),
                    document_kind=document["document_kind"],
                    source_label=document["source_label"],
                    canonical_text=document["canonical_text"],
                    blocks=[
                        CanonicalBlock(
                            block_id=block["block_id"],
                            text=block["text"],
                            page_number=block.get("page_number"),
                            metadata=block.get("metadata", {}),
                        )
                        for block in document["blocks"]
                    ],
                )
            )

        return notice.id


def print_summary() -> None:
    with session_scope() as session:
        notice_count = session.query(ScholarshipNotice).count()
        document_count = session.query(CanonicalDocument).count()
        rule_count = session.query(ScholarshipRule).count()
        recent_notices = (
            session.query(ScholarshipNotice.id, ScholarshipNotice.title)
            .order_by(ScholarshipNotice.id.asc())
            .limit(10)
            .all()
        )

    print("[summary] scholarship_notices={0}".format(notice_count))
    print("[summary] canonical_documents={0}".format(document_count))
    print("[summary] scholarship_rules={0}".format(rule_count))
    for notice_id, title in recent_notices:
        print("[notice] id={0} title={1}".format(notice_id, title))


def main() -> int:
    args = parse_args()
    create_all_tables()

    payloads = load_fixture_payloads(args.count)
    seeded_notice_ids = [seed_payload(payload) for payload in payloads]

    print("[seeded] notice_ids={0}".format(",".join(str(notice_id) for notice_id in seeded_notice_ids)))
    print_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
