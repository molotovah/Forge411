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
STALE_DAYS = 3                  # sans validation au-delà : « À vérifier sur le site »
CHECK_EVERY = 30 * 60           # secondes entre deux vérifications automatiques
LABELS = {"approved": "Validé", "rejected": "Refusé", "pending": "En attente"}


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
    if not is_published(entry):
        return "—"                                  # brouillon : pas encore soumis à la Team Pending
    st = entry.get("c411_status")
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


def to_check(entries: list) -> list:
    """Infohashes des uploads publiés pas encore validés (un par torrent, l'entrée la plus ancienne en premier)."""
    seen, out = set(), []
    for e in sorted(entries, key=_date):
        ih = str(e.get("infohash", "")).lower()
        if is_published(e) and ih not in seen and e.get("c411_status") != "approved":
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
