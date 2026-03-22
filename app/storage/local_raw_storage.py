from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from app.core.config import get_settings


class LocalRawStorage:
    """Store raw notice HTML and attachment bytes on the local filesystem."""

    def __init__(self, base_path: Optional[str] = None):
        """Resolve the storage root from settings unless explicitly overridden."""

        root_path = base_path or get_settings().raw_storage_path
        self.base_path = Path(root_path).expanduser().resolve()

    def save_notice_html(
        self,
        source_board: str,
        source_notice_id: str,
        html_text: str,
    ) -> str:
        """Persist one detail HTML payload and return its relative storage path."""

        relative_path = self._notice_root(source_board, source_notice_id) / "notice.html"
        return self._write_bytes(relative_path, html_text.encode("utf-8"))

    def save_attachment(
        self,
        source_board: str,
        source_notice_id: str,
        file_name: str,
        content: bytes,
    ) -> str:
        """Persist one attachment payload and return its relative storage path."""

        safe_name = self._safe_segment(file_name) or "attachment.bin"
        relative_path = self._notice_root(source_board, source_notice_id) / "attachments" / safe_name
        return self._write_bytes(relative_path, content)

    def read_text(self, relative_path: str) -> str:
        """Read a UTF-8 raw file that was previously stored by the adapter."""

        return self._resolve(relative_path).read_text(encoding="utf-8")

    def read_bytes(self, relative_path: str) -> bytes:
        """Read raw bytes for a previously stored attachment or HTML file."""

        return self._resolve(relative_path).read_bytes()

    def exists(self, relative_path: str) -> bool:
        """Check whether a relative storage path exists under the adapter root."""

        return self._resolve(relative_path).exists()

    def _notice_root(self, source_board: str, source_notice_id: str) -> Path:
        """Build the per-notice directory used by both HTML and attachment files."""

        return Path(self._safe_segment(source_board)) / self._safe_segment(source_notice_id)

    def _resolve(self, relative_path: str) -> Path:
        """Resolve a relative storage path against the configured root directory."""

        return self.base_path / Path(relative_path)

    def _write_bytes(self, relative_path: Path, content: bytes) -> str:
        """Write bytes under the storage root and return a relative POSIX path."""

        destination = self._resolve(str(relative_path))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return relative_path.as_posix()

    def _safe_segment(self, value: str) -> str:
        """Sanitize path segments so external notice ids can be used safely."""

        return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
