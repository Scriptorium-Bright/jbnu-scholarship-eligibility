from __future__ import annotations

import mimetypes
import re
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from app.collectors.types import CollectedAttachment, CollectedNotice, CollectedNoticeSummary, CollectorSource
from app.core.time import ASIA_SEOUL

_APPLICATION_WINDOW_PATTERN = re.compile(
    r"(20\d{2}[./-]\d{1,2}[./-]\d{1,2})(?:\s+(\d{1,2}:\d{2}))?\s*[~\-]\s*"
    r"(20\d{2}[./-]\d{1,2}[./-]\d{1,2})(?:\s+(\d{1,2}:\d{2}))?"
)


def _clean_text(text: str) -> str:
    """
    연속된 빈칸과 줄바꿈 문자를 단일 공백으로 치환하여 텍스트를 매끄럽게 정규화합니다.
    파싱된 문자열 데이터들이 일관된 형식으로 비교 및 저장될 수 있도록 보장합니다.
    """

    return re.sub(r"\s+", " ", text or "").strip()


def _first_text(root: Tag, selectors: Sequence[str]) -> str:
    """
    주어진 여러 CSS 선택자(Selector) 목록 중 제일 먼저 일치하는 DOM 요소의 텍스트를 반환합니다.
    버전이나 구조가 상이한 여러 게시판 템플릿에서도 유연하게 필요한 값을 긁어오기 위함입니다.
    """

    for selector in selectors:
        node = root.select_one(selector)
        if node is not None:
            text = _clean_text(node.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _parse_notice_datetime(raw_text: str) -> datetime:
    """
    기본적인 날짜 문자열(예: YYYY-MM-DD 등)을 파싱하여 타임존(KST)이 반영된 datetime 객체를 만듭니다.
    각기 다른 게시판에서 표시하는 날짜 포맷의 파편화를 하나의 일관된 기준으로 맞춥니다.
    """

    normalized = _clean_text(raw_text).replace("/", "-").replace(".", "-")
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(normalized, pattern)
            return parsed.replace(tzinfo=ASIA_SEOUL)
        except ValueError:
            continue
    raise ValueError("Unsupported notice datetime format: {0}".format(raw_text))


def _extract_notice_id(notice_url: str) -> str:
    """
    게시글의 고유 링크에서 쿼리 파라미터나 URL 경로를 추출해 식별가능한 고유 ID 문자열을 뽑아냅니다.
    중복된 수집을 걸러내고 향후 원본 글을 다시 찾을 수 있게 하는 Key 정보로 활용됩니다.
    """

    parsed_url = urlparse(notice_url)
    query_params = parse_qs(parsed_url.query)
    for key in ("articleNo", "article_no", "nttSn"):
        if key in query_params and query_params[key]:
            return query_params[key][0]

    artcl_match = re.search(r"/(\d+)/artclView\.do", parsed_url.path)
    if artcl_match:
        return artcl_match.group(1)

    numeric_segments = re.findall(r"(\d+)", parsed_url.path)
    if numeric_segments:
        return numeric_segments[-1]
    raise ValueError("Unable to derive source notice id from URL: {0}".format(notice_url))


def _parse_application_window(body_text: str) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    본문 텍스트 안에 'YYYY-MM-DD ~ YYYY-MM-DD' 형태의 신청 유효 기간이 들어있는지 정규식으로 찾습니다.
    발견될 경우 해당 기간의 시작 날짜와 종료 날짜를 타임존 객체로 변환하여 두 개의 반환값으로 줍니다.
    """

    match = _APPLICATION_WINDOW_PATTERN.search(body_text)
    if match is None:
        return None, None

    start_date, start_time, end_date, end_time = match.groups()
    start_value = "{0} {1}".format(start_date, start_time or "00:00")
    end_value = "{0} {1}".format(end_date, end_time or "23:59")
    return _parse_notice_datetime(start_value), _parse_notice_datetime(end_value)


def _infer_media_type(file_name: str, source_url: str) -> str:
    """
    파일의 이름이나 URL에서 발견되는 확장자를 토대로 데이터의 MIME 타입(예: application/pdf)을 유추합니다.
    파악이 어려운 미지의 파일일 경우 기본값인 범용 바이트 스트림(octet-stream) 타입을 쥐어줍니다.
    """

    media_type, _ = mimetypes.guess_type(file_name or source_url)
    return media_type or "application/octet-stream"


def _extract_detail_label(root: Tag, labels: Sequence[str]) -> str:
    """
    HTML 태그 중에서 '작성일', '조회수' 같이 특징적인 라벨 바로 뒤에 오는 데이터 문자열을 추출합니다.
    테이블 뷰나 설명 목록(dt/dd)으로 레이아웃이 잡혀있는 상세 페이지 메타데이터를 파싱할 때 쓰입니다.
    """

    for label in labels:
        for tag_name in ("dt", "th", "strong", "span"):
            label_node = root.find(tag_name, string=re.compile(r"^\s*{0}\s*$".format(re.escape(label))))
            if label_node is None:
                continue
            sibling = label_node.find_next_sibling(["dd", "td", "span", "div"])
            if sibling is not None:
                text = _clean_text(sibling.get_text(" ", strip=True))
                if text:
                    return text
    return ""


def _extract_attachment_links(root: Tag, base_url: str) -> List[CollectedAttachment]:
    """
    공지사항 상세 본문 내부의 첨부파일 링크(a 태그)를 찾아 다운로드 가능한 URL 리스트를 만듭니다.
    중복되는 파일 주소를 제외하고 깔끔한 이름과 MIME 타입이 래핑된 첨부파일 객체들을 수집합니다.
    """

    attachments = []
    seen_urls = set()
    containers = root.select(".attachments, .attach-file, .file-list, [data-field='attachments']")
    for container in containers:
        for link in container.select("a[href]"):
            source_url = urljoin(base_url, link["href"])
            if source_url in seen_urls:
                continue
            seen_urls.add(source_url)
            file_name = _clean_text(link.get_text(" ", strip=True)) or source_url.rsplit("/", 1)[-1]
            attachments.append(
                CollectedAttachment(
                    source_url=source_url,
                    file_name=file_name,
                    media_type=_infer_media_type(file_name, source_url),
                )
            )
    return attachments


def _dedupe_summaries(summaries: Iterable[CollectedNoticeSummary]) -> List[CollectedNoticeSummary]:
    """
    하나의 목록 페이지 안에 같은 식별자를 가진 게시글이 여러 번 노출되는 경우를 필터링합니다.
    불필요한 중복 수집 작업을 피하기 위해 제일 처음 발견된 항목만 살려두는 역할을 합니다.
    """

    deduped = []
    seen_ids = set()
    for summary in summaries:
        if summary.source_notice_id in seen_ids:
            continue
        seen_ids.add(summary.source_notice_id)
        deduped.append(summary)
    return deduped


class JbnuMainNoticeListParser:
    """Parse the JBNU main notice board list page."""

    def parse(self, html: str, source: CollectorSource) -> List[CollectedNoticeSummary]:
        """
        전북대 본부가 운영하는 메인 게시판의 HTML 목록 화면을 순회하면서 글들의 정보를 파싱합니다.
        제목, 게시일정, 부서명 등의 핵심 데이터를 추출해 가벼운 요약본 리스트로 만들어줍니다.
        """

        soup = BeautifulSoup(html, "html.parser")
        summaries = []
        for row in soup.select("tr.notice-row, table tbody tr"):
            title_link = row.select_one(".title a[href], td.title a[href], a[href]")
            if title_link is None:
                continue

            title = _clean_text(title_link.get_text(" ", strip=True))
            if not title:
                continue

            published_text = _first_text(row, ("td.date", ".date", "time", "[data-field='published_at']"))
            if not published_text:
                continue

            notice_url = urljoin(source.list_url, title_link["href"])
            summaries.append(
                CollectedNoticeSummary(
                    source_notice_id=_extract_notice_id(notice_url),
                    title=title,
                    notice_url=notice_url,
                    published_at=_parse_notice_datetime(published_text),
                    department_name=_first_text(
                        row,
                        ("td.department", ".department", "td.author", ".author"),
                    )
                    or source.default_department_name,
                    category=_first_text(row, ("td.category", ".category", "[data-field='category']")) or None,
                )
            )
        return _dedupe_summaries(summaries)


class K2WebNoticeListParser:
    """Parse K2Web-based department board list pages."""

    def parse(self, html: str, source: CollectorSource) -> List[CollectedNoticeSummary]:
        """
        K2Web 시스템을 쓰는 단과대/학과 게시판의 HTML 목록 화면을 전용 룰에 맞춰 파싱합니다.
        마찬가지로 테이블 구조에서 게시글 제목과 정보를 추출해 요약 모델로 감싸 반환합니다.
        """

        soup = BeautifulSoup(html, "html.parser")
        summaries = []
        for row in soup.select("tr.notice-row, table tbody tr, ul.board-list li"):
            title_link = row.select_one(".title a[href], td.title a[href], a[href*='artclView.do'], a[href]")
            if title_link is None:
                continue

            title = _clean_text(title_link.get_text(" ", strip=True))
            if not title:
                continue

            published_text = _first_text(row, ("td.date", ".date", "time", "[data-field='published_at']"))
            if not published_text:
                continue

            notice_url = urljoin(source.list_url, title_link["href"])
            summaries.append(
                CollectedNoticeSummary(
                    source_notice_id=_extract_notice_id(notice_url),
                    title=title,
                    notice_url=notice_url,
                    published_at=_parse_notice_datetime(published_text),
                    department_name=_first_text(
                        row,
                        ("td.department", ".department", "td.writer", ".writer"),
                    )
                    or source.default_department_name,
                    category=_first_text(row, ("td.category", ".category", "[data-field='category']")) or None,
                )
            )
        return _dedupe_summaries(summaries)


class GenericNoticeDetailParser:
    """Parse notice detail pages from the main board and K2Web pages."""

    def parse(self, html: str, summary: CollectedNoticeSummary, source: CollectorSource) -> CollectedNotice:
        """
        게시글 상세 화면 안에 담긴 장문의 본문 텍스트와 여러 첨부파일 링크를 꼼꼼하게 추출합니다.
        기존 목록에서 받아둔 요약 정보와 병합하여 최종 저장에 사용될 완전한 데이터 객체를 생성합니다.
        """

        soup = BeautifulSoup(html, "html.parser")
        body_root = soup.select_one(
            ".article-body, .board-view-body, .fr-view, .view-content, .detail-body, [data-field='body']"
        )
        body_text = _clean_text(body_root.get_text("\n", strip=True)) if body_root is not None else ""
        summary_text = ""
        if body_root is not None:
            first_paragraph = body_root.find(["p", "div", "li"])
            if first_paragraph is not None:
                summary_text = _clean_text(first_paragraph.get_text(" ", strip=True))
        summary_text = summary_text or body_text[:200] or summary.title

        published_text = _extract_detail_label(soup, ("작성일", "등록일")) or _first_text(
            soup,
            ("time", ".article-date", ".board-date", "[data-field='published_at']"),
        )
        published_at = _parse_notice_datetime(published_text) if published_text else summary.published_at
        department_name = _extract_detail_label(soup, ("작성자", "부서")) or _first_text(
            soup,
            (".article-writer", ".department", "[data-field='department']"),
        )
        application_started_at, application_ended_at = _parse_application_window(body_text)

        return CollectedNotice(
            source_notice_id=summary.source_notice_id,
            title=_first_text(
                soup,
                ("h1", "h2.article-title", "h2.title", ".article-title", "[data-field='title']"),
            )
            or summary.title,
            notice_url=summary.notice_url,
            published_at=published_at,
            department_name=department_name or summary.department_name or source.default_department_name,
            summary=summary_text,
            application_started_at=application_started_at,
            application_ended_at=application_ended_at,
            attachments=_extract_attachment_links(soup, summary.notice_url),
        )
