from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import NoticeAttachment, ScholarshipNotice
from app.schemas import NoticeAttachmentUpsert, ScholarshipNoticeUpsert


class ScholarshipNoticeRepository:
    """Persist and query collected notice metadata."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_source_identity(
        self,
        source_board: str,
        source_notice_id: str,
    ) -> Optional[ScholarshipNotice]:
        """
        크롤링 수집 대상 게시판 영문 명칭과 고유 외부 문서 번호를 활용해 기존에 동일 데이터가 이미 적재됐는지 조회합니다.
        자식 첨부파일 레코드를 즉시 지연 조인(Pre-load)하여, 이중 크롤링 방지 및 갱신 판단 근거로 사용됩니다.
        """

        statement = (
            select(ScholarshipNotice)
            .where(ScholarshipNotice.source_board == source_board)
            .where(ScholarshipNotice.source_notice_id == source_notice_id)
            .options(selectinload(ScholarshipNotice.attachments))
        )
        return self.session.scalar(statement)

    def get_by_id(self, notice_id: int) -> Optional[ScholarshipNotice]:
        """
        내부 DB의 자동증가 PK(Primary Key) 값을 기준으로 하나의 완결된 장학금 공지사항 게시물 데이터를 불러옵니다.
        API 단말 시스템에서 클라이언트에게 상세 정보 및 첨부파일 목록(Pre-load)을 전달하고자 할 때 씁니다.
        """

        statement = (
            select(ScholarshipNotice)
            .where(ScholarshipNotice.id == notice_id)
            .options(selectinload(ScholarshipNotice.attachments))
        )
        return self.session.scalar(statement)

    def upsert_notice(self, payload: ScholarshipNoticeUpsert) -> ScholarshipNotice:
        """
        수집 단계를 마친 공지사항이 아직 없다면 새로 기입(Insert)하고, 이미 존재한다면 최신 크롤링 데이터 내용으로 모델 필드를 업데이트합니다.
        단일 세션 내에서 변경된 모델 속성들을 트래킹한 뒤 한 번의 Flush로 물리적 변경 사항을 동기화시킵니다.
        """

        notice = self.get_by_source_identity(payload.source_board, payload.source_notice_id)
        payload_data = payload.model_dump()

        if notice is None:
            notice = ScholarshipNotice(**payload_data)
            self.session.add(notice)
        else:
            for field_name, value in payload_data.items():
                setattr(notice, field_name, value)

        self.session.flush()
        return notice

    def add_or_update_attachment(
        self,
        notice_id: int,
        payload: NoticeAttachmentUpsert,
    ) -> NoticeAttachment:
        """
        추가로 수집된 첨부파일들 각각의 중복 여부를 원본 Source URL 기반으로 검증해 병합(Upsert) 방식으로 안전하게 갱신 삽입합니다.
        수정된 첨부물 정보의 멱등성(Idempotency)을 보장하는 기초 메소드입니다.
        """

        statement = (
            select(NoticeAttachment)
            .where(NoticeAttachment.notice_id == notice_id)
            .where(NoticeAttachment.source_url == payload.source_url)
        )
        attachment = self.session.scalar(statement)
        payload_data = payload.model_dump()

        if attachment is None:
            attachment = NoticeAttachment(notice_id=notice_id, **payload_data)
            self.session.add(attachment)
        else:
            for field_name, value in payload_data.items():
                setattr(attachment, field_name, value)

        self.session.flush()
        return attachment

    def list_recent_notices(self, limit: int = 20) -> List[ScholarshipNotice]:
        """
        배포된 최신 외부 게시일(Published_at) 순서대로 정렬된 N개의 장학 공지 테이블 데이터 목록을 반환합니다.
        메인 모니터링 목록 반환 API나, 새로운 공지만 확인하며 페이징해야 하는 신규 크롤링 상태 점검 등에서 활용됩니다.
        """

        statement = (
            select(ScholarshipNotice)
            .order_by(ScholarshipNotice.published_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))
