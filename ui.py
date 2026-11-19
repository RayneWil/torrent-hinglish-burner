#!/usr/bin/env python3
"""
DSA Subber Ready - Interactive Terminal UI
Full terminal interface for Termux, Linux VPS, Colab, and PC.
"""

import os
import sys
import shutil
import time
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

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

    new_keys_input = Prompt.ask(
        "[cyan]Enter Gemini API Keys (comma-separated, e.g. key1,key2,key3) or press Enter to cancel[/cyan]"
    ).strip()

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
    console.print("[1] 720p (High Definition - Recommended for PC & Mobile)")
    console.print("[2] 480p (Standard Definition - Fast & Low File Size)")
    console.print("[3] Keep Current")

    choice = Prompt.ask("[cyan]Select option[/cyan]", choices=["1", "2", "3"], default="3")
    if choice == "1":
        return "720p"
    elif choice == "2":
        return "480p"
    return current_quality

def start_burning_workflow(quality: str):
    show_header()
    console.print(Panel(
        f"[bold green]🚀 Start Burning Process | Target Quality: {quality}[/bold green]\n"
        f"Output Destination: [cyan]{config.OUTPUT_DIR}[/cyan]",
        border_style="green"
    ))

    # Check API keys
    if not config.GEMINI_API_KEYS:
        console.print("[bold red]❌ No Gemini API keys found![/bold red]")
        console.print("Please select 'Change API Key' from the main menu first.")
        Prompt.ask("\nPress Enter to return to menu")
        return

    torrent_input = Prompt.ask("\n[bold yellow]👉 Torrent link ya Magnet URI do[/bold yellow]").strip()
    if not torrent_input:
        console.print("[red]Link empty hai. Process cancelled.[/red]")
        time.sleep(1.5)
        return

    temp_dir = config.TEMP_DIR / f"job_{int(time.time())}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
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

        # Step 4: AI Hinglish Translation (30 lines/req, 20 reqs/key)
        console.rule("[bold cyan]Step 4: AI Hinglish Translation (30 lines/req)[/bold cyan]")
        hinglish_subs = translate_subtitles_to_hinglish(
            subs,
            api_keys=config.GEMINI_API_KEYS,
            batch_size=30,
            max_requests_per_key=20
        )
        final_ass_path = temp_dir / f"{video_file.stem}_hinglish.ass"
        save_ass_subtitles(hinglish_subs, final_ass_path)

        # Step 5: Encoding & Burning
        console.rule(f"[bold cyan]Step 5: Burning Subtitles & Encoding ({quality})[/bold cyan]")
        temp_encoded_video = temp_dir / f"{video_file.stem}_Hinglish_{quality}.mp4"
        burn_subtitles_and_encode(
            video_path=video_file,
            ass_path=final_ass_path,
            output_path=temp_encoded_video,
            quality=quality
        )

        # Step 6: Move to Download/Anime Burn folder
        final_destination = config.OUTPUT_DIR / f"{video_file.stem}_Hinglish_{quality}.mp4"
        shutil.move(str(temp_encoded_video), str(final_destination))

        # Completion Success Banner
        show_header()
        console.print(Panel(
            f"[bold green]🎉 SUBTITLES BURNED & MOVED SUCCESSFULLY! 🎉[/bold green]\n\n"
            f"[bold white]File Name:[/bold white] {final_destination.name}\n"
            f"[bold white]Quality:[/bold white] {quality}\n"
            f"[bold white]Location:[/bold white] [bold cyan]{final_destination}[/bold cyan]\n"
            f"[bold white]File Size:[/bold white] {final_destination.stat().st_size / (1024*1024):.1f} MB\n\n"
            f"[dim]Saved inside 'Anime Burn' in your Downloads folder![/dim]",
            title="[bold green]Done[/bold green]",
            border_style="green"
        ))

    except Exception as e:
        console.print(f"\n[bold red]❌ Error occurred: {e}[/bold red]")
    finally:
        # Cleanup temp directory
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

    Prompt.ask("\n[bold yellow]Press Enter to return to main menu...[/bold yellow]")

def main_menu():
    quality = "720p"

    while True:
        show_header()
        console.print(Panel(
            "[bold white]Select an option:[/bold white]\n\n"
            "[bold green][1][/bold green] 🔥 [bold]Start Burning[/bold]\n"
            "[bold yellow][2][/bold yellow] 🔑 [bold]Change API Key[/bold]\n"
            f"[bold cyan][3][/bold cyan] ⚙️ [bold]Change Quality[/bold] (Current: [cyan]{quality}[/cyan])\n"
            f"[bold blue][4][/bold blue] 📂 [bold]Open Anime Burn Folder[/bold] ([dim]{config.OUTPUT_DIR}[/dim])\n"
            "[bold red][5][/bold red] 🚪 [bold]Exit[/bold]",
            title="[bold cyan]Main Menu[/bold cyan]",
            border_style="cyan"
        ))

        choice = Prompt.ask("[bold cyan]Enter choice (1-5)[/bold cyan]", choices=["1", "2", "3", "4", "5"], default="1")

        if choice == "1":
            start_burning_workflow(quality)
        elif choice == "2":
            change_api_keys_menu()
        elif choice == "3":
            quality = select_quality_menu(quality)
        elif choice == "4":
            console.print(f"\n[bold cyan]Output Folder: {config.OUTPUT_DIR}[/bold cyan]")
            time.sleep(2)
        elif choice == "5":
            console.print("\n[bold yellow]👋 Exiting DSA Subber. Bye bhai![/bold yellow]\n")
            sys.exit(0)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print("\n\n[bold yellow]Exiting... Bye![/bold yellow]")
        sys.exit(0)
