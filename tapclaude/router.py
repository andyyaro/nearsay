"""Decide which project a spoken task belongs to.

Order of precedence (first match wins):

1. **Spoken routing** at the start of the task, for example
   "In orkestra, add tests for the parser" or "Provalume: fix the README".
   Explicit words beat everything else, so one sticker can still reach any project.
2. **Sticker hint**: the name the iPhone Shortcut sends (one sticker per project).
3. **Default project** from the config.

Spoken routing is deliberately conservative. A bare project name only counts when
it is followed by punctuation ("Orkestra: ...") and matches exactly. A routing word
("in", "for", "on", ...) followed by a project name may match loosely, to survive
dictation spellings ("In Orchestra, ...").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Sequence, Tuple

from .config import Config
from .text import fold, sound_key

ROUTE_WORDS = {"in", "on", "for", "inside", "within", "into", "under"}
DETERMINERS = {"the", "my", "our"}
TRAILERS = {"project", "repo", "repository", "folder", "codebase", "directory"}
FILLERS: Sequence[Tuple[str, ...]] = (
    ("hey", "claude"), ("ok", "claude"), ("okay", "claude"), ("hi", "claude"), ("hello", "claude"),
    ("claude",), ("hey",), ("okay",), ("ok",), ("so",), ("um",), ("uh",), ("please",),
)
_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
_SEPARATORS = ":,;—–-"


@dataclass(frozen=True)
class Route:
    project: str
    task: str
    matched_by: str  # "spoken" | "sticker" | "default"
    heard_as: Optional[str] = None  # the words that selected the project, if spoken
    score: float = 1.0


@dataclass(frozen=True)
class _Tok:
    norm: str
    start: int
    end: int


def _tokens(text: str) -> List[_Tok]:
    return [_Tok(fold(m.group(0)), m.start(), m.end()) for m in _WORD.finditer(text)]


def alias_table(cfg: Config) -> List[Tuple[Tuple[str, ...], str]]:
    """(normalized alias words, project) pairs, longest aliases first."""
    seen: Dict[Tuple[str, ...], str] = {}
    for name, proj in cfg.projects.items():
        forms = [name, name.replace("-", " ").replace("_", " ").replace(".", " ")] + list(proj.aliases)
        for form in forms:
            words = tuple(fold(w) for w in _WORD.findall(form))
            if words and words not in seen:
                seen[words] = name
    return sorted(seen.items(), key=lambda kv: (-len(kv[0]), kv[0]))


def _skip_fillers(toks: List[_Tok], text: str) -> int:
    i = 0
    changed = True
    while changed and i < len(toks):
        changed = False
        for phrase in FILLERS:
            n = len(phrase)
            if tuple(t.norm for t in toks[i:i + n]) == phrase:
                # Only treat it as filler if a pause/punctuation follows or a route word follows,
                # so "So the build is broken" keeps its meaning.
                nxt = toks[i + n] if i + n < len(toks) else None
                gap = text[toks[i + n - 1].end: nxt.start] if nxt else ""
                if nxt is None or any(c in gap for c in ",.;:!?—") or nxt.norm in ROUTE_WORDS:
                    i += n
                    changed = True
                    break
    return i


def _exact_at(toks: List[_Tok], i: int, table) -> Optional[Tuple[str, int]]:
    for words, project in table:
        n = len(words)
        if tuple(t.norm for t in toks[i:i + n]) == words:
            return project, i + n
    return None


def _similar(a: str, b: str) -> float:
    plain = SequenceMatcher(None, a, b).ratio()
    ka, kb = sound_key(a), sound_key(b)
    sound = SequenceMatcher(None, ka, kb).ratio() if ka and kb else 0.0
    return max(plain, sound)


def _fuzzy_at(toks: List[_Tok], i: int, table, threshold: float) -> Optional[Tuple[str, int, float]]:
    """Best loose match of 1-4 heard words against any alias, glued without spaces."""
    best: Dict[str, Tuple[float, int]] = {}
    for words, project in table:
        target = "".join(words)
        if len(target) < 3:
            continue
        for width in range(max(1, len(words) - 1), min(len(words) + 1, 4) + 1):
            if i + width > len(toks):
                break
            heard = "".join(t.norm for t in toks[i:i + width])
            if not heard or sound_key(heard)[:1] != sound_key(target)[:1]:
                continue
            score = _similar(heard, target)
            if score >= threshold and score > best.get(project, (0.0, 0))[0]:
                best[project] = (score, i + width)
    if not best:
        return None
    ranked = sorted(best.items(), key=lambda kv: -kv[1][0])
    if len(ranked) > 1 and ranked[0][1][0] - ranked[1][1][0] < 0.03:
        return None  # too close to call between two projects; don't guess
    project, (score, end) = ranked[0]
    return project, end, score


def _remainder(text: str, toks: List[_Tok], end_tok: int) -> str:
    if end_tok >= len(toks):
        return ""
    rest = text[toks[end_tok - 1].end:] if end_tok > 0 else text
    rest = rest.lstrip(" \t\n" + _SEPARATORS + ".")
    return rest.strip()


def _spoken(text: str, cfg: Config) -> Optional[Route]:
    toks = _tokens(text)
    if not toks:
        return None
    table = alias_table(cfg)
    i = _skip_fillers(toks, text)
    if i >= len(toks):
        return None

    # Pattern A: "<route word> [the|my] <alias> [project|repo] <task>"
    if toks[i].norm in ROUTE_WORDS:
        j = i + 1
        if j < len(toks) and toks[j].norm in DETERMINERS:
            j += 1
        if j < len(toks):
            hit = _exact_at(toks, j, table)
            score = 1.0
            if hit is None:
                fz = _fuzzy_at(toks, j, table, cfg.fuzzy_threshold)
                if fz:
                    hit, score = (fz[0], fz[1]), fz[2]
            if hit:
                project, end = hit
                if end < len(toks) and toks[end].norm in TRAILERS:
                    end += 1
                heard = text[toks[i].start: toks[end - 1].end]
                return Route(project, _remainder(text, toks, end), "spoken", heard, score)

    # Pattern B: "<alias>: <task>" / "<alias>, <task>" (exact match only)
    hit = _exact_at(toks, i, table)
    if hit:
        project, end = hit
        after = text[toks[end - 1].end:].lstrip(" \t")
        if after[:1] and after[0] in _SEPARATORS:
            heard = text[toks[i].start: toks[end - 1].end]
            return Route(project, _remainder(text, toks, end), "spoken", heard, 1.0)
    return None


def route(text: str, cfg: Config, sticker_project: Optional[str] = None) -> Route:
    spoken = _spoken(text, cfg)
    if spoken:
        return spoken
    if sticker_project and sticker_project in cfg.projects:
        return Route(sticker_project, text.strip(), "sticker")
    return Route(cfg.default_project, text.strip(), "default")


def resolve_name(name: str, cfg: Config) -> Optional[str]:
    """Map a sticker name, project name or exact alias to a project (case-insensitive)."""
    key = name.strip().lower()
    if key in cfg.stickers:
        return cfg.stickers[key]
    if key in cfg.projects:
        return key
    words = tuple(fold(w) for w in _WORD.findall(name))
    for alias_words, project in alias_table(cfg):
        if alias_words == words:
            return project
    return None
