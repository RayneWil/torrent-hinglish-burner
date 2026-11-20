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

# Style presets for SD (384x288, 640x360)
STYLES_SD = [
    "Style: Info,Roboto Medium,26,&H00FFFFFF,&H000000FF,&H00000000,&H24000000,0,0,0,0,100,100,0,0,1,1.0,0.8,2,20,20,20,1",
    "Style: WatermarkTop,Montserrat SemiBold,16,&H00B8FFC8,&H00B8FFC8,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,0,0.0,0.5,9,30,14,6,1"
]

# Style presets for HD & Full HD (1280x720, 1920x1080)
STYLES_HD = [
    "Style: Info,HelveticaRounded LT Std BdCn,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0.8,0,1,2,2,2,30,30,40,1",
    "Style: WatermarkTop,Montserrat SemiBold,16,&H00B8FFC8,&H00B8FFC8,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,0,0.0,1.0,9,30,14,6,1"
]

def get_watermark_events(pos_x: int, pos_y: int, fs: int) -> List[str]:
    return [
        f"Dialogue: 0,0:00:00.00,0:07:10.10,WatermarkTop,,0,0,0,,{{\\fad(2000,500)\\fnComic Sans MS\\c&H307DEE&\\3c&HFFFFFF&\\fs{fs}\\pos({pos_x},{pos_y})}}Dark{{\\c&H56DDB5&}}Soul{{\\c&H215BEC&}}Academy😉",
        f"Dialogue: 0,0:07:10.10,0:15:10.10,WatermarkTop,,0,0,0,,{{\\fad(500,500)\\fnComic Sans MS\\c&H307DEE&\\3c&HFFFFFF&\\fs{fs}\\pos({pos_x},{pos_y})}}Dark{{\\c&H56DDB5&}}Soul{{\\c&H215BEC&}}Academy😈",
        f"Dialogue: 0,0:15:10.10,0:30:00.00,WatermarkTop,,0,0,0,,{{\\fad(500,500)\\fnComic Sans MS\\c&H307DEE&\\3c&HFFFFFF&\\fs{fs}\\pos({pos_x},{pos_y})}}Dark{{\\c&H56DDB5&}}Soul{{\\c&H215BEC&}}Academy😘"
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

def apply_custom_font_to_all_styles(subs: pysubs2.SSAFile, font_size: Optional[int] = None):
    """
    Applies 'HelveticaRounded LT Std BdCn' to all dialogue styles.
    If resolution is 1280x720 (PlayResX: 1280, PlayResY: 720), sets fontsize to 52 across all styles.
    Protects custom watermark styles (Info, WatermarkTop).
    """
    target_font = ASS_STYLE_DEFAULTS.get("fontname", "HelveticaRounded LT Std BdCn")
    protected_styles = {"Info", "WatermarkTop"}

    # Detect resolution
    rx = None
    ry = None
    try:
        rx = int(subs.info.get("PlayResX", 0))
        ry = int(subs.info.get("PlayResY", 0))
    except Exception:
        pass

    if rx == 1920 and ry == 1080:
        target_fontsize = 80
    elif rx == 1280 and ry == 720:
        target_fontsize = 52
    elif rx == 640 and ry == 360:
        target_fontsize = 26
    elif font_size is not None:
        target_fontsize = font_size
    else:
        target_fontsize = ASS_STYLE_DEFAULTS.get("fontsize", 22)

    # If no styles, create Default
    if not subs.styles:
        default_style = pysubs2.SSAStyle()
        default_style.fontname = target_font
        default_style.fontsize = target_fontsize
        default_style.primarycolor = pysubs2.Color(255, 255, 255)
        default_style.outlinecolor = pysubs2.Color(0, 0, 0)
        default_style.bold = True
        default_style.outline = 2.5
        default_style.shadow = 1.0
        subs.styles["Default"] = default_style

    for style_name, style in subs.styles.items():
        if style_name in protected_styles or "watermark" in style_name.lower():
            continue
        style.fontname = target_font
        style.fontsize = target_fontsize
        style.outline = max(style.outline, 2.5)
        style.shadow = max(style.shadow, 1.0)

    console.print(f"[bold cyan]🎨 Applied font '{target_font}' (fontsize: {target_fontsize}) across all subtitle styles![/bold cyan]")

def load_and_style_subtitles(sub_path: Path, font_size: Optional[int] = None) -> pysubs2.SSAFile:
    """Loads subtitle file using pysubs2 and formats all styles with the target custom font."""
    subs = pysubs2.load(str(sub_path.resolve()))
    apply_custom_font_to_all_styles(subs, font_size=font_size)
    return subs

def inject_watermark_into_file(file_path: Path):
    """
    Post-processes the .ass file ensuring:
    - Style: Info & Style: WatermarkTop are placed 2 LINES BELOW ALL STYLES (separated by a blank line).
    - Watermark dialogues are placed 2 LINES BELOW ALL DIALOGUES (separated by a blank line).
    - Clear visual separation so it is easy to find in text editors.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Remove existing watermark lines to prevent duplicates
        lines = [
            l for l in content.splitlines()
            if not ("Style: WatermarkTop" in l or "Style: Info" in l or "DarkSoulAcademy" in l)
        ]

        full_text = "\n".join(lines)
        rx_match = re.search(r"PlayResX:\s*(\d+)", full_text)
        ry_match = re.search(r"PlayResY:\s*(\d+)", full_text)
        rx = int(rx_match.group(1)) if rx_match else None
        ry = int(ry_match.group(1)) if ry_match else None

        # Check resolution profile
        if rx == 384 and ry == 288:
            target_rx, target_ry = 384, 288
            pos_x, pos_y, fs = 380, 5, 13
            target_styles = STYLES_SD
        elif rx == 640 and ry == 360:
            target_rx, target_ry = 640, 360
            pos_x, pos_y, fs = 630, 5, 16
            target_styles = STYLES_SD
        elif rx == 1280 and ry == 720:
            target_rx, target_ry = 1280, 720
            pos_x, pos_y, fs = 1260, 10, 32
            target_styles = STYLES_HD
        elif rx == 1920 and ry == 1080:
            target_rx, target_ry = 1920, 1080
            pos_x, pos_y, fs = 1900, 10, 42
            target_styles = STYLES_HD
        else:
            if rx and ry:
                if rx >= 1920 or ry >= 1080:
                    target_rx, target_ry = 1920, 1080
                    pos_x, pos_y, fs = 1900, 10, 42
                    target_styles = STYLES_HD
                elif rx >= 1280 or ry >= 720:
                    target_rx, target_ry = 1280, 720
                    pos_x, pos_y, fs = 1260, 10, 32
                    target_styles = STYLES_HD
                elif abs(rx/ry - 4/3) < 0.1:
                    target_rx, target_ry = 384, 288
                    pos_x, pos_y, fs = 380, 5, 13
                    target_styles = STYLES_SD
                else:
                    target_rx, target_ry = 640, 360
                    pos_x, pos_y, fs = 630, 5, 16
                    target_styles = STYLES_SD
            else:
                target_rx, target_ry = 1280, 720
                pos_x, pos_y, fs = 1260, 10, 32
                target_styles = STYLES_HD

        # Update PlayResX / PlayResY in lines
        has_rx = False
        has_ry = False
        for i, line in enumerate(lines):
            if line.startswith("PlayResX:"):
                lines[i] = f"PlayResX: {target_rx}"
                has_rx = True
            elif line.startswith("PlayResY:"):
                lines[i] = f"PlayResY: {target_ry}"
                has_ry = True

        if not has_rx or not has_ry:
            for i, line in enumerate(lines):
                if "[Script Info]" in line:
                    if not has_rx:
                        lines.insert(i + 1, f"PlayResX: {target_rx}")
                    if not has_ry:
                        lines.insert(i + 2, f"PlayResY: {target_ry}")
                    break

        # Determine target subtitle font size based on resolution:
        # - PlayResX: 1920 | PlayResY: 1080 -> font size 80
        # - PlayResX: 1280 | PlayResY: 720  -> font size 52
        # - PlayResX: 640  | PlayResY: 360  -> font size 26
        # (Custom watermark styles Info and WatermarkTop are strictly protected)
        chosen_fontsize = None
        if target_rx == 1920 and target_ry == 1080:
            chosen_fontsize = "80"
        elif target_rx == 1280 and target_ry == 720:
            chosen_fontsize = "52"
        elif target_rx == 640 and target_ry == 360:
            chosen_fontsize = "26"

        if chosen_fontsize:
            fontsize_idx = 2
            name_idx = 0
            for l in lines:
                l_strip = l.strip()
                if l_strip.startswith("Format:") and "name" in l_strip.lower() and "fontsize" in l_strip.lower():
                    cols = [c.strip().lower() for c in l_strip.replace("Format:", "").split(",")]
                    if "name" in cols:
                        name_idx = cols.index("name")
                    if "fontsize" in cols:
                        fontsize_idx = cols.index("fontsize")
                    break

            protected_style_names = {"info", "watermarktop"}
            for i, line in enumerate(lines):
                match = re.match(r"^(Style:\s*)(.*)$", line)
                if match:
                    prefix = match.group(1)
                    parts = match.group(2).split(",")
                    if len(parts) > max(name_idx, fontsize_idx):
                        style_name = parts[name_idx].strip().lower()
                        if style_name not in protected_style_names and "watermark" not in style_name:
                            parts[fontsize_idx] = chosen_fontsize
                            lines[i] = f"{prefix}{','.join(parts)}"

        # 1. Place styles 2 LINES BELOW ALL EXISTING STYLES (leave a blank line before)
        last_style_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("Style:"):
                last_style_idx = i

        if last_style_idx != -1:
            # Leave a blank line (2 lines below)
            insert_styles = [""] + target_styles
            for st in reversed(insert_styles):
                lines.insert(last_style_idx + 1, st)
        else:
            for i, line in enumerate(lines):
                if "[V4+ Styles]" in line:
                    insert_styles = [""] + target_styles
                    for st in reversed(insert_styles):
                        lines.insert(i + 2, st)
                    break

        # 2. Place watermark dialogues 2 LINES BELOW ALL EXISTING DIALOGUES (leave a blank line before)
        last_dialogue_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("Dialogue:"):
                last_dialogue_idx = i

        wm_events = get_watermark_events(pos_x, pos_y, fs)
        if last_dialogue_idx != -1:
            # Leave a blank line (2 lines below)
            insert_events = [""] + wm_events
            for ev in reversed(insert_events):
                lines.insert(last_dialogue_idx + 1, ev)
        else:
            lines.append("")
            lines.extend(wm_events)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        console.print(f"[bold green]🌟 Injected Custom Watermark ({target_rx}x{target_ry}) 2 lines below styles & dialogues![/bold green]")
    except Exception as e:
        console.print(f"[bold yellow]⚠️ Watermark injection warning: {e}[/bold yellow]")

def save_ass_subtitles(subs: pysubs2.SSAFile, out_path: Path):
    """Saves the SSAFile and post-processes custom watermark & resolution."""
    apply_custom_font_to_all_styles(subs)
    subs.save(str(out_path.resolve()))
    inject_watermark_into_file(out_path)
    console.print(f"[bold green]💾 Saved stylized ASS subtitles to {out_path.name}[/bold green]")
