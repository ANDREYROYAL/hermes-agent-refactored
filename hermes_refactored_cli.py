#!/usr/bin/env python3
"""
Hermes Agent Refactored — CLI Entry Point
==========================================

Быстрый запуск агента из командной строки.

Usage:
    hermes                          # Интерактивный режим
    hermes "What is Python?"        # Одиночный запрос
    hermes --model claude-sonnet-4.6  # Выбор модели
    hermes --toolsets web,terminal  # Включить toolsets
    hermes --version                # Версия
"""

import sys
import os


def _get_version():
    try:
        from importlib.metadata import version
        return version("hermes-agent")
    except Exception:
        return "0.12.0-refactored"


def _print_banner():
    print(r"""
  ╔══════════════════════════════════════════════════════╗
  ║          Hermes Agent — Refactored Edition          ║
  ║   Modular architecture · Fixed vulnerabilities      ║
  ║         github.com/ANDREYROYAL/hermes-agent         ║
  ╚══════════════════════════════════════════════════════╝
""")


def _print_help():
    print(f"""
Hermes Agent Refactored — v{_get_version()}

Usage:
    hermes                          Start interactive chat
    hermes "your question"          Single query mode
    hermes --model MODEL            Set model (e.g. claude-sonnet-4.6)
    hermes --provider PROVIDER      Set provider (anthropic, openai, openrouter)
    hermes --toolsets web,terminal  Enable specific toolsets
    hermes --max-turns N            Max tool-calling iterations (default: 90)
    hermes --api-key KEY            Set API key
    hermes --base-url URL           Custom API base URL
    hermes --verbose                Enable verbose logging
    hermes --version                Show version
    hermes --help                   Show this help

Examples:
    hermes                                                    # Interactive chat
    hermes "What's the weather in London?"                    # Single query
    hermes --model claude-opus-4.6 --provider anthropic       # Choose model
    hermes --toolsets web,terminal "Search for Python news"   # With toolsets

Environment:
    ANTHROPIC_API_KEY    Anthropic API key
    OPENAI_API_KEY       OpenAI API key
    OPENROUTER_API_KEY   OpenRouter API key

Repository:
    https://github.com/ANDREYROYAL/hermes-agent-refactored

Documentation:
    cat ~/hermes-agent-refactored/QUICKSTART.md
""")


def _resolve_api_key(provider: str, explicit_key: str = None) -> str:
    if explicit_key:
        return explicit_key
    provider = (provider or "").lower()
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "google": "GEMINI_API_KEY",
        "xai": "XAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }
    env_var = env_map.get(provider)
    if env_var:
        key = os.getenv(env_var, "")
        if key:
            return key
    # Fallback to generic keys
    return os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or ""


def _check_env():
    """Check if .env file exists and suggest loading it."""
    env_path = os.path.expanduser("~/.hermes/.env")
    local_env = os.path.join(os.getcwd(), ".env")
    
    if os.path.exists(local_env) and not os.getenv("ANTHROPIC_API_KEY"):
        print("[i] .env file found in current directory. Loading...")
        try:
            from dotenv import load_dotenv
            load_dotenv(local_env)
        except ImportError:
            pass


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Hermes Agent Refactored — AI Agent CLI",
        add_help=False,
    )
    parser.add_argument("query", nargs="?", help="Single query to execute")
    parser.add_argument("--model", "-m", default=None, help="Model name")
    parser.add_argument("--provider", "-p", default=None, help="Provider (anthropic, openai, openrouter)")
    parser.add_argument("--api-key", "-k", default=None, help="API key")
    parser.add_argument("--base-url", default=None, help="Custom API base URL")
    parser.add_argument("--toolsets", "-t", default=None, help="Comma-separated toolsets")
    parser.add_argument("--max-turns", "-n", type=int, default=90, help="Max tool iterations")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode")
    parser.add_argument("--version", action="store_true", help="Show version")
    parser.add_argument("--help", "-h", action="store_true", help="Show help")
    
    args = parser.parse_args()
    
    if args.help:
        _print_help()
        return
    
    if args.version:
        print(f"hermes-agent v{_get_version()} (refactored edition)")
        return
    
    _check_env()
    
    # Resolve provider
    provider = args.provider or "anthropic"
    model = args.model or "claude-sonnet-4.6"
    api_key = _resolve_api_key(provider, args.api_key)
    
    if not api_key and not args.quiet:
        print(f"[!] No API key found for {provider}. Set {provider.upper()}_API_KEY env var or use --api-key")
        print(f"[i] Running anyway — the agent will report the error.")
    
    # Parse toolsets
    enabled_toolsets = None
    if args.toolsets:
        enabled_toolsets = [t.strip() for t in args.toolsets.split(",") if t.strip()]
    
    # Determine mode: interactive or single query
    if args.query:
        _run_single_query(
            query=args.query,
            model=model,
            provider=provider,
            api_key=api_key,
            base_url=args.base_url,
            enabled_toolsets=enabled_toolsets,
            max_turns=args.max_turns,
            verbose=args.verbose,
            quiet=args.quiet,
        )
    else:
        _run_interactive(
            model=model,
            provider=provider,
            api_key=api_key,
            base_url=args.base_url,
            enabled_toolsets=enabled_toolsets,
            max_turns=args.max_turns,
            verbose=args.verbose,
            quiet=args.quiet,
        )


def _run_single_query(
    query: str,
    model: str,
    provider: str,
    api_key: str,
    base_url: str = None,
    enabled_toolsets: list = None,
    max_turns: int = 90,
    verbose: bool = False,
    quiet: bool = False,
):
    """Run a single query and exit."""
    if not quiet:
        _print_banner()
        print(f"Model: {model}  |  Provider: {provider}  |  Max turns: {max_turns}")
        print(f"Query: {query}")
        print()
    
    try:
        agent = _create_agent(
            model, provider, api_key, base_url,
            enabled_toolsets, max_turns, verbose, quiet,
        )
        
        if not quiet:
            print("Thinking", end="", flush=True)
        
        response = agent.chat(query)
        
        if not quiet:
            print("\r" + " " * 20 + "\r", end="")
        
        print(response)
    
    except Exception as e:
        print(f"\n[✗] Error: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def _run_interactive(
    model: str,
    provider: str,
    api_key: str,
    base_url: str = None,
    enabled_toolsets: list = None,
    max_turns: int = 90,
    verbose: bool = False,
    quiet: bool = False,
):
    """Run interactive chat mode."""
    _print_banner()
    print(f"  Model: {model}  |  Provider: {provider}  |  Max turns: {max_turns}")
    print(f"  Type your message or /help for commands, /quit to exit")
    print()
    
    # Try to load prompt_toolkit for nice input
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import InMemoryHistory
        session = PromptSession(history=InMemoryHistory())
        use_pt = True
    except ImportError:
        use_pt = False
    
    try:
        agent = _create_agent(
            model, provider, api_key, base_url,
            enabled_toolsets, max_turns, verbose, quiet,
        )
    except Exception as e:
        print(f"\n[✗] Failed to initialize agent: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    
    while True:
        try:
            if use_pt:
                user_input = session.prompt("> ")
            else:
                user_input = input("> ")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        
        user_input = user_input.strip()
        
        if not user_input:
            continue
        
        if user_input.lower() in ("/quit", "/exit", "/q"):
            print("Goodbye!")
            break
        
        if user_input.lower() == "/help":
            print("""
Commands:
  /quit, /exit, /q   Exit
  /help              Show this help
  /model MODEL       Change model (e.g. /model claude-opus-4.6)
  /clear             Clear conversation history
  /verbose           Toggle verbose logging
  Anything else      Send message to agent
""")
            continue
        
        if user_input.lower() == "/verbose":
            verbose = not verbose
            print(f"Verbose: {'ON' if verbose else 'OFF'}")
            continue
        
        if user_input.lower().startswith("/model "):
            model = user_input[7:].strip()
            print(f"Model changed to: {model}")
            agent = _create_agent(
                model, provider, api_key, base_url,
                enabled_toolsets, max_turns, verbose, quiet,
            )
            continue
        
        # Send to agent
        try:
            print("Thinking", end="", flush=True)
            response = agent.chat(user_input)
            print("\r" + " " * 20 + "\r", end="")
            print(response)
            print()
        except Exception as e:
            print(f"\r[✗] Error: {e}")
            if verbose:
                import traceback
                traceback.print_exc()


def _create_agent(
    model: str,
    provider: str,
    api_key: str,
    base_url: str = None,
    enabled_toolsets: list = None,
    max_turns: int = 90,
    verbose: bool = False,
    quiet: bool = False,
):
    """Create an AIAgent instance using refactored components."""
    from run_agent import AIAgent
    
    agent = AIAgent(
        model=model,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        max_iterations=max_turns,
        enabled_toolsets=enabled_toolsets,
        quiet_mode=quiet,
        verbose_logging=verbose,
    )
    
    return agent


if __name__ == "__main__":
    main()
