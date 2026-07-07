import json
from urllib import error, request as urlrequest

from app.core.config import get_settings
from app.schemas.llm import LLMRequest, LLMResponse


class OllamaLLMProvider:
    name = "ollama_llm_provider"

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self.timeout_seconds = settings.ollama_timeout_seconds

    def generate(self, request: LLMRequest) -> LLMResponse:
        prompt = self._messages_to_prompt(request)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature,
            },
        }

        if request.max_tokens is not None:
            payload["options"]["num_predict"] = request.max_tokens

        body = json.dumps(payload).encode("utf-8")
        http_request = urlrequest.Request(
            f"{self.base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlrequest.urlopen(http_request, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except error.URLError as exc:
            raise RuntimeError(
                "Ollama request failed. Confirm Ollama is running and "
                "OLLAMA_BASE_URL/OLLAMA_MODEL are configured."
            ) from exc

        try:
            data = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama returned invalid JSON.") from exc

        content = str(data.get("response") or "")

        return LLMResponse(
            content=content,
            provider=self.name,
            model=self.model,
            input_tokens=int(data.get("prompt_eval_count") or 0),
            output_tokens=int(data.get("eval_count") or 0),
            estimated_cost_usd=0.0,
            metadata={
                "base_url": self.base_url,
                "done": data.get("done"),
                "total_duration": data.get("total_duration"),
            },
        )

    def _messages_to_prompt(self, request: LLMRequest) -> str:
        lines = [f"{message.role.upper()}: {message.content}" for message in request.messages]

        if request.response_format == "json":
            lines.append("Return valid JSON only.")

        return "\n\n".join(lines)
