"""
Traduction en français des résumés (fiches TMDB, ThePornDB, RAWG, livres…) quand ils sont dans une autre langue.

Service Google Translate public (client « gtx », secours « dict-chrome-ex ») : gratuit, sans clé ni compte. En cas d'échec
(réseau, quota), le texte d'origine est conservé : la traduction n'est jamais bloquante.
"""

import logging
import re

import requests

from . import USER_AGENT

URL = "https://translate.googleapis.com/translate_a/single"
CHUNK = 1800                       # caractères par requête (URL GET)


def _chunks(text: str) -> list:
    """Morceaux de CHUNK caractères au plus, coupés entre deux phrases (séparateurs conservés)."""
    pieces = re.findall(r"[^.!?\n]*(?:[.!?]+|\n)\s*|[^.!?\n]+$", text)
    out, cur = [], ""
    for p in pieces:
        if cur and len(cur) + len(p) > CHUNK:
            out.append(cur)
            cur = ""
        while len(p) > CHUNK:                 # phrase démesurée : coupe brute
            out.append(p[:CHUNK])
            p = p[CHUNK:]
        cur += p
    if cur:
        out.append(cur)
    return out


URL_ALT = "https://clients5.google.com/translate_a/t"     # client « dict-chrome-ex » : secours si gtx est limité
_gtx_blocked = [0.0]                                     # gtx limité (HTTP 429) : on passe au secours une heure


def _gtx(text, target):
    r = requests.get(URL, params={"client": "gtx", "sl": "auto", "tl": target, "dt": "t", "q": text}, timeout=15,
                     headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    j = r.json()
    translated = "".join(seg[0] for seg in (j[0] or []) if seg and seg[0])
    return translated, (j[2] if len(j) > 2 else "") or ""


def _dict_chrome(text, target):
    r = requests.post(URL_ALT, params={"client": "dict-chrome-ex", "sl": "auto", "tl": target}, data={"q": text},
                      timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    j = r.json()
    first = j[0] if isinstance(j, list) and j else j
    if isinstance(first, list):                    # [[traduction, langue]]
        return first[0], (first[1] if len(first) > 1 else "")
    return str(first), ""


def _call(text: str, target: str) -> tuple:
    import time
    if time.monotonic() > _gtx_blocked[0]:
        try:
            return _gtx(text, target)
        except requests.HTTPError as e:
            if e.response is None or e.response.status_code not in (429, 403):
                raise
            _gtx_blocked[0] = time.monotonic() + 3600
    return _dict_chrome(text, target)


def to_french(text: str) -> tuple:
    """(texte en français, langue détectée). Texte déjà français ou échec : texte d'origine."""
    text = (text or "").strip()
    if not text:
        return text, ""
    try:
        parts, lang = [], ""
        for i, chunk in enumerate(_chunks(text)):
            tr, src = _call(chunk, "fr")
            lang = lang or src
            if i == 0 and src.startswith("fr"):
                return text, "fr"
            parts.append(tr)
        return "".join(parts).strip() or text, lang
    except (requests.RequestException, ValueError, IndexError, TypeError) as e:
        logging.info("Traduction du résumé impossible : %s", e)
        return text, ""


def protect(text: str, names: list) -> tuple:
    """Remplace les noms propres (interprètes, studio…) par des jetons que la traduction ne touche pas."""
    words = []
    for n in names:
        n = (n or "").strip()
        if n:
            words.append(n)
            words += [w for w in re.split(r"[\s.\-]+", n) if len(w) >= 3]
    # « Hannah Blue », « Amber Rose » : prénom connu suivi d'un nom à majuscule, protégés ensemble
    for w in list(words):
        if " " not in w:
            words += [f"{w} {m.group(1)}" for m in re.finditer(rf"(?<!\w){re.escape(w)}\s+([A-Z][a-z]+)\b", text)]
    table = {}
    for w in sorted(set(words), key=len, reverse=True):
        tok = f"ZQ{len(table)}QZ"
        new = re.sub(rf"(?<![\w]){re.escape(w)}(?![\w])", tok, text)
        if new != text:
            table[tok], text = w, new
    return text, table


def restore(text: str, table: dict) -> str:
    for tok, w in table.items():
        text = re.sub(tok, w, text, flags=re.I)
    return text


def french_overview(ident, enabled: bool = True):
    """Résumé de la fiche traduit en français s'il est dans une autre langue (langue d'origine dans raw).
    Les noms des interprètes et du studio ne sont pas traduits (Amber, Blue, White…)."""
    if not enabled or ident is None or not (ident.overview or "").strip():
        return ident
    raw = ident.raw or {}
    names = list(raw.get("performers") or []) + [raw.get("site") or ""]
    names += [p.strip() for _, v in (ident.people or []) for p in str(v).split(",")]
    masked, table = protect(ident.overview, names)
    text, lang = to_french(masked)
    text = restore(text, table)
    if lang.startswith("fr") or text == masked:
        text = ident.overview
    if text != ident.overview:
        ident.raw = {**(ident.raw or {}), "overview_original": ident.overview, "overview_lang": lang}
        ident.overview = text
    return ident
