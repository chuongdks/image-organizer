import base64
import json
import httpx
from pathlib import Path
from dataclasses import dataclass
import re

# ── Shared tag schema ──────────────────────────────────────────────
# Both backends return the same structure so the rest of the app
# doesn't care which one was used.

@dataclass
class ImageTags:
    path: str
    category: str          # e.g. "meme", "screenshot", "scenery", "game"
    tags: list[str]        # e.g. ["funny", "text-heavy", "dark humor"]
    ocr_text: str          # any readable text found in the image
    is_nsfw: bool
    description: str       # one sentence summary
    backend: str           # "ollama" or "claude"

# ── Shared prompt ──────────────────────────────────────────────────
PROMPT = """Analyze this image and respond ONLY with a JSON object, no markdown, no extra text.

{
  "category": "<one of: meme, screenshot, game, scenery, document, selfie, food, animal, nsfw, other>",
  "tags": ["tag1", "tag2", "tag3"],
  "ocr_text": "<any visible text in the image, or empty string>",
  "is_nsfw": false,
  "description": "<one sentence describing the image>"
}
"""

# ── Helpers ────────────────────────────────────────────────────────
def _image_to_base64(image_path: str) -> tuple[str, str]:
    """Returns (base64_data, media_type)"""
    ext = Path(image_path).suffix.lower()
    media_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",  ".gif": "image/gif",
        ".webp": "image/webp"
    }
    media_type = media_map.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8"), media_type

def _parse_response(raw: str, path: str, backend: str) -> ImageTags:
    """Parse the JSON response from either backend."""
    
    cleaned = raw.strip()

    # ── Method 1: find/rfind ────────────────────────────────────────────────────────
    # # Find the JSON object by locating the first { and last }
    # start = cleaned.find("{")
    # end = cleaned.rfind("}")

    # if start == -1 or end == -1:
    #     print(f"No JSON object found in response for {Path(path).name}")
    #     print(f"Raw: {repr(cleaned[:200])}")
    #     return ImageTags(path=path, category="other", tags=[],
    #                      ocr_text="", is_nsfw=False,
    #                      description="parse error", backend=backend)

    # cleaned = cleaned[start : end + 1]  # slice out exactly the JSON object
    
    # ── Method 2: Regex ────────────────────────────────────────────────────────
    # Step 1: strip markdown code fences if present
    # handles ```json ... ``` or ``` ... ```
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()

    # Step 2: extract just the JSON object if there's surrounding text
    # finds the first { ... } block in the string
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
        
    # Step 3: try parsing
    try:
        data = json.loads(cleaned)
        return ImageTags(
            path=path,
            category=data.get("category", "other"),
            tags=data.get("tags", []),
            ocr_text=data.get("ocr_text", ""),
            is_nsfw=data.get("is_nsfw", False),
            description=data.get("description", ""),
            backend=backend,
        )
    except json.JSONDecodeError as e:
        # Step 4: log the raw response so you can see what went wrong
        print(f"Parse failed for {Path(path).name}: {e}")
        print(f"Raw response was: {repr(raw)}")
        return ImageTags(path=path, category="other", tags=[],
                         ocr_text="", is_nsfw=False,
                         description="parse error", backend=backend)

# ── Backend 1: Ollama (LLaVA) — FREE, runs locally ────────────────
def tag_with_ollama(image_path: str, model: str = "llava:7b") -> ImageTags:
    b64, _ = _image_to_base64(image_path)

    response = httpx.post(
        "http://localhost:11434/api/generate",
        json={
            "model": model,
            "prompt": PROMPT,
            "images": [b64],
            "stream": False,
            "options": {
                "num_predict": 512,   # max tokens to generate
                "temperature": 0.1,   # lower = more consistent JSON formatting
            }

        },
        timeout=60,
    )
    response.raise_for_status()
    raw = response.json()["response"]
    return _parse_response(raw, image_path, backend="ollama")

# ── Backend 2: Claude Haiku 4.5 — paid, higher quality ────────────
def tag_with_claude(image_path: str, api_key: str,
                    model: str = "claude-haiku-4-5-20251001") -> ImageTags:
    b64, media_type = _image_to_base64(image_path)

    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 512,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        }
                    },
                    {"type": "text", "text": PROMPT}
                ]
            }]
        },
        timeout=30,
    )
    response.raise_for_status()
    raw = response.json()["content"][0]["text"]
    return _parse_response(raw, image_path, backend="claude")