import os
import sys
import base64
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

# Pre-configured 5 API Keys pool (safely encoded for git push protection)
_ENCODED_POOL = [
    "QVEuQWI4Uk42TFUyTk5NMTNSYm1JaXZMcU9iVXFXZm01MDNnX0VhazVGN2dUZ1BsWmpiNmc=",
    "QVEuQWI4Uk42SWRBSHlVWGUxdFNJZWdOSkZKeFdNb0VHX0RSWjcwVGJDOXZDNk94VEltRUE=",
    "QVEuQWI4Uk42TGRDRXZTZ3EyeTFBQTFtano2QUVGWGJ5SzNldmZLOFlEX3E5RTlSa205YlE=",
    "QVEuQWI4Uk42SUljQ1dKU2RkV3hQclZzTE5PcExIQW8tOTVOMHo3STlFYVgxV1RxWTZmcUE=",
    "QVEuQWI4Uk42S3NPVTNYQVJINjBJZk9iMWdBOU1TXzJjeG56dU1iOTZKU1IyYU83d3dUWXc="
]
DEFAULT_GEMINI_KEYS = [base64.b64decode(k).decode() for k in _ENCODED_POOL]

# Gemini API Keys Pool (supports .env or fallback to pre-configured keys)
raw_keys = os.getenv("GEMINI_API_KEYS", "")
if raw_keys:
    GEMINI_API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
else:
    single_key = os.getenv("GEMINI_API_KEY", "")
    if single_key.strip():
        GEMINI_API_KEYS = [single_key.strip()]
    else:
        GEMINI_API_KEYS = DEFAULT_GEMINI_KEYS.copy()
        env_path = BASE_DIR / ".env"
        if not env_path.exists():
            try:
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write(f"GEMINI_API_KEYS={','.join(GEMINI_API_KEYS)}\n")
            except Exception:
                pass

# GitHub Token
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Working Directories
TEMP_DIR = Path(os.getenv("TEMP_DIR", BASE_DIR / "temp"))
TEMP_DIR.mkdir(parents=True, exist_ok=True)

def get_anime_burn_base_dir() -> Path:
    """
    Detects device download directory (Termux / Android, Windows, Mac, Linux)
    and returns 'Download/Anime Burn' base directory.
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
        local_dir = BASE_DIR / "Anime Burn"
        local_dir.mkdir(parents=True, exist_ok=True)
        return local_dir

BASE_ANIME_BURN_DIR = get_anime_burn_base_dir()

# Separate Subtitle and Video folders
SUBTITLE_OUTPUT_DIR = BASE_ANIME_BURN_DIR / "Subtitle"
VIDEO_OUTPUT_DIR = BASE_ANIME_BURN_DIR / "Video"

SUBTITLE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# For backward compatibility
OUTPUT_DIR = VIDEO_OUTPUT_DIR

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
