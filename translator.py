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
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview"
]

HINGLISH_PROMPT = """ROLE:
You are a professional anime subtitle translator.
Your task is to translate subtitle files (.ass, .srt, .vtt) into natural, emotional, and smooth Hinglish.
Translation must sound human, casual, anime-style, and expressive — NOT word-to-word.

VERY IMPORTANT FORMAT RULES (STRICT):
- DO NOT change subtitle numbering.
- DO NOT change timestamps (start/end time must remain EXACTLY the same).
- DO NOT merge lines.
- DO NOT split lines.
- DO NOT reorder subtitles.
- Each subtitle entry must remain exactly where it is.
- Output structure must be IDENTICAL to the input file.
- Do not translate into Devanagari

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

STRICT RULE MUST FOLLOW:
Look at the dialogue and understand who is speaking—and to whom—in terms of gender. 
Ensure that the verb endings (like 'raha hoon' or 'rahi hoon') are consistent with that gender. 
Maintain this throughout.

TECHNICAL FORMAT:
You will receive a JSON array of objects with "id" and "text". You MUST reply with ONLY a valid JSON array of objects with the exact same "id" and the translated Hinglish "text". Do not include markdown codeblocks or conversational text, just the raw JSON array.
"""

class GeminiKeyManager:
    """
    Manages pool of multiple Gemini API keys.
    Rotates ONLY when quota (429/403) is exhausted or after max_requests_per_key (20).
    Never burns keys on temporary 503/server spikes.
    """
    def __init__(self, keys: List[str], max_requests_per_key: int = 20):
        self.keys = [k.strip() for k in keys if k.strip()]
        self.max_requests_per_key = max_requests_per_key
        self.current_idx = 0
        self.request_counts = [0] * len(self.keys)

    @property
    def has_keys(self) -> bool:
        return len(self.keys) > 0 and self.current_idx < len(self.keys)

    @property
    def total_keys(self) -> int:
        return len(self.keys)

    def get_active_key(self) -> Optional[str]:
        if self.current_idx >= len(self.keys):
            return None
        return self.keys[self.current_idx]

    def record_success(self):
        """Track successful request. If hits 20 requests, auto-rotate to next key."""
        if self.current_idx < len(self.keys):
            self.request_counts[self.current_idx] += 1
            used = self.request_counts[self.current_idx]
            console.print(
                f"[dim]🔑 Key #{self.current_idx + 1}/{len(self.keys)}: "
                f"{used}/{self.max_requests_per_key} requests used[/dim]"
            )
            if used >= self.max_requests_per_key:
                self.rotate(reason=f"Quota of {self.max_requests_per_key} requests reached")

    def rotate(self, reason: str = ""):
        """Switch to the next available API key."""
        old_idx = self.current_idx
        self.current_idx += 1
        if self.current_idx < len(self.keys):
            console.print(
                f"[bold yellow]🔄 Key #{old_idx + 1} shifted ({reason}). "
                f"Now switching to Key #{self.current_idx + 1}/{len(self.keys)}...[/bold yellow]"
            )
        else:
            console.print(f"[bold red]❌ All {len(self.keys)} API Keys have been exhausted![/bold red]")

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

def translate_batch_with_retry(batch: List[Dict], key_manager: GeminiKeyManager) -> List[Dict]:
    """
    Translates a 30-line batch using direct REST API.
    - Model fallback chain: tries flash-lite first, falls back if 503 high demand occurs.
    - Rotates API keys ONLY on true quota exhaustion (429/403) or after 20 successful requests.
    """
    input_json = json.dumps(batch, ensure_ascii=False)
    full_prompt = f"{HINGLISH_PROMPT}\n\nInput:\n{input_json}\n\nOutput:\n"

    while key_manager.has_keys:
        active_key = key_manager.get_active_key()

        # Try candidate models on the current active key
        for model in CANDIDATE_MODELS:
            try:
                raw_text = call_gemini_rest(full_prompt, active_key, model_name=model).strip()

                translated_batch = parse_gemini_json_response(raw_text)
                key_manager.record_success()
                return translated_batch

            except urllib.error.HTTPError as e:
                err_code = e.code
                err_body = e.read().decode("utf-8", errors="ignore")

                # If Quota limit (429 / 403), rotate to NEXT KEY immediately
                if err_code in (429, 403) or "quota" in err_body.lower() or "resourceexhausted" in err_body.lower():
                    console.print(f"[bold yellow]⚠️ Quota limit on Key #{key_manager.current_idx + 1} (HTTP {err_code}). Shifting key...[/bold yellow]")
                    key_manager.rotate(reason=f"HTTP {err_code} Quota Limit")
                    break  # Break out to try new key with first model

                # If 503 (Server high demand) or 404, DO NOT burn key! Try next candidate model
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
        time.sleep(2)

    console.print("[bold red]❌ All Gemini API keys exhausted. Preserving original lines for remaining dialogues.[/bold red]")
    return batch

def translate_subtitles_to_hinglish(
    subs: pysubs2.SSAFile,
    api_keys: List[str],
    batch_size: int = 30,
    max_requests_per_key: int = 20
) -> pysubs2.SSAFile:
    """
    Translates all dialogue lines in pysubs2 SSAFile to Hinglish:
    - 30 lines per request
    - Automatically rotates to next key after 20 requests or on quota exhaustion.
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
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        # Skip watermark lines so AI doesn't modify them
        if getattr(event, "style", "") == "WatermarkTop" or "DarkSoulAcademy" in event.text:
            continue
        cleaned = clean_sub_text(event.text)
        if cleaned:
            dialogues_to_translate.append({"id": idx, "text": cleaned})

    total_lines = len(dialogues_to_translate)
    console.print(f"[bold cyan]🌐 Translating {total_lines} subtitle lines to Hinglish in batches of {batch_size}...[/bold cyan]")

    # Split into exact batches of 30 lines
    batches = [
        dialogues_to_translate[i:i + batch_size]
        for i in range(0, total_lines, batch_size)
    ]

    translations_map = {}
    for batch in track(batches, description="[green]Translating batches..."):
        translated_results = translate_batch_with_retry(batch, key_manager)
        for item in translated_results:
            translations_map[item["id"]] = item["text"]
        # Small delay between requests to be gentle on rate limits
        time.sleep(0.4)

    # Apply translated texts back to SSAFile
    for idx, event in enumerate(subs.events):
        if idx in translations_map:
            event.text = translations_map[idx]

    console.print("[bold green]✅ Translation to Hinglish Completed Successfully![/bold green]")
    return subs
