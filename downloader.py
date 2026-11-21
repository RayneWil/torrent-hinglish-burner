import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, List
from rich.console import Console
from rich.markup import escape
from notifier import notifier

console = Console()

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".webm", ".flv", ".ts"}

def check_aria2c() -> bool:
    """Check if aria2c is installed on the system."""
    return shutil.which("aria2c") is not None

def download_torrent(source: str, download_dir: Path) -> Path:
    """
    Downloads video using aria2c from a Magnet URI or a .torrent file path.
    High-speed uncapped BitTorrent configuration.
    Returns the Path to the largest downloaded video file.
    """
    if not check_aria2c():
        console.print("[bold red]❌ Error: aria2c is not installed or not in PATH![/bold red]")
        console.print("Please install aria2c (`pkg install aria2` or `apt install aria2`).")
        sys.exit(1)

    download_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[bold cyan]📥 Starting Torrent Download via aria2c (Full Speed Uncapped)...[/bold cyan]")

    # Build clean high-speed aria2c command (No upload throttling, no tracker congestion)
    cmd = [
        "aria2c",
        "--seed-time=0",
        "--max-connection-per-server=16",
        "--split=16",
        "--min-split-size=1M",
        "--summary-interval=1",
        "--file-allocation=none",           # Immediate start on Android/Termux
        "--enable-dht=true",
        "--enable-peer-exchange=true",
        "--follow-torrent=mem",
        "--console-log-level=warn",
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

        # Print output lines cleanly without markup injection errors
        for line in process.stdout:
            clean_line = line.strip()
            if not clean_line:
                continue
            if any(k in clean_line for k in ["[#", "ETA:", "Download Speed:", "CN:", "SD:"]):
                console.print(f"[bold green]{escape(clean_line)}[/bold green]")
                
                # Live parse aria2c progress for owner notifications
                pct_m = re.search(r'\((\d+)%\)', clean_line)
                dl_m = re.search(r'DL:([^\s\]]+)', clean_line)
                eta_m = re.search(r'ETA:([^\s\]]+)', clean_line)
                cn_m = re.search(r'CN:(\d+)', clean_line)

                pct_val = float(pct_m.group(1)) if pct_m else None
                dl_val = dl_m.group(1) if dl_m else ""
                eta_val = eta_m.group(1) if eta_m else ""
                cn_val = int(cn_m.group(1)) if cn_m else 0

                notifier.update_download_progress(percent=pct_val, speed_str=dl_val, eta_str=eta_val, cn=cn_val)

            elif "Download complete:" in clean_line or "errorCode=" in clean_line:
                console.print(f"[bold yellow]{escape(clean_line)}[/bold yellow]")

        process.wait()

        if process.returncode != 0:
            console.print(f"[bold red]❌ aria2c exited with returncode {process.returncode}[/bold red]")
            notifier.notify_error("Download", f"aria2c exited with code {process.returncode}")
            sys.exit(1)

    except Exception as e:
        console.print("[bold red]❌ Exception during download:[/bold red]")
        console.print(str(e), markup=False)
        notifier.notify_error("Download", str(e))
        sys.exit(1)

    # Find the downloaded video file
    video_file = find_largest_video(download_dir)
    if not video_file:
        console.print(f"[bold red]❌ No video file found in {download_dir}![/bold red]")
        notifier.notify_error("Download", f"No video file found in {download_dir}")
        sys.exit(1)

    size_mb = video_file.stat().st_size / (1024 * 1024)
    console.print(f"[bold green]✅ Download Finished: {video_file.name} ({size_mb:.1f} MB)[/bold green]")
    notifier.finish_download(video_file.name, size_mb)
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
