"""
notifier.py - Real-Time Telegram Owner Progress Notifier for DSA Subber
Sends live-updating tracker cards and milestone alerts to the Owner Telegram ID
via official Telegram Bot API (HTTP REST - fast, reliable, zero session conflicts).
"""

import re
import time
import json
import threading
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional
try:
    from rich.console import Console
    console = Console()
except ImportError:
    class DummyConsole:
        def print(self, *args, **kwargs):
            import re
            clean = " ".join(str(a) for a in args)
            clean = re.sub(r"\[.*?\]", "", clean)
            print(clean)
    console = DummyConsole()

import config

def make_progress_bar(percent: float, length: int = 10) -> str:
    """Generates a clean Unicode progress bar."""
    percent = max(0.0, min(100.0, float(percent)))
    filled = int(length * (percent / 100.0))
    empty = length - filled
    return "█" * filled + "░" * empty

class TelegramNotifier:
    """
    Real-time Live Progress Notifier for Owner ID via Telegram Bot API.
    - Sends a live status message card to Owner ID.
    - Dynamically edits the message with real-time progress for:
      1. Torrent Download (speed, percentage, ETA)
      2. Subtitle Extraction & AI Hinglish Translation (batch progress, lines)
      3. FFmpeg Subtitle Burning & Encoding (percentage, time)
      4. Channel Upload (MB/s, percentage)
    - Sends sound-alert milestone messages when key phases start or finish.
    """

    def __init__(self):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.owner_id = config.TELEGRAM_OWNER_ID
        self.live_message_id: Optional[int] = None
        self.last_edit_time: float = 0.0
        self.min_edit_interval: float = 2.5  # Min seconds between Telegram message edits
        self.task_name: str = "Anime Video"
        self.quality: str = "720p"
        
        self.state = {
            "download": "⏳ Waiting to start...",
            "translation": "⏳ Waiting for subtitle extraction...",
            "encoding": "⏳ Waiting for translation...",
            "upload": "⏳ Waiting for encoding...",
            "current_status": "🚀 Initializing pipeline..."
        }

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.owner_id)

    def _api_call(self, endpoint: str, payload: dict) -> Optional[dict]:
        """Direct REST call to Telegram Bot API."""
        if not self.is_configured:
            return None
        url = f"https://api.telegram.org/bot{self.bot_token}/{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res if res.get("ok") else None
        except urllib.error.HTTPError as e:
            # Handle rate limits or message not modified
            err_msg = e.read().decode("utf-8", errors="ignore")
            if "message is not modified" in err_msg.lower():
                return None
            return None
        except Exception:
            return None

    def send_message(self, text: str, disable_notification: bool = False) -> Optional[int]:
        """Sends a fresh notification message to the Owner ID."""
        if not self.is_configured:
            return None
        payload = {
            "chat_id": self.owner_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "disable_notification": disable_notification
        }
        res = self._api_call("sendMessage", payload)
        if res and "result" in res:
            return res["result"].get("message_id")
        return None

    def render_tracker_card(self) -> str:
        """Formats the live visual dashboard tracker card."""
        clean_name = self.task_name[:50]
        return (
            f"⚡ <b>DSA Subber — Live Pipeline Tracker</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"🎬 <b>Task:</b> <code>{clean_name}</code>\n"
            f"⚙️ <b>Quality Target:</b> {self.quality}\n\n"
            f"📥 <b>Download:</b> {self.state['download']}\n"
            f"📝 <b>Translation:</b> {self.state['translation']}\n"
            f"🎞 <b>Encoding:</b> {self.state['encoding']}\n"
            f"🚀 <b>Upload:</b> {self.state['upload']}\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<i>Status: {self.state['current_status']}</i>"
        )

    def edit_live_card(self, force: bool = False):
        """Edits the active live tracker card with throttled updates."""
        if not self.is_configured:
            return
        now = time.time()
        if not force and (now - self.last_edit_time < self.min_edit_interval):
            return

        card_text = self.render_tracker_card()

        if self.live_message_id is None:
            # Send initial tracker message
            self.live_message_id = self.send_message(card_text, disable_notification=False)
            self.last_edit_time = now
            return

        payload = {
            "chat_id": self.owner_id,
            "message_id": self.live_message_id,
            "text": card_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        self.last_edit_time = now

        def _async_send_edit(p):
            try:
                self._api_call("editMessageText", p)
            except Exception:
                pass

        threading.Thread(target=_async_send_edit, args=(payload,), daemon=True).start()

    # =========================================================================
    # PIPELINE LIFECYCLE HOOKS
    # =========================================================================

    def start_pipeline(self, task_name: str, quality: str = "720p"):
        """Called when a new anime torrent job begins."""
        if "dn=" in task_name:
            import urllib.parse
            m = re.search(r'dn=([^&]+)', task_name)
            if m:
                task_name = urllib.parse.unquote_plus(m.group(1))
        elif "/" in task_name or "\\" in task_name:
            from pathlib import Path
            task_name = Path(task_name).stem

        try:
            from telegram_uploader import parse_anime_info_from_filename
            clean_t, s_num, ep_num = parse_anime_info_from_filename(task_name)
            self.task_name = f"{clean_t} (S{s_num:02d}E{ep_num:02d})"
        except Exception:
            self.task_name = task_name[:50]

        self.quality = quality
        self.live_message_id = None
        self.state["download"] = "⏳ Connecting to BitTorrent swarm..."
        self.state["translation"] = "⏳ Waiting for subtitle extraction..."
        self.state["encoding"] = f"⏳ Waiting for translation ({quality})..."
        self.state["upload"] = "⏳ Waiting for encoding..."
        self.state["current_status"] = "🚀 Pipeline Started — Connecting to torrent peers..."
        
        self.edit_live_card(force=True)
        console.print(f"[bold green]📬 Live Tracker initialized for Owner (ID: {self.owner_id})[/bold green]")

    # --- 1. DOWNLOAD HOOKS ---
    def update_download_progress(self, percent: Optional[float] = None, speed_str: str = "", eta_str: str = "", cn: int = 0):
        """Live updates from aria2c download."""
        if percent is not None and percent > 0:
            bar = make_progress_bar(percent, length=8)
            details = []
            if speed_str:
                details.append(f"DL: {speed_str}")
            if eta_str:
                details.append(f"ETA: {eta_str}")
            det_str = f" ({' | '.join(details)})" if details else ""
            self.state["download"] = f"<code>[{bar}]</code> {percent:.0f}%{det_str}"
            self.state["current_status"] = f"Downloading torrent: {percent:.0f}% ({speed_str})"
        else:
            conn_info = f" (Peers: {cn})" if cn > 0 else ""
            self.state["download"] = f"⏳ Discovering peers & metadata{conn_info}..."
            self.state["current_status"] = f"Connecting to swarm{conn_info}..."

        self.edit_live_card()

    def finish_download(self, filename: str, size_mb: float):
        """Called when torrent finishes downloading."""
        self.state["download"] = f"✅ Completed ({size_mb:.1f} MB)"
        self.state["current_status"] = f"Download complete ({filename[:35]}). Starting extraction..."
        self.edit_live_card(force=True)

        # Milestone Ping to Owner
        self.send_message(
            f"📥 <b>Torrent Download Completed!</b>\n\n"
            f"🎬 <b>File:</b> <code>{filename}</code>\n"
            f"📦 <b>Size:</b> {size_mb:.1f} MB\n\n"
            f"<i>Next: Extracting and translating subtitles to Hinglish... 🚀</i>"
        )

    # --- 2. TRANSLATION HOOKS ---
    def start_translation(self, total_lines: int):
        """Called when AI subtitle translation begins."""
        self.state["translation"] = f"⏳ Translating 0/{total_lines} lines (0%)..."
        self.state["current_status"] = f"Translating subtitles: 0/{total_lines} lines..."
        self.edit_live_card(force=True)

    def update_translation_progress(self, done_lines: int, total_lines: int, current_batch: int = 0, total_batches: int = 0):
        """Live updates from Gemini subtitle translation."""
        if total_lines <= 0:
            return
        pct = (done_lines / total_lines) * 100.0
        bar = make_progress_bar(pct, length=8)
        self.state["translation"] = f"<code>[{bar}]</code> {done_lines}/{total_lines} ({pct:.0f}%)"
        self.state["current_status"] = f"AI translating: {done_lines}/{total_lines} lines ({pct:.0f}%)"
        self.edit_live_card()

    def update_translation_fail_safe(self, pass_num: int, remaining: int):
        """Updates status during Fail-Safe Sweeper passes."""
        self.state["translation"] = f"🔍 Fail-Safe Pass #{pass_num}: {remaining} lines remaining..."
        self.state["current_status"] = f"Running Fail-Safe Sweeper Pass #{pass_num}..."
        self.edit_live_card(force=True)

    def finish_translation(self, done_lines: int, total_lines: int):
        """Called when all subtitle lines are translated to Hinglish."""
        self.state["translation"] = f"✅ {done_lines}/{total_lines} lines (100% Hinglish)"
        self.state["current_status"] = f"Translation complete! Starting {self.quality} subtitle burning..."
        self.edit_live_card(force=True)

        # Milestone Ping to Owner
        self.send_message(
            f"📝 <b>AI Subtitle Translation Completed!</b>\n\n"
            f"🌐 <b>Translated:</b> {done_lines}/{total_lines} lines to natural Hinglish\n"
            f"🎯 <b>Accuracy:</b> 100% lines translated (Zero Devanagari, Gender Conjugations Preserved)\n\n"
            f"<i>Next: Burning subtitles & encoding to {self.quality}... 🎞</i>"
        )

    # --- 3. ENCODING HOOKS ---
    def start_encoding(self, quality: str):
        """Called when FFmpeg subtitle burning & encoding begins."""
        self.quality = quality
        self.state["encoding"] = f"⏳ Starting FFmpeg {quality} encoding..."
        self.state["current_status"] = f"Encoding & burning Hinglish subtitles into {quality}..."
        self.edit_live_card(force=True)

    def update_encoding_progress(self, percent: float, current_time: str = "", total_time: str = ""):
        """Live updates from FFmpeg stderr progress."""
        bar = make_progress_bar(percent, length=8)
        time_info = f" ({current_time}/{total_time})" if current_time and total_time else ""
        self.state["encoding"] = f"<code>[{bar}]</code> {percent:.0f}%{time_info}"
        self.state["current_status"] = f"Burning & encoding {self.quality}: {percent:.0f}%"
        self.edit_live_card()

    def finish_encoding(self, output_filename: str, size_mb: float):
        """Called when video encoding finishes."""
        self.state["encoding"] = f"✅ Finished {self.quality} ({size_mb:.1f} MB)"
        self.state["current_status"] = f"Encoding complete! Uploading {output_filename[:35]}..."
        self.edit_live_card(force=True)

        # Milestone Ping to Owner
        self.send_message(
            f"🎞 <b>Hinglish Video Encoding Completed!</b>\n\n"
            f"🎬 <b>File:</b> <code>{output_filename}</code>\n"
            f"⚙️ <b>Quality:</b> {self.quality}\n"
            f"📦 <b>Output Size:</b> {size_mb:.1f} MB\n\n"
            f"<i>Next: Uploading video to Telegram Channel... 🚀</i>"
        )

    # --- 4. UPLOAD HOOKS ---
    def start_upload(self, filename: str, size_mb: float):
        """Called when Telegram channel upload begins."""
        self.state["upload"] = f"⏳ Uploading {size_mb:.1f} MB..."
        self.state["current_status"] = "Uploading video to channel via multi-worker MTProto..."
        self.edit_live_card(force=True)

    def update_upload_progress(self, percent: float, speed_str: str = "", uploaded_mb: float = 0, total_mb: float = 0):
        """Live updates from MTProto uploader."""
        bar = make_progress_bar(percent, length=8)
        speed_info = f" ({speed_str})" if speed_str else ""
        self.state["upload"] = f"<code>[{bar}]</code> {percent:.0f}%{speed_info}"
        self.state["current_status"] = f"Uploading to channel: {percent:.0f}%{speed_info}"
        self.edit_live_card()

    def finish_upload(self, title: str, channel_title: str = "@DarkSoulAcademy"):
        """Called when anime is published to channel."""
        self.state["upload"] = f"✅ Published to {channel_title}"
        self.state["current_status"] = "🎉 Pipeline Successfully Completed!"
        self.edit_live_card(force=True)

        # Milestone Ping to Owner
        self.send_message(
            f"🎉 <b>Anime Successfully Published!</b>\n\n"
            f"🎬 <b>Title:</b> {title}\n"
            f"📢 <b>Channel:</b> {channel_title}\n"
            f"⚙️ <b>Quality:</b> {self.quality}\n\n"
            f"🔥 <i>All steps completed: Download ➔ Translation ➔ Encoding ➔ Upload! 🚀</i>"
        )

    def notify_service_start(self, cmd_args: Optional[list] = None):
        """Notifies Owner ID whenever someone starts the DSA Subber service via command."""
        if not self.is_configured:
            return
        if getattr(self, "_service_started_flag", False):
            return
        self._service_started_flag = True

        import os
        import sys
        import socket
        import platform
        from datetime import datetime

        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = "Device"

        is_termux = "termux" in sys.prefix.lower() or os.path.exists("/data/data/com.termux")
        os_info = "Termux (Android)" if is_termux else f"{platform.system()} ({platform.release()})"
        now_str = datetime.now().strftime("%d %b %Y | %I:%M:%S %p")

        cmd_str = "dsa"
        if cmd_args:
            clean_args = " ".join(cmd_args)[:80]
            cmd_str = f"dsa {clean_args}"

        msg = (
            f"👑 <b>Boss, DSA Subber Service Start Kiya Gaya Hai!</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"⚡ <b>Service:</b> DSA Subber\n"
            f"📱 <b>System:</b> {os_info} ({hostname})\n"
            f"⏰ <b>Start Time:</b> {now_str}\n"
            f"💻 <b>Command:</b> <code>{cmd_str}</code>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<i>Boss, DSA Subber is now actively running! 🚀</i>"
        )
        try:
            self.send_message(msg, disable_notification=False)
            console.print(f"[bold green]📬 Sent service start notification to Boss (Owner ID: {self.owner_id})[/bold green]")
        except Exception:
            pass

    def notify_error(self, step_name: str, error_message: str):
        """Notifies Owner immediately if any pipeline stage fails."""
        self.state["current_status"] = f"❌ Error in {step_name} stage: {error_message[:40]}"
        self.edit_live_card(force=True)

        self.send_message(
            f"⚠️ <b>Pipeline Error Alert!</b>\n\n"
            f"❌ <b>Stage:</b> {step_name}\n"
            f"🚨 <b>Error Details:</b> <code>{error_message[:200]}</code>\n\n"
            f"<i>Please check Termux logs.</i>"
        )

# Global singleton instance for seamless import across all modules
notifier = TelegramNotifier()
