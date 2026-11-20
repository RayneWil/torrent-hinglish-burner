import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
import config
from config import QUALITY_MAP
from notifier import notifier

console = Console()

def escape_ffmpeg_filter_path(path: Path) -> str:
    """
    Escapes paths correctly for FFmpeg filter arguments (subtitles/ass filter).
    Handles Windows backslashes and drive colons.
    """
    p_str = str(path.resolve()).replace("\\", "/")
    # Escape single quotes and colons
    p_str = p_str.replace(":", "\\:")
    p_str = p_str.replace("'", "'\\''")
    return p_str

def get_video_duration(video_path: Path) -> float:
    """Gets total duration of video in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path.resolve())
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0

def burn_subtitles_and_encode(
    video_path: Path,
    ass_path: Path,
    output_path: Path,
    quality: str = "720p"
) -> Path:
    """
    Burns .ass subtitles into video and compresses/rescales to 480p, 720p, or 1080p using FFmpeg.
    """
    if quality not in QUALITY_MAP:
        quality = "720p"

    q_config = QUALITY_MAP[quality]
    height = q_config["height"]
    audio_bitrate = q_config["audio_bitrate"]

    escaped_ass = escape_ffmpeg_filter_path(ass_path)
    fonts_dir = config.BASE_DIR / "fonts"
    if fonts_dir.exists():
        escaped_fonts = escape_ffmpeg_filter_path(fonts_dir)
        vf_filter = f"ass='{escaped_ass}':fontsdir='{escaped_fonts}',scale=-2:{height}"
    else:
        vf_filter = f"ass='{escaped_ass}',scale=-2:{height}"

    total_duration = get_video_duration(video_path)

    console.print(f"[bold cyan]🔥 Encoding & Burning Hinglish Subtitles into {quality}...[/bold cyan]")
    console.print(f"[dim]Input: {video_path.name}[/dim]")
    console.print(f"[dim]Resolution Target: {height}p | Filter: {vf_filter}[/dim]")
    notifier.start_encoding(quality)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path.resolve()),
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-sn",  # Drop embedded subtitle streams since we are burning them in
        str(output_path.resolve())
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            universal_newlines=True
        )

        time_pattern = re.compile(r"time=(\d+):(\d+):(\d+.\d+)")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task = progress.add_task(f"[yellow]Encoding {quality}...", total=int(total_duration) if total_duration > 0 else 100)

            for line in process.stdout:
                match = time_pattern.search(line)
                if match and total_duration > 0:
                    hours, minutes, seconds = match.groups()
                    current_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                    progress.update(task, completed=min(int(current_seconds), int(total_duration)))

                    pct = min(99.0, (current_seconds / total_duration) * 100.0)
                    curr_str = f"{int(hours):02d}:{int(minutes):02d}:{int(float(seconds)):02d}"
                    tot_h = int(total_duration // 3600)
                    tot_m = int((total_duration % 3600) // 60)
                    tot_s = int(total_duration % 60)
                    tot_str = f"{tot_h:02d}:{tot_m:02d}:{tot_s:02d}"
                    notifier.update_encoding_progress(percent=pct, current_time=curr_str, total_time=tot_str)

            process.wait()

        if process.returncode != 0:
            console.print(f"[bold red]❌ FFmpeg encoding failed with exit code {process.returncode}![/bold red]")
            notifier.notify_error("Encoding", f"FFmpeg failed with exit code {process.returncode}")
            sys.exit(1)

    except Exception as e:
        console.print("[bold red]❌ Encoding error:[/bold red]")
        console.print(str(e), markup=False)
        notifier.notify_error("Encoding", str(e))
        sys.exit(1)

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    console.print(f"[bold green]✨ Video Encoding Finished Successfully![/bold green]")
    console.print(f"[bold white]Output file:[/bold white] [green]{output_path}[/green] ([cyan]{file_size_mb:.1f} MB[/cyan])")
    notifier.finish_encoding(output_path.name, file_size_mb)

    return output_path
