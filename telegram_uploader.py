import os
import sys
import re
import json
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn
)

import config

console = Console()

def ensure_telethon_installed():
    """Silently ensures telethon is installed."""
    try:
        import telethon
    except ImportError:
        console.print("[dim]📦 Installing telethon package for 2GB MTProto upload support...[/dim]")
        cmd = [sys.executable, "-m", "pip", "install", "telethon", "--break-system-packages", "--quiet"]
        try:
            subprocess.run(cmd, check=True)
        except Exception:
            cmd = [sys.executable, "-m", "pip", "install", "telethon", "--quiet"]
            subprocess.run(cmd, check=True)

def get_video_metadata(video_path: Path) -> Dict:
    """Extracts width, height, and duration of video using ffprobe."""
    meta = {"width": 1280, "height": 720, "duration": 0}
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration",
        "-of", "json",
        str(video_path.resolve())
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(res.stdout)
        streams = data.get("streams", [])
        if streams:
            s = streams[0]
            meta["width"] = int(s.get("width", 1280))
            meta["height"] = int(s.get("height", 720))
            dur_str = s.get("duration")
            if dur_str:
                meta["duration"] = int(float(dur_str))
    except Exception:
        pass

    # Fallback duration from format if stream duration was missing
    if meta["duration"] <= 0:
        cmd_fmt = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path.resolve())
        ]
        try:
            res = subprocess.run(cmd_fmt, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            meta["duration"] = int(float(res.stdout.strip()))
        except Exception:
            meta["duration"] = 0

    return meta

def generate_video_thumbnail(video_path: Path, output_thumb: Path, seek_sec: int = 15) -> Optional[Path]:
    """Extracts a sharp thumbnail image from the video."""
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(seek_sec),
        "-i", str(video_path.resolve()),
        "-vframes", "1",
        "-q:v", "2",
        str(output_thumb.resolve())
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if output_thumb.exists() and output_thumb.stat().st_size > 0:
            return output_thumb
    except Exception:
        pass
    return None

def format_duration(seconds: int) -> str:
    """Formats seconds into readable string (e.g. 23m 45s)."""
    if seconds <= 0:
        return "Unknown"
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours}h {mins:02d}m {secs:02d}s"
    return f"{mins:02d}m {secs:02d}s"

def clean_anime_title(filename: str) -> str:
    """Extracts clean anime title from filename."""
    name = Path(filename).stem
    # Remove _Hinglish suffix if present
    name = re.sub(r"_Hinglish$", "", name, flags=re.IGNORECASE)
    # Remove release group tags like [Erai-raws], [SubsPlease]
    name = re.sub(r"^\[.*?\]\s*", "", name)
    # Remove trailing resolution/codec brackets like [720p CR WEB-DL AVC AAC][...]
    name = re.sub(r"\[.*?\]", "", name)
    name = name.strip(" -_")
    return name or Path(filename).stem

def build_caption(title: str, quality: str, height: int, size_mb: float, duration_str: str) -> str:
    """Builds an attractive HTML caption for Telegram channel post."""
    caption = (
        f"🎬 <b>{title}</b>\n\n"
        f"📺 <b>Resolution:</b> {height}p ({quality})\n"
        f"📦 <b>File Size:</b> {size_mb:.1f} MB\n"
        f"⏱️ <b>Duration:</b> {duration_str}\n"
        f"🌐 <b>Audio/Sub:</b> Japanese Audio + Hinglish Subtitles\n\n"
        f"✨ <i>Subbed in Hinglish by @DarkSoulAcademy</i>\n"
        f"📢 <b>Join Telegram:</b> @DarkSoulAcademy"
    )
    return caption

async def _async_upload_to_telegram(
    video_path: Path,
    sub_path: Optional[Path] = None,
    quality: str = "720p"
) -> bool:
    """Asynchronous video and subtitle uploader via Telethon MTProto."""
    ensure_telethon_installed()
    from telethon import TelegramClient
    from telethon.tl.types import DocumentAttributeVideo

    bot_token = config.TELEGRAM_BOT_TOKEN
    api_id = config.TELEGRAM_API_ID
    api_hash = config.TELEGRAM_API_HASH
    chat_id = config.TELEGRAM_CHAT_ID

    if not bot_token or not api_id or not api_hash or not chat_id:
        console.print("[bold red]❌ Telegram credentials incomplete! Please check your configuration.[/bold red]")
        return False

    console.print(f"[bold cyan]✈️ Connecting to Telegram MTProto Client...[/bold cyan]")
    console.print(f"[dim]Destination Channel/Chat ID: {chat_id}[/dim]")

    session_path = str(config.TEMP_DIR / "dsa_uploader_session")
    client = TelegramClient(session_path, api_id, api_hash)

    try:
        await client.start(bot_token=bot_token)
    except Exception as e:
        console.print(f"[bold red]❌ Failed to authenticate Telegram Bot: {e}[/bold red]")
        return False

    meta = get_video_metadata(video_path)
    file_size_bytes = video_path.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)
    duration_str = format_duration(meta["duration"])
    clean_title = clean_anime_title(video_path.name)
    caption = build_caption(clean_title, quality, meta["height"], file_size_mb, duration_str)

    # Generate thumbnail
    thumb_path = config.TEMP_DIR / f"{video_path.stem}_thumb.jpg"
    thumb = generate_video_thumbnail(video_path, thumb_path, seek_sec=15)

    video_attributes = [
        DocumentAttributeVideo(
            duration=meta["duration"],
            w=meta["width"],
            h=meta["height"],
            supports_streaming=True
        )
    ]

    console.print(f"[bold yellow]📤 Uploading '{clean_title}' ({file_size_mb:.1f} MB) to Telegram...[/bold yellow]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[yellow]Uploading Video...", total=file_size_bytes)

        def progress_callback(current, total):
            progress.update(task, completed=current, total=total)

        try:
            await client.send_file(
                entity=chat_id,
                file=str(video_path.resolve()),
                caption=caption,
                parse_mode="html",
                thumb=str(thumb.resolve()) if thumb else None,
                attributes=video_attributes,
                progress_callback=progress_callback,
                supports_streaming=True
            )
            console.print(f"[bold green]🎉 Video successfully uploaded to Telegram Channel: {chat_id}![/bold green]")
        except Exception as e:
            console.print(f"[bold red]❌ Video upload failed: {e}[/bold red]")
            await client.disconnect()
            return False

    # Optional: Also upload the .ass subtitle file
    if config.TELEGRAM_UPLOAD_SUBTITLE and sub_path and sub_path.exists():
        console.print(f"[dim]📄 Uploading Hinglish subtitle file ({sub_path.name})...[/dim]")
        try:
            sub_caption = (
                f"📝 <b>Hinglish Subtitle File (.ass)</b>\n"
                f"🎬 {clean_title}\n\n"
                f"<i>@DarkSoulAcademy</i>"
            )
            await client.send_file(
                entity=chat_id,
                file=str(sub_path.resolve()),
                caption=sub_caption,
                parse_mode="html"
            )
            console.print("[bold green]✅ Subtitle file (.ass) also uploaded![/bold green]")
        except Exception as e:
            console.print(f"[dim]⚠️ Subtitle upload notice: {e}[/dim]")

    # Clean up thumbnail
    if thumb and thumb.exists():
        try:
            thumb.unlink()
        except Exception:
            pass

    await client.disconnect()
    return True

def upload_to_telegram(
    video_path: Path,
    sub_path: Optional[Path] = None,
    quality: str = "720p"
) -> bool:
    """
    Synchronous wrapper to upload burned anime video and .ass subtitle
    to Telegram channel using Telethon (supports up to 2GB).
    """
    try:
        return asyncio.run(_async_upload_to_telegram(video_path, sub_path, quality))
    except Exception as e:
        console.print(f"[bold red]❌ Telegram Uploader encountered an error: {e}[/bold red]")
        return False
