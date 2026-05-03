"""
SessionManager — управление сессиями, историей сообщений и контекстом.

Заменяет разбросанную логику из run_agent.py:
- session_id
- session_db
- conversation_history
- prefill_messages
- context files (SOUL.md, AGENTS.md, .cursorrules)
"""

import logging
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Централизованное управление сессией агента.
    
    Отвечает за:
    - Генерацию и хранение session_id
    - Управление историей сообщений
    - Загрузку контекстных файлов
    - Интеграцию с SessionDB
    """
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        session_db=None,
        parent_session_id: Optional[str] = None,
        prefill_messages: Optional[List[Dict[str, Any]]] = None,
        skip_context_files: bool = False,
        load_soul_identity: bool = False,
        platform: Optional[str] = None,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        chat_id: Optional[str] = None,
        chat_name: Optional[str] = None,
        chat_type: Optional[str] = None,
        thread_id: Optional[str] = None,
        gateway_session_key: Optional[str] = None,
    ):
        """
        Args:
            session_id: ID сессии (генерируется автоматически если None)
            session_db: Экземпляр SessionDB для персистентности
            parent_session_id: ID родительской сессии (для subagents)
            prefill_messages: Предзаполненные сообщения для контекста
            skip_context_files: Пропустить загрузку SOUL.md, AGENTS.md, .cursorrules
            load_soul_identity: Загрузить ~/.hermes/SOUL.md даже если skip_context_files=True
            platform: Платформа (cli, telegram, discord, whatsapp, etc.)
            user_id: ID пользователя на платформе
            user_name: Имя пользователя
            chat_id: ID чата
            chat_name: Название чата
            chat_type: Тип чата (dm, group, channel)
            thread_id: ID треда (для платформ с тредами)
            gateway_session_key: Стабильный ключ сессии для gateway
        """
        self.session_id = session_id or self._generate_session_id()
        self.session_db = session_db
        self.parent_session_id = parent_session_id
        self.prefill_messages = list(prefill_messages or [])
        self.skip_context_files = skip_context_files
        self.load_soul_identity = load_soul_identity
        
        # Platform context
        self.platform = platform
        self.user_id = user_id
        self.user_name = user_name
        self.chat_id = chat_id
        self.chat_name = chat_name
        self.chat_type = chat_type
        self.thread_id = thread_id
        self.gateway_session_key = gateway_session_key
        
        # История сообщений (в памяти)
        self._conversation_history: List[Dict[str, Any]] = []
        
        logger.info(f"Session initialized: {self.session_id}")
    
    @staticmethod
    def _generate_session_id() -> str:
        """Сгенерировать уникальный ID сессии."""
        return str(uuid.uuid4())
    
    def add_message(self, message: Dict[str, Any]) -> None:
        """
        Добавить сообщение в историю.
        
        Args:
            message: Сообщение в формате OpenAI (role, content, tool_calls, etc.)
        """
        self._conversation_history.append(message)
        logger.debug(f"Added message: role={message.get('role')}, session={self.session_id}")
    
    def get_history(self) -> List[Dict[str, Any]]:
        """
        Получить полную историю сообщений.
        
        Returns:
            Список сообщений
        """
        return self._conversation_history.copy()
    
    def clear_history(self) -> None:
        """Очистить историю сообщений."""
        self._conversation_history.clear()
        logger.info(f"History cleared for session {self.session_id}")
    
    def load_context_files(self, hermes_home: Path, cwd: Path) -> List[str]:
        """
        Загрузить контекстные файлы (SOUL.md, AGENTS.md, .cursorrules).
        
        Args:
            hermes_home: Путь к ~/.hermes
            cwd: Текущая рабочая директория
        
        Returns:
            Список загруженных файлов с их содержимым
        """
        if self.skip_context_files and not self.load_soul_identity:
            return []
        
        context_files = []
        
        # ~/.hermes/SOUL.md — личная идентичность
        if self.load_soul_identity or not self.skip_context_files:
            soul_path = hermes_home / "SOUL.md"
            if soul_path.exists():
                try:
                    content = soul_path.read_text(encoding="utf-8")
                    context_files.append(f"# SOUL.md\n{content}")
                    logger.debug(f"Loaded SOUL.md from {soul_path}")
                except Exception as e:
                    logger.warning(f"Failed to load SOUL.md: {e}")
        
        if not self.skip_context_files:
            # AGENTS.md — инструкции для агентов
            agents_path = cwd / "AGENTS.md"
            if agents_path.exists():
                try:
                    content = agents_path.read_text(encoding="utf-8")
                    context_files.append(f"# AGENTS.md\n{content}")
                    logger.debug(f"Loaded AGENTS.md from {agents_path}")
                except Exception as e:
                    logger.warning(f"Failed to load AGENTS.md: {e}")
            
            # .cursorrules — правила проекта
            cursorrules_path = cwd / ".cursorrules"
            if cursorrules_path.exists():
                try:
                    content = cursorrules_path.read_text(encoding="utf-8")
                    context_files.append(f"# .cursorrules\n{content}")
                    logger.debug(f"Loaded .cursorrules from {cursorrules_path}")
                except Exception as e:
                    logger.warning(f"Failed to load .cursorrules: {e}")
        
        return context_files
    
    def save_to_db(self, trajectory_data: Dict[str, Any]) -> None:
        """
        Сохранить траекторию в SessionDB.
        
        Args:
            trajectory_data: Данные траектории для сохранения
        """
        if self.session_db is None:
            return
        
        try:
            self.session_db.save_trajectory(
                session_id=self.session_id,
                data=trajectory_data,
            )
            logger.debug(f"Trajectory saved to DB: session={self.session_id}")
        except Exception as e:
            logger.error(f"Failed to save trajectory: {e}")
    
    def get_platform_context(self) -> Dict[str, Any]:
        """
        Получить контекст платформы для system prompt.
        
        Returns:
            Словарь с информацией о платформе и пользователе
        """
        context = {}
        
        if self.platform:
            context["platform"] = self.platform
        
        if self.user_name:
            context["user_name"] = self.user_name
        
        if self.chat_type:
            context["chat_type"] = self.chat_type
        
        if self.chat_name:
            context["chat_name"] = self.chat_name
        
        return context
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Получить сводку по сессии.
        
        Returns:
            Словарь с метаданными сессии
        """
        return {
            "session_id": self.session_id,
            "parent_session_id": self.parent_session_id,
            "platform": self.platform,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "message_count": len(self._conversation_history),
            "has_db": self.session_db is not None,
        }
