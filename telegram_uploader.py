import os
import sys
import re
import time
import math
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

def make_text_progress_bar(percentage: float, total_blocks: int = 10) -> str:
    """Generates a text-based progress bar for Telegram messages (e.g. [█████░░░░░])."""
    filled = int(round(total_blocks * (percentage / 100)))
    filled = max(0, min(total_blocks, filled))
    return "█" * filled + "░" * (total_blocks - filled)

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

async def fast_upload_file(
    client,
    file_path: Path,
    progress_callback=None,
    max_workers: int = 6
):
    """
    High-Speed Parallel Multi-Chunk Uploader for Telethon (2GB MTProto).
    Transmits 512KB chunks in 6 concurrent parallel streams, boosting upload
    speeds from 1 MB/s up to 4-8+ MB/s!
    """
    from telethon import helpers
    from telethon.tl import functions, types

    file_size = file_path.stat().st_size
    file_name = file_path.name

    # If small file (< 10MB), standard upload is fast enough
    if file_size <= 10 * 1024 * 1024:
        return await client.upload_file(
            str(file_path.resolve()),
            progress_callback=progress_callback
        )

    # 512 KB is the maximum Telegram MTProto chunk size for highest throughput
    part_size = 512 * 1024
    total_parts = math.ceil(file_size / part_size)
    file_id = helpers.generate_random_long()

    queue = asyncio.Queue(maxsize=max_workers * 2)
    uploaded_bytes = 0
    uploaded_lock = asyncio.Lock()

    async def worker():
        nonlocal uploaded_bytes
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                break

            part_idx, chunk_data = item
            chunk_len = len(chunk_data)

            for attempt in range(3):
                try:
                    await client(functions.upload.SaveBigFilePartRequest(
                        file_id=file_id,
                        file_part=part_idx,
                        file_total_parts=total_parts,
                        bytes=chunk_data
                    ))
                    break
                except Exception as e:
                    if attempt == 2:
                        queue.task_done()
                        raise e
                    await asyncio.sleep(1)

            async with uploaded_lock:
                uploaded_bytes += chunk_len
                current = uploaded_bytes

            if progress_callback:
                progress_callback(current, file_size)

            queue.task_done()

    # Launch worker pool
    workers = [asyncio.create_task(worker()) for _ in range(max_workers)]

    # Stream file chunks into the queue without reading whole file into RAM
    with open(file_path, "rb") as f:
        for part_idx in range(total_parts):
            chunk = f.read(part_size)
            await queue.put((part_idx, chunk))

    # Wait for all chunks to be uploaded
    await queue.join()

    # Stop workers
    for _ in range(max_workers):
        await queue.put(None)
    await asyncio.gather(*workers)

    return types.InputFileBig(
        id=file_id,
        parts=total_parts,
        name=file_name
    )

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

    # Send initial upload start message to Owner
    owner_id = config.TELEGRAM_OWNER_ID
    owner_msg = None
    if owner_id:
        try:
            owner_msg = await client.send_message(
                owner_id,
                f"🚀 <b>DSA Subber: Upload Started!</b>\n\n"
                f"🎬 <b>Title:</b> {clean_title}\n"
                f"📦 <b>Size:</b> {file_size_mb:.1f} MB\n"
                f"📺 <b>Resolution:</b> {meta['height']}p ({quality})\n"
                f"📢 <b>Target Channel:</b> <code>{chat_id}</code>\n\n"
                f"⏳ <i>Connecting upload stream...</i>",
                parse_mode="html"
            )
            console.print(f"[bold green]📬 Upload notification sent to Owner (ID: {owner_id})[/bold green]")
        except Exception as e:
            console.print(f"[dim]⚠️ Notice: Could not send start message to Owner ({owner_id}): {e}[/dim]")
            console.print("[dim]💡 Hint: Please send /start to your bot in Telegram so it can DM you updates![/dim]")

    last_edit_time = 0.0
    start_time = time.time()

    async def update_owner_progress(current: int, total: int):
        nonlocal last_edit_time
        if not owner_msg or total <= 0:
            return

        now = time.time()
        # Edit every 3.5 seconds or on finish to respect Telegram rate limits and avoid FloodWait
        if now - last_edit_time < 3.5 and current < total:
            return

        last_edit_time = now
        pct = (current / total) * 100
        bar = make_text_progress_bar(pct, total_blocks=10)
        curr_mb = current / (1024 * 1024)
        tot_mb = total / (1024 * 1024)
        elapsed = max(0.1, now - start_time)
        speed_mb = (curr_mb / elapsed)
        rem_bytes = max(0, total - current)
        eta_sec = int(rem_bytes / (speed_mb * 1024 * 1024)) if speed_mb > 0 else 0
        eta_str = f"{eta_sec}s" if eta_sec < 60 else f"{eta_sec // 60}m {eta_sec % 60}s"

        text = (
            f"📤 <b>Uploading Video to Channel:</b>\n"
            f"🎬 <b>{clean_title}</b>\n\n"
            f"<code>[{bar}]</code> <b>{pct:.1f}%</b>\n"
            f"📦 <b>Uploaded:</b> {curr_mb:.1f} / {tot_mb:.1f} MB\n"
            f"⚡ <b>Speed:</b> {speed_mb:.2f} MB/s\n"
            f"⏱️ <b>ETA:</b> {eta_str}\n\n"
            f"📢 <i>Target: {chat_id}</i>"
        )
        try:
            await owner_msg.edit(text, parse_mode="html")
        except Exception:
            pass

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[yellow]Uploading Video (Parallel Multi-Stream)...", total=file_size_bytes)

        def progress_callback(current, total):
            progress.update(task, completed=current, total=total)
            if owner_msg:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(update_owner_progress(current, total))
                except Exception:
                    pass

        try:
            uploaded_file = await fast_upload_file(
                client=client,
                file_path=video_path,
                progress_callback=progress_callback,
                max_workers=6
            )
            console.print(f"[dim]Publishing video to channel...[/dim]")
            await client.send_file(
                entity=chat_id,
                file=uploaded_file,
                caption=caption,
                parse_mode="html",
                thumb=str(thumb.resolve()) if thumb else None,
                attributes=video_attributes,
                supports_streaming=True
            )
            console.print(f"[bold green]🎉 Video successfully uploaded to Telegram Channel: {chat_id}![/bold green]")
        except Exception as e:
            console.print(f"[bold red]❌ Video upload failed: {e}[/bold red]")
            await client.disconnect()
            return False

    # Send final success status to Owner
    if owner_msg:
        try:
            await owner_msg.edit(
                f"🎉 <b>Video Upload Complete!</b>\n\n"
                f"🎬 <b>Title:</b> {clean_title}\n"
                f"📦 <b>Size:</b> {file_size_mb:.1f} MB\n"
                f"⏱️ <b>Duration:</b> {duration_str}\n"
                f"📺 <b>Resolution:</b> {meta['height']}p ({quality})\n\n"
                f"✅ <i>Successfully published to Channel: {chat_id}</i>",
                parse_mode="html"
            )
        except Exception:
            pass

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

def send_pipeline_start_notification(task_info: str) -> None:
    """Sends a notification to Owner ID when anime downloading/burning begins."""
    owner_id = config.TELEGRAM_OWNER_ID
    if not owner_id or not config.TELEGRAM_AUTO_UPLOAD:
        return

    async def _notify():
        ensure_telethon_installed()
        from telethon import TelegramClient
        session_path = str(config.TEMP_DIR / "dsa_notify_session")
        client = TelegramClient(session_path, config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)
        try:
            await client.start(bot_token=config.TELEGRAM_BOT_TOKEN)
            short_task = clean_anime_title(task_info[:60])
            await client.send_message(
                owner_id,
                f"🔥 <b>DSA Subber: Pipeline Started!</b>\n\n"
                f"🎬 <b>Task:</b> {short_task}\n"
                f"⚙️ <b>Status:</b> Downloading & Translating...\n\n"
                f"<i>Upload progress bar will appear here once burning finishes! 🚀</i>",
                parse_mode="html"
            )
        except Exception:
            pass
        finally:
            await client.disconnect()

    try:
        asyncio.run(_notify())
    except Exception:
        pass
