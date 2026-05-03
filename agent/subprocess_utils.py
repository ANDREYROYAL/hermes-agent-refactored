"""
Subprocess utilities — безопасная обёртка для subprocess.run с обработкой ошибок.

Заменяет 40+ мест с subprocess.run() без проверки returncode.
"""

import logging
import subprocess
import shlex
from typing import Optional, List, Union
from pathlib import Path

logger = logging.getLogger(__name__)


class SubprocessError(Exception):
    """Исключение при ошибке выполнения subprocess."""
    
    def __init__(self, cmd: str, returncode: int, stdout: str, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(
            f"Command failed with exit code {returncode}: {cmd}\n"
            f"stderr: {stderr[:500]}"
        )


def run_command(
    cmd: Union[str, List[str]],
    *,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    timeout: Optional[float] = None,
    cwd: Optional[Union[str, Path]] = None,
    shell: bool = False,
    env: Optional[dict] = None,
    log_output: bool = True,
) -> subprocess.CompletedProcess:
    """
    Безопасная обёртка для subprocess.run с логированием и обработкой ошибок.
    
    Args:
        cmd: Команда (строка или список аргументов)
        check: Выбросить SubprocessError при ненулевом exit code
        capture_output: Захватить stdout/stderr
        text: Декодировать вывод как текст
        timeout: Таймаут в секундах
        cwd: Рабочая директория
        shell: Использовать shell (ОПАСНО — избегайте если возможно)
        env: Переменные окружения
        log_output: Логировать stdout/stderr
    
    Returns:
        CompletedProcess с результатом
    
    Raises:
        SubprocessError: Если check=True и команда вернула ненулевой код
        subprocess.TimeoutExpired: Если превышен timeout
    """
    # Логируем команду
    if isinstance(cmd, list):
        cmd_str = shlex.join(cmd)
    else:
        cmd_str = cmd
    
    logger.debug(f"Running command: {cmd_str[:200]}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=text,
            timeout=timeout,
            cwd=cwd,
            shell=shell,
            env=env,
        )
        
        # Логируем результат
        if log_output and result.returncode != 0:
            logger.warning(
                f"Command exited with code {result.returncode}: {cmd_str[:100]}\n"
                f"stderr: {result.stderr[:500] if result.stderr else '(empty)'}"
            )
        elif log_output and result.stdout:
            logger.debug(f"Command output: {result.stdout[:200]}")
        
        # Проверяем returncode
        if check and result.returncode != 0:
            raise SubprocessError(
                cmd=cmd_str,
                returncode=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )
        
        return result
    
    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out after {timeout}s: {cmd_str[:100]}")
        raise
    
    except FileNotFoundError as e:
        logger.error(f"Command not found: {cmd_str[:100]}")
        raise SubprocessError(
            cmd=cmd_str,
            returncode=-1,
            stdout="",
            stderr=f"Command not found: {e}",
        )


def run_git_command(
    args: List[str],
    *,
    cwd: Optional[Union[str, Path]] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """
    Обёртка для git команд.
    
    Args:
        args: Аргументы git команды (без 'git')
        cwd: Рабочая директория
        check: Выбросить исключение при ошибке
    
    Returns:
        CompletedProcess с результатом
    """
    return run_command(
        ["git"] + args,
        cwd=cwd,
        check=check,
        timeout=30,
    )


def run_npm_command(
    args: List[str],
    *,
    cwd: Optional[Union[str, Path]] = None,
    check: bool = True,
    timeout: float = 300,
) -> subprocess.CompletedProcess:
    """
    Обёртка для npm команд.
    
    Args:
        args: Аргументы npm команды (без 'npm')
        cwd: Рабочая директория
        check: Выбросить исключение при ошибке
        timeout: Таймаут (по умолчанию 5 минут для npm install)
    
    Returns:
        CompletedProcess с результатом
    """
    return run_command(
        ["npm"] + args,
        cwd=cwd,
        check=check,
        timeout=timeout,
    )


def is_git_repo(path: Optional[Union[str, Path]] = None) -> bool:
    """
    Проверить, является ли директория git репозиторием.
    
    Args:
        path: Путь для проверки (по умолчанию текущая директория)
    
    Returns:
        True если это git репозиторий
    """
    try:
        run_git_command(
            ["rev-parse", "--git-dir"],
            cwd=path,
            check=True,
        )
        return True
    except (SubprocessError, subprocess.TimeoutExpired):
        return False


def get_git_branch(cwd: Optional[Union[str, Path]] = None) -> Optional[str]:
    """
    Получить текущую git ветку.
    
    Args:
        cwd: Рабочая директория
    
    Returns:
        Имя ветки или None если не git репозиторий
    """
    try:
        result = run_git_command(
            ["rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            check=True,
        )
        return result.stdout.strip()
    except (SubprocessError, subprocess.TimeoutExpired):
        return None
