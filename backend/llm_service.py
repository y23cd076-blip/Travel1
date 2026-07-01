"""
LLM narrative layer.

Important design decision (explain this in your report's "Hallucination
Mitigation" section): the LLM NEVER decides which attractions/restaurants/
hotels go into the itinerary - the optimizer already fixed that using real
data from destinations.json. The LLM's only job here is to:
  1. Write short, engaging summaries for each day given the fixed list of
     places (grounded generation).
  2. Produce general travel tips, packing tips, and "things to avoid" -
     things that don't require inventing facts about specific places.

If no API key is configured, a template-based fallback is used instead, so
the app still runs end-to-end without any external dependency (useful for
early development, testing, and demoing without incurring API costs).

Uses Google's Gemini API via the `google-genai` SDK. Set GEMINI_API_KEY to
enable it; optionally set GEMINI_MODEL to override the default model.
"""

import os
import json
from typing import List, Dict, Any

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
USE_LLM = bool(GEMINI_API_KEY)

if USE_LLM:
    from google import genai
    from google.genai import types

    _client = genai.Client(api_key=GEMINI_API_KEY)


def _build_prompt(destination_name: str, interests: List[str], day_plans: List[Dict[str, Any]]) -> str:
    schedule_summary = []
    for d in day_plans:
        att_names = [a["name"] for a in d["attractions"]]
        rest_names = [r["name"] for r in d["restaurants"]]
        schedule_summary.append({
            "day": d["day_number"],
            "attractions": att_names,
            "restaurants": rest_names,
        })

    return f"""You are an expert travel writer. A trip-planning algorithm has ALREADY
decided the exact schedule below for a trip to {destination_name}. Your ONLY job is to
add narrative text. Do NOT suggest any place that is not already listed below - the
schedule is fixed and cannot change.

Traveler interests: {", ".join(interests)}

Fixed schedule:
{json.dumps(schedule_summary, indent=2)}

Return ONLY valid JSON (no markdown fences, no preamble) with this exact structure:
{{
  "day_summaries": {{"1": "one or two engaging sentences about day 1's plan", "2": "..."}},
  "travel_tips": ["tip1", "tip2", "tip3", "tip4"],
  "things_to_avoid": ["thing1", "thing2", "thing3"],
  "packing_tips": ["item1", "item2", "item3", "item4"]
}}
"""


def _fallback_narrative(destination_name: str, interests: List[str], day_plans: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic template-based narrative, used when no API key is set."""
    day_summaries = {}
    for d in day_plans:
        names = ", ".join(a["name"] for a in d["attractions"]) or "a relaxed day at leisure"
        day_summaries[str(d["day_number"])] = f"Day {d['day_number']} covers {names}, paired with local dining nearby."

    return {
        "day_summaries": day_summaries,
        "travel_tips": [
            f"Book {destination_name} attraction tickets a day in advance where possible.",
            "Keep a mix of cash and digital payments handy for local vendors.",
            "Start early in the day to avoid peak crowds and heat.",
            "Check local weather the night before to plan outdoor activities.",
        ],
        "things_to_avoid": [
            "Avoid unlicensed taxis/tour operators near tourist hubs.",
            "Avoid overpaying at unmarked-price stalls - confirm rates first.",
            "Avoid scheduling long travel right after a heavy meal.",
        ],
        "packing_tips": [
            "Comfortable walking shoes",
            "Reusable water bottle",
            "Weather-appropriate light layers",
            "Power bank and universal adapter",
        ],
    }


def generate_narrative(destination_name: str, interests: List[str], day_plans: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not USE_LLM:
        return _fallback_narrative(destination_name, interests, day_plans)

    prompt = _build_prompt(destination_name, interests, day_plans)
    try:
        response = _client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=1200,
            ),
        )
        text = (response.text or "").strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)
    except Exception as e:
        # Never let a flaky LLM call break the whole trip response - degrade gracefully.
        print(f"[llm_service] Gemini call failed, falling back to template narrative: {e}")
        return _fallback_narrative(destination_name, interests, day_plans)
