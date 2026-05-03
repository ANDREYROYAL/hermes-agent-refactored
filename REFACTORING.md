# Рефакторинг Hermes Agent — Итоги

## Выполненные работы

### 1. Исправлены критические уязвимости безопасности

#### Утечки файловых дескрипторов (CRITICAL)
- **gateway/status.py:381-393** — добавлен `finally: os.close(fd)` в `write_pid_file()`
- **gateway/status.py:542-554** — добавлен `finally: os.close(fd)` в `acquire_scoped_lock()`

#### Утечки event listeners (HIGH)
- **scripts/whatsapp-bridge/bridge.js** — `sock.ev.removeAllListeners()` перед реконнектом
- **web/src/components/ChatSidebar.tsx** — явное удаление WebSocket listeners перед `close()`
- **ui-tui/src/gatewayClient.ts** — `removeAllListeners('error'/'exit')` перед `proc.kill()`

#### Утечки таймеров (MEDIUM)
- **web/src/hooks/useToast.ts** — `useRef` для таймера + cleanup при размонтировании

#### Раскрытие трейсбеков (HIGH)
- **tools/terminal_tool.py** — убран `"traceback": tb_str` из JSON-ответа (логируется только в файл)

#### Неограниченные кэши (MEDIUM)
- **agent/model_metadata.py** — добавлен лимит 5000 записей + eviction 10% при переполнении

---

### 2. Создана архитектура компонентов

Вместо монолитного `AIAgent` (14K строк, 60+ параметров в `__init__`) создана модульная структура:

#### `agent/components/` — новые компоненты

**BudgetTracker** (`agent/components/budget_tracker.py`)
- Управление iteration budget, api_call_count, grace call логикой
- Заменяет 5 разбросанных атрибутов в `AIAgent`
- Методы: `increment_api_call()`, `is_exhausted()`, `activate_grace_call()`, `get_status_summary()`

**SessionManager** (`agent/components/session_manager.py`)
- Управление session_id, conversation history, context files
- Загрузка SOUL.md, AGENTS.md, .cursorrules
- Интеграция с SessionDB
- Методы: `add_message()`, `get_history()`, `load_context_files()`, `save_to_db()`

**CredentialResolver** (`agent/components/credential_resolver.py`)
- Резолвинг API ключей из env vars
- Управление credential pool и fallback логикой
- Provider-specific auth (OAuth, AWS SDK)
- Методы: `get_next_credential()`, `should_use_fallback()`, `is_oauth_token()`

#### Утилиты

**subprocess_utils** (`agent/subprocess_utils.py`)
- Безопасная обёртка `run_command()` с логированием и обработкой ошибок
- Специализированные обёртки: `run_git_command()`, `run_npm_command()`
- Хелперы: `is_git_repo()`, `get_git_branch()`
- Заменяет 40+ мест с `subprocess.run()` без проверки returncode

**LLMAdapter** (`agent/llm_adapter.py`)
- Базовый интерфейс для всех LLM провайдеров
- Унифицированные `LLMRequest` / `LLMResponse` dataclasses
- Реализации: `AnthropicAdapter`, `OpenAIAdapter`
- Фабрика `create_adapter()` для создания адаптера по имени провайдера

---

### 3. Улучшено логирование

Заменены `print()` на `logger` в критичных местах:
- **gateway/hooks.py** — 4 замены (hook loading warnings)
- **model_tools.py** — 6 замен (toolset enable/disable messages)

Теперь все сообщения идут через структурированное логирование с уровнями (INFO/WARNING/ERROR).

---

## Как использовать новые компоненты

### Пример 1: BudgetTracker

```python
from agent.components import BudgetTracker

# Создание
budget = BudgetTracker(max_iterations=90)

# В цикле агента
budget.increment_api_call()

if budget.is_exhausted():
    if not budget.was_budget_message_injected():
        # Добавить сообщение об исчерпании бюджета
        budget.mark_budget_message_injected()
        budget.activate_grace_call()

if budget.should_allow_grace_call():
    # Разрешить финальный вызов
    pass

# Получить статус
status = budget.get_status_summary()
# {"api_calls": 45, "max_iterations": 90, "remaining_local": 45, ...}
```

### Пример 2: SessionManager

```python
from agent.components import SessionManager
from pathlib import Path

# Создание
session = SessionManager(
    platform="telegram",
    user_name="John Doe",
    chat_type="dm",
)

# Добавление сообщений
session.add_message({"role": "user", "content": "Hello"})
session.add_message({"role": "assistant", "content": "Hi!"})

# Загрузка контекстных файлов
context_files = session.load_context_files(
    hermes_home=Path.home() / ".hermes",
    cwd=Path.cwd(),
)

# Получение истории
history = session.get_history()

# Сохранение в DB
session.save_to_db({"trajectory": history})
```

### Пример 3: CredentialResolver

```python
from agent.components import CredentialResolver

# Создание
creds = CredentialResolver(
    provider="anthropic",
    credential_pool=my_pool,
    fallback_model={"model": "gpt-4", "provider": "openai"},
)

# API ключ резолвится автоматически из env vars
print(creds.api_key)  # Из ANTHROPIC_API_KEY или ANTHROPIC_TOKEN

# Проверка OAuth
if creds.is_oauth_token():
    print("Using OAuth token")

# Fallback при ошибке
try:
    response = call_api()
except Exception as e:
    if creds.should_use_fallback(e):
        fallback_config = creds.get_fallback_config()
        # Переключиться на fallback модель
```

### Пример 4: subprocess_utils

```python
from agent.subprocess_utils import run_command, run_git_command, SubprocessError

# Безопасный запуск команды
try:
    result = run_command(
        ["ls", "-la"],
        cwd="/tmp",
        check=True,  # Выбросит SubprocessError при ошибке
    )
    print(result.stdout)
except SubprocessError as e:
    print(f"Command failed: {e.cmd}")
    print(f"Exit code: {e.returncode}")
    print(f"Stderr: {e.stderr}")

# Git команды
result = run_git_command(["status"], cwd="/path/to/repo")

# Проверка git репозитория
if is_git_repo():
    branch = get_git_branch()
    print(f"Current branch: {branch}")
```

### Пример 5: LLMAdapter

```python
from agent.llm_adapter import create_adapter, LLMRequest

# Создание адаптера
adapter = create_adapter(
    provider="anthropic",
    api_key="sk-ant-...",
    timeout=600.0,
)

# Синхронный запрос
request = LLMRequest(
    messages=[
        {"role": "user", "content": "Hello!"}
    ],
    model="claude-sonnet-4.6",
    max_tokens=1024,
)

response = adapter.complete(request)
print(response.content)
print(response.tool_calls)

# Стриминг
for chunk in adapter.stream(request):
    print(chunk)

# Проверка возможностей
if adapter.supports_reasoning("claude-sonnet-4.6"):
    print("Model supports extended thinking")

if adapter.supports_prompt_caching("claude-sonnet-4.6"):
    print("Model supports prompt caching")
```

---

## Следующие шаги

### Приоритет 1: Интеграция компонентов в AIAgent

1. **Рефакторить `AIAgent.__init__`** — заменить 60+ параметров на компоненты:
   ```python
   def __init__(self, ...):
       self.budget = BudgetTracker(max_iterations, iteration_budget)
       self.session = SessionManager(session_id, session_db, ...)
       self.credentials = CredentialResolver(api_key, provider, ...)
       self.adapter = create_adapter(provider, self.credentials.api_key, ...)
   ```

2. **Разбить `run_conversation()`** (3508 строк) на методы:
   - `_prepare_messages()` — построение промпта
   - `_execute_api_call()` — вызов LLM через adapter
   - `_process_tool_calls()` — обработка tool calls
   - `_handle_budget_exhaustion()` — логика grace call
   - `_finalize_response()` — сохранение траектории

### Приоритет 2: Создать оставшиеся компоненты

- **ToolDispatcher** — оркестрация вызовов инструментов
- **MessageBuilder** — построение system prompts с context files
- **PromptCache** — управление Anthropic prompt caching

### Приоритет 3: Расширить LLMAdapter

Добавить адаптеры для:
- **BedrockAdapter** — AWS Bedrock
- **GeminiAdapter** — Google Gemini
- **DeepSeekAdapter** — DeepSeek
- **XAIAdapter** — xAI Grok

### Приоритет 4: Тесты

Написать юнит-тесты для каждого компонента:
- `tests/agent/components/test_budget_tracker.py`
- `tests/agent/components/test_session_manager.py`
- `tests/agent/components/test_credential_resolver.py`
- `tests/agent/test_subprocess_utils.py`
- `tests/agent/test_llm_adapter.py`

---

## Метрики улучшения

### Безопасность
- ✅ 2 критические утечки FD исправлены
- ✅ 3 утечки event listeners исправлены
- ✅ 1 утечка таймера исправлена
- ✅ Раскрытие трейсбеков устранено
- ✅ Кэши ограничены по размеру

### Архитектура
- ✅ 3 новых компонента (BudgetTracker, SessionManager, CredentialResolver)
- ✅ 1 утилита (subprocess_utils)
- ✅ 1 базовый интерфейс (LLMAdapter)
- ✅ 10 замен `print()` на `logger`

### Следующий этап
- ⏳ Интеграция компонентов в AIAgent
- ⏳ Декомпозиция run_conversation() (3508 строк → ~300 строк)
- ⏳ Создание ToolDispatcher, MessageBuilder
- ⏳ Расширение LLMAdapter (Bedrock, Gemini, DeepSeek)
- ⏳ Юнит-тесты для всех компонентов

---

## Обратная совместимость

Все изменения **обратно совместимы**:
- Старый код продолжает работать без изменений
- Новые компоненты живут параллельно со старым кодом
- Миграция на новую архитектуру — постепенная, без breaking changes

Когда все компоненты будут интегрированы, старый монолитный код можно будет удалить.
