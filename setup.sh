#!/usr/bin/env bash
# Setup script for Ubuntu / Debian / VPS / Google Colab

echo "🚀 Installing System Dependencies (aria2, ffmpeg)..."
sudo apt-get update -y
sudo apt-get install -y aria2 ffmpeg python3 python3-pip

echo "📦 Installing Python Requirements..."
pip3 install -r requirements.txt

if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚙️ Created .env file. Please edit .env to insert your GEMINI_API_KEY!"
fi

echo "✅ Setup Complete! Run the CLI using:"
echo "python3 cli.py -t 'YOUR_MAGNET_LINK' -q 720p"
