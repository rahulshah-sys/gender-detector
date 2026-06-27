"""
gender_detector.py
-------------------
Combines three detectors behind one simple function: predict(username, full_name)

1. Korean   -> seed dictionary (Hangul + romanized) + light suffix heuristic
2. Japanese -> japanese-personal-name-dataset (pip package), matched by romaji
3. Global   -> gender_guesser (covers English/European/Indian/etc. first names)

Output schema (always the same, easy to write into a Google Sheet column):
{
    "gender": "Male" | "Female" | "Unisex" | "Unknown",
    "confidence": 0.0 - 1.0,
    "method": "korean_dict" | "japanese_dict" | "gender_guesser" | "korean_suffix_heuristic" | "none",
    "matched_token": "<the name token that produced the result>"
}
"""

import json
import os
import re

import gender_guesser.detector as gg
from japanese_personal_name_dataset import load_dataset as load_jp_dataset

from name_cleaner import get_candidate_names

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# ---------------------------------------------------------------------------
# One-time setup (runs once at process start, not per-request -> keeps the
# Space fast and avoids the Gunicorn-timeout problem you hit on the DeepFace
# Space, since there is no model loading here, only small dicts).
# ---------------------------------------------------------------------------

_gg_detector = gg.Detector(case_sensitive=False)

with open(os.path.join(DATA_DIR, "korean_names_seed.json"), encoding="utf-8") as f:
    _KR = json.load(f)

_KR_SURNAMES = set(_KR["surnames_to_strip"])
_KR_GIVEN = _KR["given_names"]
_KR_ROMAN = _KR["romanized_given_names"]
_KR_SUFFIX_F = tuple(_KR["suffix_hints"]["female_leaning_endings"])
_KR_SUFFIX_M = tuple(_KR["suffix_hints"]["male_leaning_endings"])

_jp_male_raw, _jp_female_raw = load_jp_dataset(kind="org")


def _build_romaji_gender_map(male_raw, female_raw):
    male_set, female_set = set(), set()
    for info in male_raw.values():
        r = info.get("en")
        if r:
            male_set.add(r.lower())
    for info in female_raw.values():
        r = info.get("en")
        if r:
            female_set.add(r.lower())
    return male_set, female_set


_JP_MALE_ROMAJI, _JP_FEMALE_ROMAJI = _build_romaji_gender_map(_jp_male_raw, _jp_female_raw)

HANGUL_RE = re.compile(r"[\uAC00-\uD7A3]")
JP_KANA_RE = re.compile(r"[\u3040-\u30FF]")
JP_KANJI_RE = re.compile(r"[\u4E00-\u9FFF]")


def _detect_script(token: str) -> str:
    if HANGUL_RE.search(token):
        return "korean"
    if JP_KANA_RE.search(token):
        return "japanese"
    if JP_KANJI_RE.search(token):
        return "kanji_ambiguous"  # shared by Japanese/Chinese, low confidence
    return "latin"


# ---------------------------------------------------------------------------
# Korean
# ---------------------------------------------------------------------------

def _strip_korean_surname(token: str) -> str:
    if len(token) >= 3 and token[0] in _KR_SURNAMES:
        return token[1:]
    return token


def _try_korean_hangul(token: str):
    given = _strip_korean_surname(token)
    if given in _KR_GIVEN:
        gender = _KR_GIVEN[given]
        return _format_result(gender, 0.85, "korean_dict", given)
    if token in _KR_GIVEN:  # in case surname stripping wasn't needed
        gender = _KR_GIVEN[token]
        return _format_result(gender, 0.85, "korean_dict", token)
    return None


def _try_korean_romanized(token: str):
    t = token.lower()
    if t in _KR_ROMAN:
        return _format_result(_KR_ROMAN[t], 0.75, "korean_dict", t)
    # last-resort suffix heuristic, intentionally low confidence
    if t.endswith(_KR_SUFFIX_F) and not t.endswith(_KR_SUFFIX_M):
        return _format_result("female", 0.35, "korean_suffix_heuristic", t)
    if t.endswith(_KR_SUFFIX_M) and not t.endswith(_KR_SUFFIX_F):
        return _format_result("male", 0.35, "korean_suffix_heuristic", t)
    return None


# ---------------------------------------------------------------------------
# Japanese
# ---------------------------------------------------------------------------

def _try_japanese(token: str):
    t = token.lower()
    in_male = t in _JP_MALE_ROMAJI
    in_female = t in _JP_FEMALE_ROMAJI
    if in_male and in_female:
        return _format_result("unisex", 0.5, "japanese_dict", t)
    if in_male:
        return _format_result("male", 0.8, "japanese_dict", t)
    if in_female:
        return _format_result("female", 0.8, "japanese_dict", t)
    return None


# ---------------------------------------------------------------------------
# Global / Latin (gender_guesser)
# ---------------------------------------------------------------------------

_GG_MAP = {
    "male": "male",
    "mostly_male": "male",
    "female": "female",
    "mostly_female": "female",
    "andy": "unisex",
}

_GG_CONFIDENCE = {
    "male": 0.85,
    "mostly_male": 0.65,
    "female": 0.85,
    "mostly_female": 0.65,
    "andy": 0.5,
}


def _try_global(token: str):
    raw = _gg_detector.get_gender(token)
    if raw == "unknown":
        return None
    gender = _GG_MAP[raw]
    confidence = _GG_CONFIDENCE[raw]
    return _format_result(gender, confidence, "gender_guesser", token)


# ---------------------------------------------------------------------------
# Shared formatting
# ---------------------------------------------------------------------------

def _format_result(gender: str, confidence: float, method: str, token: str):
    return {
        "gender": gender.capitalize() if gender != "unisex" else "Unisex",
        "confidence": confidence,
        "method": method,
        "matched_token": token,
    }


_NO_MATCH = {"gender": "Unknown", "confidence": 0.0, "method": "none", "matched_token": None}


def predict_token(token: str):
    """Run the right detector(s) for a single name token, by script."""
    script = _detect_script(token)

    if script == "korean":
        return _try_korean_hangul(token) or _NO_MATCH

    if script == "japanese":
        return _try_japanese(token) or _NO_MATCH

    if script == "kanji_ambiguous":
        # Could be Chinese or Japanese written in kanji only; we only have a
        # Japanese romaji map, so we can't safely match here. Skip.
        return _NO_MATCH

    # latin script: could be a plain Western/Indian name, OR a romanized
    # Korean/Japanese name typed in the username. Try both, prefer whichever
    # is a confident dictionary hit over a guess.
    jp_result = _try_japanese(token)
    kr_result = _try_korean_romanized(token)
    gg_result = _try_global(token)

    for result in (jp_result, kr_result, gg_result):
        if result and result["method"] not in ("korean_suffix_heuristic",):
            return result

    # nothing confident found, fall back to the weak heuristic if present
    return kr_result or _NO_MATCH


def predict(username: str = "", full_name: str = ""):
    """
    Main entry point. Tries each candidate token (best guess first) and
    returns the first confident result, or Unknown if nothing matched.
    """
    candidates = get_candidate_names(username=username, full_name=full_name)

    if not candidates:
        return dict(_NO_MATCH)

    best = dict(_NO_MATCH)
    for token in candidates:
        result = predict_token(token)
        if result["confidence"] > best["confidence"]:
            best = result
        if best["confidence"] >= 0.75:
            break  # good enough, no need to keep checking weaker candidates

    return best


if __name__ == "__main__":
    tests = [
        ("rahul_2002", ""),
        ("priya.fitness", "Priya Sharma"),
        ("minjun.kr99", ""),
        ("", "지은 김"),
        ("", "김민준"),
        ("HarutoOfficial", ""),
        ("xx_jisoo_xx", ""),
        ("sakura.chan", ""),
        ("random123", ""),
    ]
    for u, f in tests:
        print(f"{u!r:25} {f!r:15} -> {predict(u, f)}")
