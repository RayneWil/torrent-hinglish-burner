import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional
from rich.console import Console

console = Console()

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".webm", ".flv", ".ts"}

def check_aria2c() -> bool:
    """Check if aria2c is installed on the system."""
    return shutil.which("aria2c") is not None

def download_torrent(source: str, download_dir: Path) -> Path:
    """
    Downloads video using aria2c from a Magnet URI or a .torrent file path.
    Returns the Path to the largest downloaded video file.
    """
    if not check_aria2c():
        console.print("[bold red]❌ Error: aria2c is not installed or not in PATH![/bold red]")
        console.print("Please install aria2c (`sudo apt install aria2` or `choco install aria2`).")
        sys.exit(1)

    download_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[bold cyan]📥 Starting Torrent Download via aria2c...[/bold cyan]")

    # Build aria2c command
    cmd = [
        "aria2c",
        "--seed-time=0",
        "--max-connection-per-server=16",
        "--split=16",
        "--min-split-size=1M",
        "--summary-interval=5",
        "--dir", str(download_dir.resolve()),
        "--bt-stop-timeout=600",
        source
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

        # Print output lines to terminal
        for line in process.stdout:
            clean_line = line.strip()
            if any(k in clean_line for k in ["[#", "ETA:", "Download Speed:", "Download Progress", "SEED"]):
                console.print(f"[dim]{clean_line}[/dim]")
            elif "Download complete:" in clean_line or "errorCode=" in clean_line:
                console.print(f"[bold yellow]{clean_line}[/bold yellow]")

        process.wait()

        if process.returncode != 0:
            console.print(f"[bold red]❌ aria2c exited with returncode {process.returncode}[/bold red]")
            sys.exit(1)

    except Exception as e:
        console.print(f"[bold red]❌ Exception during download: {e}[/bold red]")
        sys.exit(1)

    # Find the downloaded video file
    video_file = find_largest_video(download_dir)
    if not video_file:
        console.print(f"[bold red]❌ No video file found in {download_dir}![/bold red]")
        sys.exit(1)

    console.print(f"[bold green]✅ Download Finished: {video_file.name} ({video_file.stat().st_size / (1024*1024):.1f} MB)[/bold green]")
    return video_file

def find_largest_video(directory: Path) -> Optional[Path]:
    """Search recursively for video files and return the largest one."""
    videos = []
    for ext in VIDEO_EXTENSIONS:
        videos.extend(directory.rglob(f"*{ext}"))
        videos.extend(directory.rglob(f"*{ext.upper()}"))

    if not videos:
        return None

    # Pick largest file
    largest = max(videos, key=lambda f: f.stat().st_size)
    return largest
