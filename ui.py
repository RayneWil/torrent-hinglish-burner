#!/usr/bin/env python3
"""
DSA Subber Ready - Interactive Terminal UI
Full terminal interface for Termux, Linux VPS, Colab, and PC.
Saves Subtitles in Download/Anime Burn/Subtitle and Videos in Download/Anime Burn/Video.
"""

import os
import sys

# Reconnect stdin to /dev/tty if launched via a pipe (like curl | bash)
if not sys.stdin.isatty():
    try:
        if os.path.exists("/dev/tty"):
            sys.stdin = open("/dev/tty", "r")
    except Exception:
        pass

import shutil
import time
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

import config
from downloader import download_torrent
from subtitles import extract_subtitle, load_and_style_subtitles, save_ass_subtitles
from translator import translate_subtitles_to_hinglish
from encoder import burn_subtitles_and_encode

console = Console()

def clear_screen():
    os.system("clear" if os.name != "nt" else "cls")

def show_header():
    clear_screen()
    banner_text = (
        "[bold cyan]==================================================================\n"
        "                     🔥 DSA Subber Ready 🔥\n"
        "       Automated Torrent to Hinglish Burner (Termux & Linux)\n"
        "==================================================================[/bold cyan]"
    )
    console.print(banner_text)

def change_api_keys_menu():
    show_header()
    console.print(Panel("[bold yellow]🔑 API Key Settings[/bold yellow]", border_style="yellow"))
    current_count = len(config.GEMINI_API_KEYS)
    console.print(f"Current active Gemini API Keys: [bold green]{current_count}[/bold green]\n")

    try:
        new_keys_input = Prompt.ask(
            "[cyan]Enter Gemini API Keys (comma-separated, e.g. key1,key2,key3) or press Enter to cancel[/cyan]"
        ).strip()
    except (EOFError, KeyboardInterrupt):
        return

    if new_keys_input:
        keys_list = [k.strip() for k in new_keys_input.split(",") if k.strip()]
        if keys_list:
            config.GEMINI_API_KEYS = keys_list
            # Update .env file
            env_path = config.BASE_DIR / ".env"
            env_lines = []
            if env_path.exists():
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.startswith("GEMINI_API_KEYS="):
                            env_lines.append(line)
            env_lines.insert(0, f"GEMINI_API_KEYS={','.join(keys_list)}\n")
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(env_lines)
            console.print(f"[bold green]✅ Successfully saved {len(keys_list)} API Keys![/bold green]")
            time.sleep(1.5)

def select_quality_menu(current_quality: str) -> str:
    show_header()
    console.print(Panel(f"[bold yellow]⚙️ Select Output Quality (Current: {current_quality})[/bold yellow]", border_style="yellow"))
    console.print("[1] 720p (High Definition - Super Fast & Recommended for Phone, ~4-5 mins)")
    console.print("[2] 1080p (Full High Definition - Crisp Quality, Takes ~2x more encoding time)")
    console.print("[3] 480p (Standard Definition - Fastest, Low File Size)")
    console.print("[4] Keep Current")

    try:
        choice = Prompt.ask("[cyan]Select option[/cyan]", choices=["1", "2", "3", "4"], default="4")
        if choice == "1":
            return "720p"
        elif choice == "2":
            return "1080p"
        elif choice == "3":
            return "480p"
    except (EOFError, KeyboardInterrupt):
        pass
    return current_quality

def start_burning_workflow(quality: str):
    show_header()
    console.print(Panel(
        f"[bold green]🚀 Start Burning Process | Target Quality: {quality}[/bold green]\n"
        f"📁 Subtitle Output: [cyan]{config.SUBTITLE_OUTPUT_DIR}[/cyan]\n"
        f"🎬 Video Output:    [cyan]{config.VIDEO_OUTPUT_DIR}[/cyan]",
        border_style="green"
    ))

    # Check API keys
    if not config.GEMINI_API_KEYS:
        console.print("[bold red]❌ No Gemini API keys found![/bold red]")
        console.print("Please select 'Change API Key' from the main menu first.")
        try:
            Prompt.ask("\nPress Enter to return to menu")
        except (EOFError, KeyboardInterrupt):
            pass
        return

    try:
        torrent_input = Prompt.ask("\n[bold yellow]👉 Torrent link ya Magnet URI do[/bold yellow]").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if not torrent_input:
        console.print("[red]Link empty hai. Process cancelled.[/red]")
        time.sleep(1.5)
        return

    temp_dir = config.TEMP_DIR / f"job_{int(time.time())}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Send start notification to Telegram Owner if configured
        try:
            from telegram_uploader import send_pipeline_start_notification
            send_pipeline_start_notification(torrent_input, quality=quality)
        except Exception:
            pass

        # Step 1: Downloading
        console.rule("[bold cyan]Step 1: Downloading Torrent Video[/bold cyan]")
        video_file = download_torrent(torrent_input, temp_dir)

        # Step 2: Subtitle Extraction
        console.rule("[bold cyan]Step 2: Subtitle Extraction[/bold cyan]")
        raw_sub_path = temp_dir / f"{video_file.stem}_extracted.ass"
        extracted_sub = extract_subtitle(video_file, raw_sub_path)

        # Step 3: ASS Styling
        console.rule("[bold cyan]Step 3: Styling Subtitles[/bold cyan]")
        font_size = config.QUALITY_MAP[quality]["fontsize"]
        subs = load_and_style_subtitles(extracted_sub, font_size=font_size)

        # Step 4: AI Hinglish Translation (20 lines/req, 20 reqs/key)
        console.rule("[bold cyan]Step 4: AI Hinglish Translation (20 lines/req)[/bold cyan]")
        hinglish_subs = translate_subtitles_to_hinglish(
            subs,
            api_keys=config.GEMINI_API_KEYS,
            batch_size=20,
            max_requests_per_key=20
        )
        
        # Save translated subtitle into Download/Anime Burn/Subtitle/
        final_sub_destination = config.SUBTITLE_OUTPUT_DIR / f"{video_file.stem}_Hinglish.ass"
        save_ass_subtitles(hinglish_subs, final_sub_destination)
        console.print(f"[bold green]💾 Subtitle saved to: {final_sub_destination}[/bold green]")

        # Step 5: Encoding & Burning
        console.rule(f"[bold cyan]Step 5: Burning Subtitles & Encoding ({quality})[/bold cyan]")
        temp_encoded_video = temp_dir / f"{video_file.stem}_Hinglish_{quality}.mp4"
        burn_subtitles_and_encode(
            video_path=video_file,
            ass_path=final_sub_destination,
            output_path=temp_encoded_video,
            quality=quality
        )

        # Step 6: Move burned video to Download/Anime Burn/Video/
        final_video_destination = config.VIDEO_OUTPUT_DIR / f"{video_file.stem}_Hinglish_{quality}.mp4"
        shutil.move(str(temp_encoded_video), str(final_video_destination))

        # Step 7: Auto-Upload to Telegram Channel
        if config.TELEGRAM_AUTO_UPLOAD:
            console.rule("[bold cyan]Step 6: Uploading to Telegram Channel[/bold cyan]")
            try:
                from telegram_uploader import upload_to_telegram
                upload_to_telegram(final_video_destination, final_sub_destination, quality=quality)
            except Exception as e:
                console.print(f"[bold red]⚠️ Telegram upload skipped due to error: {e}[/bold red]")

        # Completion Success Banner
        show_header()
        console.print(Panel(
            f"[bold green]🎉 PROCESSING COMPLETED SUCCESSFULLY! 🎉[/bold green]\n\n"
            f"[bold white]🎬 Burned Video:[/bold white] [bold cyan]{final_video_destination}[/bold cyan] "
            f"({final_video_destination.stat().st_size / (1024*1024):.1f} MB)\n"
            f"[bold white]📝 Hinglish Subtitle:[/bold white] [bold cyan]{final_sub_destination}[/bold cyan]\n"
            f"[bold white]Quality:[/bold white] {quality}\n\n"
            f"[dim]Saved in: Download/Anime Burn/Video & Download/Anime Burn/Subtitle[/dim]",
            title="[bold green]Done[/bold green]",
            border_style="green"
        ))

    except Exception as e:
        console.print("\n[bold red]❌ Error occurred:[/bold red]")
        console.print(str(e), markup=False)
    finally:
        # Cleanup temp directory
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

    try:
        Prompt.ask("\n[bold yellow]Press Enter to return to main menu...[/bold yellow]")
    except (EOFError, KeyboardInterrupt):
        pass

def test_telegram_connection():
    """Tests the Telegram Bot connection and sends a test message to the channel."""
    console.print("\n[bold cyan]✈️ Testing Telegram Bot connection...[/bold cyan]")
    try:
        from telegram_uploader import ensure_telethon_installed
        ensure_telethon_installed()
        from telethon import TelegramClient

        async def _test():
            session_path = str(config.TEMP_DIR / "dsa_test_session")
            client = TelegramClient(session_path, config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)
            try:
                await client.start(bot_token=config.TELEGRAM_BOT_TOKEN)
                me = await client.get_me()
                console.print(f"[bold green]✅ Bot connected successfully as: @{me.username} ({me.first_name})![/bold green]")
                console.print(f"[dim]Sending test message to channel {config.TELEGRAM_CHAT_ID}...[/dim]")
                msg = await client.send_message(
                    config.TELEGRAM_CHAT_ID,
                    "🤖 <b>DSA Subber Connected!</b>\n\nTelegram Auto-Uploader is ready! 🚀\n<i>Channel: @DarkSoulAcademy</i>",
                    parse_mode="html"
                )
                console.print(f"[bold green]🎉 Test message delivered successfully to your channel (Message ID: {msg.id})![/bold green]")

                # Send test message to Owner ID
                if config.TELEGRAM_OWNER_ID:
                    try:
                        await client.send_message(
                            config.TELEGRAM_OWNER_ID,
                            f"👋 <b>Hello Boss! (Owner ID: {config.TELEGRAM_OWNER_ID})</b>\n\n"
                            f"DSA Subber Bot (@{me.username}) is connected to your personal chat!\n"
                            f"You will receive live work progress tracker cards and milestone alerts for Download, Translation, Encoding, and Upload here! 🚀",
                            parse_mode="html"
                        )
                        console.print(f"[bold green]📬 Test message sent to Owner ({config.TELEGRAM_OWNER_ID}) successfully![/bold green]")
                    except Exception as ex:
                        console.print(f"[yellow]⚠️ Could not DM Owner ({config.TELEGRAM_OWNER_ID}): {ex}[/yellow]")
                        console.print(f"[dim]💡 Please open @{me.username} in Telegram and click /start so the bot can DM you![/dim]")
            except Exception as err:
                console.print(f"[bold red]❌ Telegram connection failed: {err}[/bold red]")
                console.print("[yellow]💡 Note: Ensure your bot is added as an Administrator with 'Post Messages' permission in your channel![/yellow]")
            finally:
                await client.disconnect()

        import asyncio
        asyncio.run(_test())
    except Exception as e:
        console.print(f"[bold red]❌ Error: {e}[/bold red]")

    try:
        Prompt.ask("\n[bold yellow]Press Enter to return...[/bold yellow]")
    except (EOFError, KeyboardInterrupt):
        pass

def manage_telegram_settings():
    """Sub-menu to configure Telegram auto-upload."""
    while True:
        show_header()
        status_text = "[bold green]ENABLED (Auto-upload ON)[/bold green]" if config.TELEGRAM_AUTO_UPLOAD else "[bold red]DISABLED (Auto-upload OFF)[/bold red]"
        console.print(Panel(
            f"[bold white]✈️ Telegram Auto-Uploader Configuration[/bold white]\n\n"
            f"• [bold]Auto-Upload Status:[/bold] {status_text}\n"
            f"• [bold]Target Channel/Chat ID:[/bold] [bold cyan]{config.TELEGRAM_CHAT_ID}[/bold cyan]\n"
            f"• [bold]Owner Notification ID:[/bold] [bold cyan]{config.TELEGRAM_OWNER_ID}[/bold cyan]\n"
            f"• [bold]Upload .ass Subtitle:[/bold] [bold cyan]{'Yes' if config.TELEGRAM_UPLOAD_SUBTITLE else 'No'}[/bold cyan]\n"
            f"• [bold]Engine:[/bold] [bold green]Telethon MTProto (Supports up to 2 GB)[/bold green]\n\n"
            "[bold cyan][1][/bold cyan] 🔄 [bold]Toggle Auto-Upload (ON / OFF)[/bold]\n"
            "[bold cyan][2][/bold cyan] 📢 [bold]Change Target Channel / Chat ID[/bold]\n"
            "[bold cyan][3][/bold cyan] 🧪 [bold]Test Bot Connection & Send Test Message[/bold]\n"
            "[bold cyan][4][/bold cyan] ↩️ [bold]Back to Main Menu[/bold]",
            title="[bold magenta]Telegram Settings[/bold magenta]",
            border_style="magenta"
        ))

        try:
            choice = Prompt.ask("[bold cyan]Enter choice (1-4)[/bold cyan]", choices=["1", "2", "3", "4"], default="4")
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "1":
            config.TELEGRAM_AUTO_UPLOAD = not config.TELEGRAM_AUTO_UPLOAD
            console.print(f"\n[bold green]✅ Telegram Auto-Upload is now {'ENABLED' if config.TELEGRAM_AUTO_UPLOAD else 'DISABLED'}![/bold green]")
            time.sleep(1.5)
        elif choice == "2":
            new_id = Prompt.ask("\n[bold yellow]Enter new Channel ID (e.g. -1003511011855) or @username[/bold yellow]")
            if new_id.strip():
                clean_val = new_id.strip()
                config.TELEGRAM_CHAT_ID = int(clean_val) if clean_val.lstrip("-").isdigit() else clean_val
                console.print(f"[bold green]✅ Channel ID updated to: {config.TELEGRAM_CHAT_ID}[/bold green]")
                time.sleep(1.5)
        elif choice == "3":
            test_telegram_connection()
        elif choice == "4":
            break

def main_menu():
    try:
        from notifier import notifier
        notifier.notify_service_start(cmd_args=sys.argv[1:])
    except Exception:
        pass

    quality = "720p"

    while True:
        show_header()
        tg_badge = "[bold green]ON[/bold green]" if config.TELEGRAM_AUTO_UPLOAD else "[bold red]OFF[/bold red]"
        console.print(Panel(
            "[bold white]Select an option:[/bold white]\n\n"
            "[bold green][1][/bold green] 🔥 [bold]Start Burning[/bold]\n"
            "[bold yellow][2][/bold yellow] 🔑 [bold]Change API Key[/bold]\n"
            f"[bold cyan][3][/bold cyan] ⚙️ [bold]Change Quality[/bold] (Current: [cyan]{quality}[/cyan])\n"
            f"[bold blue][4][/bold blue] 📂 [bold]View Anime Burn Folders[/bold]\n"
            "       ├── [dim]Video:    " + str(config.VIDEO_OUTPUT_DIR) + "[/dim]\n"
            "       └── [dim]Subtitle: " + str(config.SUBTITLE_OUTPUT_DIR) + "[/dim]\n"
            f"[bold magenta][5][/bold magenta] ✈️ [bold]Telegram Settings / Test Upload[/bold] ({tg_badge})\n"
            "[bold red][6][/bold red] 🚪 [bold]Exit[/bold]",
            title="[bold cyan]Main Menu[/bold cyan]",
            border_style="cyan"
        ))

        try:
            choice = Prompt.ask("[bold cyan]Enter choice (1-6)[/bold cyan]", choices=["1", "2", "3", "4", "5", "6"], default="1")
        except (EOFError, KeyboardInterrupt):
            console.print("\n\n[bold yellow]Exiting... Bye![/bold yellow]")
            sys.exit(0)

        if choice == "1":
            start_burning_workflow(quality)
        elif choice == "2":
            change_api_keys_menu()
        elif choice == "3":
            quality = select_quality_menu(quality)
        elif choice == "4":
            console.print(f"\n[bold cyan]🎬 Video Folder:    {config.VIDEO_OUTPUT_DIR}[/bold cyan]")
            console.print(f"[bold cyan]📝 Subtitle Folder: {config.SUBTITLE_OUTPUT_DIR}[/bold cyan]\n")
            time.sleep(3)
        elif choice == "5":
            manage_telegram_settings()
        elif choice == "6":
            console.print("\n[bold yellow]👋 Exiting DSA Subber. Bye bhai![/bold yellow]\n")
            sys.exit(0)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print("\n\n[bold yellow]Exiting... Bye![/bold yellow]")
        sys.exit(0)
