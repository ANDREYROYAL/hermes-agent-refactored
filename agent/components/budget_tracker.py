"""
BudgetTracker — отслеживание лимитов итераций и API-вызовов.

Заменяет разбросанную логику из run_agent.py:
- iteration_budget (класс IterationBudget)
- max_iterations
- api_call_count
- _budget_exhausted_injected
- _budget_grace_call
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class BudgetTracker:
    """
    Централизованное управление бюджетом итераций агента.
    
    Отслеживает:
    - Количество API-вызовов
    - Общий бюджет итераций (shared между parent и subagents)
    - Состояние grace call (финальный вызов после исчерпания бюджета)
    """
    
    def __init__(
        self,
        max_iterations: int = 90,
        shared_budget: Optional["IterationBudget"] = None,
    ):
        """
        Args:
            max_iterations: Максимальное количество итераций для этого агента
            shared_budget: Общий бюджет с parent-агентом (для subagents)
        """
        self.max_iterations = max_iterations
        self.api_call_count = 0
        
        # Shared budget между parent и children
        if shared_budget is None:
            # Импортируем здесь, чтобы избежать циклических зависимостей
            from run_agent import IterationBudget
            self.shared_budget = IterationBudget(max_iterations)
        else:
            self.shared_budget = shared_budget
        
        # Флаги для grace call логики
        self._budget_exhausted_injected = False
        self._grace_call_active = False
    
    def increment_api_call(self) -> None:
        """Увеличить счётчик API-вызовов."""
        self.api_call_count += 1
        logger.debug(f"API call count: {self.api_call_count}/{self.max_iterations}")
    
    def is_exhausted(self) -> bool:
        """
        Проверить, исчерпан ли бюджет.
        
        Returns:
            True если достигнут лимит итераций
        """
        return (
            self.api_call_count >= self.max_iterations
            and self.shared_budget.remaining <= 0
        )
    
    def should_allow_grace_call(self) -> bool:
        """
        Проверить, нужно ли разрешить финальный grace call.
        
        Grace call — это один дополнительный вызов после исчерпания бюджета,
        чтобы дать модели шанс завершить ответ текстом вместо tool calls.
        
        Returns:
            True если grace call должен быть разрешён
        """
        return self._grace_call_active
    
    def activate_grace_call(self) -> None:
        """Активировать режим grace call."""
        if not self._grace_call_active:
            self._grace_call_active = True
            logger.info("Budget exhausted — activating grace call")
    
    def mark_budget_message_injected(self) -> None:
        """Отметить, что сообщение об исчерпании бюджета было добавлено."""
        self._budget_exhausted_injected = True
    
    def was_budget_message_injected(self) -> bool:
        """Проверить, было ли уже добавлено сообщение об исчерпании бюджета."""
        return self._budget_exhausted_injected
    
    def get_remaining_iterations(self) -> int:
        """
        Получить количество оставшихся итераций.
        
        Returns:
            Минимум из локального лимита и shared budget
        """
        local_remaining = self.max_iterations - self.api_call_count
        shared_remaining = self.shared_budget.remaining
        return min(local_remaining, shared_remaining)
    
    def get_status_summary(self) -> dict:
        """
        Получить сводку по текущему состоянию бюджета.
        
        Returns:
            Словарь с метриками бюджета
        """
        return {
            "api_calls": self.api_call_count,
            "max_iterations": self.max_iterations,
            "remaining_local": self.max_iterations - self.api_call_count,
            "remaining_shared": self.shared_budget.remaining,
            "is_exhausted": self.is_exhausted(),
            "grace_call_active": self._grace_call_active,
        }
