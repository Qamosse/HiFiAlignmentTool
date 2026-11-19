"""Tolerant channel-name matching: "DAPI" matches "DAPI", "dapi", "DAPI_2", "DAPI-1", "DAPI 2"
(but "AF4" does not match "AF488")."""


def channel_matches(name: str, wanted: str) -> bool:
    n, w = (name or '').strip().lower(), (wanted or '').strip().lower()
    if not n or not w:
        return False
    return n == w or (n.startswith(w) and not n[len(w)].isalnum())


def find_channel(names: list[str], wanted: str) -> int:
    """Index of `wanted` in `names` (exact, case-insensitive, then tolerant). Raises KeyError."""
    low = [x.strip().lower() for x in names]
    w = (wanted or '').strip().lower()
    if w in low:
        return low.index(w)
    hits = [i for i, x in enumerate(names) if channel_matches(x, wanted)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise KeyError(f'Canal "{wanted}" ambigu : {", ".join(names[i] for i in hits)}')
    raise KeyError(f'Canal "{wanted}" introuvable (canaux : {", ".join(names)})')
