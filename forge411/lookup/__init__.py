"""Bases de données en ligne : outils HTTP communs."""

import threading
import time

import requests

from .. import USER_AGENT


class LookupFailed(Exception):
    """Erreur lisible par l'utilisateur."""


class Http:
    """Session requests avec User-Agent, délai minimal entre appels et erreurs lisibles."""

    def __init__(self, name: str, base: str, min_interval: float = 0.0, headers: dict = None):
        self.name = name
        self.base = base
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        if headers:
            self.s.headers.update(headers)
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()

    def get(self, path: str, **params) -> dict:
        with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
        url = path if path.startswith("http") else f"{self.base}{path}"
        for attempt in range(3):
            try:
                r = self.s.get(url, params=params, timeout=20)
            except requests.RequestException as e:
                if attempt == 2:
                    raise LookupFailed(f"{self.name} injoignable : {e.__class__.__name__}") from e
                time.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code in (429, 502, 503, 504) and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            break
        if r.status_code in (401, 403):
            raise LookupFailed(f"{self.name} : clé refusée ({r.status_code}).")
        if r.status_code == 404:
            raise LookupFailed(f"{self.name} : introuvable.")
        if r.status_code == 429:
            raise LookupFailed(f"{self.name} : trop de requêtes, réessaie dans un instant.")
        if r.status_code != 200:
            raise LookupFailed(f"{self.name} : erreur HTTP {r.status_code}.")
        try:
            return r.json()
        except ValueError as e:
            raise LookupFailed(f"{self.name} : réponse illisible.") from e


def fetch_image(url: str) -> bytes:
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
            if r.status_code in (429, 502, 503, 504) and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
