from __future__ import annotations

import httpx


class HttpTextFetcher:
    """Fetch HTML text over HTTP for production collector runs."""

    def __init__(self, timeout_seconds: float = 10.0):
        """
        HTTP 클라이언트를 재사용 가능하도록 초기화합니다.
        리다이렉트 허용 및 연결 타임아웃 설정을 기본적으로 적용합니다.
        """

        self._client = httpx.Client(
            follow_redirects=True,
            timeout=timeout_seconds,
        )

    def fetch(self, url: str) -> str:
        """
        기존 호출부와의 호환성을 유지하기 위한 텍스트 수집 래퍼(Wrapper) 헬퍼 메서드입니다.
        내부적으로 fetch_text를 호출하여 파싱된 HTML 문자열을 반환합니다.
        """

        return self.fetch_text(url)

    def fetch_text(self, url: str) -> str:
        """
        주어진 URL에서 HTML 텍스트를 다운로드하고 디코딩하여 반환합니다.
        게시판의 공지 목록 또는 개별 상세 페이지를 크롤링할 때 사용됩니다.
        """

        response = self._client.get(url)
        response.raise_for_status()
        return response.text

    def fetch_bytes(self, url: str) -> bytes:
        """
        원격 경로로부터 첨부파일 같은 바이너리(Bytes) 데이터를 다운로드합니다.
        원시(Raw) 저장소에 HWP나 PDF 파일들을 보관하는 목적으로 사용됩니다.
        """

        response = self._client.get(url)
        response.raise_for_status()
        return response.content

    def close(self) -> None:
        """
        작업이 끝난 HTTP 클라이언트의 통신 리소스를 안전하게 해제합니다.
        장기 실행되는 백그라운드 수집 서비스의 네트워크 연결 누수를 방지합니다.
        """

        self._client.close()
