#!/usr/bin/env bash
set -e

echo ""
echo "============================================================"
echo "        OpenHouse Bot - Smart Installer (Linux/macOS)"
echo "============================================================"
echo ""

# ── Step 1: Check Python ─────────────────────────────────────
echo "[1/5] Checking Python..."
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    echo "[OK] $PY_VER found."
    PYTHON=python3
elif command -v python &>/dev/null; then
    PY_VER=$(python --version 2>&1)
    echo "[OK] $PY_VER found."
    PYTHON=python
else
    echo "[MISSING] Python 3.10+ is required but not found."
    echo "Install it from: https://www.python.org/downloads/"
    exit 1
fi

# Verify version >= 3.9
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")
PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
    echo "[ERROR] Python 3.9+ is required. Found Python $PY_MAJOR.$PY_MINOR."
    exit 1
fi

# ── Step 2: Check pip ────────────────────────────────────────
echo ""
echo "[2/5] Checking pip..."
if command -v pip3 &>/dev/null; then
    echo "[OK] $(pip3 --version) found."
    PIP=pip3
elif command -v pip &>/dev/null; then
    echo "[OK] $(pip --version) found."
    PIP=pip
else
    echo "[INSTALLING] pip not found. Installing via ensurepip..."
    $PYTHON -m ensurepip --upgrade
    PIP="$PYTHON -m pip"
fi

# ── Step 3: Check Git ────────────────────────────────────────
echo ""
echo "[3/5] Checking Git..."
if command -v git &>/dev/null; then
    echo "[OK] $(git --version) found."
else
    echo "[MISSING] Git is not installed."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "Install via: brew install git   OR   xcode-select --install"
    else
        echo "Install via: sudo apt install git   OR   sudo dnf install git"
    fi
    exit 1
fi

# ── Step 4: Check if already installed ───────────────────────
echo ""
echo "[4/5] Checking if openhouse-bot is already installed..."
if $PIP show openhouse-bot &>/dev/null; then
    CURRENT_VER=$($PIP show openhouse-bot | grep Version | awk '{print $2}')
    echo "[FOUND] openhouse-bot v$CURRENT_VER is already installed."
    read -p "Reinstall/upgrade? (y/N): " REINSTALL
    if [[ "${REINSTALL,,}" != "y" ]]; then
        echo "Skipping installation."
        SKIP_INSTALL=true
    fi
else
    echo "[NOT FOUND] openhouse-bot will be installed."
fi

# ── Step 5: Clone and install ────────────────────────────────
if [ "${SKIP_INSTALL}" != "true" ]; then
    echo ""
    echo "[5/5] Installing OpenHouse Bot..."

    if [ -d "openhouse-bot" ]; then
        echo "[INFO] Folder openhouse-bot already exists. Pulling latest changes..."
        cd openhouse-bot
        git pull origin main
    else
        git clone https://github.com/masood1996-geo/openhouse-bot.git
        cd openhouse-bot
    fi

    $PIP install .
    echo "[OK] OpenHouse Bot installed successfully!"
else
    echo "[5/5] Installation skipped."
fi

# ── Done ─────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo " Installation complete! Run the bot with:"
echo "   openhouse-bot"
echo "============================================================"
echo ""
read -p "Launch OpenHouse Bot now? (y/N): " LAUNCH
if [[ "${LAUNCH,,}" == "y" ]]; then
    openhouse-bot
fi
