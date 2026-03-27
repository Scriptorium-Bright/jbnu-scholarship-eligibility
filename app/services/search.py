from __future__ import annotations

import re
from datetime import datetime
from typing import Any, List, Optional, Sequence, Tuple

from app.core.time import now_in_seoul
from app.db import session_scope
from app.models import ScholarshipRule
from app.repositories import ScholarshipRuleRepository
from app.schemas import (
    OpenScholarshipListResponse,
    ScholarshipProvenanceAnchorResponse,
    ScholarshipSearchItem,
    ScholarshipSearchResponse,
)

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")


class ScholarshipSearchService:
    """Assemble scholarship search and open-list responses from stored rules."""

    def list_published_scholarships(
        self,
        *,
        limit: Optional[int] = None,
        reference_time: Optional[datetime] = None,
        include_provenance: bool = True,
    ) -> List[ScholarshipSearchItem]:
        """
        별도의 검색어 조건 없이 현재 DB에 배포(Publish)된 모든 장학금 조회 모델(Read Model)을 불러옵니다.
        메인 화면이나 필터 초기화 상태에서 전체 장학금 리스트를 열람할 때 진입점으로 사용됩니다.
        """

        reference_time = reference_time or now_in_seoul()
        with session_scope() as session:
            rules = ScholarshipRuleRepository(session).list_published_rules(
                include_provenance_anchors=False
            )
            items = [
                self._build_item(
                    rule,
                    reference_time,
                    include_provenance=False,
                )
                for rule in rules
            ]

        items = sorted(items, key=self._published_sort_key)
        if limit is not None:
            items = items[:limit]
        if include_provenance:
            self.populate_provenance(items)
        return items

    def search(
        self,
        query: str,
        *,
        open_only: bool = False,
        limit: int = 10,
        reference_time: Optional[datetime] = None,
        include_provenance: bool = True,
    ) -> ScholarshipSearchResponse:
        """
        사용자가 입력한 검색어를 정규화/토큰화하여 DB의 전체 장학금 규칙들과 점수 기반으로 대조합니다.
        점수 및 주요 마감일정에 따라 적절하게 정렬된 검색 결과 리스트 및 채점 근거 정보를 응답합니다.
        """

        reference_time = reference_time or now_in_seoul()
        normalized_query = self._normalize_text(query)
        if not normalized_query:
            return ScholarshipSearchResponse(query=query, open_only=open_only, count=0, items=[])

        tokens = self._extract_tokens(query)
        with session_scope() as session:
            rules = ScholarshipRuleRepository(session).list_published_rules(
                include_provenance_anchors=False
            )
            items = self._search_rules(rules, normalized_query, tokens, reference_time, open_only)

        items = sorted(items, key=self._search_sort_key)[:limit]
        if include_provenance:
            self.populate_provenance(items)
        return ScholarshipSearchResponse(
            query=query,
            open_only=open_only,
            count=len(items),
            items=items,
        )

    def list_open_scholarships(
        self,
        *,
        limit: int = 10,
        reference_time: Optional[datetime] = None,
        include_provenance: bool = True,
    ) -> OpenScholarshipListResponse:
        """
        기준 시간(Reference Time)을 바탕으로 현재 신청 기간이 만료되지 않은 'open' 상태의 장학금만 가져옵니다.
        급하게 당장 신청 가능한 공고 목록만을 빠르게 탐색하고자 하는 API 엔드포인트에서 호출됩니다.
        """

        reference_time = reference_time or now_in_seoul()
        items = [
            item
            for item in self.list_published_scholarships(
                reference_time=reference_time,
                include_provenance=False,
            )
            if item.application_status == "open"
        ]
        items = sorted(items, key=self._open_list_sort_key)[:limit]
        if include_provenance:
            self.populate_provenance(items)
        return OpenScholarshipListResponse(
            reference_time=reference_time,
            count=len(items),
            items=items,
        )

    def populate_provenance(self, items: Sequence[ScholarshipSearchItem]) -> None:
        """
        최종적으로 API 응답 객체(Item)로 선택된 목록에 한정해 지연(Lazy) 방식으로 출처(Provenance) 정보를 채웁니다.
        초기 풀 탐색 시 모든 후보군의 출처들을 무겁게 수합해가며 발생하는 성능 저하 오버헤드를 막아줍니다.
        """

        rule_ids = [item.rule_id for item in items]
        if not rule_ids:
            return

        with session_scope() as session:
            rules = ScholarshipRuleRepository(session).list_published_rules_by_ids(
                rule_ids,
                include_provenance_anchors=True,
            )
            provenance_by_rule_id = {
                rule.id: self._build_provenance(rule)
                for rule in rules
            }

        for item in items:
            item.provenance = provenance_by_rule_id.get(item.rule_id, [])

    def _search_rules(
        self,
        rules: Sequence[ScholarshipRule],
        normalized_query: str,
        tokens: Sequence[str],
        reference_time: datetime,
        open_only: bool,
    ) -> List[ScholarshipSearchItem]:
        """
        불러온 전체 규칙 후보를 순회하며 제목/내용과 검색어 간의 텍스트 일치도를 채점(Score)합니다.
        점수가 0보다 큰 유의미한 매칭 검색 결과물만 도출하여 매칭 필드명과 함께 리스트 형태로 반환합니다.
        """

        matched_items: List[ScholarshipSearchItem] = []
        for rule in rules:
            item = self._build_item(
                rule,
                reference_time,
                include_provenance=False,
            )
            if open_only and item.application_status != "open":
                continue

            score, matched_fields = self._score_rule(rule, item, normalized_query, tokens)
            if score <= 0:
                continue

            item.score = round(score, 2)
            item.matched_fields = matched_fields
            matched_items.append(item)

        return matched_items

    def _build_item(
        self,
        rule: ScholarshipRule,
        reference_time: datetime,
        *,
        include_provenance: bool = True,
    ) -> ScholarshipSearchItem:
        """
        SQLAlchemy 데이터베이스 모델 객체(Rule, Notice)들을 조합하여 순수 API DTO(ScholarshipSearchItem)로 합칩니다.
        일정 날짜 보정과 런타임 상태 계산이 모두 통과된 하나의 독립적인 검색 응답 단일 행을 완성합니다.
        """

        application_started_at, application_ended_at = self._resolve_application_window(rule)
        application_started_at = self._coerce_datetime(application_started_at, reference_time)
        application_ended_at = self._coerce_datetime(application_ended_at, reference_time)
        published_at = self._coerce_datetime(rule.notice.published_at, reference_time) or reference_time
        return ScholarshipSearchItem(
            notice_id=rule.notice_id,
            rule_id=rule.id,
            scholarship_name=rule.scholarship_name,
            notice_title=rule.notice.title,
            source_board=rule.notice.source_board,
            department_name=rule.notice.department_name,
            notice_url=rule.notice.notice_url,
            published_at=published_at,
            application_started_at=application_started_at,
            application_ended_at=application_ended_at,
            application_status=self._compute_application_status(
                application_started_at,
                application_ended_at,
                reference_time,
            ),
            summary_text=rule.summary_text or rule.notice.summary,
            qualification=rule.qualification_json,
            provenance=self._build_provenance(rule) if include_provenance else [],
        )

    def _resolve_application_window(
        self,
        rule: ScholarshipRule,
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        공지사항 메타정보 자체에 명시된 일정과 룰(Rule)에서 별도로 기재된 일정 중 구체적인 값을 취사선택합니다.
        일관적이지 않게 수집되는 일정 정보의 파편화를 방어하고 정확한 장학 신청 윈도우 시점을 계산합니다.
        """

        return (
            rule.application_started_at or rule.notice.application_started_at,
            rule.application_ended_at or rule.notice.application_ended_at,
        )

    def _compute_application_status(
        self,
        application_started_at: Optional[datetime],
        application_ended_at: Optional[datetime],
        reference_time: datetime,
    ) -> str:
        """
        신청 시작일과 종료일을 현재 서버 시간(Reference Time)과 비교하여 활성 상태 키워드(open/closed 등)를 결정합니다.
        향후 검색 필터링 조건이나 정렬 채점에서 추가 가중치를 부여하기 위함입니다.
        """

        if application_started_at and reference_time < application_started_at:
            return "upcoming"
        if application_ended_at and reference_time > application_ended_at:
            return "closed"
        if application_started_at is None and application_ended_at is None:
            return "unknown"
        return "open"

    def _coerce_datetime(
        self,
        value: Optional[datetime],
        reference_time: datetime,
    ) -> Optional[datetime]:
        """
        타임존 정보가 누락된 naive datetime 객체(SQLite 반환 객체 등)에 서버 기준 타임존을 강제로 박아넣습니다.
        시간들의 비교 연산 시점에 발생하는 오프셋 에러(Offset-naive vs Aware)를 사전에 차단합니다.
        """

        if value is None:
            return None
        if value.tzinfo is not None:
            return value
        return value.replace(tzinfo=reference_time.tzinfo)

    def _build_provenance(self, rule: ScholarshipRule) -> List[ScholarshipProvenanceAnchorResponse]:
        """
        장학금 정보 추출 시점에 생성해둔 고유 출처 핀(Anchor) 중 해당 규정에 연관성이 있는 항목만 필터링해 모읍니다.
        사용자에게나 추후 답변 생성 AI에게 '이 규칙이 원문 데이터의 어디서 파생되었는지' 근거 영역을 제공합니다.
        """

        if rule.document is None:
            return []

        anchors_by_key = {
            anchor.anchor_key: anchor for anchor in rule.document.provenance_anchors
        }
        ordered_anchors: List[ScholarshipProvenanceAnchorResponse] = []
        for anchor_key in rule.provenance_keys_json:
            anchor = anchors_by_key.get(anchor_key)
            if anchor is None:
                continue
            ordered_anchors.append(
                ScholarshipProvenanceAnchorResponse(
                    anchor_key=anchor.anchor_key,
                    block_id=anchor.block_id,
                    quote_text=anchor.quote_text,
                    page_number=anchor.page_number,
                    source_label=rule.document.source_label,
                    document_kind=rule.document.document_kind,
                    locator=anchor.locator_json,
                )
            )
        return ordered_anchors

    def _score_rule(
        self,
        rule: ScholarshipRule,
        item: ScholarshipSearchItem,
        normalized_query: str,
        tokens: Sequence[str],
    ) -> Tuple[float, List[str]]:
        """
        제목, 요약, 자격 요건, 원문 전체 등 정의된 필드별 가중치에 맞춰 텍스트 검색어 채점을 수행하고 합산합니다.
        현재 오픈된 신청 가능 상태일 경우 보너스 추가 점수를 부여하여 노출 문서의 품질 및 우선순위를 최적화합니다.
        """

        document_text = ""
        if rule.document is not None and rule.document.canonical_text:
            document_text = rule.document.canonical_text

        search_fields = [
            ("scholarship_name", item.scholarship_name, 6.0),
            ("notice_title", item.notice_title, 4.0),
            ("summary_text", item.summary_text or "", 3.0),
            ("qualification", self._flatten_value(item.qualification), 4.0),
            ("document_text", document_text, 2.5),
        ]

        score = 0.0
        matched_fields = set()
        for field_name, value, field_weight in search_fields:
            field_score = self._score_text(value, normalized_query, tokens, field_weight)
            if field_score <= 0:
                continue
            score += field_score
            matched_fields.add(field_name)

        if item.application_status == "open":
            score += 1.0
        elif item.application_status == "upcoming":
            score += 0.25

        return score, sorted(matched_fields)

    def _score_text(
        self,
        value: str,
        normalized_query: str,
        tokens: Sequence[str],
        field_weight: float,
    ) -> float:
        """
        정규화된 서치 쿼리의 전체 문자열 일치 및 각각 개별 토큰 단위의 부분 일치를 종합하여 특정 텍스트 필드의 점수를 산출합니다.
        대상 키워드가 자주 포함될수록, 또 완벽하게 일치할수록 가중치에 비례한 높은 점수가 할당됩니다.
        """

        normalized_value = self._normalize_text(value)
        if not normalized_value:
            return 0.0

        score = 0.0
        if normalized_query in normalized_value:
            score += field_weight

        token_hits = sum(1 for token in tokens if token in normalized_value)
        if token_hits:
            score += min(token_hits, 4) * (field_weight * 0.45)

        return score

    def _extract_tokens(self, query: str) -> List[str]:
        """
        검색어 문자열을 정규식 기반(영숫자/한글 포함)으로 분해하여 개별적으로 탐색 가능한 토큰 목록 세트로 변환합니다.
        짧은 조사나 1자 짜리 무의미한 단어를 사전에서 걸러내 검색 정확도 향상과 노이즈 감소를 이끕니다.
        """

        tokens = {
            self._normalize_text(match.group(0))
            for match in TOKEN_PATTERN.finditer(query)
            if len(match.group(0).strip()) >= 2
        }
        return sorted(token for token in tokens if token)

    def _normalize_text(self, value: str) -> str:
        """
        주어진 대상 텍스트를 모두 소문자로 변환하고 다중 공백이나 탭을 단일 띄어쓰기로 압축하는 단순 정규화를 수행합니다.
        결정론적(Deterministic) 부분 문자열 매칭 시 오타나 특수기호 등으로 인한 서치 누락 성공률을 보정합니다.
        """

        collapsed = " ".join(value.lower().split())
        return collapsed.strip()

    def _flatten_value(self, value: Any) -> str:
        """
        JSON 딕셔너리나 리스트 형태로 깊게 중첩될 수 있는 자격증명(Qualification) 객체 트리를 단일 평면 텍스트로 풀어냅니다.
        검색 대상 스코어링 함수가 복잡한 데이터 구조체의 안쪽 텍스트값에도 자유롭게 접근하고 키워드를 비교할 수 있게 합니다.
        """

        if isinstance(value, dict):
            return " ".join(
                f"{key} {self._flatten_value(nested_value)}"
                for key, nested_value in value.items()
            )
        if isinstance(value, list):
            return " ".join(self._flatten_value(item) for item in value)
        return str(value)

    def _search_sort_key(self, item: ScholarshipSearchItem) -> Tuple[float, int, float]:
        """
        기본 검색 결과의 정렬 우선순위를 복합적인 튜플 지표(점수 1순위 > 활성 상태 랭크 > 최신 글순)로 구성합니다.
        정확도가 높은 정보 위주로, 그리고 당장 조치가 가능한 최신의 정보가 상단에 배치되게 만듭니다.
        """

        return (
            -item.score,
            self._application_status_rank(item.application_status),
            -item.published_at.timestamp(),
        )

    def _open_list_sort_key(self, item: ScholarshipSearchItem) -> Tuple[bool, datetime, float]:
        """
        '오픈된 리스트 전용' 정렬 우선순위 튜플(종료일 명시 여부 > 종료일 임박 순 > 최신 글순)을 생성합니다.
        조만간 먼저 마감되어 사라질 위기의 공고들이 리스트에서 묻히지 않고 상단으로 자연스럽게 호출되게 조율합니다.
        """

        fallback_end = datetime.max.replace(tzinfo=item.published_at.tzinfo)
        return (
            item.application_ended_at is None,
            item.application_ended_at or fallback_end,
            -item.published_at.timestamp(),
        )

    def _application_status_rank(self, status: str) -> int:
        """
        텍스트 성격의 상태값(open, closed 등)을 다중 정렬 알고리즘이 쉽게 인식 가능한 숫자형 랭크 데이터로 대체합니다.
        중요도가 높은 활성화 상태(open)일수록 0에 가까운 작은 숫자를 반환해 무조건 상위 위계로 정렬을 유도합니다.
        """

        return {
            "open": 0,
            "upcoming": 1,
            "unknown": 2,
            "closed": 3,
        }.get(status, 99)

    def _published_sort_key(self, item: ScholarshipSearchItem) -> Tuple[int, float]:
        """
        전체 조회 및 초기화면 기능의 기본 정렬 우선순위 튜플(활성 상태 랭크 > 등록 생성된 최신 시간순)을 매핑합니다.
        점수 체계가 반영되지 않는 조회 환경일 경우 최대한 유의미한 신청가능(Actionable) 항목을 무조건 첫 페이지로 스윕합니다.
        """

        return (
            self._application_status_rank(item.application_status),
            -item.published_at.timestamp(),
        )
