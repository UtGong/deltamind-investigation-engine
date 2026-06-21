import json
import re

from app.schemas.llm import LLMRequest, LLMResponse


class MockLLMProvider:
    name = "mock_llm_provider"
    model = "mock-llm-v0"

    def generate(self, request: LLMRequest) -> LLMResponse:
        joined_prompt = "\n".join(message.content for message in request.messages)

        if "extract atomic claims" in joined_prompt.lower():
            input_text = self._extract_input_text(joined_prompt)
            claims = self._make_claims(input_text)
            content = json.dumps({"claims": claims})
        else:
            content = json.dumps({"message": "Mock LLM response."})

        return LLMResponse(
            content=content,
            provider=self.name,
            model=self.model,
            input_tokens=len(joined_prompt.split()),
            output_tokens=len(content.split()),
            estimated_cost_usd=0.0,
            metadata={"mock": True},
        )

    def _extract_input_text(self, prompt: str) -> str:
        marker = "Input:"
        if marker not in prompt:
            return prompt

        return prompt.split(marker, maxsplit=1)[1].strip()

    def _make_claims(self, input_text: str) -> list[dict]:
        sentences = [
            item.strip()
            for item in re.split(r"(?<=[.!?])\s+|\n+", input_text)
            if item.strip()
        ]

        if not sentences:
            sentences = [input_text.strip()]

        return [
            {
                "claim_text": sentence,
                "claim_type": self._infer_claim_type(sentence),
                "subject": None,
                "predicate": None,
                "object": None,
                "confidence": 0.78,
            }
            for sentence in sentences
        ]

    def _infer_claim_type(self, text: str) -> str:
        lowered = text.lower()

        if any(word in lowered for word in ["joined", "signed", "transfer"]):
            return "transfer"

        if any(word in lowered for word in ["injured", "injury", "available", "returned"]):
            return "injury"

        if any(word in lowered for word in ["won", "lost", "beat", "defeated", "score"]):
            return "result"

        if any(word in lowered for word in ["schedule", "fixture", "match date"]):
            return "schedule"

        return "unknown"
