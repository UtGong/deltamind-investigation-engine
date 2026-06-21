import httpx

from app.agents.url_fetch_agent import UrlFetchAgent, UrlFetchInput


def test_url_fetch_agent_extracts_title_and_text(monkeypatch):
    html = """
    <html>
      <head><title>Test Article</title></head>
      <body>
        <script>ignore me</script>
        <p>Team A won the final 3-1.</p>
      </body>
    </html>
    """

    def fake_get(self, url):
        return httpx.Response(
            status_code=200,
            request=httpx.Request("GET", url),
            content=html.encode("utf-8"),
        )

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    agent = UrlFetchAgent()
    output = agent.run(UrlFetchInput(url="https://example.com/article"))

    assert output.error is None
    assert output.status_code == 200
    assert output.title == "Test Article"
    assert "Team A won the final 3-1." in output.text


def test_url_fetch_agent_handles_fetch_error(monkeypatch):
    def fake_get(self, url):
        raise httpx.ConnectError("connection failed")

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    agent = UrlFetchAgent()
    output = agent.run(UrlFetchInput(url="https://example.com/article"))

    assert output.error is not None
    assert output.text is None
