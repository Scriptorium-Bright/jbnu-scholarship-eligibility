from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from app.db import session_scope
from app.extractors import HeuristicScholarshipRuleExtractor, StructuredRuleExtractor
from app.repositories import CanonicalDocumentRepository, ScholarshipNoticeRepository, ScholarshipRuleRepository
from app.schemas import ProvenanceAnchorCreate, ScholarshipRuleCreate


class ScholarshipRuleExtractionService:
    """Extract structured scholarship rules and provenance from canonical documents."""

    def __init__(self, extractor: Optional[StructuredRuleExtractor] = None):
        """
        공용 structured extraction contract를 따르는 구현체를 주입받아 초기화합니다.
        phase 8부터는 heuristic extractor와 future LLM extractor가 같은 자리에서 교체됩니다.
        """

        self._extractor = extractor or HeuristicScholarshipRuleExtractor()

    def extract_notice(self, notice_id: int):
        """
        해당 공지사항에 속한 정규화 문서 집합을 불러와 장학금 선발 규정과 근거(Provenance)를 체계적으로 추출합니다.
        생성된 구조화된 규칙들을 DB의 기존 룰 내역 및 앵커 데이터와 원자적으로 교체(Replace)합니다.
        """

        with session_scope() as session:
            notice_repository = ScholarshipNoticeRepository(session)
            document_repository = CanonicalDocumentRepository(session)
            rule_repository = ScholarshipRuleRepository(session)

            notice = notice_repository.get_by_id(notice_id)
            if notice is None:
                raise ValueError("Notice does not exist: {0}".format(notice_id))

            canonical_documents = document_repository.list_documents_for_notice(notice_id)
            if not canonical_documents:
                raise ValueError("Notice does not have canonical documents: {0}".format(notice_id))

            extracted_rule = self._extractor.extract_notice_rule(
                notice_title=notice.title,
                canonical_documents=canonical_documents,
                application_started_at=notice.application_started_at,
                application_ended_at=notice.application_ended_at,
                fallback_summary=notice.summary,
            )

            saved_rules = rule_repository.replace_rules(
                notice_id=notice.id,
                rules=[
                    ScholarshipRuleCreate(
                        notice_id=notice.id,
                        document_id=extracted_rule.source_document_id,
                        scholarship_name=extracted_rule.scholarship_name,
                        application_started_at=extracted_rule.application_started_at,
                        application_ended_at=extracted_rule.application_ended_at,
                        summary_text=extracted_rule.summary_text,
                        qualification=extracted_rule.qualification,
                        provenance_keys=[anchor.anchor_key for anchor in extracted_rule.provenance_anchors],
                        status=extracted_rule.status,
                    )
                ],
            )

            anchors_by_document: Dict[int, List[ProvenanceAnchorCreate]] = defaultdict(list)
            for anchor in extracted_rule.provenance_anchors:
                anchors_by_document[anchor.document_id].append(
                    ProvenanceAnchorCreate(
                        document_id=anchor.document_id,
                        anchor_key=anchor.anchor_key,
                        block_id=anchor.block_id,
                        quote_text=anchor.quote_text,
                        page_number=anchor.page_number,
                        locator=anchor.locator,
                    )
                )

            for document_id, anchors in anchors_by_document.items():
                document_repository.replace_anchors(document_id=document_id, anchors=anchors)

            return saved_rules
