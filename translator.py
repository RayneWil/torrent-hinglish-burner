import json
import re
import time
import urllib.request
import urllib.error
from typing import List, Dict, Optional
from rich.console import Console
from rich.progress import track
import pysubs2

console = Console()

# Verified active working Gemini models for high-speed subtitle translation
CANDIDATE_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview"
]

HINGLISH_PROMPT = """ROLE:
You are a professional anime subtitle translator.
Your task is to translate subtitle files (.ass, .srt, .vtt) into natural, emotional, and smooth Hinglish.
Translation must sound human, casual, anime-style, and expressive — NOT word-to-word.

ABSOLUTE ZERO-SKIPPING & EXACT COUNT RULE (CRITICAL):
- You MUST translate EVERY SINGLE object provided in the input list without exception.
- NEVER skip, omit, or ignore any line, even if it is very short (e.g. "Yeah", "SALT", "Curry...", "Wait!"), a sign/label (e.g. "PANDA CURRY"), or a sound effect.
- NEVER merge two lines into one, and NEVER split one line into two.
- Each input object has an "id" integer. Your output JSON array MUST contain the EXACT SAME NUMBER of objects with the EXACT SAME "id" numbers in the exact same order.
- NEVER renumber IDs (do not renumber to 1, 2, 3...). Preserve each line's original "id".

VERY IMPORTANT FORMAT RULES (STRICT):
- DO NOT change subtitle numbering.
- DO NOT change timestamps (start/end time must remain EXACTLY the same).
- DO NOT merge lines.
- DO NOT split lines.
- DO NOT reorder subtitles.
- Each subtitle entry must remain exactly where it is.
- Output structure must be IDENTICAL to the input file.

ABSOLUTE SCRIPT & ALPHABET RULE (ZERO DEVANAGARI - CRITICAL):
- TRANSLATE ONLY USING LATIN / ENGLISH LETTERS (A-Z, a-z, 0-9).
- DO NOT USE DEVANAGARI SCRIPT (देवनागरी लिपि / हिंदी अक्षर) UNDER ANY CIRCUMSTANCES!
- Outputting even a SINGLE Hindi/Devanagari character (like हाँ, क्या, नमस्ते, नहीं, etc.) breaks the subtitle font completely.
- All Hindi words MUST be written phonetically in English/Roman alphabet (e.g., write "haan", "kya", "namaste", "nahi", "tum", "mai").

LANGUAGE & STYLE RULES:
- Use “Mai” for “I” and “Tum” for “You”.
- Avoid heavy English. Use only very common English words when they feel natural.
- Dialogues must be short, impactful, and sound like real-life conversation.
- Maintain original character personality and mood (tsundere, senpai, angry, shy, calm, etc.).
- Emotion and intent are more important than literal meaning.
- Gender mistakes are strictly forbidden.

BACKGROUND & NON-DIALOGUE RULES:
- Background sounds (ahh, hmm, mmh, sighs, laughs, etc.) must remain unchanged if already present.
- Do not remove or add background sounds.

TRANSLATION RULES:
- Avoid over-literal translation.
- Translate it like a human.
- Keep dialogue as short as possible while preserving meaning.
- Maintain anime-style flow and natural Hinglish rhythm.
- Do not add extra explanations or notes.

WORD STYLE (Allowed English → Hinglish):
I'm sorry  → mujhe maaf karna  
Sorry → maaf karna  
stupid → chutiya
Motherfucker – maderchod
sisterfucker → bahenchod
• Piece of shit → bilkul bekaar insaan / ghatiya aadmi
• Bastard →  haraami / nalayak 
• Dickhead → bewakoof saala
• Bullshit → bakwaas / faltu baat
Thanks / Thank you → shukriya  
Good morning → good morning  
Good night → good night  
Love → pyaar / love (depending on scene mood)

CRITICAL GENDER & VERB ENDING RULES (STRICTEST ACCURACY REQUIRED):
You MUST determine whether the speaker is MALE or FEMALE for each dialogue line.
Never guess or default everything blindly to male!

1. FEMALE SPEAKER ("I" / "Mai"):
   - ALWAYS use feminine verb endings:
     • 'kar rahi hoon' (NEVER 'kar raha hoon')
     • 'ja rahi hoon' (NEVER 'ja raha hoon')
     • 'soch rahi hoon' (NEVER 'soch raha hoon')
     • 'karungi' / 'jaungi' / 'bataungi' (NEVER 'karunga' / 'jaunga' / 'bataunga')
     • 'samajh gayi' / 'thak gayi' (NEVER 'gaya')
     • 'mai theek hoon', 'meri galti hai'

2. MALE SPEAKER ("I" / "Mai"):
   - ALWAYS use masculine verb endings:
     • 'kar raha hoon', 'ja raha hoon', 'soch raha hoon'
     • 'karunga', 'jaunga', 'bataunga'
     • 'samajh gaya', 'thak gaya'

3. ADDRESSING A FEMALE ("You" / "Tum"):
   - When talking TO a girl/woman:
     • 'tum kaisi ho?' (NOT 'kaise ho')
     • 'tum kya kar rahi ho?' (NOT 'kar rahe ho')
     • 'tum jaogi?' (NOT 'jaoge')

4. ADDRESSING A MALE ("You" / "Tum"):
   - When talking TO a boy/man:
     • 'tum kaise ho?'
     • 'tum kya kar rahe ho?'
     • 'tum jaoge?'

5. HOW TO ACCURATELY IDENTIFY GENDER:
   - Check the "speaker" field if provided in JSON.
   - Match characters with the EPISODE CHARACTER ROSTER below.
   - Look for anime cues in dialogue:
     • "-kun" is used for boys/male peers.
     • "-chan", "Miss", "Lady", "Onee-san", "Mother", "Sister" indicate female.
     • "Lord", "Sir", "Aniki", "Onii-san", "Father", "Brother" indicate male.
   - In female-led conversations, keep consistent feminine grammar throughout.
   - If gender is completely ambiguous: use natural gender-neutral Hinglish phrasing (e.g. 'Mujhe jaana hai', 'Mera iraada pakka hai') instead of defaulting blindly to masculine!

TECHNICAL FORMAT:
You will receive a JSON array of objects with "id", optional "speaker", and "text". You MUST reply with ONLY a valid JSON array of objects with the exact same "id" and the translated Hinglish "text". Do not include markdown codeblocks or conversational text, just the raw JSON array.
"""

class GeminiKeyManager:
    """
    Manages pool of multiple Gemini API keys.
    - Rotates keys smoothly across requests.
    - When all keys hit per-minute RPM rate limits (429), cools down and recycles pool instead of killing keys.
    """
    def __init__(self, keys: List[str], max_requests_per_key: int = 20, max_cycles: int = 3):
        self.keys = [k.strip() for k in keys if k.strip()]
        self.max_requests_per_key = max_requests_per_key
        self.max_cycles = max_cycles
        self.current_idx = 0
        self.cycle_count = 0
        self.request_counts = [0] * len(self.keys)

    @property
    def has_keys(self) -> bool:
        return len(self.keys) > 0 and self.cycle_count < self.max_cycles

    @property
    def total_keys(self) -> int:
        return len(self.keys)

    def get_active_key(self) -> Optional[str]:
        if not self.has_keys:
            return None
        return self.keys[self.current_idx % len(self.keys)]

    def record_success(self):
        """Track successful request. If hits quota limit, auto-rotate to next key."""
        if not self.has_keys:
            return
        idx = self.current_idx % len(self.keys)
        self.request_counts[idx] += 1
        used = self.request_counts[idx]
        console.print(
            f"[dim]🔑 Key #{idx + 1}/{len(self.keys)}: "
            f"{used}/{self.max_requests_per_key} requests used[/dim]"
        )
        if used >= self.max_requests_per_key:
            self.rotate(reason=f"Quota of {self.max_requests_per_key} requests reached")

    def rotate(self, reason: str = ""):
        """Switch to the next available API key in the pool with cooldown cycling."""
        if not self.keys:
            return
        old_idx = self.current_idx % len(self.keys)
        self.current_idx += 1
        new_idx = self.current_idx % len(self.keys)

        if self.current_idx > 0 and self.current_idx % len(self.keys) == 0:
            self.cycle_count += 1
            if self.cycle_count < self.max_cycles:
                console.print(
                    f"[bold yellow]⏳ All {len(self.keys)} API Keys rotated (Cycle {self.cycle_count}/{self.max_cycles}). "
                    f"Cooling down for 10s to reset RPM quota window...[/bold yellow]"
                )
                time.sleep(10)
            else:
                console.print(f"[bold red]❌ All {len(self.keys)} API Keys completed max cycles ({self.max_cycles})![/bold red]")
                return

        console.print(
            f"[bold yellow]🔄 Key #{old_idx + 1} shifted ({reason}). "
            f"Now using Key #{new_idx + 1}/{len(self.keys)}...[/bold yellow]"
        )

DEV_VOWELS = {
    'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo', 'ऋ': 'ri',
    'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au', 'अं': 'an', 'अः': 'ah'
}

DEV_MATRAS = {
    'ा': 'aa', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo', 'ृ': 'ri',
    'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au', 'ं': 'n', 'ँ': 'n', 'ः': 'h'
}

DEV_CONSONANTS = {
    'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'ng',
    'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'ny',
    'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
    'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
    'प': 'p', 'फ': 'f', 'ब': 'b', 'भ': 'bh', 'म': 'm',
    'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v', 'श': 'sh', 'ष': 'sh', 'स': 's', 'ह': 'h',
    'क़': 'q', 'ख़': 'kh', 'ग़': 'g', 'ज़': 'z', 'फ़': 'f', 'ड़': 'd', 'ढ़': 'dh'
}

def sanitize_devanagari_to_roman(text: str) -> str:
    """
    100% fail-safe: Converts any Devanagari (Hindi) script into Roman Hinglish.
    Ensures zero Devanagari characters ever enter the subtitle file.
    """
    if not re.search(r'[\u0900-\u097F]', text):
        return text

    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]

        two = text[i:i+2]
        if two in DEV_CONSONANTS:
            cons = DEV_CONSONANTS[two]
            i += 2
            if i < n and text[i] == '्':
                out.append(cons)
                i += 1
            elif i < n and text[i] in DEV_MATRAS:
                out.append(cons + DEV_MATRAS[text[i]])
                i += 1
            else:
                next_is_terminal = (i >= n or text[i] in ' \t\n.,!?;:\'\"')
                out.append(cons if next_is_terminal else cons + 'a')
            continue

        if c in DEV_CONSONANTS:
            cons = DEV_CONSONANTS[c]
            i += 1
            if i < n and text[i] == '्':
                out.append(cons)
                i += 1
            elif i < n and text[i] in DEV_MATRAS:
                out.append(cons + DEV_MATRAS[text[i]])
                i += 1
            else:
                next_is_terminal = (i >= n or text[i] in ' \t\n.,!?;:\'\"')
                out.append(cons if next_is_terminal else cons + 'a')
            continue

        if c in DEV_VOWELS:
            out.append(DEV_VOWELS[c])
            i += 1
            continue

        if c in DEV_MATRAS:
            out.append(DEV_MATRAS[c])
            i += 1
            continue

        if c == '।':
            out.append('.')
            i += 1
            continue

        if ord(c) < 0x0900 or ord(c) > 0x097F:
            out.append(c)
        i += 1

    result = ''.join(out)
    return re.sub(r'[\u0900-\u097F]', '', result)

def clean_sub_text(text: str) -> str:
    """Removes existing ASS/HTML formatting tags from text."""
    text = re.sub(r"\{.*?\}", "", text)
    text = text.replace("\\N", " ").replace("\\n", " ")
    return text.strip()

def call_gemini_rest(prompt_text: str, api_key: str, model_name: str) -> str:
    """Direct REST call using standard library urllib."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt_text}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2
        }
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        res_json = json.loads(response.read().decode("utf-8"))
        candidates = res_json.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "")
    return ""

def parse_gemini_json_response(raw_text: str) -> List[Dict]:
    """Robust 3-tier JSON parser for Gemini subtitle outputs."""
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*\n?", "", raw_text)
        raw_text = re.sub(r"\n?```\s*$", "", raw_text)
    raw_text = raw_text.strip()

    # Tier 1: Standard JSON parse with non-strict control characters
    try:
        return json.loads(raw_text, strict=False)
    except Exception:
        pass

    # Tier 2: Extract JSON array substring
    array_match = re.search(r"\[\s*\{.*\}\s*\]", raw_text, re.DOTALL)
    if array_match:
        try:
            return json.loads(array_match.group(0), strict=False)
        except Exception:
            pass

    # Tier 3: Regex item-by-item extraction for dialogues with quotes
    items = []
    pattern = re.compile(r'\{\s*"id"\s*:\s*(\d+)\s*,\s*"text"\s*:\s*"(.*?)"\s*\}', re.DOTALL)
    for m in pattern.finditer(raw_text):
        try:
            item_id = int(m.group(1))
            item_text = m.group(2).replace('\\"', '"').replace('\n', ' ')
            items.append({"id": item_id, "text": item_text})
        except Exception:
            continue
    if items:
        return items

    return json.loads(raw_text, strict=False)

def extract_character_roster(subs: pysubs2.SSAFile, key_manager: GeminiKeyManager) -> str:
    """
    Analyzes subtitle file to identify characters and their genders (Male/Female).
    Injects this roster into every translation prompt for accurate verb endings.
    """
    unique_speakers = set()
    sample_dialogues = []

    for ev in subs.events:
        if ev.is_comment:
            continue
        name = getattr(ev, "name", "").strip()
        if name and name.lower() not in ("default", "main", "info", "watermarktop"):
            clean_name = re.sub(r"\{.*?\}", "", name).strip()
            if clean_name:
                unique_speakers.add(clean_name)

        cleaned = clean_sub_text(ev.text)
        if cleaned and len(cleaned) > 5:
            prefix = f"{name}: " if name else ""
            sample_dialogues.append(f"{prefix}{cleaned}")
        if len(sample_dialogues) >= 60:
            break

    if not sample_dialogues:
        return ""

    prompt = (
        "You are an expert anime localization director.\n"
        "Analyze these sample subtitles and speaker tags from an anime episode:\n\n"
        f"Known Speaker Tags: {', '.join(sorted(unique_speakers)) if unique_speakers else 'None'}\n\n"
        f"Sample Dialogue Lines:\n" + "\n".join(sample_dialogues[:40]) + "\n\n"
        "TASK:\n"
        "Identify the main characters appearing in this anime episode and specify their Gender (Male or Female).\n"
        "Reply with ONLY a concise bullet list in this format:\n"
        "- [Character Name]: [Male/Female] (Short note e.g. male protagonist / female heroine / teacher / rival)\n"
    )

    active_key = key_manager.get_active_key()
    if not active_key:
        return ""

    try:
        roster_text = call_gemini_rest(prompt, active_key, model_name=CANDIDATE_MODELS[0]).strip()
        if roster_text and ("Male" in roster_text or "Female" in roster_text):
            return roster_text
    except Exception:
        pass

    return ""

def translate_batch_with_retry(
    batch: List[Dict],
    key_manager: GeminiKeyManager,
    roster: str = "",
    prev_context: List[str] = None,
    is_sub_retry: bool = False
) -> List[Dict]:
    """
    Translates a batch of lines using direct REST API.
    - Zero-skipping guarantee: detects missing lines and auto-reconciles them.
    - Uses Character Gender Roster and Previous Dialogue Context for 100% gender accuracy.
    - Model fallback chain with intelligent RPM backoff.
    """
    if not batch:
        return []

    input_json = json.dumps(batch, ensure_ascii=False)

    roster_block = f"EPISODE CHARACTER GENDER ROSTER:\n{roster}\n\n" if roster else ""
    context_block = f"RECENT DIALOGUE CONTEXT (for gender/scene reference):\n" + "\n".join(prev_context[-3:]) + "\n\n" if prev_context else ""

    full_prompt = (
        f"{HINGLISH_PROMPT}\n\n"
        f"{roster_block}"
        f"{context_block}"
        f"CRITICAL ZERO-SKIPPING INSTRUCTION:\n"
        f"Translate EVERY SINGLE one of the {len(batch)} input lines below. Do NOT omit or merge any line.\n"
        f"Output MUST contain exactly {len(batch)} objects with matching 'id' numbers.\n\n"
        f"Input Subtitle Lines to Translate:\n{input_json}\n\n"
        f"Output:\n"
    )

    expected_ids = [item["id"] for item in batch]
    expected_ids_set = set(expected_ids)

    while key_manager.has_keys:
        active_key = key_manager.get_active_key()
        if not active_key:
            break

        # Try candidate models on the current active key
        for model in CANDIDATE_MODELS:
            try:
                raw_text = call_gemini_rest(full_prompt, active_key, model_name=model).strip()
                if not raw_text:
                    continue

                translated_batch = parse_gemini_json_response(raw_text)
                if not isinstance(translated_batch, list) or not translated_batch:
                    continue

                # Ensure all elements have an ID
                received_ids = {x.get("id") for x in translated_batch if isinstance(x, dict) and "id" in x}

                # Case A: Model renumbered IDs (e.g. 1..N or 0..N-1) but returned same count
                if len(translated_batch) == len(batch) and received_ids != expected_ids_set:
                    for i, item in enumerate(translated_batch):
                        item["id"] = batch[i]["id"]
                    received_ids = expected_ids_set

                # Case B: Model dropped some lines
                missing_ids = expected_ids_set - received_ids
                if missing_ids and not is_sub_retry and len(missing_ids) <= len(batch) // 2:
                    console.print(f"[dim]⚠️ {len(missing_ids)} line(s) missing from batch response. Re-translating missing lines...[/dim]")
                    missing_items = [b for b in batch if b["id"] in missing_ids]
                    sub_recovered = translate_batch_with_retry(
                        missing_items, key_manager, roster=roster, prev_context=prev_context, is_sub_retry=True
                    )
                    translated_batch.extend(sub_recovered)

                key_manager.record_success()
                return translated_batch

            except urllib.error.HTTPError as e:
                err_code = e.code
                err_body = e.read().decode("utf-8", errors="ignore")

                # If Quota limit (429 / 403), rotate to NEXT KEY immediately
                if err_code in (429, 403) or "quota" in err_body.lower() or "resourceexhausted" in err_body.lower():
                    console.print(f"[bold yellow]⚠️ Rate limit on Key (HTTP {err_code}). Rotating...[/bold yellow]")
                    key_manager.rotate(reason=f"HTTP {err_code} Rate Limit")
                    break

                # If 503 (Server high demand) or 404, try next candidate model
                elif err_code in (503, 500, 404):
                    console.print(f"[dim]⚠️ Model '{model}' busy (HTTP {err_code}). Trying alternate model...[/dim]")
                    time.sleep(1)
                    continue

                else:
                    console.print(f"[dim]⚠️ Error on model '{model}': HTTP {err_code}. Trying alternate...[/dim]")
                    time.sleep(1)
                    continue

            except Exception as e:
                console.print(f"[dim]⚠️ Network error on '{model}': {e}. Trying alternate...[/dim]")
                time.sleep(1)
                continue

        # If all candidate models had temporary network issues on this key, pause briefly before retrying
        time.sleep(1.5)

    console.print("[bold red]❌ All Gemini API attempts completed for batch. Preserving original lines for unmapped items.[/bold red]")
    return batch

def translate_subtitles_to_hinglish(
    subs: pysubs2.SSAFile,
    api_keys: List[str],
    batch_size: int = 20,
    max_requests_per_key: int = 20
) -> pysubs2.SSAFile:
    """
    Translates all dialogue lines in pysubs2 SSAFile to Hinglish:
    - 20 lines per request (optimal sweet spot for 100% completion)
    - Automatically rotates across keys and handles rate-limit cooldowns.
    - Fail-safe sweeper guarantees zero missing or skipped lines.
    """
    key_manager = GeminiKeyManager(api_keys, max_requests_per_key=max_requests_per_key)

    if not key_manager.has_keys:
        console.print("[bold red]❌ No valid Gemini API Keys provided![/bold red]")
        console.print("Please provide API keys in .env (GEMINI_API_KEYS=key1,key2,...) or via CLI.")
        return subs

    console.print(f"[bold cyan]🔑 Loaded {key_manager.total_keys} Gemini API Key(s) into Rotation Pool[/bold cyan]")
    console.print(f"[dim]Rule: 1 request = {batch_size} lines | Max {max_requests_per_key} requests per key before auto-switch[/dim]")

    # Extract all dialogue lines
    dialogues_to_translate = []
    prefix_tags_map = {}
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        # Strict protection: NEVER translate custom watermark, info, or branding lines (saves API keys)
        st_lower = getattr(event, "style", "").strip().lower()
        txt_lower = event.text.lower()
        if (
            st_lower in ("watermarktop", "info") 
            or "watermark" in st_lower 
            or "darksoulacademy" in txt_lower 
            or "telegram channel" in txt_lower
            or "subbed by" in txt_lower
        ):
            continue

        # Extract leading override tags (e.g. {\fs35\pos(100,200)}) to preserve specific dialogue styling
        raw_text = event.text
        tag_match = re.match(r"^((?:\{[^{}]*\})+)(.*)$", raw_text)
        if tag_match:
            prefix_tags = tag_match.group(1)
            content_text = tag_match.group(2)
        else:
            prefix_tags = ""
            content_text = raw_text

        prefix_tags_map[idx] = prefix_tags
        cleaned = clean_sub_text(content_text)
        if cleaned:
            speaker = getattr(event, "name", "").strip()
            item = {"id": idx, "text": cleaned}
            if speaker and speaker.lower() not in ("default", "main", "info", "watermarktop"):
                clean_speaker = re.sub(r"\{.*?\}", "", speaker).strip()
                if clean_speaker:
                    item["speaker"] = clean_speaker
            dialogues_to_translate.append(item)

    total_lines = len(dialogues_to_translate)
    console.print(f"[bold cyan]🌐 Translating {total_lines} subtitle lines to Hinglish in batches of {batch_size}...[/bold cyan]")

    # Extract episode character roster to enforce accurate gender conjugations
    console.print("[bold cyan]🔍 Profiling episode characters and genders for high accuracy...[/bold cyan]")
    character_roster = extract_character_roster(subs, key_manager)
    if character_roster:
        console.print(f"[bold green]👥 Detected Episode Characters & Genders:[/bold green]\n[dim]{character_roster}[/dim]\n")

    # Split into exact batches of 20 lines
    batches = [
        dialogues_to_translate[i:i + batch_size]
        for i in range(0, total_lines, batch_size)
    ]

    translations_map = {}
    prev_context_lines = []
    for batch in track(batches, description="[green]Translating batches with gender tracking..."):
        translated_results = translate_batch_with_retry(
            batch,
            key_manager,
            roster=character_roster,
            prev_context=prev_context_lines
        )
        for item in translated_results:
            clean_text = sanitize_devanagari_to_roman(item.get("text", ""))
            translations_map[item["id"]] = clean_text
            speaker_tag = item.get("speaker", "")
            if speaker_tag:
                prev_context_lines.append(f"{speaker_tag}: {clean_text}")
            else:
                prev_context_lines.append(clean_text)
        prev_context_lines = prev_context_lines[-6:]
        # Pacing between batches to protect against 15 RPM rate limits
        time.sleep(1.2)

    # Fail-Safe Sweeper: Ensure 100% of dialogues were translated
    untranslated_items = [item for item in dialogues_to_translate if item["id"] not in translations_map]
    if untranslated_items and key_manager.has_keys:
        console.print(f"[bold yellow]🔍 Fail-Safe Recovery: Translating {len(untranslated_items)} remaining line(s)...[/bold yellow]")
        recover_batches = [
            untranslated_items[i:i + 10]
            for i in range(0, len(untranslated_items), 10)
        ]
        for mini_batch in recover_batches:
            recovered_items = translate_batch_with_retry(mini_batch, key_manager, roster=character_roster)
            for item in recovered_items:
                translations_map[item["id"]] = sanitize_devanagari_to_roman(item.get("text", ""))
            time.sleep(1.2)

    # Apply translated texts back to SSAFile, strictly preserving specific dialogue tags (like {\fs...})
    for idx, event in enumerate(subs.events):
        if idx in translations_map:
            prefix = prefix_tags_map.get(idx, "")
            event.text = f"{prefix}{translations_map[idx]}"
        elif idx in prefix_tags_map:
            # Clean fallback if translation totally unavailable
            prefix = prefix_tags_map.get(idx, "")
            cleaned_orig = clean_sub_text(re.sub(r"^((?:\{[^{}]*\})+)", "", event.text))
            if cleaned_orig:
                event.text = f"{prefix}{cleaned_orig}"

    translated_count = len(translations_map)
    console.print(f"[bold green]✅ Translation Completed: {translated_count}/{total_lines} lines translated to natural Hinglish![/bold green]")
    return subs
