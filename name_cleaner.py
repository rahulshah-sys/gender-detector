"""
name_cleaner.py
----------------
Instagram usernames are messy: "rahul_2002", "minjun.kr99", "Haruto.Official"
This module pulls out the most likely "real name" tokens so the gender
detector has something clean to work with.

Two-pass approach (same idea Rahul used in the desktop tool):
  Pass 1: try the full_name field as-is (usually cleaner than username)
  Pass 2: clean the username -> split into tokens -> try each token
"""

import re

# common junk words seen in IG usernames/bios that should never be treated as a name
STOPWORDS = {
    "official", "real", "the", "its", "im", "i", "and", "of", "by",
    "love", "lover", "fan", "page", "account", "insta", "instagram",
    "fc", "army", "team", "tm", "yt", "fb", "id", "edits", "edit",
    "world", "store", "shop", "studio", "media", "press", "news",
    "x", "xx", "xxx", "vip", "king", "queen", "boy", "girl", "bro",
}


def _split_tokens(raw: str):
    """Break a username into plausible word tokens."""
    if not raw:
        return []

    text = raw.strip()

    # drop a leading @ if someone pastes the handle with it
    text = text.lstrip("@")

    # camelCase / PascalCase -> split: "HarutoOfficial" -> "Haruto Official"
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)

    # replace common separators with spaces
    text = re.sub(r"[._\-]+", " ", text)

    # drop digits (years, counters, etc.)
    text = re.sub(r"\d+", " ", text)

    # keep Hangul, Hiragana/Katakana/Kanji, and Latin letters; drop everything else
    text = re.sub(r"[^a-zA-Z\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7A3\s]", " ", text)

    tokens = [t.strip() for t in text.split() if t.strip()]
    tokens = [t for t in tokens if t.lower() not in STOPWORDS and len(t) > 1]
    return tokens


def get_candidate_names(username: str = "", full_name: str = ""):
    """
    Returns an ordered list of candidate name-tokens to try, best guess first.

    Pass 1 -> tokens from full_name (people often type their real first name here)
    Pass 2 -> tokens from username (fallback when full_name is empty/garbage)
    """
    candidates = []

    for source in (full_name, username):
        for tok in _split_tokens(source):
            if tok not in candidates:
                candidates.append(tok)

    return candidates


if __name__ == "__main__":
    tests = [
        ("rahul_2002", ""),
        ("minjun.kr99", ""),
        ("HarutoOfficial", ""),
        ("", "지은 김"),
        ("priya.fitness", "Priya Sharma"),
        ("xx_jisoo_xx", ""),
    ]
    for u, f in tests:
        print(u, "|", f, "->", get_candidate_names(u, f))
