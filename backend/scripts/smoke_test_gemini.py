import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.providers.llm.gemini_provider import GeminiLLMProvider
from app.schemas.llm import LLMMessage, LLMRequest


def main() -> int:
    settings = get_settings()

    print("=== Gemini Smoke Test ===")
    print(f"APP_ENV: {settings.app_env}")
    print(f"GEMINI_MODEL: {settings.gemini_model}")

    if not settings.gemini_api_key:
        print("ERROR: GEMINI_API_KEY is missing.")
        print("Set it in backend/.env first.")
        return 1

    provider = GeminiLLMProvider()

    request = LLMRequest(
        messages=[
            LLMMessage(
                role="system",
                content=(
                    "You are a claim decomposition agent. "
                    "Return valid JSON only."
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    "Extract atomic claims from this text. "
                    "Return JSON with a top-level 'claims' array. "
                    "Each item must have claim_text, claim_type, subject, "
                    "predicate, object, and confidence.\n\n"
                    "Text: Player X joined Club A on June 10. "
                    "Team A won the final 3-1. Player Y is injured."
                ),
            ),
        ],
        temperature=0.0,
        response_format="json",
    )

    response = provider.generate(request)

    print("\n--- Provider ---")
    print(response.provider)

    print("\n--- Model ---")
    print(response.model)

    print("\n--- Token Usage ---")
    print(f"Input tokens: {response.input_tokens}")
    print(f"Output tokens: {response.output_tokens}")

    print("\n--- Raw Response ---")
    print(response.content)

    print("\n--- JSON Parse Check ---")
    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError as error:
        print("FAILED: Gemini response was not valid JSON.")
        print(error)
        return 1

    if isinstance(parsed, dict):
        claims = parsed.get("claims", [])
    elif isinstance(parsed, list):
        claims = parsed
    else:
        print("FAILED: Gemini JSON was neither object nor list.")
        return 1

    if not isinstance(claims, list) or not claims:
        print("FAILED: No claims found.")
        return 1

    print(f"PASSED: Parsed {len(claims)} claim(s).")

    for index, claim in enumerate(claims, start=1):
        print(f"\nClaim {index}:")
        print(json.dumps(claim, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
