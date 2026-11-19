import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Working Directories
TEMP_DIR = Path(os.getenv("TEMP_DIR", BASE_DIR / "temp"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "output"))

# Create directories if they don't exist
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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
