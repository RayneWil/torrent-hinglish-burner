import json
import re
import time
from typing import List, Dict, Optional
from rich.console import Console
from rich.progress import track
import pysubs2

console = Console()

HINGLISH_PROMPT = """You are an expert subtitle translator. Translate the following video subtitles into natural, modern, conversational Hinglish (Hindi written using the Roman/English alphabet, exactly how people speak and text in India).

CRITICAL GUIDELINES:
1. SCRIPT: NEVER use Devanagari script (क, ख, ग). Strictly use the Roman English alphabet (e.g., "Bhai tu kahan ja raha hai?", "Mujhe ye bilkul pasand nahi aaya").
2. TONE: Keep it natural, conversational, and context-appropriate (like modern Indian OTT web series or movies).
3. PRESERVATION: Keep proper nouns, character names, places, technical jargon, and international terms in English.
4. FORMAT: You will receive a JSON array of objects with "id" and "text". You MUST reply with ONLY a valid JSON array of objects with the exact same "id" and the translated Hinglish "text".

Example:
Input:
[
  {"id": 1, "text": "What are you doing here?"},
  {"id": 2, "text": "I came to check on you, bro."}
]

Output:
[
  {"id": 1, "text": "Tu yahan kya kar raha hai?"},
  {"id": 2, "text": "Main bas tereko check karne aaya tha, bro."}
]
"""

class GeminiKeyManager:
    """
    Manages pool of multiple Gemini API keys.
    Rotates automatically after max_requests_per_key (20) or on quota errors (429/ResourceExhausted).
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

def translate_batch_with_retry(batch: List[Dict], key_manager: GeminiKeyManager) -> List[Dict]:
    """
    Translates a 30-line batch using the currently active Gemini API key.
    Automatically rotates keys if 429 quota is hit or after 20 requests.
    """
    import google.generativeai as genai

    while key_manager.has_keys:
        active_key = key_manager.get_active_key()
        try:
            genai.configure(api_key=active_key)
            model = genai.GenerativeModel("gemini-1.5-flash")

            input_json = json.dumps(batch, ensure_ascii=False)
            prompt = f"{HINGLISH_PROMPT}\n\nInput:\n{input_json}\n\nOutput:\n"

            response = model.generate_content(prompt)
            raw_text = response.text.strip()

            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```(?:json)?\n", "", raw_text)
                raw_text = re.sub(r"\n```$", "", raw_text)

            translated_batch = json.loads(raw_text)
            key_manager.record_success()
            return translated_batch

        except Exception as e:
            err_str = str(e).lower()
            # If quota exceeded / 429 rate limit hit, switch to next key immediately
            if any(term in err_str for term in ["429", "quota", "resourceexhausted", "limit"]):
                console.print(f"[bold yellow]⚠️ Quota limit hit on Key #{key_manager.current_idx + 1}: {e}[/bold yellow]")
                key_manager.rotate(reason="429 Rate/Quota Limit")
                time.sleep(1)
                continue
            else:
                console.print(f"[bold yellow]⚠️ Translation error: {e}. Retrying...[/bold yellow]")
                time.sleep(2)
                try:
                    response = model.generate_content(prompt)
                    raw_text = response.text.strip()
                    if raw_text.startswith("```"):
                        raw_text = re.sub(r"^```(?:json)?\n", "", raw_text)
                        raw_text = re.sub(r"\n```$", "", raw_text)
                    translated_batch = json.loads(raw_text)
                    key_manager.record_success()
                    return translated_batch
                except Exception as retry_err:
                    console.print(f"[bold red]❌ Retry failed: {retry_err}. Switching key to continue...[/bold red]")
                    key_manager.rotate(reason="Retry error")

    console.print("[bold red]❌ No active Gemini API key remaining. Keeping original lines for this batch.[/bold red]")
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
        # Small delay between requests
        time.sleep(0.3)

    # Apply translated texts back to SSAFile
    for idx, event in enumerate(subs.events):
        if idx in translations_map:
            event.text = translations_map[idx]

    console.print("[bold green]✅ Translation to Hinglish Completed Successfully![/bold green]")
    return subs
