import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Fallback .env parser in case python-dotenv is not installed
def load_env_file(filepath: Path):
    if not filepath.exists():
        return
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key not in os.environ:
                    os.environ[key] = val

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    load_env_file(BASE_DIR / ".env")

# Gemini API Keys Pool (supports multiple comma-separated keys or single key)
raw_keys = os.getenv("GEMINI_API_KEYS", "")
if raw_keys:
    GEMINI_API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
else:
    single_key = os.getenv("GEMINI_API_KEY", "")
    GEMINI_API_KEYS = [single_key.strip()] if single_key.strip() else []

# GitHub Token
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Working Directories
TEMP_DIR = Path(os.getenv("TEMP_DIR", BASE_DIR / "temp"))
TEMP_DIR.mkdir(parents=True, exist_ok=True)

def get_anime_burn_dir() -> Path:
    """
    Detects device download directory (Termux / Android, Windows, Mac, Linux)
    and returns 'Download/Anime Burn' directory path.
    """
    # 1. Android Termux paths
    candidates = [
        Path("/sdcard/Download/Anime Burn"),
        Path.home() / "storage/downloads/Anime Burn",
        Path.home() / "storage/shared/Download/Anime Burn"
    ]
    for c in candidates:
        if c.parent.exists() or Path("/sdcard").exists():
            c.mkdir(parents=True, exist_ok=True)
            return c

    # 2. Windows / Mac / Linux standard Downloads folder
    user_home = Path.home()
    std_download = user_home / "Downloads" / "Anime Burn"
    try:
        std_download.mkdir(parents=True, exist_ok=True)
        return std_download
    except Exception:
        # Fallback to local project folder if home is restricted
        local_dir = BASE_DIR / "Anime Burn"
        local_dir.mkdir(parents=True, exist_ok=True)
        return local_dir

OUTPUT_DIR = get_anime_burn_dir()

# Quality presets
QUALITY_MAP = {
    "480p": {
        "width": -2,
        "height": 480,
        "video_bitrate": "800k",
        "audio_bitrate": "96k",
        "fontsize": 18
    },
    "720p": {
        "width": -2,
        "height": 720,
        "video_bitrate": "1600k",
        "audio_bitrate": "128k",
        "fontsize": 24
    }
}

# ASS Subtitle Default Styling
ASS_STYLE_DEFAULTS = {
    "fontname": "Arial",
    "fontsize": 22,
    "primarycolor": "&H00FFFFFF",     # Bright White
    "secondarycolor": "&H000000FF",   # Yellow/Accent
    "outlinecolor": "&H00000000",     # Deep Black Outline
    "backcolor": "&H80000000",        # Semi-transparent shadow
    "bold": 1,
    "italic": 0,
    "outline": 2.5,
    "shadow": 1.0,
    "alignment": 2,                   # Bottom-Center
    "marginl": 20,
    "marginr": 20,
    "marginv": 25,
}
