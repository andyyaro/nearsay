"""Cleaning of dictated text before it goes anywhere near a terminal.

The task text is never interpreted by a shell (it travels as a file and a single
argv element), but cleaning still matters:

* invisible and bidirectional control characters are removed, so what you see in
  the notification is exactly what Claude receives (no "Trojan Source" tricks);
* a leading dash is removed so the task can never be mistaken for a command-line
  flag by ``claude``;
* whitespace is tidied so session names and previews stay readable.
"""

from __future__ import annotations

import re
import unicodedata

# C0 controls except tab (0x09) and newline (0x0a); DEL; zero-width and
# bidirectional formatting characters; byte-order mark.
_CONTROL = re.compile(
    "[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]"
)
_LEADING_JUNK = re.compile(r"^[\s\-‐-―−*•>]+")


def normalize_task(raw: str) -> str:
    s = raw.replace("\r\n", "\n").replace("\r", "\n")
    s = unicodedata.normalize("NFC", s)
    s = _CONTROL.sub("", s)
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    s = _LEADING_JUNK.sub("", s)
    return s.strip()


def preview(text: str, limit: int = 70) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= limit:
        return one_line
    cut = one_line[: limit - 1].rstrip()
    return cut + "…"


def fold(word: str) -> str:
    """Lowercase and strip accents/apostrophes for matching ("Orkestrá's" -> "orkestras")."""
    decomposed = unicodedata.normalize("NFKD", word.lower())
    no_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"['’`]", "", no_marks)


def sound_key(word: str) -> str:
    """A small phonetic key so dictation spellings still match project names.

    Dictation often writes "Orchestra" for "orkestra" or "Pro Valume" for
    "provalume". This key maps letters that sound alike onto one letter and
    collapses doubles, which is enough for short project names without pulling
    in a phonetics library.
    """
    w = re.sub(r"[^a-z0-9]", "", fold(word))
    for a, b in (("ph", "f"), ("ck", "k"), ("ch", "k"), ("qu", "k"), ("q", "k"), ("c", "k"),
                 ("x", "ks"), ("z", "s"), ("y", "i"), ("w", "v"), ("ee", "i"), ("oo", "u")):
        w = w.replace(a, b)
    w = re.sub(r"([a-z])h", r"\1", w)  # silent h after a letter ("th" stays "t")
    w = re.sub(r"(.)\1+", r"\1", w)     # collapse doubled letters
    return w
