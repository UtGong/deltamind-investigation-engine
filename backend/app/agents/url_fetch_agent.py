import re
from html import unescape

import httpx
from pydantic import BaseModel, HttpUrl


class UrlFetchInput(BaseModel):
    url: HttpUrl


class UrlFetchOutput(BaseModel):
    url: str
    final_url: str | None = None
    status_code: int | None = None
    title: str | None = None
    text: str | None = None
    error: str | None = None


class UrlFetchAgent:
    name = "url_fetch_agent"

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    def run(self, input_data: UrlFetchInput) -> UrlFetchOutput:
        url = str(input_data.url)

        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 DeltaMindVerify/0.1 "
                        "(research prototype; URL fetch for user-submitted pages)"
                    )
                },
            ) as client:
                response = client.get(url)
                response.raise_for_status()
        except Exception as error:
            return UrlFetchOutput(
                url=url,
                error=str(error),
            )

        html = response.text or ""

        return UrlFetchOutput(
            url=url,
            final_url=str(response.url),
            status_code=response.status_code,
            title=self._extract_title(html),
            text=self._extract_text(html),
            error=None,
        )

    def _extract_title(self, html: str) -> str | None:
        match = re.search(
            r"<title[^>]*>(.*?)</title>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if not match:
            return None

        return self._clean_text(match.group(1))[:300] or None

    def _extract_text(self, html: str) -> str:
        cleaned = re.sub(
            r"<(script|style|noscript)[^>]*>.*?</\1>",
            " ",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = self._clean_text(cleaned)

        return cleaned[:20000]

    def _clean_text(self, text: str) -> str:
        text = unescape(text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
