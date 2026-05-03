"""
LLMAdapter — базовый интерфейс для всех LLM провайдеров.

Унифицирует работу с Anthropic, OpenAI, Bedrock, Gemini, и другими провайдерами.
Заменяет разбросанную логику из anthropic_adapter.py, bedrock_adapter.py,
gemini_native_adapter.py, codex_responses_adapter.py и т.д.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Iterator
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMRequest:
    """Унифицированный запрос к LLM."""
    
    messages: List[Dict[str, Any]]
    model: str
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    tools: Optional[List[Dict[str, Any]]] = None
    stream: bool = False
    reasoning_config: Optional[Dict[str, Any]] = None
    extra_params: Optional[Dict[str, Any]] = None


@dataclass
class LLMResponse:
    """Унифицированный ответ от LLM."""
    
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    reasoning: Optional[str] = None
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    raw_response: Optional[Any] = None


class LLMAdapter(ABC):
    """
    Базовый интерфейс для всех LLM провайдеров.
    
    Каждый провайдер (Anthropic, OpenAI, Bedrock, etc.) реализует этот интерфейс,
    что позволяет единообразно работать с ними в AIAgent.
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ):
        """
        Args:
            api_key: API ключ провайдера
            base_url: Базовый URL (если отличается от дефолтного)
            timeout: Таймаут запросов в секундах
            **kwargs: Дополнительные параметры провайдера
        """
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.extra_config = kwargs
        
        logger.debug(f"Initialized {self.__class__.__name__}")
    
    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Выполнить синхронный запрос к LLM.
        
        Args:
            request: Параметры запроса
        
        Returns:
            Ответ от модели
        """
        pass
    
    @abstractmethod
    def stream(self, request: LLMRequest) -> Iterator[Dict[str, Any]]:
        """
        Выполнить стриминговый запрос к LLM.
        
        Args:
            request: Параметры запроса
        
        Yields:
            Чанки ответа (delta, tool_calls, reasoning, etc.)
        """
        pass
    
    @abstractmethod
    def get_context_length(self, model: str) -> int:
        """
        Получить максимальную длину контекста для модели.
        
        Args:
            model: Имя модели
        
        Returns:
            Длина контекста в токенах
        """
        pass
    
    @abstractmethod
    def supports_tool_calling(self, model: str) -> bool:
        """
        Проверить, поддерживает ли модель tool calling.
        
        Args:
            model: Имя модели
        
        Returns:
            True если поддерживает
        """
        pass
    
    def supports_reasoning(self, model: str) -> bool:
        """
        Проверить, поддерживает ли модель reasoning (thinking).
        
        Args:
            model: Имя модели
        
        Returns:
            True если поддерживает
        """
        # По умолчанию не поддерживает, переопределяется в конкретных адаптерах
        return False
    
    def supports_prompt_caching(self, model: str) -> bool:
        """
        Проверить, поддерживает ли модель prompt caching.
        
        Args:
            model: Имя модели
        
        Returns:
            True если поддерживает
        """
        # По умолчанию не поддерживает
        return False
    
    def close(self) -> None:
        """Закрыть соединения и освободить ресурсы."""
        pass


class AnthropicAdapter(LLMAdapter):
    """Адаптер для Anthropic Claude API."""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, timeout: Optional[float] = None, **kwargs):
        super().__init__(api_key, base_url, timeout, **kwargs)
        
        # Ленивый импорт Anthropic SDK
        from anthropic import Anthropic
        self.client = Anthropic(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout or 600.0,
        )
    
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Синхронный запрос к Claude."""
        # Конвертируем messages в формат Anthropic
        system_messages = [m for m in request.messages if m["role"] == "system"]
        user_messages = [m for m in request.messages if m["role"] != "system"]
        
        system_prompt = "\n\n".join(m["content"] for m in system_messages) if system_messages else None
        
        response = self.client.messages.create(
            model=request.model,
            messages=user_messages,
            system=system_prompt,
            max_tokens=request.max_tokens or 4096,
            temperature=request.temperature,
            tools=request.tools,
        )
        
        # Конвертируем ответ в унифицированный формат
        content = ""
        tool_calls = []
        
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": block.input,
                    }
                })
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=response.stop_reason,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            raw_response=response,
        )
    
    def stream(self, request: LLMRequest) -> Iterator[Dict[str, Any]]:
        """Стриминговый запрос к Claude."""
        system_messages = [m for m in request.messages if m["role"] == "system"]
        user_messages = [m for m in request.messages if m["role"] != "system"]
        
        system_prompt = "\n\n".join(m["content"] for m in system_messages) if system_messages else None
        
        with self.client.messages.stream(
            model=request.model,
            messages=user_messages,
            system=system_prompt,
            max_tokens=request.max_tokens or 4096,
            temperature=request.temperature,
            tools=request.tools,
        ) as stream:
            for event in stream:
                yield {"type": event.type, "data": event}
    
    def get_context_length(self, model: str) -> int:
        """Получить длину контекста для Claude."""
        if "opus-4" in model or "sonnet-4" in model:
            return 200_000
        return 200_000  # Дефолт для Claude
    
    def supports_tool_calling(self, model: str) -> bool:
        """Claude поддерживает tool calling."""
        return True
    
    def supports_reasoning(self, model: str) -> bool:
        """Claude 4.6+ поддерживает extended thinking."""
        return "4.6" in model or "4.7" in model or "4-6" in model or "4-7" in model
    
    def supports_prompt_caching(self, model: str) -> bool:
        """Claude поддерживает prompt caching."""
        return True


class OpenAIAdapter(LLMAdapter):
    """Адаптер для OpenAI API (и совместимых)."""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, timeout: Optional[float] = None, **kwargs):
        super().__init__(api_key, base_url, timeout, **kwargs)
        
        from openai import OpenAI
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout or 600.0,
        )
    
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Синхронный запрос к OpenAI."""
        response = self.client.chat.completions.create(
            model=request.model,
            messages=request.messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            tools=request.tools,
        )
        
        message = response.choices[0].message
        
        return LLMResponse(
            content=message.content or "",
            tool_calls=[
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in (message.tool_calls or [])
            ] if message.tool_calls else None,
            finish_reason=response.choices[0].finish_reason,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            } if response.usage else None,
            raw_response=response,
        )
    
    def stream(self, request: LLMRequest) -> Iterator[Dict[str, Any]]:
        """Стриминговый запрос к OpenAI."""
        stream = self.client.chat.completions.create(
            model=request.model,
            messages=request.messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            tools=request.tools,
            stream=True,
        )
        
        for chunk in stream:
            yield {"type": "chunk", "data": chunk}
    
    def get_context_length(self, model: str) -> int:
        """Получить длину контекста для OpenAI."""
        if "gpt-5" in model:
            return 400_000
        elif "gpt-4" in model:
            return 128_000
        return 128_000
    
    def supports_tool_calling(self, model: str) -> bool:
        """OpenAI поддерживает tool calling."""
        return True


def create_adapter(
    provider: str,
    api_key: str,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs,
) -> LLMAdapter:
    """
    Фабрика для создания адаптера по имени провайдера.
    
    Args:
        provider: Имя провайдера (anthropic, openai, bedrock, etc.)
        api_key: API ключ
        base_url: Базовый URL
        timeout: Таймаут
        **kwargs: Дополнительные параметры
    
    Returns:
        Экземпляр LLMAdapter
    """
    provider_lower = provider.lower()
    
    if provider_lower == "anthropic":
        return AnthropicAdapter(api_key, base_url, timeout, **kwargs)
    elif provider_lower in ("openai", "openrouter", "openai-codex"):
        return OpenAIAdapter(api_key, base_url, timeout, **kwargs)
    else:
        # Fallback — используем OpenAI-совместимый адаптер
        logger.warning(f"Unknown provider '{provider}', using OpenAI-compatible adapter")
        return OpenAIAdapter(api_key, base_url, timeout, **kwargs)
