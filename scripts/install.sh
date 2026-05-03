#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# Hermes Agent Refactored — Quick Install
# Репозиторий: https://github.com/ANDREYROYAL/hermes-agent-refactored
# Поддерживает: Linux, macOS, WSL2, Android (Termux)
# ─────────────────────────────────────────────────────────────

REPO_URL="https://github.com/ANDREYROYAL/hermes-agent-refactored.git"
INSTALL_DIR="$HOME/hermes-agent-refactored"
PYTHON_MIN_VERSION="3.10"
LOGFILE="$HOME/hermes-install.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()   { echo -e "${GREEN}[✓]${NC} $*" | tee -a "$LOGFILE"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*" | tee -a "$LOGFILE"; }
error() { echo -e "${RED}[✗]${NC} $*" | tee -a "$LOGFILE"; }
info()  { echo -e "${BLUE}[i]${NC} $*" | tee -a "$LOGFILE"; }
header(){ echo -e "\n${BOLD}${CYAN}━━━ $* ━━━${NC}\n" | tee -a "$LOGFILE"; }

trap 'error "Installation failed. See log: $LOGFILE"' ERR

# ─────────────────────────────────────────────────────────────
# 1. Welcome
# ─────────────────────────────────────────────────────────────

clear
echo -e "${CYAN}"
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║          Hermes Agent — Refactored Edition          ║"
echo "  ║   Modular architecture · Fixed vulnerabilities     ║"
echo "  ║         https://github.com/ANDREYROYAL/             ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"

> "$LOGFILE"

# ─────────────────────────────────────────────────────────────
# 2. Detect platform
# ─────────────────────────────────────────────────────────────

header "Detecting platform"

detect_platform() {
    local os=""
    local arch=""
    
    case "$(uname -s)" in
        Linux*)     os="linux" ;;
        Darwin*)    os="macos" ;;
        CYGWIN*|MINGW*|MSYS*) os="windows" ;;
        *)          os="unknown" ;;
    esac
    
    case "$(uname -m)" in
        x86_64|amd64)  arch="amd64" ;;
        arm64|aarch64) arch="arm64" ;;
        *)             arch="unknown" ;;
    esac
    
    echo "${os}/${arch}"
}

PLATFORM=$(detect_platform)
info "Platform: $PLATFORM"

# Android/Termux detection
IS_TERMUX=false
if [ -d "/data/data/com.termux" ] || [ -n "${TERMUX_VERSION:-}" ]; then
    IS_TERMUX=true
    info "Termux (Android) detected"
fi

# WSL detection
IS_WSL=false
if grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=true
    info "WSL2 detected"
fi

# ─────────────────────────────────────────────────────────────
# 3. Check Python
# ─────────────────────────────────────────────────────────────

header "Checking Python"

find_python() {
    if command -v python3 &>/dev/null; then
        echo "python3"
    elif command -v python &>/dev/null; then
        echo "python"
    else
        echo ""
    fi
}

PYTHON=$(find_python)

if [ -z "$PYTHON" ]; then
    error "Python not found. Installing..."
    
    if $IS_TERMUX; then
        pkg update -y && pkg install python -y
    elif $IS_WSL || [ "$(uname -s)" = "Linux" ]; then
        sudo apt-get update -y && sudo apt-get install -y python3 python3-pip python3-venv
    elif [ "$(uname -s)" = "Darwin" ]; then
        if ! command -v brew &>/dev/null; then
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi
        brew install python@3.11
    fi
    
    PYTHON=$(find_python)
fi

PYTHON_VERSION=$($PYTHON --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
log "Python: $PYTHON $($PYTHON --version 2>&1)"

# Version check
PY_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
REQ_MAJOR=$(echo "$PYTHON_MIN_VERSION" | cut -d. -f1)
REQ_MINOR=$(echo "$PYTHON_MIN_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt "$REQ_MAJOR" ] || { [ "$PY_MAJOR" -eq "$REQ_MAJOR" ] && [ "$PY_MINOR" -lt "$REQ_MINOR" ]; }; then
    error "Python $PYTHON_MIN_VERSION+ required. Found: $PYTHON_VERSION"
    exit 1
fi

# ─────────────────────────────────────────────────────────────
# 4. Install git (if needed)
# ─────────────────────────────────────────────────────────────

header "Checking git"

if ! command -v git &>/dev/null; then
    info "Installing git..."
    if $IS_TERMUX; then
        pkg install git -y
    elif $IS_WSL || [ "$(uname -s)" = "Linux" ]; then
        sudo apt-get install -y git
    elif [ "$(uname -s)" = "Darwin" ]; then
        xcode-select --install 2>/dev/null || true
    fi
fi
log "git: $(git --version 2>&1)"

# ─────────────────────────────────────────────────────────────
# 5. Install system dependencies
# ─────────────────────────────────────────────────────────────

if [ "$(uname -s)" = "Linux" ] && ! $IS_TERMUX; then
    header "System dependencies"
    info "Installing python3-venv and build tools..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3-venv python3-dev 2>/dev/null
    log "System dependencies ready"
fi

# ─────────────────────────────────────────────────────────────
# 6. Clone repository
# ─────────────────────────────────────────────────────────────

header "Cloning repository"

if [ -d "$INSTALL_DIR" ]; then
    warn "Directory $INSTALL_DIR already exists."
    read -rp "Overwrite? [y/N] " yn
    if [ "${yn:-n}" = "y" ] || [ "${yn:-n}" = "Y" ]; then
        # cd out first in case we're inside the directory
        if [[ "$PWD" == "$INSTALL_DIR"* ]]; then
            cd "$HOME" 2>/dev/null || cd /
        fi
        rm -rf "$INSTALL_DIR"
    else
        info "Skipping clone. Using existing directory."
    fi
fi

if [ ! -d "$INSTALL_DIR" ]; then
    info "Cloning from $REPO_URL"
    git clone "$REPO_URL" "$INSTALL_DIR"
    log "Repository cloned to $INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ─────────────────────────────────────────────────────────────
# 7. Create virtual environment
# ─────────────────────────────────────────────────────────────

header "Setting up virtual environment"

if [ -d ".venv" ]; then
    warn "Virtual environment already exists. Recreating..."
    rm -rf .venv
fi

info "Creating virtual environment..."
$PYTHON -m venv .venv

# Activate
source .venv/bin/activate || source .venv/bin/activate.csh 2>/dev/null || true

log "Virtual environment: $INSTALL_DIR/.venv"

# ─────────────────────────────────────────────────────────────
# 8. Install Python dependencies
# ─────────────────────────────────────────────────────────────

header "Installing dependencies"

info "Upgrading pip..."
$PYTHON -m pip install --upgrade pip --quiet

info "Installing base package..."
$PYTHON -m pip install -e . 2>&1 | tee -a "$LOGFILE" || {
    warn "Base install failed. Installing minimal dependencies..."
    $PYTHON -m pip install openai anthropic pyyaml requests 2>&1 | tee -a "$LOGFILE"
}

log "Dependencies installed"

# ─────────────────────────────────────────────────────────────
# 9. Configure environment
# ─────────────────────────────────────────────────────────────

header "Configuration"

# Create .env from example if needed
ENV_FILE="$INSTALL_DIR/.env"
ENV_EXAMPLE="$INSTALL_DIR/.env.example"

if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        log "Created .env from .env.example"
    else
        touch "$ENV_FILE"
        log "Created empty .env"
    fi
fi

# Check for API keys
MISSING_KEYS=()

if [ -z "${ANTHROPIC_API_KEY:-}" ] && ! grep -q "ANTHROPIC_API_KEY=sk-" "$ENV_FILE" 2>/dev/null; then
    MISSING_KEYS+=("ANTHROPIC_API_KEY")
fi
if [ -z "${OPENAI_API_KEY:-}" ] && ! grep -q "OPENAI_API_KEY=sk-" "$ENV_FILE" 2>/dev/null; then
    MISSING_KEYS+=("OPENAI_API_KEY")
fi

if [ ${#MISSING_KEYS[@]} -gt 0 ]; then
    warn "No API keys detected. You'll need to add them to:"
    echo -e "     ${BOLD}$ENV_FILE${NC}"
    echo ""
    echo "  Example keys to add:"
    for key in "${MISSING_KEYS[@]}"; do
        echo "    $key=sk-..."
    done
    echo ""
fi

# ─────────────────────────────────────────────────────────────
# 10. Add activation to shell config
# ─────────────────────────────────────────────────────────────

header "Shell integration"

ACTIVATE_CMD="alias hermes-refactored='cd $INSTALL_DIR && source .venv/bin/activate && python agent/refactored_agent_example.py'"

add_to_shell_config() {
    local config_file="$1"
    if [ -f "$config_file" ]; then
        if ! grep -q "hermes-refactored" "$config_file" 2>/dev/null; then
            echo "" >> "$config_file"
            echo "# Hermes Agent Refactored" >> "$config_file"
            echo "$ACTIVATE_CMD" >> "$config_file"
            log "Added alias to $config_file"
        fi
    fi
}

if ! $IS_TERMUX; then
    add_to_shell_config "$HOME/.zshrc"
    add_to_shell_config "$HOME/.bashrc"
    add_to_shell_config "$HOME/.bash_profile"
fi

# ─────────────────────────────────────────────────────────────
# 11. Verify installation
# ─────────────────────────────────────────────────────────────

header "Verifying installation"

cd "$INSTALL_DIR"

if $PYTHON -c "
import sys
sys.path.insert(0, '.')
try:
    from agent.components import BudgetTracker, SessionManager, CredentialResolver
    from agent.components import ToolDispatcher, MessageBuilder
    from agent.subprocess_utils import run_command
    print('OK')
    sys.exit(0)
except ImportError as e:
    print(f'FAIL: {e}')
    sys.exit(1)
" 2>/dev/null; then
    log "All components loaded successfully"
else
    warn "Some components failed to load. Installation may be incomplete."
fi

# ─────────────────────────────────────────────────────────────
# 12. Done
# ─────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✅ Hermes Agent Refactored installed successfully!${NC}"
echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}Location:${NC} ${CYAN}$INSTALL_DIR${NC}"
echo -e "  ${BOLD}Log:${NC}      ${CYAN}$LOGFILE${NC}"
echo -e "  ${BOLD}Config:${NC}   ${CYAN}$ENV_FILE${NC}"
echo ""
echo -e "  ${BOLD}Quick start:${NC}"
echo ""
echo "    cd $INSTALL_DIR"
echo "    source .venv/bin/activate"
echo "    python agent/refactored_agent_example.py"
echo ""
echo -e "  ${BOLD}Or use alias (restart shell first):${NC}"
echo "    hermes-refactored"
echo ""

if [ ${#MISSING_KEYS[@]} -gt 0 ]; then
    echo -e "  ${YELLOW}${BOLD}⚠️  Don't forget to add your API keys:${NC}"
    echo -e "     ${BOLD}$ENV_FILE${NC}"
    echo ""
fi

echo -e "  ${BOLD}Documentation:${NC}"
echo "    cat $INSTALL_DIR/QUICKSTART.md"
echo "    cat $INSTALL_DIR/REFACTORING.md"
echo ""

echo -e "  ${BOLD}Repository:${NC} https://github.com/ANDREYROYAL/hermes-agent-refactored"
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}"
echo ""
