import os
from typing import Any

import anyio
import httpx

os.environ["LLM_PROVIDER"] = "mock"
os.environ["GEMINI_API_KEY"] = "test_key"
os.environ["GEMINI_MODEL"] = "gemini-test-model"

# Product default: LLM planner.
# In tests this uses MockLLMProvider, so no external API call occurs.
os.environ["SEARCH_PLANNER_PROVIDER"] = "llm"

os.environ["FREE_SEARCH_PROVIDER"] = "mock"
os.environ["PAID_SEARCH_PROVIDER"] = "tavily"
os.environ["ALLOW_PAID_SEARCH"] = "false"
os.environ["MAX_PAID_SEARCH_CALLS_PER_CASE"] = "0"

os.environ["TAVILY_API_KEY"] = "test_key"
os.environ["TAVILY_MAX_RESULTS"] = "5"
os.environ["TAVILY_SEARCH_DEPTH"] = "basic"


class CompatibleTestClient:
    __test__ = False

    """Small sync ASGI client for the installed FastAPI/Starlette/httpx stack.

    The installed Starlette TestClient waits forever in its portal startup path
    unless the external httpx2 compatibility package is installed. Tests only
    need HTTP request/response behavior, so use httpx's in-process ASGI
    transport directly and keep the public methods used by the suite.
    """

    def __init__(
        self,
        app,
        base_url: str = "http://testserver",
        raise_server_exceptions: bool = True,
        **_: Any,
    ) -> None:
        self.app = app
        self.base_url = base_url
        self.raise_server_exceptions = raise_server_exceptions

    def __enter__(self) -> "CompatibleTestClient":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async def send_request() -> httpx.Response:
            transport = httpx.ASGITransport(
                app=self.app,
                raise_app_exceptions=self.raise_server_exceptions,
                client=("testclient", 50000),
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
                follow_redirects=True,
            ) as client:
                return await client.request(method, url, **kwargs)

        return anyio.run(send_request)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)


import fastapi.testclient as fastapi_testclient

fastapi_testclient.TestClient = CompatibleTestClient
