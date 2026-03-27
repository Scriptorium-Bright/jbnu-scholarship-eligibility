from __future__ import annotations

import re
from typing import List

from bs4 import BeautifulSoup, Tag

from app.models import DocumentKind
from app.schemas import CanonicalBlock, CanonicalDocumentUpsert


def _clean_text(text: str) -> str:
    """
    HTML 태그가 벗겨진 순수 텍스트(Text)에 포함된 중복 공백, 탭 등을 가지런한 단일 공백으로 치환합니다.
    데이터베이스에 저장될 정규화 블록(Canonical Block) 문서 모델의 용량을 줄이고 퀄리티를 높입니다.
    """

    return re.sub(r"\s+", " ", text or "").strip()


class HtmlNoticeNormalizer:
    """Convert stored raw notice HTML into canonical block documents."""

    def normalize_notice_html(
        self,
        notice_id: int,
        raw_html: str,
        source_label: str = "notice_html",
    ) -> CanonicalDocumentUpsert:
        """
        크롤링된 긴 공지사항 HTML 내용에서 본문 DOM만 분리한 뒤, 이를 구역별 텍스트 블록(블록 객체들의 리스트)으로 파싱합니다.
        이후 DB 스키마에 부합하는 CanonicalDocumentUpsert 형태의 모델로 이쁘게 감싸 반환합니다.
        """

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
        """
        전체 HTML 계층 트리(Soup) 중에서 헤더, 푸터 등을 제외하고 핵심 내용이 들어간 본문 컨테이너(글 영역)만을 집어냅니다.
        CSS 선택자를 활용하며, 실패 시 `body` 태그 전체를 fallback으로 반환합니다.
        """

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
        """
        가려진 본문 영역(DOM)에서 문단(p), 리스트(li), 제목(h) 등의 주요 태그별 텍스트를 독립적인 블록 단위로 쪼갭니다.
        블록별로 어떤 태그 소스에서 왔는지 메타데이터로 남겨두어 룰 탐색기(Extractor)가 식별하기 좋게 만듭니다.
        """

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
