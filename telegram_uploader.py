import os
import sys
import re
import time
import math
import json
import asyncio
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Tuple, List

try:
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
    console = Console()
except ImportError:
    class DummyConsole:
        def print(self, *args, **kwargs):
            import re
            clean = " ".join(str(a) for a in args)
            clean = re.sub(r"\[.*?\]", "", clean)
            print(clean)
    console = DummyConsole()
    Progress = None
    SpinnerColumn = TextColumn = BarColumn = DownloadColumn = TransferSpeedColumn = TimeRemainingColumn = None

import config

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

ROMAN_NUMERALS = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10
}

def clean_anime_title_name(raw_title: str) -> str:
    """Cleans broadcast year tags e.g. (2024), cour tags e.g. 1_2, and trailing punctuation."""
    t = raw_title.strip()
    # Remove cour or split notation like "1_2" or "1/2" at the very end of title (unless Ranma)
    if "ranma" not in t.lower():
        t = re.sub(r'[\s\-_]+(?:1_2|1/2|Part[\s\-_]*\d+|Cour[\s\-_]*\d+)$', '', t, flags=re.IGNORECASE)

    # Remove broadcast/release year in parentheses e.g. (2024), (2023), (2025), [2024]
    t = re.sub(r'[\s\-_]*[\(\[]\d{4}[\)\]]', '', t)

    # Strip trailing dashes, underscores, dots, spaces
    t = re.sub(r'[\s\-_.]+$', '', t).strip()
    return t

def parse_anime_info_from_filename(filename: str) -> Tuple[str, int, int]:
    """
    Accurately extracts (clean_title, season, episode) from typical anime filenames.
    Supports all standard release group patterns:
      '[Erai-raws] Tantei wa Mou Shindeiru S0201 [...]'           -> ('Tantei wa Mou Shindeiru', 2, 1)
      '[Erai-raws] Tantei wa Mou Shindeiru S02 - 01 [...]'       -> ('Tantei wa Mou Shindeiru', 2, 1)
      '[Erai-raws] Tantei wa Mou Shindeiru 1_2 Season 2 - 01 [...]' -> ('Tantei wa Mou Shindeiru', 2, 1)
      '[Erai-raws] Tantei wa Mou Shindeiru (2024) S02 - 01 [...]'  -> ('Tantei wa Mou Shindeiru', 2, 1)
      '[Erai-raws] Tantei wa Mou Shindeiru Season 2 - 01 [...]'   -> ('Tantei wa Mou Shindeiru', 2, 1)
      '[Erai-raws] Tantei wa Mou Shindeiru 02 - 01 [...]'         -> ('Tantei wa Mou Shindeiru', 2, 1)
      '[Erai-raws] Tantei wa Mou Shindeiru II - 01 [...]'         -> ('Tantei wa Mou Shindeiru', 2, 1)
      '[Erai-raws] Tantei wa Mou Shindeiru 01 [...]'              -> ('Tantei wa Mou Shindeiru', 1, 1)
      '[Erai-raws] Ranma 1_2 (2024) 3rd Season - 01 [...]'        -> ('Ranma 1_2', 3, 1)
      '[SubsPlease] Bleach - S03E05 (1080p) [...]'                -> ('Bleach', 3, 5)
    """
    name = Path(filename).stem
    # Remove _Hinglish and anything after it (like _720p, _480p)
    name = re.sub(r"_Hinglish.*$", "", name, flags=re.IGNORECASE)
    # Remove leading release group [Group]
    name = re.sub(r"^\[.*?\]\s*", "", name)

    # Strip all trailing bracket tags from the right (e.g. [720p CR WEB-DL AVC AAC], [MultiSub], [08E85F11])
    while True:
        m = re.search(r"\s*\[[^\]]*\]$", name)
        if m:
            name = name[:m.start()]
        else:
            break

    # Strip trailing parenthesis tags like (1080p), (720p)
    while True:
        m = re.search(r"\s*\(\d{3,4}p[^\)]*\)$", name, re.IGNORECASE)
        if m:
            name = name[:m.start()]
        else:
            break

    name = name.strip()

    season = 1
    episode = 1
    raw_title = name

    # Pattern 1: Check for S01E08, S1E8, S02 - E01, etc.
    s_e = re.search(r"\b[Ss](\d+)\s*[-_ ]*[Ee](\d+)\b", name)
    if s_e:
        season = int(s_e.group(1))
        episode = int(s_e.group(2))
        raw_title = name[:s_e.start()]
        return clean_anime_title_name(raw_title) or name, season, episode

    # Pattern 2: Check for S0201 (S followed by 4 digits: 2 for season, 2 for episode)
    # e.g. S0201 -> Season 2, Episode 1 | S0108 -> Season 1, Episode 8
    s_merged = re.search(r"\b[Ss](\d{2})(\d{2})\b", name)
    if s_merged:
        season = int(s_merged.group(1))
        episode = int(s_merged.group(2))
        raw_title = name[:s_merged.start()]
        return clean_anime_title_name(raw_title) or name, season, episode

    # Pattern 3: Check for S02 - 01 or S2 - 14 (S followed by digits, dash/space, episode)
    s_dash = re.search(r"\b[Ss](\d+)\s*[-_ ]+(?:(?:EP|Ep|Episode)\s*)?(\d+)\b", name)
    if s_dash:
        season = int(s_dash.group(1))
        episode = int(s_dash.group(2))
        raw_title = name[:s_dash.start()]
        return clean_anime_title_name(raw_title) or name, season, episode

    # Pattern 4: Check for explicit Season word: Season 2 - 01, 3rd Season - 01, 2nd Season - 06
    s_word = re.search(r"\b(?:(\d+)(?:st|nd|rd|th)\s+Season|Season\s*(\d+))\s*[-_ ]+(?:(?:EP|Ep|Episode)\s*)?(\d+)\b", name, re.IGNORECASE)
    if s_word:
        s_num = s_word.group(1) or s_word.group(2)
        season = int(s_num)
        episode = int(s_word.group(3))
        raw_title = name[:s_word.start()]
        return clean_anime_title_name(raw_title) or name, season, episode

    # Pattern 5: Check for Roman numerals before episode: Title II - 01, Title III - 01
    roman_m = re.search(r"\b(I|II|III|IV|V|VI|VII|VIII|IX|X)\s*[-_ ]+(?:(?:EP|Ep|Episode)\s*)?(\d+)\b", name)
    if roman_m:
        season = ROMAN_NUMERALS.get(roman_m.group(1), 1)
        episode = int(roman_m.group(2))
        raw_title = name[:roman_m.start()]
        return clean_anime_title_name(raw_title) or name, season, episode

    # Pattern 6: Check for Season Number - Episode Number: Title 02 - 01
    two_nums = re.search(r"\b(\d{1,2})\s*-\s*(\d{1,4})\b$", name)
    if two_nums:
        season = int(two_nums.group(1))
        episode = int(two_nums.group(2))
        raw_title = name[:two_nums.start()]
        return clean_anime_title_name(raw_title) or name, season, episode

    # Pattern 7: Check for standalone Season mention: Title Season 2
    s_only = re.search(r"\b(?:(\d+)(?:st|nd|rd|th)\s+Season|(?:Season|S)\s*(\d+))\b", name, re.IGNORECASE)
    if s_only:
        s_num = s_only.group(1) or s_only.group(2)
        season = int(s_num)
        name = (name[:s_only.start()] + name[s_only.end():]).strip(" -_.")

    # Pattern 8: Check for single Episode at the end: Title - 08 or Title 01
    ep_only = re.search(r"(?:[-_ ]+(?:EP|Ep|Episode)?\s*|^)(\d{1,4})(?:\s*v\d+)?$", name)
    if ep_only:
        episode = int(ep_only.group(1))
        raw_title = name[:ep_only.start()]
    else:
        raw_title = name

    return clean_anime_title_name(raw_title) or Path(filename).stem, season, episode

def extract_year_from_filename(filename: str) -> str:
    """Extracts 4-digit release/broadcast year e.g. (2024), [2023] from filename."""
    m = re.search(r'[\(\[](\d{4})[\)\]]', filename)
    if m:
        val = int(m.group(1))
        if 1960 <= val <= 2035:
            return str(val)
    return ""

def get_ordinal(n: int) -> str:
    """Returns ordinal string e.g. 1st, 2nd, 3rd, 4th."""
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    rem = n % 10
    if rem == 1:
        return f"{n}st"
    elif rem == 2:
        return f"{n}nd"
    elif rem == 3:
        return f"{n}rd"
    return f"{n}th"

def clean_caption_title(title: str) -> str:
    """
    Ensures caption title contains ONLY the pure anime title:
    Strips out:
      - Release years e.g. (2024), [2024], 2024, (1989)
      - Seasons e.g. Season 2, 3rd Season, S02, S2, Part 2, Cour 2, II, III
      - Episodes e.g. S01E08, EP 01, Ep. 01, Episode 01, E01, - 01
      - Redundant trailing colons, dashes, dots, spaces
    """
    t = title.strip()

    # 1. Remove S01E08, S1E8, S02-E01, etc.
    t = re.sub(r'[\s\-_]+[Ss]\d+[\s\-_]*[Ee]\d+\b', '', t)

    # 2. Remove Season markers: Season 2, 3rd Season, S02, Season 02, 2nd Season, etc.
    t = re.sub(r'[\s\-_]+(?:(\d+)(?:st|nd|rd|th)\s+Season|Season\s*\d+|S\d+)\b', '', t, flags=re.IGNORECASE)

    # 3. Remove Roman numeral season markers at the end: II, III, IV, etc.
    t = re.sub(r'[\s\-_]+(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\b$', '', t)

    # 4. Remove Part / Cour markers: Part 1, Part 2, Cour 1, Cour 2 (except Ranma)
    if 'ranma' not in t.lower():
        t = re.sub(r'[\s\-_]+(?:Part|Cour)\s*\d+\b', '', t, flags=re.IGNORECASE)

    # 5. Remove Episode markers: EP 01, Ep. 01, Episode 01, E01, - 01, etc.
    t = re.sub(r'[\s\-_]+(?:(?:EP|Ep|Episode|E)\s*\.?\s*\d+)\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'[\s\-_]+[-–]\s*\d+\b', '', t)
    t = re.sub(r'[\s\-_]+#\d+\b', '', t)

    # 6. Remove 4-digit release year in parentheses, brackets, or standalone: (2024), [2024], (1989)
    t = re.sub(r'[\s\-_]*[\(\[]\s*(?:19\d\d|20\d\d)\s*[\)\]]', '', t)
    t = re.sub(r'[\s\-_]+\b(?:19\d\d|20\d\d)\b', '', t)

    # 7. Remove any remaining trailing standalone episode number e.g. ' - 01' or ' 01'
    t = re.sub(r'[\s\-_]+(?:\d{1,4})$', '', t)

    # 8. If title ended with '1/2' without spaces like 'Ranma1/2', format nicely to 'Ranma 1/2'
    t = re.sub(r'(\w)1/2\b', r'\1 1/2', t)

    # 9. Strip trailing punctuation, colons, dashes, dots, spaces
    t = re.sub(r'[\s\-:._]+$', '', t).strip()
    return t

ANILIST_GRAPHQL_QUERY = """
query ($search: String) {
  Page(page: 1, perPage: 25) {
    media(search: $search, type: ANIME) {
      id
      title {
        english
        romaji
        userPreferred
      }
      coverImage {
        extraLarge
        large
      }
      format
      seasonYear
      startDate { year }
      genres
    }
  }
}
"""

def fetch_anilist_candidates(search_query: str) -> List[Dict]:
    """Queries AniList GraphQL API returning candidate media list."""
    url = "https://graphql.anilist.co"
    data = json.dumps({"query": ANILIST_GRAPHQL_QUERY, "variables": {"search": search_query}}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "DSA-Subber/1.0"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res.get("data", {}).get("Page", {}).get("media", []) or []
    except Exception:
        return []

def fetch_from_anilist(title: str) -> Dict:
    """Queries AniList GraphQL API (backwards compatibility)."""
    cands = fetch_anilist_candidates(title)
    return cands[0] if cands else {}

def score_candidate(candidate: dict, base_title: str, target_season: int, year: str = "") -> float:
    """
    Intelligently scores an AniList candidate based on:
    - Exact season match (+60) vs wrong season penalty (-50)
    - Year match (+40) vs huge historical gap penalty (-30)
    - Format match: TV (+25), ONA (+15) vs MOVIE/OVA/SPECIAL (-25)
    - Title word overlap (+25)
    """
    score = 0.0
    titles = [
        candidate.get("title", {}).get("english") or "",
        candidate.get("title", {}).get("romaji") or "",
        candidate.get("title", {}).get("userPreferred") or ""
    ]
    combined_titles = " ".join(titles).lower()

    # 1. Season matching
    ord_str = get_ordinal(target_season).lower() # e.g. "3rd"
    roman_map = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X"}
    roman = roman_map.get(target_season, "").lower()

    season_keywords = [
        f"season {target_season}",
        f"season{target_season}",
        f"s{target_season:02d}",
        f"s{target_season}",
        f"{ord_str} season",
        f"{ord_str}"
    ]
    if roman:
        season_keywords.append(f" {roman} ")
        season_keywords.append(f" {roman}:")

    has_target_season = any(re.search(rf"\b{re.escape(kw.strip())}\b", combined_titles) for kw in season_keywords)

    if target_season > 1:
        if has_target_season:
            score += 60.0
        else:
            for other_s in range(1, 15):
                if other_s != target_season:
                    other_ord = get_ordinal(other_s).lower()
                    if f"season {other_s}" in combined_titles or f"{other_ord} season" in combined_titles:
                        score -= 50.0
    else:
        for other_s in range(2, 15):
            other_ord = get_ordinal(other_s).lower()
            if f"season {other_s}" in combined_titles or f"{other_ord} season" in combined_titles:
                score -= 60.0
        if "season 1" in combined_titles or "1st season" in combined_titles:
            score += 20.0

    # 2. Year matching
    cand_year = str(candidate.get("seasonYear") or (candidate.get("startDate") or {}).get("year") or "")
    if year:
        if year in combined_titles or cand_year == year:
            score += 40.0
        elif cand_year:
            gap = abs(int(cand_year) - int(year))
            if gap <= 1:
                score += 15.0
            elif gap > 4:
                score -= 30.0

    # 3. Format matching (TV episodes preferred over movies/music/specials)
    fmt = (candidate.get("format") or "").upper()
    if fmt == "TV":
        score += 25.0
    elif fmt in ("ONA", "TV_SHORT"):
        score += 15.0
    elif fmt in ("MOVIE", "OVA", "SPECIAL", "MUSIC"):
        score -= 25.0

    # 4. Title similarity
    clean_base = re.sub(r"[^\w\s]", " ", base_title.lower()).split()
    matched_words = sum(1 for w in clean_base if w in combined_titles)
    score += (matched_words / max(1, len(clean_base))) * 25.0

    return score

def fetch_anime_metadata_and_poster(
    filename: str,
    temp_dir: Path,
    tmdb_api_key: str = ""
) -> Tuple[str, int, int, str, Optional[Path]]:
    """
    Identifies anime English title, Season, Episode, Genres, and downloads
    official HD Anime Poster thumbnail matching the exact season.
    Uses intelligent multi-candidate scoring on AniList.
    Order of operations:
      1. Multi-candidate AniList search ranking by Season, Year, Format (TV), Title overlap.
      2. Exact Season poster selection for video thumbnail.
      3. Fallback to TMDB if AniList doesn't yield title or season poster.
    """
    clean_title, season, episode = parse_anime_info_from_filename(filename)
    year = extract_year_from_filename(filename)
    english_title = clean_title
    genres = "Animation, Anime"
    poster_url = None

    console.print(f"[bold cyan]🔍 Parsed Filename: Title='{clean_title}', Season={season:02d}, Episode={episode:02d}, Year='{year}'[/bold cyan]")

    # Step 1: Query AniList with multiple variations to build a candidate pool
    norm_title = clean_title.replace("_", " ").strip()
    slash_title = clean_title.replace("_", "/").strip()
    ord_str = get_ordinal(season)

    search_queries = []
    if season > 1:
        if year:
            search_queries.append(f"{norm_title} ({year}) {ord_str} Season")
            search_queries.append(f"{norm_title} {ord_str} Season")
            search_queries.append(f"{norm_title} Season {season}")
            search_queries.append(f"{slash_title} {ord_str} Season")
        else:
            search_queries.append(f"{norm_title} {ord_str} Season")
            search_queries.append(f"{norm_title} Season {season}")
            search_queries.append(f"{slash_title} Season {season}")

    if year:
        search_queries.append(f"{norm_title} {year}")
        if slash_title != norm_title:
            search_queries.append(f"{slash_title} {year}")

    search_queries.append(norm_title)
    if slash_title != norm_title:
        search_queries.append(slash_title)

    candidates_by_id = {}
    for q in search_queries:
        if not q:
            continue
        cands = fetch_anilist_candidates(q)
        for c in cands:
            candidates_by_id[c["id"]] = c
        if len(candidates_by_id) >= 20:
            break

    best_candidate = None
    if candidates_by_id:
        # Score candidates for target season poster
        scored = []
        for cid, c in candidates_by_id.items():
            s = score_candidate(c, norm_title, season, year)
            scored.append((s, c))
        scored.sort(key=lambda x: x[0], reverse=True)

        if scored and scored[0][0] > 0:
            best_score, best_candidate = scored[0]
            c_name = best_candidate.get("title", {}).get("romaji") or best_candidate.get("title", {}).get("english")
            console.print(f"[bold green]✨ Best AniList Poster Match (Score: {best_score:.1f}): ID={best_candidate['id']}, Title='{c_name}'[/bold green]")
            cover = best_candidate.get("coverImage", {})
            poster_url = cover.get("extraLarge") or cover.get("large")
            g_list = best_candidate.get("genres", [])
            if g_list:
                genres = ", ".join(g_list[:3])

        # Find base title for caption (English title of main franchise / Season 1)
        base_title_candidate = None
        s1_scored = []
        for cid, c in candidates_by_id.items():
            s1_s = score_candidate(c, norm_title, target_season=1, year="")
            s1_scored.append((s1_s, c))
        s1_scored.sort(key=lambda x: x[0], reverse=True)
        if s1_scored and s1_scored[0][0] > 0:
            base_title_candidate = s1_scored[0][1]

        target_title_cand = base_title_candidate or best_candidate
        if target_title_cand:
            found_eng = (target_title_cand.get("title", {}) or {}).get("english")
            found_rom = (target_title_cand.get("title", {}) or {}).get("romaji")
            found_usr = (target_title_cand.get("title", {}) or {}).get("userPreferred")
            chosen_raw = found_eng or found_rom or found_usr or clean_title
            english_title = clean_caption_title(chosen_raw)
            console.print(f"[bold green]✨ AniList English Caption Title: '{english_title}'[/bold green]")

    # Step 3: Fallback to TMDB if AniList didn't provide English title or poster
    if (not english_title or english_title == clean_title or not poster_url) and tmdb_api_key:
        try:
            console.print("[dim]🔄 Querying TMDB fallback for anime metadata and season poster...[/dim]")
            if tmdb_api_key.startswith("eyJ"):
                tmdb_url = f"https://api.themoviedb.org/3/search/tv?query={urllib.parse.quote(clean_title)}&include_adult=false&language=en-US&page=1"
                headers = {
                    "Authorization": f"Bearer {tmdb_api_key}",
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0"
                }
            else:
                tmdb_url = f"https://api.themoviedb.org/3/search/tv?api_key={tmdb_api_key}&query={urllib.parse.quote(clean_title)}"
                headers = {"User-Agent": "Mozilla/5.0"}

            req = urllib.request.Request(tmdb_url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as r:
                tmdb_data = json.loads(r.read().decode("utf-8"))
                results = tmdb_data.get("results", [])
                if results:
                    first = results[0]
                    tv_id = first.get("id")
                    if not english_title or english_title == clean_title:
                        english_title = first.get("name") or english_title

                    # If we still need poster, check specific season on TMDB
                    if not poster_url and tv_id:
                        if season > 1:
                            try:
                                if tmdb_api_key.startswith("eyJ"):
                                    s_url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{season}?language=en-US"
                                    s_req = urllib.request.Request(s_url, headers=headers)
                                else:
                                    s_url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{season}?api_key={tmdb_api_key}"
                                    s_req = urllib.request.Request(s_url, headers=headers)
                                with urllib.request.urlopen(s_req, timeout=5) as s_resp:
                                    s_data = json.loads(s_resp.read().decode("utf-8"))
                                    if s_data.get("poster_path"):
                                        poster_url = f"https://image.tmdb.org/t/p/w500{s_data.get('poster_path')}"
                                        console.print(f"[bold green]🖼️ Found Season {season:02d} poster on TMDB![/bold green]")
                            except Exception:
                                pass

                        if not poster_url and first.get("poster_path"):
                            poster_url = f"https://image.tmdb.org/t/p/w500{first.get('poster_path')}"
        except Exception as e:
            console.print(f"[dim]⚠️ TMDB fallback notice: {e}[/dim]")

    # Step 4: Download and scale poster for Telegram thumbnail
    poster_thumb_path = None
    if poster_url:
        try:
            raw_poster = temp_dir / "anime_poster_raw.jpg"
            out_thumb = temp_dir / f"{Path(filename).stem}_poster_thumb.jpg"
            req = urllib.request.Request(poster_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp, open(raw_poster, "wb") as f:
                f.write(resp.read())

            cmd = [
                "ffmpeg", "-y",
                "-i", str(raw_poster.resolve()),
                "-vf", "scale=320:-1",
                "-q:v", "2",
                str(out_thumb.resolve())
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            if out_thumb.exists() and out_thumb.stat().st_size > 0:
                poster_thumb_path = out_thumb
                console.print(f"[bold green]🖼️ Anime Season {season:02d} Poster thumbnail ready ({poster_thumb_path.stat().st_size // 1024} KB)[/bold green]")
        except Exception as e:
            console.print(f"[dim]⚠️ Poster download notice: {e}[/dim]")

    return english_title, season, episode, genres, poster_thumb_path

def make_text_progress_bar(percentage: float, total_blocks: int = 10) -> str:
    """Generates a text-based progress bar for Telegram messages (e.g. [█████░░░░░])."""
    filled = int(round(total_blocks * (percentage / 100)))
    filled = max(0, min(total_blocks, filled))
    return "█" * filled + "░" * (total_blocks - filled)

def build_caption(
    title: str,
    quality: str,
    season: int = 1,
    episode: int = 1
) -> str:
    """
    Builds the exact customized HTML caption for Telegram channel post:
    - Pure anime title row (NO release year, NO season, NO episode in title)
    - Exact quality burned (e.g. 720P)
    - 2-digit Season and Episode on dedicated season row
    - All text formatted in bold
    - Powered by link to @DarkSoulAcademy
    """
    clean_q = quality.upper()
    if not clean_q.endswith("P"):
        clean_q += "P"

    pure_title = clean_caption_title(title)

    caption = (
        f"<b>» {pure_title} •</b>\n"
        f"<b>➖➖➖➖➖➖➖➖➖➖➖➖</b>\n"
        f"<b>‣ Language: Jap (Hindi Sub)</b>\n"
        f"<b>‣ Quality: {clean_q}</b>\n"
        f"<b>‣ Season: {season:02d} | ‣ EP - {episode:02d}</b>\n"
        f"<b>➖➖➖➖➖➖➖➖➖➖➖➖</b>\n"
        f"<b>» Powered by ~ ♡<a href=\"https://t.me/DarkSoulAcademy\">DαɾƙSσυʅAƈαԃҽɱყ</a>✦</b>"
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

    # Fetch official English anime title & HD poster from TMDB / AniList
    console.print("[bold cyan]🔍 Fetching official English title & HD poster from TMDB/AniList...[/bold cyan]")
    eng_title, season, episode, genres, poster_thumb = fetch_anime_metadata_and_poster(
        video_path.name,
        config.TEMP_DIR,
        tmdb_api_key=getattr(config, "TMDB_API_KEY", "")
    )
    console.print(f"[bold green]✨ Identified Anime: {eng_title} (S{season:02d}E{episode:02d})[/bold green]")

    caption = build_caption(
        title=eng_title,
        quality=quality,
        season=season,
        episode=episode
    )

    # Use HD Anime Poster thumbnail if available, otherwise fallback to video frame
    if poster_thumb and poster_thumb.exists():
        thumb = poster_thumb
        console.print("[bold green]🖼️ Applied official Anime Poster as video thumbnail![/bold green]")
    else:
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

    console.print(f"[bold yellow]📤 Uploading '{eng_title}' ({file_size_mb:.1f} MB) to Telegram...[/bold yellow]")
    try:
        from notifier import notifier
        notifier.start_upload(eng_title, file_size_mb)
    except Exception:
        pass

    # Send initial upload start message to Owner
    owner_id = config.TELEGRAM_OWNER_ID
    owner_msg = None
    if owner_id:
        try:
            owner_msg = await client.send_message(
                owner_id,
                f"🚀 <b>DSA Subber: Upload Started!</b>\n\n"
                f"🎬 <b>Title:</b> {eng_title}\n"
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
            f"🎬 <b>{eng_title}</b>\n\n"
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
            if total > 0:
                pct = (current / total) * 100
                curr_mb = current / (1024 * 1024)
                tot_mb = total / (1024 * 1024)
                elapsed = max(0.1, time.time() - start_time)
                speed_mb = curr_mb / elapsed
                try:
                    from notifier import notifier
                    notifier.update_upload_progress(percent=pct, speed_str=f"{speed_mb:.1f} MB/s", uploaded_mb=curr_mb, total_mb=tot_mb)
                except Exception:
                    pass

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
            try:
                from notifier import notifier
                notifier.finish_upload(eng_title, channel_title=str(chat_id))
            except Exception:
                pass
        except Exception as e:
            console.print(f"[bold red]❌ Video upload failed: {e}[/bold red]")
            await client.disconnect()
            return False

    # Send final success status to Owner
    if owner_msg:
        try:
            await owner_msg.edit(
                f"🎉 <b>Video Upload Complete!</b>\n\n"
                f"🎬 <b>Title:</b> {eng_title}\n"
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
                f"🎬 <b>{eng_title}</b> (S{season:02d}E{episode:02d})\n\n"
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

def send_pipeline_start_notification(
    task_info: str,
    quality: str = "720p",
    save_mode: str = "both",
    queue_info: str = ""
) -> None:
    """Initializes the live tracking notification for Owner ID."""
    try:
        from notifier import notifier
        clean_t, s_num, ep_num = parse_anime_info_from_filename(task_info)
        disp = f"{clean_t} (S{s_num:02d}E{ep_num:02d})"
        notifier.start_pipeline(task_name=disp, quality=quality, save_mode=save_mode, queue_info=queue_info)
    except Exception as e:
        console.print(f"[dim]⚠️ Could not initialize live tracker: {e}[/dim]")
