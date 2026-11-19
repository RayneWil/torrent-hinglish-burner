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

def clean_sub_text(text: str) -> str:
    """Removes existing ASS/HTML formatting tags from text."""
    # Remove ASS override tags like {\an8}, {\b1}, etc.
    text = re.sub(r"\{.*?\}", "", text)
    # Replace line breaks
    text = text.replace("\\N", " ").replace("\\n", " ")
    return text.strip()

def translate_batch_gemini(batch: List[Dict], api_key: str) -> List[Dict]:
    """
    Translates a batch of subtitle entries into Hinglish using Google Gemini.
    """
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    # Use gemini-1.5-flash or gemini-2.0-flash / gemini-2.5-flash
    model = genai.GenerativeModel("gemini-1.5-flash")

    input_json = json.dumps(batch, ensure_ascii=False)
    prompt = f"{HINGLISH_PROMPT}\n\nInput:\n{input_json}\n\nOutput:\n"

    try:
        response = model.generate_content(prompt)
        raw_text = response.text.strip()

        # Clean markdown codeblocks if returned
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\n", "", raw_text)
            raw_text = re.sub(r"\n```$", "", raw_text)

        translated_batch = json.loads(raw_text)
        return translated_batch
    except Exception as e:
        console.print(f"[bold yellow]⚠️ Batch translation failed: {e}. Retrying in 2s...[/bold yellow]")
        time.sleep(2)
        try:
            response = model.generate_content(prompt)
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```(?:json)?\n", "", raw_text)
                raw_text = re.sub(r"\n```$", "", raw_text)
            return json.loads(raw_text)
        except Exception as retry_err:
            console.print(f"[bold red]❌ Batch retry failed: {retry_err}. Keeping original text for this batch.[/bold red]")
            return batch

def translate_subtitles_to_hinglish(
    subs: pysubs2.SSAFile,
    api_key: str,
    batch_size: int = 35
) -> pysubs2.SSAFile:
    """
    Translates all dialogue lines in pysubs2 SSAFile to Hinglish in batches.
    """
    if not api_key:
        console.print("[bold red]❌ GEMINI_API_KEY is required for Hinglish translation![/bold red]")
        console.print("Please set GEMINI_API_KEY in .env or pass via --api-key.")
        return subs

    # Extract all dialogue lines
    dialogues_to_translate = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        cleaned = clean_sub_text(event.text)
        if cleaned:
            dialogues_to_translate.append({"id": idx, "text": cleaned})

    total_lines = len(dialogues_to_translate)
    console.print(f"[bold cyan]🌐 Translating {total_lines} subtitle lines to Hinglish...[/bold cyan]")

    # Split into batches
    batches = [
        dialogues_to_translate[i:i + batch_size]
        for i in range(0, total_lines, batch_size)
    ]

    translations_map = {}
    for batch in track(batches, description="[green]Translating batches..."):
        translated_results = translate_batch_gemini(batch, api_key)
        for item in translated_results:
            translations_map[item["id"]] = item["text"]
        # Small delay to respect rate limits
        time.sleep(0.3)

    # Apply translated texts back to SSAFile
    for idx, event in enumerate(subs.events):
        if idx in translations_map:
            event.text = translations_map[idx]

    console.print("[bold green]✅ Translation to Hinglish Completed Successfully![/bold green]")
    return subs
