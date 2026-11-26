"""
Suivi de la validation des uploads par la Team Pending.

L'API C411 (clé API) ne montre un torrent qu'une fois validé : GET /api/torrents/<infohash> répond 404 tant
qu'il est en attente, en modification demandée, refusé ou supprimé, puis 200 avec status « approved ».
Forge411 interroge donc les uploads publiés pas encore validés et note dans l'historique le statut et l'heure
de validation constatés. Au-delà de quelques jours sans validation, l'upload est signalé « à vérifier » :
une modification a peut-être été demandée (visible seulement sur le site).
"""

import time
from datetime import datetime
from typing import Callable

from .config import update_history

PUBLISHED = ("Publication", "Correction")
DRAFT_DAYS = 30                 # brouillons suivis : publiés depuis le site, leur validation se voit aussi
ORPHAN_DAYS = 7                 # captures et NFO sans upload connu : supprimés passé ce délai
STALE_DAYS = 3                  # sans validation au-delà : « À vérifier sur le site »
CHECK_EVERY = 30 * 60           # secondes entre deux vérifications automatiques
LABELS = {"approved": "Validé", "rejected": "Refusé", "pending": "En attente"}
# Règle C411 : tant que l'uploader n'est pas certifié (15 torrents validés), un seul upload à la fois en attente
# de la Team Pending (« modification demandée » compte comme en attente). L'API ne donne ni le statut certifié ni
# la liste des uploads en attente : Forge411 compte ceux de son historique, complété par un réglage manuel.
CERTIFIED_AT = 15
CLOSED = ("approved", "rejected")


def _date(entry) -> float:
    try:
        return datetime.strptime(entry.get("date", ""), "%Y-%m-%d %H:%M").timestamp()
    except ValueError:
        return 0.0


def is_published(entry) -> bool:
    return entry.get("action") in PUBLISHED and bool(entry.get("infohash"))


def label(entry, now: float = None, since: float = None) -> str:
    """Statut C411 affiché dans l'historique. since : dernière soumission de ce torrent (publication ou
    correction), point de départ du délai « À vérifier » ; par défaut la date de l'entrée."""
    st = entry.get("c411_status")
    if st == "approved":                            # brouillon compris, s'il a été publié depuis le site
        return LABELS[st]
    if not is_published(entry):
        return "—"                                  # brouillon : pas encore soumis à la Team Pending
    if st:
        return LABELS.get(st, st)
    now = now or time.time()
    sent = since if since is not None else _date(entry)
    if sent and now - sent > STALE_DAYS * 86400:
        return "À vérifier"
    return "En attente"


def labels(entries: list, now: float = None) -> list:
    """Statut de chaque entrée, identique pour toutes les lignes d'un même torrent (délai compté depuis la
    dernière soumission : une correction relance l'attente)."""
    last = {}
    for e in entries:
        if is_published(e):
            ih = str(e["infohash"]).lower()
            last[ih] = max(last.get(ih, 0.0), _date(e))
    return [label(e, now, last.get(str(e.get("infohash", "")).lower())) for e in entries]


def is_recent_draft(entry, now: float = None) -> bool:
    """Brouillon envoyé depuis moins de DRAFT_DAYS jours : il a pu être publié depuis la page d'upload du site.
    L'info-hash ne change pas à la publication (source C411 déjà dans le torrent) : le suivre comme un upload."""
    now = now or time.time()
    return ("Brouillon" in (entry.get("action") or "") and bool(entry.get("infohash"))
            and now - _date(entry) < DRAFT_DAYS * 86400)


def to_check(entries: list, now: float = None) -> list:
    """Infohashes à interroger : uploads publiés pas encore validés, et brouillons récents (publiés peut-être
    depuis le site). Un par torrent, l'entrée la plus ancienne en premier."""
    seen, out = set(), []
    for e in sorted(entries, key=_date):
        ih = str(e.get("infohash", "")).lower()
        if (is_published(e) or is_recent_draft(e, now)) and ih not in seen and e.get("c411_status") != "approved":
            seen.add(ih)
            out.append(ih)
    validated = {str(e.get("infohash", "")).lower() for e in entries if e.get("c411_status") == "approved"}
    return [ih for ih in out if ih not in validated]


def check(api, entries: list, save: Callable = update_history, now: float = None) -> list:
    """Interroge C411 pour chaque upload en attente. Renvoie les noms des releases validées depuis la dernière
    vérification. Une erreur réseau sur un torrent n'empêche pas de vérifier les suivants."""
    now = now or time.time()
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
    names = {}
    for e in sorted(entries, key=_date):
        names[str(e.get("infohash", "")).lower()] = e.get("name", "")
    newly = []
    for ih in to_check(entries):
        try:
            d = api.torrent_status(ih)
        except Exception:
            continue
        fields = {"c411_checked": stamp}
        if d is not None:
            st = str(d.get("status") or "approved")
            fields["c411_status"] = st
            if st == "approved":
                fields["c411_validated"] = stamp
                newly.append(names.get(ih) or d.get("name", ""))
            if d.get("rejectionReason"):
                fields["c411_reason"] = str(d["rejectionReason"])
        save(ih, **fields)
    return newly


def approved_count(entries: list) -> int:
    """Torrents validés sur C411 d'après l'historique (un par info-hash), brouillons publiés depuis le site
    compris."""
    return len({str(e.get("infohash", "")).lower() for e in entries
                if e.get("infohash") and e.get("c411_status") == "approved"})


def is_certified(entries: list, declared: bool = False) -> bool:
    return bool(declared) or approved_count(entries) >= CERTIFIED_AT


def waiting(entries: list, exclude: str = "") -> list:
    """Uploads publiés encore entre les mains de la Team Pending (ni validés ni refusés) : [(infohash, nom)],
    le plus ancien d'abord. exclude : torrent en cours de correction (il est déjà compté, il ne bloque pas)."""
    closed = {str(e.get("infohash", "")).lower() for e in entries if e.get("c411_status") in CLOSED}
    out = {}
    for e in sorted(entries, key=_date):
        ih = str(e.get("infohash", "")).lower()
        if is_published(e) and ih not in closed and ih != (exclude or "").lower():
            out.setdefault(ih, e.get("name", ""))
    return list(out.items())


def publish_blocker(entries: list, declared_certified: bool = False, exclude: str = "") -> str:
    """Nom de l'upload en attente qui empêche d'en publier un autre (uploader non certifié), sinon ""."""
    if is_certified(entries, declared_certified):
        return ""
    w = waiting(entries, exclude)
    return w[0][1] or w[0][0] if w else ""


def validated_nfo_files(nfo_root, entries: list) -> list:
    """NFO des torrents validés par C411 : le NFO est en ligne avec le torrent, la copie locale ne sert plus.
    Chemin noté dans l'historique, sinon déduit du nom (entrées antérieures). En attente, le NFO reste (une
    modification demandée peut le faire changer)."""
    from pathlib import Path
    ok = {str(e.get("infohash", "")).lower() for e in entries if e.get("c411_status") == "approved"}
    files = []
    for e in entries:
        if str(e.get("infohash", "")).lower() in ok and e.get("infohash"):
            if e.get("nfo"):
                files.append(Path(e["nfo"]))
            if e.get("name"):
                files.append(Path(nfo_root) / f"{_safe(e['name'])}.nfo")
    return list(dict.fromkeys(files))


def orphans(root, entries: list, keep=(), now: float = None, max_age_days: float = ORPHAN_DAYS,
            suffix: str = "") -> list:
    """Captures (dossiers) ou NFO (suffix=".nfo") de releases inconnues de l'historique et de l'upload en cours,
    plus vieux que max_age_days : uploads abandonnés avant l'envoi, que rien d'autre ne nettoie. keep : noms de
    release à garder (upload en cours)."""
    from pathlib import Path
    root = Path(root)
    if not root.is_dir():
        return []
    now = now or time.time()
    known = {_safe(n) for n in [e.get("name", "") for e in entries] + list(keep) if n}
    known |= {Path(e[k]).name for e in entries for k in ("shots_dir", "nfo") if e.get(k)}
    out = []
    for p in root.iterdir():
        if not (p.suffix.lower() == suffix if suffix else p.is_dir()):
            continue
        name = p.name[:-len(suffix)] if suffix else p.name
        try:
            old = now - p.stat().st_mtime > max_age_days * 86400
        except OSError:
            continue
        if old and name not in known and p.name not in known:
            out.append(p)
    return sorted(out)


def _safe(name: str) -> str:
    return "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip(" .") or "release"


def validated_capture_dirs(captures_root, entries: list) -> list:
    """Dossiers de captures des torrents validés par C411 : les images sont hébergées et leurs liens figurent
    dans la présentation en ligne, la copie locale ne sert plus. En attente, les captures restent (une
    modification demandée peut en réclamer de nouvelles)."""
    from pathlib import Path
    ok = {str(e.get("infohash", "")).lower() for e in entries if e.get("c411_status") == "approved"}
    dirs = []
    for e in entries:
        if str(e.get("infohash", "")).lower() in ok and e.get("infohash"):
            if e.get("shots_dir"):
                dirs.append(Path(e["shots_dir"]))
            if e.get("name"):
                dirs.append(Path(captures_root) / _safe(e["name"]))
    return list(dict.fromkeys(dirs))
