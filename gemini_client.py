"""Thin Gemini REST helper. Uses native generativelanguage API (AQ. auth keys)."""
import base64
import json
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("gemini_api_key")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)


def _extract_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {payload}")
    parts = candidates[0].get("content", {}).get("parts") or []
    return "".join(part.get("text", "") for part in parts).strip()


def _parse_json_text(text: str):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def generate_text(prompt: str, system: str | None = None, temperature: float = 0.5, json_mode: bool = False) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")

    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    body = {
        "contents": contents,
        "generationConfig": {"temperature": temperature},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    response = requests.post(
        GEMINI_ENDPOINT,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        json=body,
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:500]}")
    return _extract_text(response.json())


def generate_json(prompt: str, system: str | None = None, temperature: float = 0.5):
    text = generate_text(prompt, system=system, temperature=temperature, json_mode=True)
    return _parse_json_text(text)


def generate_from_image(prompt: str, image_path: str, mime_type: str = "image/jpeg") -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    with open(image_path, "rb") as image_file:
        image_b64 = base64.b64encode(image_file.read()).decode("utf-8")
    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": image_b64}},
            ],
        }],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    response = requests.post(
        GEMINI_ENDPOINT,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        json=body,
        timeout=90,
    )
    if not response.ok:
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:500]}")
    return _extract_text(response.json())


def transcribe_audio_file(audio_path: str, mime_type: str = "audio/mpeg") -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    with open(audio_path, "rb") as audio_file:
        audio_b64 = base64.b64encode(audio_file.read()).decode("utf-8")
    prompt = (
        "Transcribe this voice note. Return JSON with keys: "
        "detected_language (ISO 639-1), original_transcription, english_translation."
    )
    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": audio_b64}},
            ],
        }],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }
    response = requests.post(
        GEMINI_ENDPOINT,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        json=body,
        timeout=90,
    )
    if not response.ok:
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:500]}")
    return _parse_json_text(_extract_text(response.json()))
