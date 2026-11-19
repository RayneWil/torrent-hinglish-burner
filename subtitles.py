import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from rich.console import Console
import pysubs2
from config import ASS_STYLE_DEFAULTS

console = Console()

SUBTITLE_EXTENSIONS = {".ass", ".srt", ".vtt", ".sub"}

def check_ffmpeg() -> bool:
    """Check if ffmpeg and ffprobe are available."""
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

def probe_subtitles(video_path: Path) -> List[Dict]:
    """Inspects video file for embedded subtitle streams using ffprobe."""
    if not check_ffmpeg():
        console.print("[bold red]❌ ffmpeg/ffprobe not found! Please install ffmpeg.[/bold red]")
        sys.exit(1)

    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "s",
        "-show_entries", "stream=index,codec_name:stream_tags=language,title",
        "-of", "json",
        str(video_path.resolve())
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(res.stdout)
        streams = data.get("streams", [])
        return streams
    except Exception as e:
        console.print(f"[bold yellow]⚠️ Could not probe subtitle streams: {e}[/bold yellow]")
        return []

def extract_subtitle(video_path: Path, output_sub_path: Path, track_index: Optional[int] = None) -> Path:
    """
    Extracts an embedded subtitle stream from video or checks for an external subtitle file.
    Returns path to the extracted subtitle file.
    """
    streams = probe_subtitles(video_path)

    # 1. Try embedded streams
    if streams:
        selected_index = None
        if track_index is not None:
            for s in streams:
                if s["index"] == track_index:
                    selected_index = track_index
                    break

        if selected_index is None:
            for s in streams:
                tags = s.get("tags", {})
                lang = tags.get("language", "").lower()
                if lang in ["eng", "en", "english"]:
                    selected_index = s["index"]
                    break
            if selected_index is None:
                selected_index = streams[0]["index"]

        console.print(f"[cyan]🎬 Extracting embedded subtitle track (stream index: {selected_index})...[/cyan]")
        
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path.resolve()),
            "-map", f"0:{selected_index}",
            str(output_sub_path.resolve())
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0 and output_sub_path.exists() and output_sub_path.stat().st_size > 0:
            console.print(f"[bold green]✅ Extracted subtitle to {output_sub_path.name}[/bold green]")
            return output_sub_path

    # 2. Check for external subtitle files in the same directory
    parent_dir = video_path.parent
    for ext in SUBTITLE_EXTENSIONS:
        candidates = list(parent_dir.glob(f"*{ext}"))
        if candidates:
            chosen = candidates[0]
            console.print(f"[bold green]✅ Found external subtitle file: {chosen.name}[/bold green]")
            shutil.copy(chosen, output_sub_path)
            return output_sub_path

    console.print("[bold red]❌ No embedded or external subtitles found for this video![/bold red]")
    sys.exit(1)

def apply_custom_font_to_all_styles(subs: pysubs2.SSAFile, font_size: int = 22):
    """
    Applies 'HelveticaRounded LT Std BdCn' to EVERY style in the .ass subtitle file.
    """
    target_font = ASS_STYLE_DEFAULTS.get("fontname", "HelveticaRounded LT Std BdCn")

    # If no styles, create Default
    if not subs.styles:
        default_style = pysubs2.SSAStyle()
        default_style.fontname = target_font
        default_style.fontsize = font_size or ASS_STYLE_DEFAULTS["fontsize"]
        default_style.primarycolor = pysubs2.Color(255, 255, 255)
        default_style.outlinecolor = pysubs2.Color(0, 0, 0)
        default_style.bold = True
        default_style.outline = 2.5
        default_style.shadow = 1.0
        subs.styles["Default"] = default_style

    # Apply target font to all styles
    for style_name, style in subs.styles.items():
        style.fontname = target_font
        if font_size:
            style.fontsize = font_size
        style.outline = max(style.outline, 2.5)
        style.shadow = max(style.shadow, 1.0)

    console.print(f"[bold cyan]🎨 Applied font '{target_font}' across all {len(subs.styles)} style(s)![/bold cyan]")

def load_and_style_subtitles(sub_path: Path, font_size: int = 22) -> pysubs2.SSAFile:
    """
    Loads subtitle file using pysubs2 and formats all styles with the target custom font.
    """
    subs = pysubs2.load(str(sub_path.resolve()))
    apply_custom_font_to_all_styles(subs, font_size=font_size)
    return subs

def save_ass_subtitles(subs: pysubs2.SSAFile, out_path: Path):
    """Saves the SSAFile back as an .ass subtitle file ensuring custom font is locked in."""
    apply_custom_font_to_all_styles(subs)
    subs.save(str(out_path.resolve()))
    console.print(f"[bold green]💾 Saved stylized ASS subtitles to {out_path.name}[/bold green]")
