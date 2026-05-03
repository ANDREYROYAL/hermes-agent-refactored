"""
ToolDispatcher — оркестрация вызовов инструментов.

Заменяет разбросанную логику из run_agent.py:
- handle_function_call() вызовы
- Concurrent tool execution
- Tool progress callbacks
- Tool guardrails
- Interrupt handling во время tool execution
"""

import logging
import json
import time
import concurrent.futures
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Представление вызова инструмента."""
    
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ToolResult:
    """Результат выполнения инструмента."""
    
    tool_call_id: str
    tool_name: str
    result: str
    error: Optional[str] = None
    execution_time: float = 0.0


class ToolDispatcher:
    """
    Централизованное управление вызовами инструментов.
    
    Отвечает за:
    - Парсинг tool calls из ответа модели
    - Параллельное/последовательное выполнение
    - Обработку ошибок и retry логику
    - Callbacks для прогресса
    - Interrupt handling
    """
    
    def __init__(
        self,
        enabled_toolsets: Optional[List[str]] = None,
        disabled_toolsets: Optional[List[str]] = None,
        tool_delay: float = 1.0,
        max_workers: int = 5,
        tool_progress_callback: Optional[Callable] = None,
        tool_start_callback: Optional[Callable] = None,
        tool_complete_callback: Optional[Callable] = None,
        quiet_mode: bool = False,
    ):
        """
        Args:
            enabled_toolsets: Список разрешённых toolsets
            disabled_toolsets: Список запрещённых toolsets
            tool_delay: Задержка между вызовами инструментов (секунды)
            max_workers: Максимальное количество параллельных workers
            tool_progress_callback: Callback для прогресса выполнения
            tool_start_callback: Callback при старте инструмента
            tool_complete_callback: Callback при завершении инструмента
            quiet_mode: Подавить вывод прогресса
        """
        self.enabled_toolsets = enabled_toolsets
        self.disabled_toolsets = disabled_toolsets
        self.tool_delay = tool_delay
        self.max_workers = max_workers
        self.quiet_mode = quiet_mode
        
        # Callbacks
        self.tool_progress_callback = tool_progress_callback
        self.tool_start_callback = tool_start_callback
        self.tool_complete_callback = tool_complete_callback
        
        # Состояние
        self._interrupt_requested = False
        self._current_tool: Optional[str] = None
        
        # Загружаем доступные инструменты
        self._available_tools = self._load_tools()
        
        logger.debug(f"ToolDispatcher initialized with {len(self._available_tools)} tools")
    
    def _load_tools(self) -> Dict[str, Dict[str, Any]]:
        """
        Загрузить доступные инструменты из registry.
        
        Returns:
            Словарь {tool_name: tool_schema}
        """
        try:
            from model_tools import get_tool_definitions
            
            tools = get_tool_definitions(
                enabled_toolsets=self.enabled_toolsets,
                disabled_toolsets=self.disabled_toolsets,
                quiet_mode=self.quiet_mode,
            )
            
            # Конвертируем в словарь для быстрого доступа
            return {
                tool["function"]["name"]: tool
                for tool in tools
            }
        except Exception as e:
            logger.error(f"Failed to load tools: {e}")
            return {}
    
    def parse_tool_calls(self, response: Any) -> List[ToolCall]:
        """
        Распарсить tool calls из ответа модели.
        
        Args:
            response: Ответ от LLM (OpenAI format)
        
        Returns:
            Список ToolCall объектов
        """
        tool_calls = []
        
        # OpenAI format
        if hasattr(response, "choices") and response.choices:
            message = response.choices[0].message
            if hasattr(message, "tool_calls") and message.tool_calls:
                for tc in message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                        tool_calls.append(ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=args,
                        ))
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse tool arguments: {e}")
                        # Добавляем с пустыми аргументами
                        tool_calls.append(ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments={},
                        ))
        
        return tool_calls
    
    def execute_tool(
        self,
        tool_call: ToolCall,
        task_id: Optional[str] = None,
    ) -> ToolResult:
        """
        Выполнить один инструмент.
        
        Args:
            tool_call: Вызов инструмента
            task_id: ID задачи (для subagents)
        
        Returns:
            Результат выполнения
        """
        start_time = time.time()
        self._current_tool = tool_call.name
        
        # Callback при старте
        if self.tool_start_callback:
            try:
                self.tool_start_callback(tool_call.name, tool_call.arguments)
            except Exception as e:
                logger.warning(f"tool_start_callback failed: {e}")
        
        try:
            # Проверяем interrupt
            if self._interrupt_requested:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    result="",
                    error="Execution interrupted by user",
                    execution_time=time.time() - start_time,
                )
            
            # Вызываем инструмент через registry
            from model_tools import handle_function_call
            
            result_str = handle_function_call(
                tool_call.name,
                tool_call.arguments,
                task_id=task_id,
            )
            
            execution_time = time.time() - start_time
            
            # Callback при завершении
            if self.tool_complete_callback:
                try:
                    self.tool_complete_callback(
                        tool_call.name,
                        result_str,
                        execution_time,
                    )
                except Exception as e:
                    logger.warning(f"tool_complete_callback failed: {e}")
            
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                result=result_str,
                execution_time=execution_time,
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Tool execution failed: {str(e)}"
            logger.error(f"{error_msg} (tool={tool_call.name})")
            
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                result="",
                error=error_msg,
                execution_time=execution_time,
            )
        
        finally:
            self._current_tool = None
    
    def execute_tools_sequential(
        self,
        tool_calls: List[ToolCall],
        task_id: Optional[str] = None,
    ) -> List[ToolResult]:
        """
        Выполнить инструменты последовательно.
        
        Args:
            tool_calls: Список вызовов
            task_id: ID задачи
        
        Returns:
            Список результатов
        """
        results = []
        
        for i, tool_call in enumerate(tool_calls):
            if self._interrupt_requested:
                logger.info("Tool execution interrupted")
                break
            
            # Задержка между вызовами (кроме первого)
            if i > 0 and self.tool_delay > 0:
                time.sleep(self.tool_delay)
            
            result = self.execute_tool(tool_call, task_id)
            results.append(result)
        
        return results
    
    def execute_tools_concurrent(
        self,
        tool_calls: List[ToolCall],
        task_id: Optional[str] = None,
    ) -> List[ToolResult]:
        """
        Выполнить инструменты параллельно.
        
        Args:
            tool_calls: Список вызовов
            task_id: ID задачи
        
        Returns:
            Список результатов (в том же порядке что и tool_calls)
        """
        results = [None] * len(tool_calls)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Запускаем все инструменты
            futures = {
                executor.submit(self.execute_tool, tc, task_id): i
                for i, tc in enumerate(tool_calls)
            }
            
            # Собираем результаты
            for future in concurrent.futures.as_completed(futures):
                idx = futures[future]
                try:
                    result = future.result()
                    results[idx] = result
                except Exception as e:
                    logger.error(f"Concurrent tool execution failed: {e}")
                    results[idx] = ToolResult(
                        tool_call_id=tool_calls[idx].id,
                        tool_name=tool_calls[idx].name,
                        result="",
                        error=str(e),
                    )
        
        return results
    
    def execute_tools(
        self,
        tool_calls: List[ToolCall],
        task_id: Optional[str] = None,
        concurrent: bool = False,
    ) -> List[ToolResult]:
        """
        Выполнить инструменты (последовательно или параллельно).
        
        Args:
            tool_calls: Список вызовов
            task_id: ID задачи
            concurrent: Выполнять параллельно
        
        Returns:
            Список результатов
        """
        if not tool_calls:
            return []
        
        logger.info(f"Executing {len(tool_calls)} tools ({'concurrent' if concurrent else 'sequential'})")
        
        if concurrent:
            return self.execute_tools_concurrent(tool_calls, task_id)
        else:
            return self.execute_tools_sequential(tool_calls, task_id)
    
    def request_interrupt(self) -> None:
        """Запросить прерывание выполнения инструментов."""
        self._interrupt_requested = True
        logger.info("Tool execution interrupt requested")
    
    def clear_interrupt(self) -> None:
        """Сбросить флаг прерывания."""
        self._interrupt_requested = False
    
    def is_interrupted(self) -> bool:
        """Проверить, запрошено ли прерывание."""
        return self._interrupt_requested
    
    def get_current_tool(self) -> Optional[str]:
        """Получить имя текущего выполняющегося инструмента."""
        return self._current_tool
    
    def get_available_tools(self) -> List[str]:
        """Получить список доступных инструментов."""
        return list(self._available_tools.keys())
    
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Получить схемы всех доступных инструментов."""
        return list(self._available_tools.values())
