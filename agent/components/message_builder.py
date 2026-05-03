"""
MessageBuilder — построение промптов и system messages.

Заменяет разбросанную логику из run_agent.py:
- System prompt construction
- Context files injection (SOUL.md, AGENTS.md, .cursorrules)
- Platform-specific formatting hints
- Prefill messages
- Memory context injection
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class MessageBuilder:
    """
    Централизованное построение промптов для LLM.
    
    Отвечает за:
    - Построение system prompt с контекстными файлами
    - Добавление platform-specific hints
    - Инъекцию памяти и prefill messages
    - Форматирование для разных провайдеров
    """
    
    def __init__(
        self,
        platform: Optional[str] = None,
        skip_context_files: bool = False,
        load_soul_identity: bool = False,
        ephemeral_system_prompt: Optional[str] = None,
    ):
        """
        Args:
            platform: Платформа (cli, telegram, discord, etc.)
            skip_context_files: Пропустить загрузку контекстных файлов
            load_soul_identity: Загрузить SOUL.md даже если skip_context_files=True
            ephemeral_system_prompt: Временный system prompt (не сохраняется в траектории)
        """
        self.platform = platform
        self.skip_context_files = skip_context_files
        self.load_soul_identity = load_soul_identity
        self.ephemeral_system_prompt = ephemeral_system_prompt
        
        # Кэш загруженных контекстных файлов
        self._context_cache: Optional[List[str]] = None
        
        logger.debug(f"MessageBuilder initialized (platform={platform})")
    
    def build_system_prompt(
        self,
        base_prompt: str,
        context_files: Optional[List[str]] = None,
        memory_context: Optional[str] = None,
        platform_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Построить полный system prompt.
        
        Args:
            base_prompt: Базовый промпт
            context_files: Контекстные файлы (SOUL.md, AGENTS.md, etc.)
            memory_context: Контекст из памяти
            platform_context: Контекст платформы (user_name, chat_type, etc.)
        
        Returns:
            Полный system prompt
        """
        parts = []
        
        # Базовый промпт
        if base_prompt:
            parts.append(base_prompt)
        
        # Контекстные файлы
        if context_files:
            parts.append("\n\n# Context Files\n")
            parts.extend(context_files)
        
        # Platform-specific hints
        if self.platform:
            platform_hint = self._get_platform_hint(platform_context or {})
            if platform_hint:
                parts.append(f"\n\n# Platform Context\n{platform_hint}")
        
        # Memory context
        if memory_context:
            parts.append(f"\n\n# Memory Context\n{memory_context}")
        
        # Ephemeral prompt (не сохраняется в траектории)
        if self.ephemeral_system_prompt:
            parts.append(f"\n\n{self.ephemeral_system_prompt}")
        
        return "\n".join(parts)
    
    def _get_platform_hint(self, context: Dict[str, Any]) -> str:
        """
        Получить platform-specific hint.
        
        Args:
            context: Контекст платформы
        
        Returns:
            Hint для system prompt
        """
        hints = []
        
        if self.platform == "telegram":
            hints.append("You are communicating via Telegram.")
            if context.get("chat_type") == "group":
                hints.append("This is a group chat.")
        
        elif self.platform == "discord":
            hints.append("You are communicating via Discord.")
            if context.get("chat_type") == "channel":
                hints.append("This is a Discord channel.")
        
        elif self.platform == "whatsapp":
            hints.append("You are communicating via WhatsApp.")
        
        elif self.platform == "cli":
            hints.append("You are in a command-line interface.")
        
        # User name
        if context.get("user_name"):
            hints.append(f"User name: {context['user_name']}")
        
        # Chat name
        if context.get("chat_name"):
            hints.append(f"Chat name: {context['chat_name']}")
        
        return "\n".join(hints) if hints else ""
    
    def build_messages(
        self,
        system_prompt: str,
        conversation_history: List[Dict[str, Any]],
        prefill_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Построить полный список сообщений для LLM.
        
        Args:
            system_prompt: System prompt
            conversation_history: История сообщений
            prefill_messages: Предзаполненные сообщения
        
        Returns:
            Список сообщений в формате OpenAI
        """
        messages = []
        
        # System message
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt,
            })
        
        # Prefill messages
        if prefill_messages:
            messages.extend(prefill_messages)
        
        # Conversation history
        messages.extend(conversation_history)
        
        return messages
    
    def format_tool_result(
        self,
        tool_call_id: str,
        tool_name: str,
        result: str,
    ) -> Dict[str, Any]:
        """
        Форматировать результат инструмента для добавления в историю.
        
        Args:
            tool_call_id: ID вызова инструмента
            tool_name: Имя инструмента
            result: Результат выполнения
        
        Returns:
            Сообщение в формате OpenAI
        """
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result,
        }
    
    def format_assistant_message(
        self,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        reasoning: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Форматировать сообщение ассистента.
        
        Args:
            content: Текстовый контент
            tool_calls: Вызовы инструментов
            reasoning: Reasoning/thinking контент
        
        Returns:
            Сообщение в формате OpenAI
        """
        message = {
            "role": "assistant",
            "content": content,
        }
        
        if tool_calls:
            message["tool_calls"] = tool_calls
        
        if reasoning:
            message["reasoning"] = reasoning
        
        return message
    
    def format_user_message(
        self,
        content: str,
        images: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Форматировать сообщение пользователя.
        
        Args:
            content: Текстовый контент
            images: Изображения (для multimodal)
        
        Returns:
            Сообщение в формате OpenAI
        """
        if images:
            # Multimodal format
            content_parts = [{"type": "text", "text": content}]
            content_parts.extend(images)
            return {
                "role": "user",
                "content": content_parts,
            }
        else:
            return {
                "role": "user",
                "content": content,
            }
    
    def inject_budget_warning(
        self,
        messages: List[Dict[str, Any]],
        remaining_iterations: int,
    ) -> List[Dict[str, Any]]:
        """
        Добавить предупреждение об исчерпании бюджета.
        
        Args:
            messages: Текущие сообщения
            remaining_iterations: Оставшиеся итерации
        
        Returns:
            Обновлённый список сообщений
        """
        warning = (
            f"\n\n[System: You have {remaining_iterations} iterations remaining. "
            f"Please provide a final text response instead of calling more tools.]"
        )
        
        # Добавляем к последнему tool result или создаём новое system message
        if messages and messages[-1]["role"] == "tool":
            messages[-1]["content"] += warning
        else:
            messages.append({
                "role": "system",
                "content": warning,
            })
        
        return messages
    
    def sanitize_context_spans(self, text: str) -> str:
        """
        Удалить <memory-context> спаны из текста.
        
        Args:
            text: Текст с возможными спанами
        
        Returns:
            Очищенный текст
        """
        import re
        # Удаляем <memory-context>...</memory-context> блоки
        return re.sub(r'<memory-context>.*?</memory-context>', '', text, flags=re.DOTALL)
    
    def get_message_token_estimate(self, messages: List[Dict[str, Any]]) -> int:
        """
        Оценить количество токенов в сообщениях.
        
        Args:
            messages: Список сообщений
        
        Returns:
            Примерное количество токенов
        """
        # Простая эвристика: ~4 символа = 1 токен
        total_chars = 0
        
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                # Multimodal content
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total_chars += len(part.get("text", ""))
        
        return total_chars // 4
    
    def truncate_history(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
    ) -> List[Dict[str, Any]]:
        """
        Обрезать историю до максимального количества токенов.
        
        Args:
            messages: Список сообщений
            max_tokens: Максимальное количество токенов
        
        Returns:
            Обрезанный список (сохраняет system message и последние сообщения)
        """
        if not messages:
            return messages
        
        # Сохраняем system message
        system_messages = [m for m in messages if m["role"] == "system"]
        other_messages = [m for m in messages if m["role"] != "system"]
        
        # Оцениваем токены
        current_tokens = self.get_message_token_estimate(messages)
        
        if current_tokens <= max_tokens:
            return messages
        
        # Удаляем старые сообщения пока не влезем в лимит
        while other_messages and current_tokens > max_tokens:
            # Удаляем самое старое сообщение
            removed = other_messages.pop(0)
            current_tokens -= self.get_message_token_estimate([removed])
        
        return system_messages + other_messages
