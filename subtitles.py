import json
import re
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

WATERMARK_STYLES = [
    "Style: Info,Roboto Medium,26,&H00FFFFFF,&H000000FF,&H00000000,&H24000000,0,0,0,0,100,100,0,0,1,1.0,0.8,2,20,20,20,1",
    "Style: WatermarkTop,Montserrat SemiBold,16,&H00B8FFC8,&H00B8FFC8,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,0,0.0,0.5,9,30,14,6,1"
]

WATERMARK_EVENTS = [
    r"Dialogue: 0,0:00:00.00,0:07:10.10,WatermarkTop,,0,0,0,,{\fad(2000,500)\fnComic Sans MS\c&H307DEE&\3c&HFFFFFF&\fs13\pos(380,5)}Dark{\c&H56DDB5&}Soul{\c&H215BEC&}Academy😉",
    r"Dialogue: 0,0:07:10.10,0:15:10.10,WatermarkTop,,0,0,0,,{\fad(500,500)\fnComic Sans MS\c&H307DEE&\3c&HFFFFFF&\fs13\pos(380,5)}Dark{\c&H56DDB5&}Soul{\c&H215BEC&}Academy😈",
    r"Dialogue: 0,0:15:10.10,0:30:00.00,WatermarkTop,,0,0,0,,{\fad(500,500)\fnComic Sans MS\c&H307DEE&\3c&HFFFFFF&\fs13\pos(380,5)}Dark{\c&H56DDB5&}Soul{\c&H215BEC&}Academy😘"
]

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
    Applies 'HelveticaRounded LT Std BdCn' to all dialogue styles.
    Protects custom watermark styles (Info, WatermarkTop).
    """
    target_font = ASS_STYLE_DEFAULTS.get("fontname", "HelveticaRounded LT Std BdCn")
    protected_styles = {"Info", "WatermarkTop"}

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

    for style_name, style in subs.styles.items():
        if style_name in protected_styles:
            continue
        style.fontname = target_font
        if font_size:
            style.fontsize = font_size
        style.outline = max(style.outline, 2.5)
        style.shadow = max(style.shadow, 1.0)

    console.print(f"[bold cyan]🎨 Applied font '{target_font}' across all subtitle styles![/bold cyan]")

def load_and_style_subtitles(sub_path: Path, font_size: int = 22) -> pysubs2.SSAFile:
    """Loads subtitle file using pysubs2 and formats all styles with the target custom font."""
    subs = pysubs2.load(str(sub_path.resolve()))
    apply_custom_font_to_all_styles(subs, font_size=font_size)
    return subs

def inject_watermark_into_file(file_path: Path):
    """
    Post-processes the .ass file to ensure:
    - PlayResX: 384, PlayResY: 288
    - Exact Style: Info & Style: WatermarkTop lines under [V4+ Styles]
    - Exact 3 DarkSoulAcademy watermark lines under [Events]
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # 1. Update PlayResX and PlayResY to 384 and 288
        if "PlayResX:" in content:
            content = re.sub(r"PlayResX:\s*\d+", "PlayResX: 384", content)
        else:
            content = content.replace("[Script Info]\n", "[Script Info]\nPlayResX: 384\n")

        if "PlayResY:" in content:
            content = re.sub(r"PlayResY:\s*\d+", "PlayResY: 288", content)
        else:
            content = content.replace("[Script Info]\n", "[Script Info]\nPlayResY: 288\n")

        # 2. Inject Watermark styles under [V4+ Styles] Format: ...
        if "Style: WatermarkTop" not in content:
            style_block = "\n".join(WATERMARK_STYLES) + "\n"
            content = re.sub(
                r"(\[V4\+ Styles\]\s*\nFormat:[^\n]*\n)",
                lambda m: m.group(1) + style_block,
                content,
                count=1
            )

        # 3. Inject Watermark dialogues under [Events] Format: ...
        if "DarkSoulAcademy" not in content:
            events_block = "\n".join(WATERMARK_EVENTS) + "\n"
            content = re.sub(
                r"(\[Events\]\s*\nFormat:[^\n]*\n)",
                lambda m: m.group(1) + events_block,
                content,
                count=1
            )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        console.print("[bold green]🌟 Injected Custom Watermark (DarkSoulAcademy) & PlayRes(384x288) successfully![/bold green]")
    except Exception as e:
        console.print(f"[bold yellow]⚠️ Watermark injection warning: {e}[/bold yellow]")

def save_ass_subtitles(subs: pysubs2.SSAFile, out_path: Path):
    """Saves the SSAFile and post-processes custom watermark & resolution."""
    apply_custom_font_to_all_styles(subs)
    subs.save(str(out_path.resolve()))
    inject_watermark_into_file(out_path)
    console.print(f"[bold green]💾 Saved stylized ASS subtitles to {out_path.name}[/bold green]")
