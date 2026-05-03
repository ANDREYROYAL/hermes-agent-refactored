"""
Пример интеграции новых компонентов в AIAgent.

Этот файл показывает, как использовать новую архитектуру компонентов
для упрощения AIAgent.__init__ и run_conversation().
"""

from agent.components import (
    BudgetTracker,
    SessionManager,
    CredentialResolver,
    ToolDispatcher,
    MessageBuilder,
)
from agent.llm_adapter import create_adapter, LLMRequest


class RefactoredAIAgent:
    """
    Пример рефакторенного AIAgent с использованием компонентов.
    
    Вместо 1290 строк в __init__ и 3508 строк в run_conversation(),
    логика распределена по компонентам.
    """
    
    def __init__(
        self,
        model: str = "claude-sonnet-4.6",
        provider: str = "anthropic",
        api_key: str = None,
        base_url: str = None,
        max_iterations: int = 90,
        enabled_toolsets: list = None,
        disabled_toolsets: list = None,
        session_id: str = None,
        platform: str = None,
        quiet_mode: bool = False,
        **kwargs,
    ):
        """
        Упрощённый __init__ с компонентами.
        
        Было: 60+ параметров, 1290 строк
        Стало: ~15 основных параметров, ~50 строк
        """
        self.model = model
        self.quiet_mode = quiet_mode
        
        # Компоненты
        self.budget = BudgetTracker(max_iterations=max_iterations)
        
        self.session = SessionManager(
            session_id=session_id,
            platform=platform,
            **{k: v for k, v in kwargs.items() if k.startswith('user_') or k.startswith('chat_')}
        )
        
        self.credentials = CredentialResolver(
            api_key=api_key,
            provider=provider,
            credential_pool=kwargs.get('credential_pool'),
            fallback_model=kwargs.get('fallback_model'),
        )
        
        self.tools = ToolDispatcher(
            enabled_toolsets=enabled_toolsets,
            disabled_toolsets=disabled_toolsets,
            tool_delay=kwargs.get('tool_delay', 1.0),
            quiet_mode=quiet_mode,
        )
        
        self.message_builder = MessageBuilder(
            platform=platform,
            skip_context_files=kwargs.get('skip_context_files', False),
            load_soul_identity=kwargs.get('load_soul_identity', False),
        )
        
        # LLM adapter
        self.adapter = create_adapter(
            provider=provider,
            api_key=self.credentials.api_key,
            base_url=base_url,
            timeout=kwargs.get('timeout', 600.0),
        )
        
        if not quiet_mode:
            print(f"🤖 AI Agent initialized with model: {model}")
    
    def run_conversation(
        self,
        user_message: str,
        system_message: str = None,
        conversation_history: list = None,
    ) -> dict:
        """
        Упрощённый run_conversation с компонентами.
        
        Было: 3508 строк монолитной логики
        Стало: ~150 строк с делегированием компонентам
        """
        # 1. Подготовка сообщений
        history = conversation_history or []
        
        # Добавляем user message
        user_msg = self.message_builder.format_user_message(user_message)
        history.append(user_msg)
        self.session.add_message(user_msg)
        
        # Строим system prompt
        system_prompt = self.message_builder.build_system_prompt(
            base_prompt=system_message or "You are a helpful AI assistant.",
            platform_context=self.session.get_platform_context(),
        )
        
        # Строим полный список сообщений
        messages = self.message_builder.build_messages(
            system_prompt=system_prompt,
            conversation_history=history,
        )
        
        # 2. Основной цикл
        while not self.budget.is_exhausted() or self.budget.should_allow_grace_call():
            # Проверяем бюджет
            if self.budget.is_exhausted() and not self.budget.was_budget_message_injected():
                messages = self.message_builder.inject_budget_warning(
                    messages,
                    self.budget.get_remaining_iterations(),
                )
                self.budget.mark_budget_message_injected()
                self.budget.activate_grace_call()
            
            # API вызов
            self.budget.increment_api_call()
            
            request = LLMRequest(
                messages=messages,
                model=self.model,
                tools=self.tools.get_tool_schemas(),
            )
            
            try:
                response = self.adapter.complete(request)
            except Exception as e:
                # Fallback логика
                if self.credentials.should_use_fallback(e):
                    fallback = self.credentials.get_fallback_config()
                    # Переключаемся на fallback модель
                    # (упрощено для примера)
                    pass
                raise
            
            # Обрабатываем ответ
            if response.tool_calls:
                # Есть tool calls — выполняем
                tool_calls = [
                    self.tools.parse_tool_calls(response)
                ]
                
                results = self.tools.execute_tools(
                    tool_calls,
                    task_id=self.session.session_id,
                )
                
                # Добавляем результаты в историю
                for result in results:
                    tool_msg = self.message_builder.format_tool_result(
                        result.tool_call_id,
                        result.tool_name,
                        result.result,
                    )
                    messages.append(tool_msg)
                    self.session.add_message(tool_msg)
                
                # Продолжаем цикл
                continue
            
            else:
                # Финальный ответ — выходим
                assistant_msg = self.message_builder.format_assistant_message(
                    content=response.content,
                    reasoning=response.reasoning,
                )
                messages.append(assistant_msg)
                self.session.add_message(assistant_msg)
                
                return {
                    "final_response": response.content,
                    "messages": messages,
                    "usage": response.usage,
                    "session_id": self.session.session_id,
                }
        
        # Бюджет исчерпан
        return {
            "final_response": "Budget exhausted. Please start a new conversation.",
            "messages": messages,
            "session_id": self.session.session_id,
        }
    
    def chat(self, message: str) -> str:
        """Простой интерфейс для быстрого использования."""
        result = self.run_conversation(message)
        return result["final_response"]


# Пример использования
if __name__ == "__main__":
    agent = RefactoredAIAgent(
        model="claude-sonnet-4.6",
        provider="anthropic",
        max_iterations=50,
    )
    
    response = agent.chat("Hello! What can you help me with?")
    print(response)
