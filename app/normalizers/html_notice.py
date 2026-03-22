from __future__ import annotations

import re
from typing import List

from bs4 import BeautifulSoup, Tag

from app.models import DocumentKind
from app.schemas import CanonicalBlock, CanonicalDocumentUpsert


def _clean_text(text: str) -> str:
    """Normalize repeated whitespace so canonical blocks stay compact."""

    return re.sub(r"\s+", " ", text or "").strip()


class HtmlNoticeNormalizer:
    """Convert stored raw notice HTML into canonical block documents."""

    def normalize_notice_html(
        self,
        notice_id: int,
        raw_html: str,
        source_label: str = "notice_html",
    ) -> CanonicalDocumentUpsert:
        """Build the canonical document payload for one notice HTML file."""

        soup = BeautifulSoup(raw_html, "html.parser")
        content_root = self._extract_content_root(soup)
        blocks = self._build_blocks(content_root)
        canonical_text = "\n".join(block.text for block in blocks)

        return CanonicalDocumentUpsert(
            notice_id=notice_id,
            document_kind=DocumentKind.NOTICE_HTML,
            source_label=source_label,
            canonical_text=canonical_text,
            blocks=blocks,
            metadata={
                "block_count": len(blocks),
                "source_label": source_label,
            },
        )

    def _extract_content_root(self, soup: BeautifulSoup) -> Tag:
        """Pick the most likely detail content container from the raw HTML."""

        for selector in (
            ".article-body",
            ".board-view-body",
            ".fr-view",
            ".view-content",
            ".detail-body",
            "[data-field='body']",
        ):
            node = soup.select_one(selector)
            if node is not None:
                return node
        return soup.body or soup

    def _build_blocks(self, content_root: Tag) -> List[CanonicalBlock]:
        """Convert headings, paragraphs, and list items into canonical blocks."""

        blocks = []
        for node in content_root.find_all(["h1", "h2", "h3", "p", "li", "tr"]):
            text = _clean_text(node.get_text(" ", strip=True))
            if not text:
                continue
            blocks.append(
                CanonicalBlock(
                    block_id="block-{0}".format(len(blocks) + 1),
                    block_type=node.name,
                    text=text,
                    metadata={"source_tag": node.name},
                )
            )

        if not blocks:
            fallback_text = _clean_text(content_root.get_text("\n", strip=True))
            if fallback_text:
                blocks.append(
                    CanonicalBlock(
                        block_id="block-1",
                        block_type="body",
                        text=fallback_text,
                    )
                )
        return blocks
