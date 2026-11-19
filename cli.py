#!/usr/bin/env python3
"""
Torrent to Hinglish Burner CLI
Automated pipeline to download torrents, translate subtitles to Hinglish (.ass), and burn them into 480p/720p video.
"""

import argparse
import sys
import shutil
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
from downloader import download_torrent
from subtitles import extract_subtitle, load_and_style_subtitles, save_ass_subtitles
from translator import translate_subtitles_to_hinglish
from encoder import burn_subtitles_and_encode

console = Console()

BANNER = """
[bold cyan]╔═══════════════════════════════════════════════════════╗
║         🔥 TORRENT TO HINGLISH BURNER CLI 🔥          ║
║      Magnet ➔ Hinglish (.ASS) ➔ 480p/720p Hardcode     ║
╚═══════════════════════════════════════════════════════╝[/bold cyan]
"""

def print_banner():
    console.print(BANNER)

def parse_args():
    parser = argparse.ArgumentParser(
        description="Download torrent, translate subtitles to Hinglish (.ass) & burn into 480p/720p video."
    )
    parser.add_argument(
        "-t", "--torrent",
        type=str,
        required=True,
        help="Magnet URI or path to .torrent file"
    )
    parser.add_argument(
        "-q", "--quality",
        type=str,
        choices=["480p", "720p"],
        default="720p",
        help="Target output video quality (480p or 720p). Default: 720p"
    )
    parser.add_argument(
        "-k", "--api-key",
        type=str,
        default=config.GEMINI_API_KEY,
        help="Google Gemini API Key for Hinglish translation (or set in .env)"
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default=str(config.OUTPUT_DIR),
        help="Directory to save final processed video"
    )
    parser.add_argument(
        "-s", "--sub-track",
        type=int,
        default=None,
        help="Specific subtitle track stream index to extract (optional)"
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary downloaded & intermediate subtitle files"
    )
    return parser.parse_args()

def main():
    print_banner()
    args = parse_args()

    api_key = args.api_key or config.GEMINI_API_KEY
    if not api_key:
        console.print(Panel(
            "[bold red]❌ Missing GEMINI_API_KEY![/bold red]\n\n"
            "To translate subtitles into conversational Hinglish, please provide a Gemini API Key.\n"
            "1. Get a free key at: [link=https://aistudio.google.com/]https://aistudio.google.com/[/link]\n"
            "2. Add to [cyan].env[/cyan] file or pass via [cyan]--api-key 'YOUR_KEY'[/cyan]",
            title="Authentication Error",
            border_style="red"
        ))
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = config.TEMP_DIR / "job_run"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Step 1: Download video via aria2c
        console.rule("[bold yellow]Step 1: Downloading Video[/bold yellow]")
        video_file = download_torrent(args.torrent, temp_dir)

        # Step 2: Extract subtitle track
        console.rule("[bold yellow]Step 2: Subtitle Extraction[/bold yellow]")
        raw_sub_path = temp_dir / f"{video_file.stem}_extracted.ass"
        extracted_sub = extract_subtitle(video_file, raw_sub_path, track_index=args.sub_track)

        # Step 3: Load & format as ASS
        console.rule("[bold yellow]Step 3: ASS Styling & Preparation[/bold yellow]")
        font_size = config.QUALITY_MAP[args.quality]["fontsize"]
        subs = load_and_style_subtitles(extracted_sub, font_size=font_size)

        # Step 4: Translate to Hinglish
        console.rule("[bold yellow]Step 4: AI Hinglish Translation[/bold yellow]")
        hinglish_subs = translate_subtitles_to_hinglish(subs, api_key=api_key)
        final_ass_path = temp_dir / f"{video_file.stem}_hinglish.ass"
        save_ass_subtitles(hinglish_subs, final_ass_path)

        # Step 5: Encode video & burn-in subtitles
        console.rule(f"[bold yellow]Step 5: Burning Subtitles & Encoding to {args.quality}[/bold yellow]")
        final_video_name = f"{video_file.stem}_Hinglish_{args.quality}.mp4"
        final_video_path = out_dir / final_video_name
        burn_subtitles_and_encode(
            video_path=video_file,
            ass_path=final_ass_path,
            output_path=final_video_path,
            quality=args.quality
        )

        # Summary Table
        table = Table(title="🎉 Processing Complete!", border_style="green")
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")
        table.add_row("Original Video", video_file.name)
        table.add_row("Resolution", args.quality)
        table.add_row("Subtitle Type", "Hinglish (.ASS hardcoded)")
        table.add_row("Final Output", str(final_video_path))
        table.add_row("Output Size", f"{final_video_path.stat().st_size / (1024*1024):.1f} MB")
        console.print(table)

    except KeyboardInterrupt:
        console.print("\n[bold red]⚠️ Process cancelled by user.[/bold red]")
        sys.exit(1)
    finally:
        if not args.keep_temp and temp_dir.exists():
            console.print("[dim]Cleaning up temporary workspace...[/dim]")
            shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
