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
    """Normalize repeated whitespace so parsed values stay comparable."""

    return re.sub(r"\s+", " ", text or "").strip()


def _first_text(root: Tag, selectors: Sequence[str]) -> str:
    """Return the first non-empty text that matches one of the CSS selectors."""

    for selector in selectors:
        node = root.select_one(selector)
        if node is not None:
            text = _clean_text(node.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _parse_notice_datetime(raw_text: str) -> datetime:
    """Parse common JBNU date formats into timezone-aware Seoul datetimes."""

    normalized = _clean_text(raw_text).replace("/", "-").replace(".", "-")
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(normalized, pattern)
            return parsed.replace(tzinfo=ASIA_SEOUL)
        except ValueError:
            continue
    raise ValueError("Unsupported notice datetime format: {0}".format(raw_text))


def _extract_notice_id(notice_url: str) -> str:
    """Derive a stable source notice id from common query or path formats."""

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
    """Extract an application window if the body contains one."""

    match = _APPLICATION_WINDOW_PATTERN.search(body_text)
    if match is None:
        return None, None

    start_date, start_time, end_date, end_time = match.groups()
    start_value = "{0} {1}".format(start_date, start_time or "00:00")
    end_value = "{0} {1}".format(end_date, end_time or "23:59")
    return _parse_notice_datetime(start_value), _parse_notice_datetime(end_value)


def _infer_media_type(file_name: str, source_url: str) -> str:
    """Infer a content type from the file name first and URL as fallback."""

    media_type, _ = mimetypes.guess_type(file_name or source_url)
    return media_type or "application/octet-stream"


def _extract_detail_label(root: Tag, labels: Sequence[str]) -> str:
    """Read dd/td values that follow common metadata labels on detail pages."""

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
    """Collect attachment links from known attachment containers."""

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
    """Keep the first occurrence of each external notice id in list results."""

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
        """Extract list-page summaries from the main university board."""

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
        """Extract list-page summaries from K2Web board tables."""

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
        """Extract detail text, application window, and attachments from one page."""

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
