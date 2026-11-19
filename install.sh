#!/usr/bin/env bash
# =================================================================
#            🔥 DSA Subber - Universal 1-Line Installer 🔥
#            Compatible with Termux (Android), VPS & Linux
# =================================================================

set -e

echo ""
echo "🚀 Initializing DSA Subber Setup..."
echo "--------------------------------------------------------"

# 1. Environment Detection & Package Installation
if [ -d "/data/data/com.termux" ] || [ -n "$PREFIX" ]; then
    echo "📱 Mobile (Termux) environment detected!"
    echo "📦 Checking and installing dependencies (python, ffmpeg, aria2, git)..."
    pkg update -y
    pkg install -y git python ffmpeg aria2

    # Ensure Termux storage permission
    if [ ! -d "$HOME/storage" ]; then
        echo "📂 Requesting storage permission for saving to Download/Anime Burn..."
        termux-setup-storage || true
    fi
elif command -v apt-get &> /dev/null; then
    echo "🐧 Linux (Debian/Ubuntu/VPS) environment detected!"
    sudo apt-get update -y
    sudo apt-get install -y git python3 python3-pip ffmpeg aria2
elif command -v brew &> /dev/null; then
    echo "🍏 macOS environment detected!"
    brew install git python ffmpeg aria2
else
    echo "⚠️ Unknown OS, attempting to proceed with existing python/git/ffmpeg..."
fi

# 2. Clone or Update Repository
REPO_DIR="$HOME/torrent-hinglish-burner"

if [ -d "$REPO_DIR/.git" ]; then
    echo "🔄 Updating DSA Subber to the latest version..."
    cd "$REPO_DIR"
    git reset --hard HEAD || true
    git pull origin main || true
else
    echo "📥 Cloning DSA Subber from GitHub..."
    rm -rf "$REPO_DIR"
    git clone https://github.com/RayneWil/torrent-hinglish-burner.git "$REPO_DIR"
    cd "$REPO_DIR"
fi

# 3. Install Lightweight Python Requirements
echo "🐍 Installing Python packages (pysubs2, rich)..."
pip install -r requirements.txt --break-system-packages --quiet 2>/dev/null || \
pip install -r requirements.txt --quiet 2>/dev/null || \
pip3 install -r requirements.txt --break-system-packages --quiet 2>/dev/null || \
pip3 install -r requirements.txt --quiet

# 4. Add handy 'subber' alias to shell profile if not present
BASHRC="$HOME/.bashrc"
if [ -f "$BASHRC" ]; then
    if ! grep -q "alias subber=" "$BASHRC"; then
        echo "alias subber=\"cd $REPO_DIR && python3 ui.py\"" >> "$BASHRC"
    fi
fi

# 5. Launch DSA Subber Interactive UI with real TTY attached
echo "--------------------------------------------------------"
echo "✨ Starting DSA Subber..."

# Re-attach standard input to terminal TTY so interactive menus work seamlessly
if [ -t 0 ]; then
    python3 ui.py || python ui.py
elif [ -e /dev/tty ]; then
    python3 ui.py </dev/tty || python ui.py </dev/tty
else
    python3 ui.py || python ui.py
fi
