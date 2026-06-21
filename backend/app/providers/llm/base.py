from abc import ABC, abstractmethod

from app.schemas.llm import LLMRequest, LLMResponse


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
