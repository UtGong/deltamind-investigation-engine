from google import genai
from google.genai import types

from app.core.config import get_settings
from app.schemas.llm import LLMRequest, LLMResponse


class GeminiLLMProvider:
    name = "gemini_llm_provider"

    def __init__(self) -> None:
        settings = get_settings()

        if not settings.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is missing. Set it in backend/.env or environment variables."
            )

        self.model = settings.gemini_model
        self.client = genai.Client(api_key=settings.gemini_api_key)

    def generate(self, request: LLMRequest) -> LLMResponse:
        contents = self._messages_to_contents(request)

        config = types.GenerateContentConfig(
            temperature=request.temperature,
            max_output_tokens=request.max_tokens,
            response_mime_type=(
                "application/json"
                if request.response_format == "json"
                else None
            ),
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

        text = response.text or ""

        usage = getattr(response, "usage_metadata", None)
        input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)

        return LLMResponse(
            content=text,
            provider=self.name,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=0.0,
            metadata={
                "usage_metadata": usage.model_dump() if hasattr(usage, "model_dump") else {},
            },
        )

    def _messages_to_contents(self, request: LLMRequest) -> str:
        lines: list[str] = []

        for message in request.messages:
            lines.append(f"{message.role.upper()}: {message.content}")

        return "\n\n".join(lines)
