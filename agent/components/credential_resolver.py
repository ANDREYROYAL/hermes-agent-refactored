"""
CredentialResolver — управление credentials и fallback логикой.

Заменяет разбросанную логику из run_agent.py:
- api_key resolution
- credential_pool
- fallback_model
- provider-specific auth (Anthropic OAuth, AWS Bedrock, etc.)
"""

import logging
import os
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class CredentialResolver:
    """
    Централизованное управление credentials для API-провайдеров.
    
    Отвечает за:
    - Резолвинг API ключей из env vars
    - Управление credential pool
    - Fallback логику при ошибках аутентификации
    - Provider-specific auth (OAuth, AWS SDK, etc.)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
        credential_pool=None,
        fallback_model: Optional[Dict[str, Any]] = None,
    ):
        """
        Args:
            api_key: Явно указанный API ключ
            provider: Имя провайдера (openai, anthropic, openrouter, etc.)
            credential_pool: Пул credentials для ротации
            fallback_model: Fallback модель при ошибках
        """
        self.provider = (provider or "").strip().lower()
        self.credential_pool = credential_pool
        self.fallback_model = fallback_model
        
        # Резолвим API ключ
        self.api_key = self._resolve_api_key(api_key)
        
        logger.debug(f"Credentials resolved for provider: {self.provider}")
    
    def _resolve_api_key(self, explicit_key: Optional[str]) -> str:
        """
        Резолвить API ключ из явного значения или env vars.
        
        Args:
            explicit_key: Явно переданный ключ
        
        Returns:
            Резолвленный API ключ
        """
        # Если ключ передан явно — используем его
        if explicit_key:
            return explicit_key
        
        # Иначе пробуем env vars в зависимости от провайдера
        if self.provider == "anthropic":
            return os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_TOKEN") or ""
        
        elif self.provider == "openai":
            return os.getenv("OPENAI_API_KEY") or ""
        
        elif self.provider == "openrouter":
            return os.getenv("OPENROUTER_API_KEY") or ""
        
        elif self.provider == "gemini" or self.provider == "google":
            return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        
        elif self.provider == "xai":
            return os.getenv("XAI_API_KEY") or ""
        
        elif self.provider == "deepseek":
            return os.getenv("DEEPSEEK_API_KEY") or ""
        
        elif self.provider == "bedrock":
            # AWS Bedrock использует AWS SDK credentials, не API key
            return "aws-sdk"
        
        # Fallback — пробуем общие env vars
        return (
            os.getenv("OPENAI_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or ""
        )
    
    def get_next_credential(self) -> Optional[str]:
        """
        Получить следующий credential из пула (для ротации).
        
        Returns:
            Следующий API ключ или None если пул пуст
        """
        if self.credential_pool is None:
            return None
        
        try:
            next_cred = self.credential_pool.get_next()
            logger.debug("Rotated to next credential from pool")
            return next_cred
        except Exception as e:
            logger.warning(f"Failed to get next credential from pool: {e}")
            return None
    
    def should_use_fallback(self, error: Exception) -> bool:
        """
        Проверить, нужно ли использовать fallback модель.
        
        Args:
            error: Исключение от API
        
        Returns:
            True если нужен fallback
        """
        if self.fallback_model is None:
            return False
        
        # Проверяем типы ошибок, при которых имеет смысл fallback
        error_str = str(error).lower()
        
        # Auth errors
        if any(x in error_str for x in ["401", "403", "unauthorized", "forbidden", "invalid api key"]):
            logger.info("Auth error detected — fallback available")
            return True
        
        # Rate limit errors
        if any(x in error_str for x in ["429", "rate limit", "quota exceeded"]):
            logger.info("Rate limit error detected — fallback available")
            return True
        
        # Model not found
        if any(x in error_str for x in ["404", "model not found", "model_not_found"]):
            logger.info("Model not found error detected — fallback available")
            return True
        
        return False
    
    def get_fallback_config(self) -> Optional[Dict[str, Any]]:
        """
        Получить конфигурацию fallback модели.
        
        Returns:
            Словарь с параметрами fallback модели или None
        """
        return self.fallback_model
    
    def is_oauth_token(self) -> bool:
        """
        Проверить, является ли текущий ключ OAuth токеном.
        
        Returns:
            True если это OAuth токен (для Anthropic)
        """
        if self.provider != "anthropic":
            return False
        
        # OAuth токены Anthropic начинаются с "sk-ant-sid01-"
        return self.api_key.startswith("sk-ant-sid01-")
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Получить сводку по credentials.
        
        Returns:
            Словарь с метаданными (без раскрытия ключей)
        """
        return {
            "provider": self.provider,
            "has_api_key": bool(self.api_key),
            "has_credential_pool": self.credential_pool is not None,
            "has_fallback": self.fallback_model is not None,
            "is_oauth": self.is_oauth_token(),
        }
