# 🔥 DSA Subber (Torrent to Hinglish Burner CLI)

[![Termux](https://img.shields.io/badge/Termux-Supported-orange.svg)](https://termux.dev/)
[![Linux](https://img.shields.io/badge/Linux-Supported-blue.svg)](https://www.kernel.org/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Supported-green.svg)](https://ffmpeg.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An automated, terminal-based pipeline that downloads torrents, translates subtitles into conversational **Hinglish** (.ass) with AI, and burns them into **480p** or **720p** video directly saved into your phone or PC's **`Download/Anime Burn`** folder.

Works on **Termux (Android)**, **Linux VPS**, **Google Colab**, **macOS**, and **Windows**.

---

## ⚡ 1-Line Quickstart (Termux / Linux / VPS)

Just paste this **one single command** into your terminal (Termux, Ubuntu, or VPS). It will automatically install all requirements, pull the code, and launch the **DSA Subber Ready** interface:

```bash
curl -sSL https://raw.githubusercontent.com/RayneWil/torrent-hinglish-burner/main/install.sh | bash
```

> **Tip:** You only need to run the `curl` command once during setup! After that, you can launch DSA Subber anytime from anywhere simply by typing:
> ```bash
> dsa
> ```

---

## 📱 Interactive Terminal UI (`DSA Subber Ready`)

When you run the command, you will be greeted by the interactive menu:

```
==================================================================
                     🔥 DSA Subber Ready 🔥
       Automated Torrent to Hinglish Burner (Termux & Linux)
==================================================================

Select an option:
[1] 🔥 Start Burning
[2] 🔑 Change API Key
[3] ⚙️ Change Quality (Current: 720p)
[4] 📂 Open Anime Burn Folder
[5] 🚪 Exit
```

1. Select **`[1] Start Burning`**
2. Paste your **Torrent link / Magnet URI**.
3. Watch the live progress bar as it:
   - Downloads the torrent via `aria2c`
   - Extracts the subtitle track
   - Translates subtitles (30 lines/req with 5 API key auto-rotation)
   - Burns `.ass` subtitles into video and compresses to 480p or 720p
4. The files are automatically separated and saved in:
   - **🎬 Burned Video:** `Download/Anime Burn/Video/<Video_Name>.mp4`
   - **📝 Hinglish Subtitle:** `Download/Anime Burn/Subtitle/<Video_Name>_Hinglish.ass`
   *(On Android Termux, this is in `/sdcard/Download/Anime Burn/...`)*

---

## 🚀 Features

- **Terminal-Driven**: Works seamlessly on Linux VPS, Ubuntu Server, Google Colab, Docker, Termux, Windows, and macOS.
- **Fast Torrent Engine**: Uses `aria2c` for maximum download speed and multi-connection chunking.
- **Multi-API Key Pool & Auto-Shift**: 
  - Translates in optimal batches of **30 lines per request**.
  - Automatically shifts to the next Gemini API Key after **20 requests** or if a **429 Quota/Rate Limit** is hit.
  - Supports 5+ API keys in a single list (`key1,key2,key3,key4,key5`).
- **True Hinglish Translation**: Unlike standard Google Translate which outputs Devanagari script (`नमस्ते`), this outputs natural conversational Hinglish (`Namaste bhai, kaise ho?`).
- **Custom ASS Styling**: Generates clean, bordered subtitles that look crisp on both mobile and desktop screens.
- **Hardware/Software Encoding**: High-quality `libx264` encoding tailored for small file sizes in 480p/720p.

---

## 📦 Requirements & System Dependencies

### 1. System Packages
You need `aria2` and `ffmpeg` installed on your system.

#### Ubuntu / Debian / VPS / Google Colab:
```bash
sudo apt update
sudo apt install -y aria2 ffmpeg
```

#### Windows:
Install via [Chocolatey](https://chocolatey.org/) or [Scoop](https://scoop.sh/):
```powershell
choco install ffmpeg aria2
# OR scoop install ffmpeg aria2
```

#### macOS:
```bash
brew install aria2 ffmpeg
```

---

## 🛠️ Installation

```bash
# 1. Clone your repository
git clone https://github.com/<your-username>/torrent-hinglish-burner.git
cd torrent-hinglish-burner

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Setup your environment
cp .env.example .env
# Edit .env and put your GEMINI_API_KEY
```

> **Note:** You can get a free Google Gemini API key from [Google AI Studio](https://aistudio.google.com/).

---

## 💻 Usage

### Basic Command:
```bash
python cli.py --torrent "magnet:?xt=urn:btih:..." --quality 720p
```

### With Custom Options:
```bash
# 480p Quality output
python cli.py -t "magnet:?xt=urn:btih:..." -q 480p

# Using a .torrent file
python cli.py -t "downloads/sample.torrent" -q 720p

# Specifying multiple Gemini API Keys for auto-rotation
python cli.py -t "magnet:..." --api-keys "key1,key2,key3,key4,key5" -q 720p
```

### CLI Arguments:
| Argument | Short | Description | Default |
|---|---|---|---|
| `--torrent` | `-t` | Magnet URI or path to `.torrent` file | **Required** |
| `--quality` | `-q` | Output video resolution (`480p` or `720p`) | `720p` |
| `--api-keys` | `-k` | Comma-separated Gemini API Keys | From `.env` |
| `--output-dir` | `-o` | Directory to save final video | `./output` |
| `--sub-track` | `-s` | Subtitle track index to extract (0, 1, etc.) | Auto-detect |

---

## 📂 Project Structure

```
torrent-hinglish-burner/
├── cli.py               # Main CLI Entrypoint
├── config.py            # Global Configuration
├── downloader.py        # Torrent & Magnet Downloader (aria2c wrapper)
├── subtitles.py         # Subtitle extraction & ASS converter/styler
├── translator.py        # AI-powered Hinglish translator
├── encoder.py           # FFmpeg burner & downscaler (480p/720p)
├── requirements.txt     # Python dependencies
├── .env.example         # Example environment file
└── README.md            # Documentation
```

---

## ⚡ Google Colab Quickstart

You can run this on Google Colab completely free:

```python
!apt update && apt install -y aria2 ffmpeg
!git clone https://github.com/<your-username>/torrent-hinglish-burner.git
%cd torrent-hinglish-burner
!pip install -r requirements.txt
!python cli.py --torrent "YOUR_MAGNET_LINK" --quality 720p --api-key "YOUR_GEMINI_KEY"
```

---

## 📜 License
MIT License. Created for open-source media workflows.
