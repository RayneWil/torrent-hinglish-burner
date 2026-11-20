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
echo "🐍 Installing Python packages (pysubs2, rich, telethon)..."
pip install -r requirements.txt --break-system-packages --quiet 2>/dev/null || \
pip install -r requirements.txt --quiet 2>/dev/null || \
pip3 install -r requirements.txt --break-system-packages --quiet 2>/dev/null || \
pip3 install -r requirements.txt --quiet

# 4. Create global 'dsa' command launcher and aliases
BIN_DIR=""
if [ -d "$PREFIX/bin" ]; then
    BIN_DIR="$PREFIX/bin"
elif [ -d "/usr/local/bin" ] && [ -w "/usr/local/bin" ]; then
    BIN_DIR="/usr/local/bin"
elif [ -d "$HOME/.local/bin" ]; then
    BIN_DIR="$HOME/.local/bin"
    mkdir -p "$BIN_DIR"
fi

if [ -n "$BIN_DIR" ]; then
    cat << 'EOF' > "$BIN_DIR/dsa"
#!/usr/bin/env bash
cd "$HOME/torrent-hinglish-burner" || exit 1
if command -v python3 &> /dev/null; then
    exec python3 ui.py "$@"
else
    exec python ui.py "$@"
fi
EOF
    chmod +x "$BIN_DIR/dsa"
    ln -sf "$BIN_DIR/dsa" "$BIN_DIR/start-dsa" 2>/dev/null || true
    echo "✅ Global command 'dsa' created! You can now just type 'dsa' anywhere to launch!"
fi

# Also add alias 'dsa' and 'subber' to shell profiles
for RC in "$HOME/.bashrc" "$HOME/.profile" "$HOME/.zshrc"; do
    if [ -f "$RC" ]; then
        if ! grep -q "alias dsa=" "$RC"; then
            echo "alias dsa=\"cd $REPO_DIR && python3 ui.py\"" >> "$RC"
        fi
        if ! grep -q "alias subber=" "$RC"; then
            echo "alias subber=\"cd $REPO_DIR && python3 ui.py\"" >> "$RC"
        fi
    fi
done

# 5. Launch DSA Subber Interactive UI with real TTY attached
echo "--------------------------------------------------------"
echo "✨ Starting DSA Subber..."

if [ -t 0 ]; then
    python3 ui.py || python ui.py
elif [ -e /dev/tty ]; then
    python3 ui.py </dev/tty || python ui.py </dev/tty
else
    python3 ui.py || python ui.py
fi
