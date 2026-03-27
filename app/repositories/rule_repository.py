from __future__ import annotations

from typing import Iterable, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models import CanonicalDocument, RuleStatus, ScholarshipRule
from app.schemas import ScholarshipRuleCreate


class ScholarshipRuleRepository:
    """Persist and query structured scholarship rules."""

    def __init__(self, session: Session):
        self.session = session

    def _published_rule_statement(self, *, include_provenance_anchors: bool = True):
        """
        '배포됨(Published)' 상태를 지닌 유효 장학금 룰만을 필터링하며, 요청 시 원문 출처(Anchors)까지 즉시 조인(Fetch)하는 기본 쿼리를 만듭니다.
        N+1 쿼리 성능 저하를 방지하기 위한 selectinload 로직의 중앙 캡슐화 역할을 합니다.
        """

        statement = (
            select(ScholarshipRule)
            .where(ScholarshipRule.status == RuleStatus.PUBLISHED)
            .options(selectinload(ScholarshipRule.notice))
        )
        if include_provenance_anchors:
            statement = statement.options(
                selectinload(ScholarshipRule.document).selectinload(
                    CanonicalDocument.provenance_anchors
                )
            )
        else:
            statement = statement.options(selectinload(ScholarshipRule.document))
        return statement

    def replace_rules(
        self,
        notice_id: int,
        rules: List[ScholarshipRuleCreate],
    ) -> List[ScholarshipRule]:
        """
        단일 공지사항으로부터 재추출된 다수의 장학금 조건 규칙들을 해당 공지사항의 기존 규칙 집합 전체와 원자적(Atomically)으로 밀어내기 교체 반영합니다.
        물리적인 DELETE 이후 새로운 모델 객체들을 일괄 삽입하여 사이드 이펙트를 차단합니다.
        """

        self.session.execute(
            delete(ScholarshipRule).where(ScholarshipRule.notice_id == notice_id)
        )

        saved_rules = []
        for payload in rules:
            payload_data = payload.model_dump()
            payload_data["qualification_json"] = payload_data.pop("qualification")
            payload_data["provenance_keys_json"] = payload_data.pop("provenance_keys")
            rule = ScholarshipRule(**payload_data)
            self.session.add(rule)
            saved_rules.append(rule)

        self.session.flush()
        return saved_rules

    def list_rules_for_notice(self, notice_id: int) -> List[ScholarshipRule]:
        """
        특정한 하나의 장학 관리 공지사항 게시물 안에 포함(추출)되어 있던 전체 서브 조건 규칙 목록 전부를 로드하여 나열합니다.
        어드민 페이지 조회나 테스트 픽스처 검증 등에서 공지 단위의 룰을 살펴볼 때 쓰입니다.
        """

        statement = (
            select(ScholarshipRule)
            .where(ScholarshipRule.notice_id == notice_id)
            .order_by(ScholarshipRule.id.asc())
        )
        return list(self.session.scalars(statement))

    def list_published_rules(
        self,
        limit: Optional[int] = None,
        *,
        include_provenance_anchors: bool = True,
    ) -> List[ScholarshipRule]:
        """
        전체 서비스 검색 화면이나 유저의 장학금 조건 매칭 엔진(Eligibility API) 등에서 실시간으로 검토되어야 할 배포 상태의 활성 규칙들을 모두 제공합니다.
        서비스 조회 볼륨 조절을 위한 limit 인자를 외부에서 조정 가능하게 열어두었습니다.
        """

        statement = self._published_rule_statement(
            include_provenance_anchors=include_provenance_anchors
        ).order_by(ScholarshipRule.id.asc())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def list_published_rules_by_ids(
        self,
        rule_ids: Iterable[int],
        *,
        include_provenance_anchors: bool = True,
    ) -> List[ScholarshipRule]:
        """
        미리 확보된 복수 개의 Rule ID 식별자(List)에 정확히 부합하는 활성 장학금 규칙 모델들만을 빠르게 필터링/조인해 호출 반환합니다.
        빠른 응답 속도가 생명인 검색 결과 화면의 지연 렌더링(Lazy Hydration) 성능을 보장합니다.
        """

        normalized_rule_ids = [int(rule_id) for rule_id in rule_ids]
        if not normalized_rule_ids:
            return []

        statement = (
            self._published_rule_statement(
                include_provenance_anchors=include_provenance_anchors
            )
            .where(ScholarshipRule.id.in_(normalized_rule_ids))
            .order_by(ScholarshipRule.id.asc())
        )
        return list(self.session.scalars(statement))
