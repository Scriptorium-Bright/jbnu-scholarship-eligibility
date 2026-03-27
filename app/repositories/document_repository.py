from __future__ import annotations

from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models import CanonicalDocument, ProvenanceAnchor
from app.schemas import CanonicalDocumentUpsert, ProvenanceAnchorCreate


class CanonicalDocumentRepository:
    """Persist canonical text documents and provenance anchors."""

    def __init__(self, session: Session):
        self.session = session

    def get_document(
        self,
        notice_id: int,
        attachment_id: Optional[int],
        document_kind: str,
    ) -> Optional[CanonicalDocument]:
        """
        특정 공지사항 번호 및 첨부파일 출처(비어있을 시 본문)에 속한 단일 정규화 문서 정보를 DB에서 가져옵니다.
        조건 추출을 위한 하위 앵커(Anchor) 근거 데이터까지 한방 쿼리(Pre-load)로 묶어서 반환합니다.
        """

        statement = (
            select(CanonicalDocument)
            .where(CanonicalDocument.notice_id == notice_id)
            .where(CanonicalDocument.attachment_id == attachment_id)
            .where(CanonicalDocument.document_kind == document_kind)
            .options(selectinload(CanonicalDocument.provenance_anchors))
        )
        return self.session.scalar(statement)

    def list_documents_for_notice(self, notice_id: int) -> List[CanonicalDocument]:
        """
        단일 공지사항 메타모델에 귀속된 본문과 첨부파일 등 모든 정규화 문서들을 정해진 순서에 맞춰 나열해줍니다.
        항상 예측 가능하도록 본문이 먼저 오고, 첨부파일들은 ID 순서대로 안정적으로 처리하게 정렬합니다.
        """

        statement = (
            select(CanonicalDocument)
            .where(CanonicalDocument.notice_id == notice_id)
            .order_by(CanonicalDocument.attachment_id.is_not(None), CanonicalDocument.id.asc())
        )
        return list(self.session.scalars(statement))

    def upsert_document(self, payload: CanonicalDocumentUpsert) -> CanonicalDocument:
        """
        전달받은 신규/업데이트용 정규화 문서 모델 단일 객체를 DB 테이블에 삽입하거나 기존 레코드가 있다면 갱신(Refresh)합니다.
        딕셔너리 내부의 불규칙한 Pydantic 타입 제약들을 사전에 순수 JSON 데이터 형태로 통일된 뒤 저장 처리됩니다.
        """

        document = self.get_document(
            notice_id=payload.notice_id,
            attachment_id=payload.attachment_id,
            document_kind=payload.document_kind,
        )
        payload_data = payload.model_dump()
        payload_data["blocks_json"] = [block.model_dump() for block in payload.blocks]
        payload_data["metadata_json"] = payload_data.pop("metadata")
        payload_data.pop("blocks")

        if document is None:
            document = CanonicalDocument(**payload_data)
            self.session.add(document)
        else:
            for field_name, value in payload_data.items():
                setattr(document, field_name, value)

        self.session.flush()
        return document

    def replace_anchors(
        self,
        document_id: int,
        anchors: List[ProvenanceAnchorCreate],
    ) -> List[ProvenanceAnchor]:
        """
        룰 추출 과정에서 생성되어 특정 정규화 문서에 딸린 근거 데이터 포인트 집합 전체(Anchors)를 원자적으로 처리합니다.
        기존의 찌꺼기를 일괄 삭제 처리하고, 새로 파싱된 최신 앵커들로 완전히 통째 교체합니다.
        """

        self.session.execute(
            delete(ProvenanceAnchor).where(ProvenanceAnchor.document_id == document_id)
        )

        saved_anchors = []
        for payload in anchors:
            payload_data = payload.model_dump()
            payload_data["locator_json"] = payload_data.pop("locator")
            anchor = ProvenanceAnchor(**payload_data)
            self.session.add(anchor)
            saved_anchors.append(anchor)

        self.session.flush()
        return saved_anchors

    def list_anchors(self, document_id: int) -> List[ProvenanceAnchor]:
        """
        정규화 처리 로직의 디버깅 테스트나 향후 쳇봇 근거 설명 응답(Explanation API) 구성 시 호출됩니다.
        해당 문서에 소속된 전체 발췌 출처 핀을 PK 순서대로 정갈하게 나열해 로드합니다.
        """

        statement = (
            select(ProvenanceAnchor)
            .where(ProvenanceAnchor.document_id == document_id)
            .order_by(ProvenanceAnchor.id.asc())
        )
        return list(self.session.scalars(statement))
