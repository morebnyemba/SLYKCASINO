"""Forgiving name search for chat: finds a team, league or country even when
it is misspelt ("arsnal", "premeir leage", "zimbabwae").

Only names that have upcoming or live matches are candidates, so the lists stay
small (a few thousand at most) and plain difflib is fast enough; no extension
or search service is needed.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Iterable

CUTOFF = 0.72          # how alike a name must be to count as "what they meant"


def norm(text: str) -> str:
    """Lower case, no accents or punctuation, single spaces: 'Atlético  Madrid!' → 'atletico madrid'."""
    text = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]+', ' ', text.lower())).strip()


def score(query: str, name: str) -> float:
    """1.0 when the query is in the name; otherwise how alike the query is to
    the whole name or to any run of words in it of the query's length."""
    q, n = norm(query), norm(name)
    if not q or not n:
        return 0.0
    if q in n:
        return 1.0 if n.startswith(q) or f' {q}' in f' {n}' else 0.95
    words, k = n.split(), len(q.split())
    runs = {' '.join(words[i:i + k]) for i in range(max(1, len(words) - k + 1))} | {n}
    return max(difflib.SequenceMatcher(None, q, r).ratio() for r in runs)


def best(query: str, names: Iterable[str], *, cutoff: float = CUTOFF, limit: int = 5) -> list[str]:
    """The names that best match `query`, best first (ties: the shorter name)."""
    scored = [(score(query, n), n) for n in {n for n in names if n}]
    scored = [(s, n) for s, n in scored if s >= cutoff]
    scored.sort(key=lambda sn: (-sn[0], len(sn[1]), sn[1]))
    return [n for _, n in scored[:limit]]
