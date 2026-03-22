from __future__ import annotations

from datetime import timedelta
from typing import Dict

from app.core.time import ASIA_SEOUL
from app.db import session_scope
from app.models import DocumentKind, RuleStatus
from app.repositories import CanonicalDocumentRepository, ScholarshipNoticeRepository, ScholarshipRuleRepository
from app.schemas import CanonicalBlock, CanonicalDocumentUpsert, ProvenanceAnchorCreate, ScholarshipNoticeUpsert, ScholarshipRuleCreate
from tests.support.search_seed import REFERENCE_TIME, seed_phase6_search_data


def seed_phase7_eligibility_data(monkeypatch, tmp_path) -> Dict[str, int]:
    """Extend phase 6 seed data with ineligible and insufficient-info rules."""

    seed_result = seed_phase6_search_data(monkeypatch, tmp_path)

    with session_scope() as session:
        notice_repository = ScholarshipNoticeRepository(session)
        document_repository = CanonicalDocumentRepository(session)
        rule_repository = ScholarshipRuleRepository(session)

        ineligible_notice = notice_repository.upsert_notice(
            ScholarshipNoticeUpsert(
                source_board="jbnu-main",
                source_notice_id="open-competitive-001",
                title="2026학년도 최우수성적장학금 신청 안내",
                notice_url="https://www.jbnu.ac.kr/kor/?menuID=139&pno=1&mode=view&no=100001",
                published_at=REFERENCE_TIME - timedelta(days=3),
                department_name="학생지원과",
                application_started_at=REFERENCE_TIME - timedelta(days=1),
                application_ended_at=REFERENCE_TIME + timedelta(days=6),
                summary="평점이 매우 높은 학생을 위한 장학금 공지",
                raw_html_path=None,
            )
        )
        ineligible_document = _add_document_with_anchor(
            document_repository,
            notice_id=ineligible_notice.id,
            source_label="manual-ineligible-notice",
            scholarship_name="최우수성적장학금",
            quote_text="직전학기 평점평균 4.00 이상인 재학생만 신청할 수 있습니다.",
            anchor_key="ineligible-gpa",
        )
        rule_repository.replace_rules(
            ineligible_notice.id,
            [
                ScholarshipRuleCreate(
                    notice_id=ineligible_notice.id,
                    document_id=ineligible_document.id,
                    scholarship_name="최우수성적장학금",
                    application_started_at=ineligible_notice.application_started_at,
                    application_ended_at=ineligible_notice.application_ended_at,
                    summary_text="평점 4.00 이상 재학생 대상 장학금",
                    qualification={
                        "gpa_min": 4.0,
                        "enrollment_status": ["재학생"],
                    },
                    provenance_keys=["ineligible-gpa"],
                    status=RuleStatus.PUBLISHED,
                )
            ],
        )

        insufficient_notice = notice_repository.upsert_notice(
            ScholarshipNoticeUpsert(
                source_board="jbnu-main",
                source_notice_id="open-freshman-001",
                title="2026학년도 새내기장학금 신청 안내",
                notice_url="https://www.jbnu.ac.kr/kor/?menuID=139&pno=1&mode=view&no=100002",
                published_at=REFERENCE_TIME - timedelta(days=2),
                department_name="학생지원과",
                application_started_at=REFERENCE_TIME - timedelta(days=1),
                application_ended_at=REFERENCE_TIME + timedelta(days=4),
                summary="신입생 대상 장학금 공지",
                raw_html_path=None,
            )
        )
        insufficient_document = _add_document_with_anchor(
            document_repository,
            notice_id=insufficient_notice.id,
            source_label="manual-insufficient-notice",
            scholarship_name="새내기장학금",
            quote_text="1학년 재학생을 대상으로 하며 신청서 제출이 필요합니다.",
            anchor_key="insufficient-grade",
        )
        rule_repository.replace_rules(
            insufficient_notice.id,
            [
                ScholarshipRuleCreate(
                    notice_id=insufficient_notice.id,
                    document_id=insufficient_document.id,
                    scholarship_name="새내기장학금",
                    application_started_at=insufficient_notice.application_started_at,
                    application_ended_at=insufficient_notice.application_ended_at,
                    summary_text="1학년 재학생 대상 장학금",
                    qualification={
                        "grade_levels": [1],
                        "enrollment_status": ["재학생"],
                        "required_documents": ["신청서"],
                    },
                    provenance_keys=["insufficient-grade"],
                    status=RuleStatus.PUBLISHED,
                )
            ],
        )

        seed_result["ineligible_rule_id"] = rule_repository.list_rules_for_notice(ineligible_notice.id)[0].id
        seed_result["insufficient_rule_id"] = rule_repository.list_rules_for_notice(insufficient_notice.id)[0].id

    return seed_result


def _add_document_with_anchor(
    document_repository: CanonicalDocumentRepository,
    *,
    notice_id: int,
    source_label: str,
    scholarship_name: str,
    quote_text: str,
    anchor_key: str,
):
    """Create one canonical notice document and one provenance anchor for seeded rules."""

    document = document_repository.upsert_document(
        CanonicalDocumentUpsert(
            notice_id=notice_id,
            attachment_id=None,
            document_kind=DocumentKind.NOTICE_HTML,
            source_label=source_label,
            canonical_text=quote_text,
            blocks=[
                CanonicalBlock(
                    block_id="block-1",
                    text=quote_text,
                )
            ],
            metadata={"seeded": scholarship_name, "timezone": ASIA_SEOUL.tzname(None)},
        )
    )
    document_repository.replace_anchors(
        document.id,
        [
            ProvenanceAnchorCreate(
                document_id=document.id,
                anchor_key=anchor_key,
                block_id="block-1",
                quote_text=quote_text,
                locator={"block_id": "block-1"},
            )
        ],
    )
    return document
