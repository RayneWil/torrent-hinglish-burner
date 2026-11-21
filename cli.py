#!/usr/bin/env python3
"""
Torrent to Hinglish Burner CLI
Automated pipeline to download torrents, translate subtitles to Hinglish (.ass), and burn them into 480p/720p video.
Supports multi-key pool rotation (30 lines/request, auto-shift after 20 requests or quota limits).
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
from ui import parse_links_from_input

console = Console()

BANNER = """
[bold cyan]╔═══════════════════════════════════════════════════════╗
║         🔥 TORRENT TO HINGLISH BURNER CLI 🔥          ║
║   Magnet ➔ Hinglish (.ASS) ➔ 480p/720p/1080p Hardcode ║
║        [Multi-API Key Pool & Auto-Rotation Active]    ║
╚═══════════════════════════════════════════════════════╝[/bold cyan]
"""

def print_banner():
    console.print(BANNER)

def parse_args():
    parser = argparse.ArgumentParser(
        description="Download torrent, translate subtitles to Hinglish (.ass) & burn into 480p/720p/1080p video."
    )
    parser.add_argument(
        "-t", "--torrent",
        type=str,
        nargs="*",
        default=None,
        help="One or more Magnet URIs / .torrent file paths / text file path with links (Leave empty to launch Interactive UI)"
    )
    parser.add_argument(
        "-q", "--quality",
        type=str,
        choices=["480p", "720p", "1080p", "all"],
        default="720p",
        help="Target output video quality (480p, 720p, 1080p, or 'all'). Default: 720p"
    )
    parser.add_argument(
        "-k", "--api-keys",
        type=str,
        default=None,
        help="Comma-separated Gemini API Keys for rotation (e.g. 'key1,key2,key3')"
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default=str(config.VIDEO_OUTPUT_DIR),
        help="Directory to save final processed video"
    )
    parser.add_argument(
        "-s", "--sub-track",
        type=int,
        default=None,
        help="Specific subtitle track stream index to extract (optional)"
    )
    parser.add_argument(
        "-d", "--save-mode",
        type=str,
        choices=["both", "telegram", "storage"],
        default=config.SAVE_MODE,
        help="Saving destination: 'both' (Storage + Telegram), 'telegram' (Telegram only, 0 MB disk used), or 'storage' (Storage only, no upload). Default: both"
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary downloaded & intermediate subtitle files"
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Launch interactive Terminal UI"
    )
    return parser.parse_args()

def main():
    args = parse_args()

    # Notify Owner ID that DSA Subber service has been started
    try:
        from notifier import notifier
        notifier.notify_service_start(cmd_args=sys.argv[1:])
    except Exception:
        pass

    # If no torrent link provided or --ui flag is passed, launch interactive UI
    if args.ui or not args.torrent:
        from ui import main_menu
        main_menu()
        return

    raw_list = args.torrent if isinstance(args.torrent, list) else [args.torrent]
    queue = []
    for item in raw_list:
        queue.extend(parse_links_from_input(item))

    if not queue:
        from ui import main_menu
        main_menu()
        return

    print_banner()

    # Determine API keys list
    if args.api_keys:
        api_keys = [k.strip() for k in args.api_keys.split(",") if k.strip()]
    else:
        api_keys = config.GEMINI_API_KEYS

    if not api_keys:
        console.print(Panel(
            "[bold red]❌ Missing GEMINI_API_KEYS![/bold red]\n\n"
            "To translate subtitles into conversational Hinglish, please provide Gemini API Key(s).\n"
            "1. Add keys in [cyan].env[/cyan] as: [green]GEMINI_API_KEYS=key1,key2,key3,key4,key5[/green]\n"
            "2. Or pass via CLI: [cyan]--api-keys 'key1,key2,key3'[/cyan]",
            title="Authentication Error",
            border_style="red"
        ))
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    save_mode = args.save_mode.strip().lower()
    total_q = len(queue)
    queue_results = []

    for q_idx, torrent_link in enumerate(queue, 1):
        q_label = f"[{q_idx}/{total_q}]" if total_q > 1 else ""
        temp_dir = config.TEMP_DIR / f"cli_job_{int(time.time())}_{q_idx}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Send start notification to Owner
            try:
                from telegram_uploader import send_pipeline_start_notification
                send_pipeline_start_notification(
                    torrent_link,
                    quality=args.quality,
                    save_mode=save_mode,
                    queue_info=f"Task {q_idx}/{total_q}" if total_q > 1 else ""
                )
            except Exception:
                pass

            # Step 1: Download video via aria2c
            console.rule(f"[bold yellow]Step 1: Downloading Video {q_label}[/bold yellow]")
            video_file = download_torrent(torrent_link, temp_dir)

            # Step 2: Extract subtitle track
            console.rule(f"[bold yellow]Step 2: Subtitle Extraction {q_label}[/bold yellow]")
            raw_sub_path = temp_dir / f"{video_file.stem}_extracted.ass"
            extracted_sub = extract_subtitle(video_file, raw_sub_path, track_index=args.sub_track)

            # Step 3: Load & format as ASS
            console.rule(f"[bold yellow]Step 3: ASS Styling & Preparation {q_label}[/bold yellow]")
            font_size = config.QUALITY_MAP.get(args.quality, config.QUALITY_MAP["720p"])["fontsize"]
            subs = load_and_style_subtitles(extracted_sub, font_size=font_size)

            # Step 4: Translate to Hinglish (20 lines/request, auto-shift after 20 requests)
            console.rule(f"[bold yellow]Step 4: AI Hinglish Translation (Multi-Key Rotation) {q_label}[/bold yellow]")
            hinglish_subs = translate_subtitles_to_hinglish(
                subs,
                api_keys=api_keys,
                batch_size=20,
                max_requests_per_key=20
            )

            if save_mode in ("both", "storage"):
                final_ass_path = config.SUBTITLE_OUTPUT_DIR / f"{video_file.stem}_Hinglish.ass"
                save_ass_subtitles(hinglish_subs, final_ass_path)
                console.print(f"[bold green]💾 Subtitle saved to: {final_ass_path}[/bold green]")
            else:
                final_ass_path = temp_dir / f"{video_file.stem}_Hinglish.ass"
                save_ass_subtitles(hinglish_subs, final_ass_path)
                console.print(f"[bold cyan]📄 Subtitle prepared for Telegram upload (temporary)[/bold cyan]")

            # Step 5: Encode video & burn-in subtitles
            target_qualities = ["480p", "720p", "1080p"] if args.quality == "all" else [args.quality]
            produced_videos = []

            for q in target_qualities:
                console.rule(f"[bold yellow]Step 5: Burning Subtitles & Encoding to {q} {q_label}[/bold yellow]")
                final_video_name = f"{video_file.stem}_Hinglish_{q}.mp4"
                if save_mode in ("both", "storage"):
                    final_video_path = out_dir / final_video_name
                else:
                    final_video_path = temp_dir / final_video_name

                burn_subtitles_and_encode(
                    video_path=video_file,
                    ass_path=final_ass_path,
                    output_path=final_video_path,
                    quality=q
                )
                file_size_mb = final_video_path.stat().st_size / (1024 * 1024)
                produced_videos.append((q, final_video_path, file_size_mb))

                # Step 6: Upload to Telegram Channel (if enabled)
                if save_mode in ("both", "telegram") and config.TELEGRAM_AUTO_UPLOAD:
                    console.rule(f"[bold cyan]Step 6: Uploading {q} to Telegram Channel {q_label}[/bold cyan]")
                    from telegram_uploader import upload_to_telegram
                    upload_to_telegram(final_video_path, final_ass_path, quality=q)
                elif save_mode == "storage":
                    console.print(f"[dim]ℹ️ Skipping Telegram upload (Save mode: Storage Only)[/dim]")

                # Clean up temp video in telegram-only mode
                if save_mode == "telegram" and not args.keep_temp:
                    try:
                        final_video_path.unlink(missing_ok=True)
                        console.print(f"[dim]🗑️ Cleaned up temporary {q} video to preserve device storage.[/dim]")
                    except Exception:
                        pass

            # If storage-only mode, notify owner
            if save_mode == "storage":
                try:
                    from notifier import notifier
                    from telegram_uploader import parse_anime_info_from_filename
                    clean_t, s_num, ep_num = parse_anime_info_from_filename(video_file.name)
                    notifier.finish_storage_only(
                        f"{clean_t} (S{s_num:02d}E{ep_num:02d})",
                        str(out_dir)
                    )
                except Exception:
                    pass

            queue_results.append((True, video_file.name, produced_videos))

            # Per-task summary table
            table = Table(title=f"🎉 Processing Complete {q_label}!", border_style="green")
            table.add_column("Property", style="cyan", no_wrap=True)
            table.add_column("Value", style="magenta")
            table.add_row("Original Video", video_file.name)
            table.add_row("Resolution", "All (480p, 720p, 1080p)" if args.quality == "all" else args.quality)
            table.add_row("Subtitle Type", "Hinglish (.ASS hardcoded)")
            table.add_row("Saving Destination", save_mode.upper())
            for q, f_path, size_mb in produced_videos:
                status = "Saved & Uploaded" if save_mode == "both" else ("Uploaded (Temp cleaned)" if save_mode == "telegram" else "Saved in Storage")
                table.add_row(f"Output ({q})", f"{f_path.name} ({size_mb:.1f} MB) [{status}]")
            console.print(table)

        except KeyboardInterrupt:
            console.print("\n[bold red]⚠️ Process cancelled by user.[/bold red]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[bold red]❌ Error processing task {q_idx}: {e}[/bold red]")
            queue_results.append((False, str(torrent_link)[:40], []))
        finally:
            if not args.keep_temp and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

        if q_idx < total_q:
            console.print(f"\n[bold green]✅ Task [{q_idx}/{total_q}] finished! Starting next queued task in 3 seconds...[/bold green]\n")
            import time
            time.sleep(3)

    if total_q > 1:
        try:
            from notifier import notifier
            completed = sum(1 for r in queue_results if r[0])
            notifier.finish_queue_summary(total_q, completed, total_q - completed)
        except Exception:
            pass

if __name__ == "__main__":
    main()
