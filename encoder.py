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
        vf_filter = f"scale=-2:{height},ass='{escaped_ass}':fontsdir='{escaped_fonts}'"
    else:
        vf_filter = f"scale=-2:{height},ass='{escaped_ass}'"

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
        "-preset", "veryfast",
        "-crf", "23",
        "-threads", "0",
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-sn",  # Drop embedded subtitle streams since we are burning them in
        "-nostats",
        "-progress", "pipe:1",
        str(output_path.resolve())
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task = progress.add_task(f"[yellow]Encoding {quality}...", total=int(total_duration) if total_duration > 0 else 100)

            current_seconds = 0.0
            last_notified_pct = -1.0

            for line in process.stdout:
                line_str = line.strip()
                if not line_str:
                    continue

                if line_str.startswith("out_time_us="):
                    try:
                        us = int(line_str.split("=")[1])
                        if us > 0:
                            current_seconds = us / 1_000_000.0
                    except Exception:
                        pass
                elif line_str.startswith("out_time="):
                    t_val = line_str.split("=")[1].strip()
                    parts = t_val.split(":")
                    if len(parts) == 3:
                        try:
                            current_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                        except Exception:
                            pass
                elif line_str in ("progress=continue", "progress=end"):
                    if total_duration > 0:
                        progress.update(task, completed=min(int(current_seconds), int(total_duration)))
                        pct = min(99.0, (current_seconds / total_duration) * 100.0)

                        curr_h = int(current_seconds // 3600)
                        curr_m = int((current_seconds % 3600) // 60)
                        curr_s = int(current_seconds % 60)
                        curr_str = f"{curr_h:02d}:{curr_m:02d}:{curr_s:02d}"

                        tot_h = int(total_duration // 3600)
                        tot_m = int((total_duration % 3600) // 60)
                        tot_s = int(total_duration % 60)
                        tot_str = f"{tot_h:02d}:{tot_m:02d}:{tot_s:02d}"

                        # Update Telegram live tracker on 5% steps or completion (prevents network choke)
                        if pct - last_notified_pct >= 5.0 or line_str == "progress=end":
                            last_notified_pct = pct
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
