from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from app.core.config import get_settings


class LocalRawStorage:
    """Store raw notice HTML and attachment bytes on the local filesystem."""

    def __init__(self, base_path: Optional[str] = None):
        """
        어플리케이션 환경 변수(Config)를 읽어와 원시 데이터(HTML/첨부파일)가 저장될 디스크의 기준(Root) 폴더 위치를 파악합니다.
        생성 시 상대 경로나 `~` 문자를 평가하여 운영체제가 이해하는 정확한 절대 경로로 해상(Resolve)합니다.
        """

        root_path = base_path or get_settings().raw_storage_path
        self.base_path = Path(root_path).expanduser().resolve()

    def save_notice_html(
        self,
        source_board: str,
        source_notice_id: str,
        html_text: str,
    ) -> str:
        """
        게시물 상세 페이지의 실제 HTML 텍스트를 로컬 폴더 시스템에 `notice.html` 이라는 파일명으로 보존합니다.
        DB에는 데이터 전체가 아닌 해당 파일이 놓여진 상대 경로 위치 문자열 데이터만을 넘겨줍니다.
        """

        relative_path = self._notice_root(source_board, source_notice_id) / "notice.html"
        return self._write_bytes(relative_path, html_text.encode("utf-8"))

    def save_attachment(
        self,
        source_board: str,
        source_notice_id: str,
        file_name: str,
        content: bytes,
    ) -> str:
        """
        바이너리로 떨어진 첨부파일 내용물을 `attachments` 하위 폴더의 원본 파일명 그대로 기록 처리합니다.
        이름이 복잡하거나 알 수 없는 포맷일 경우 기본적인 `attachment.bin` 명칭으로 대체해 저장합니다.
        """

        safe_name = self._safe_segment(file_name) or "attachment.bin"
        relative_path = self._notice_root(source_board, source_notice_id) / "attachments" / safe_name
        return self._write_bytes(relative_path, content)

    def read_text(self, relative_path: str) -> str:
        """
        정규화 처리 등 텍스트 스캔 과정이 필요할 때 호출되며, 저장해둔 문자열(예: notice.html)을 UTF-8로 읽어 인메모리에 띄웁니다.
        주어진 상대 경로를 기준 루트 디렉토리에 결합(Resolve) 활용하여 디스크 접근을 수행합니다.
        """

        return self._resolve(relative_path).read_text(encoding="utf-8")

    def read_bytes(self, relative_path: str) -> bytes:
        """
        저장되어 있는 PDF, HWP 포맷 등 비-문자열 단일 바이너리(Attachment) 파일을 바이트(Bytes) 배열 타입으로 바로 읽어옵니다.
        전용 Extractor 라이브러리(pypdf 등)에게 메모리 형태의 데이터 스트림을 넘겨주기 위해 작동합니다.
        """

        return self._resolve(relative_path).read_bytes()

    def exists(self, relative_path: str) -> bool:
        """
        전달받은 상대 경로(Relative Path) 대상 데이터 파일이 로컬 디스크의 실제 폴더에 존재하는지 테스트합니다.
        이미 수집되었거나 삭제된 파일 등의 예외처리를 검증하는 기초 확인 함수입니다.
        """

        return self._resolve(relative_path).exists()

    def _notice_root(self, source_board: str, source_notice_id: str) -> Path:
        """
        `게시판이름/게시글ID/` 형태를 지닌 전용 내부 보관 디렉토리용 경로(Path) 객체를 동적으로 결합 구성합니다.
        하나의 공지에 속하는 HTML 본문과 여러 개의 첨부파일들을 한 뎁스의 방 안에 통일되게 묶기 위함입니다.
        """

        return Path(self._safe_segment(source_board)) / self._safe_segment(source_notice_id)

    def _resolve(self, relative_path: str) -> Path:
        """
        문자열 형태의 상대 경로를 시스템이 설정한 Root Base Path와 완전한 절대 경로(Path Object)로 결합 합칩니다.
        외부 디렉토리 무단 접근을 시스템 레벨에서 봉쇄하는 역할도 수행할 수 있습니다.
        """

        return self.base_path / Path(relative_path)

    def _write_bytes(self, relative_path: Path, content: bytes) -> str:
        """
        바이트 컨텐츠를 디스크 절대경로 지점에 Write 작업으로 밀어넣고 누락된 부모 폴더(mkdir)도 자동 생성합니다.
        저장이 끝나면 DB에 기입할 수 있도록 OS에 독립적인 POSIX 스타일의 상대 경로 텍스트 포맷을 반환합니다.
        """

        destination = self._resolve(str(relative_path))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return relative_path.as_posix()

    def _safe_segment(self, value: str) -> str:
        """
        사용자 입력 또는 외부 식별자가 디렉토리명으로 오인되어 크랙되거나 깨지지 않도록 위험 문자를 하이픈(-)으로 치환 삭제합니다.
        OS 파일 시스템의 명명 규칙 컨벤션(Sanitization)을 준수하게 만드는 유틸리티 함수입니다.
        """

        return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
