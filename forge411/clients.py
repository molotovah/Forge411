"""
Clients torrent (API web) : ajout du torrent créé et suivi jusqu'au seed.

C411 refuse un torrent publié qui n'est pas déjà seedé : Forge411 ajoute le
.torrent au client avec le dossier parent de la source comme emplacement, le
client vérifie les données puis passe en seed, et la publication peut partir.
"""

import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

from . import USER_AGENT

KINDS = {"": "Aucun", "qbittorrent": "qBittorrent", "transmission": "Transmission", "deluge": "Deluge"}
DEFAULT_URLS = {"qbittorrent": "http://localhost:8080", "transmission": "http://localhost:9091",
                "deluge": "http://localhost:8112"}


class ClientError(Exception):
    pass


@dataclass
class Status:
    state: str = ""            # libellé lisible
    progress: float = 0.0      # 0 à 1 (vérification ou téléchargement)
    seeding: bool = False
    error: str = ""


class _Base:
    name = ""

    def __init__(self, url: str, user: str = "", password: str = "", label: str = ""):
        self.url = (url or "").rstrip("/")
        if not self.url:
            raise ClientError(f"{self.name} : adresse de l'interface web manquante (Paramètres).")
        self.user, self.password, self.label = user or "", password or "", label or ""
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT})

    def _req(self, method, path, **kw):
        try:
            return self.s.request(method, self.url + path, timeout=kw.pop("timeout", 20), **kw)
        except requests.RequestException as e:
            raise ClientError(f"{self.name} injoignable ({self.url}) : {e.__class__.__name__}") from e

    def test(self) -> str:
        raise NotImplementedError

    def add(self, torrent: Path, save_path: Path, infohash: str):
        raise NotImplementedError

    def status(self, infohash: str) -> Optional[Status]:
        raise NotImplementedError


# ═══════════════════════════════════════════════════════════════════════════

class QBittorrent(_Base):
    name = "qBittorrent"
    SEED_STATES = {"uploading", "stalledUP", "queuedUP", "forcedUP", "pausedUP", "stoppedUP"}
    LABELS = {"checkingUP": "Vérification", "checkingDL": "Vérification", "checkingResumeData": "Vérification",
              "uploading": "En seed", "stalledUP": "En seed", "queuedUP": "En file (seed)", "forcedUP": "En seed",
              "pausedUP": "Terminé, en pause", "stoppedUP": "Terminé, arrêté", "downloading": "Données incomplètes",
              "stalledDL": "Données incomplètes", "pausedDL": "En pause", "stoppedDL": "Arrêté",
              "missingFiles": "Fichiers introuvables", "error": "Erreur", "metaDL": "Métadonnées"}

    def _login(self):
        r = self._req("POST", "/api/v2/auth/login", data={"username": self.user, "password": self.password},
                      headers={"Referer": self.url})
        if r.status_code == 403:
            raise ClientError("qBittorrent : trop d'échecs de connexion, adresse IP bannie temporairement.")
        if r.status_code != 200 or r.text.strip() not in ("Ok.", ""):
            raise ClientError("qBittorrent : identifiant ou mot de passe refusé.")

    def _api(self, method, path, **kw):
        r = self._req(method, path, **kw)
        if r.status_code == 403:
            self._login()
            r = self._req(method, path, **kw)
        if r.status_code not in (200, 202):
            raise ClientError(f"qBittorrent : erreur HTTP {r.status_code} ({r.text[:120].strip()}).")
        return r

    def test(self) -> str:
        v = self._api("GET", "/api/v2/app/version").text.strip()
        return f"qBittorrent {v} connecté"

    def add(self, torrent, save_path, infohash):
        data = {"savepath": str(save_path), "skip_checking": "false", "paused": "false", "stopped": "false",
                "autoTMM": "false"}
        if self.label:
            data["category"] = self.label
        with open(torrent, "rb") as f:
            r = self._api("POST", "/api/v2/torrents/add", data=data,
                          files={"torrents": (torrent.name, f, "application/x-bittorrent")})
        if "fail" in r.text.lower():
            raise ClientError("qBittorrent a refusé le torrent (déjà présent ?).")

    def status(self, infohash):
        items = self._api("GET", "/api/v2/torrents/info", params={"hashes": infohash.lower()}).json()
        if not items:
            return None
        t = items[0]
        state = t.get("state", "")
        seeding = state in self.SEED_STATES and float(t.get("progress", 0)) >= 1
        err = "Fichiers introuvables à l'emplacement indiqué." if state == "missingFiles" else \
            ("Erreur du client." if state == "error" else "")
        return Status(self.LABELS.get(state, state), float(t.get("progress", 0)), seeding, err)


# ═══════════════════════════════════════════════════════════════════════════

class Transmission(_Base):
    name = "Transmission"
    STATUS = {0: "Arrêté", 1: "En attente de vérification", 2: "Vérification", 3: "En attente",
              4: "Téléchargement", 5: "En file (seed)", 6: "En seed"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        if self.user:
            self.s.auth = (self.user, self.password)
        self.path = "/transmission/rpc"

    def _rpc(self, method, args=None):
        body = {"method": method, "arguments": args or {}}
        for _ in range(2):
            r = self._req("POST", self.path, json=body)
            if r.status_code == 409:            # jeton de session à reprendre
                self.s.headers["X-Transmission-Session-Id"] = r.headers.get("X-Transmission-Session-Id", "")
                continue
            break
        if r.status_code == 401:
            raise ClientError("Transmission : identifiant ou mot de passe refusé.")
        if r.status_code != 200:
            raise ClientError(f"Transmission : erreur HTTP {r.status_code}.")
        j = r.json()
        if j.get("result") != "success":
            raise ClientError(f"Transmission : {j.get('result')}")
        return j.get("arguments", {})

    def test(self) -> str:
        v = self._rpc("session-get", {"fields": ["version"]}).get("version", "")
        return f"Transmission {v} connecté".strip()

    def add(self, torrent, save_path, infohash):
        args = {"metainfo": base64.b64encode(torrent.read_bytes()).decode(), "download-dir": str(save_path),
                "paused": False}
        if self.label:
            args["labels"] = [self.label]
        self._rpc("torrent-add", args)

    def status(self, infohash):
        ts = self._rpc("torrent-get", {"ids": [infohash.lower()],
                                       "fields": ["status", "percentDone", "recheckProgress", "error", "errorString"]}
                       ).get("torrents", [])
        if not ts:
            return None
        t = ts[0]
        st = int(t.get("status", 0))
        progress = float(t.get("recheckProgress") if st == 2 else t.get("percentDone", 0))
        return Status(self.STATUS.get(st, str(st)), progress, st in (5, 6) and float(t.get("percentDone", 0)) >= 1,
                      t.get("errorString") or "" if t.get("error") else "")


# ═══════════════════════════════════════════════════════════════════════════

class Deluge(_Base):
    name = "Deluge"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._id = 0
        self._ready = False

    def _call(self, method, *params):
        self._id += 1
        r = self._req("POST", "/json", json={"method": method, "params": list(params), "id": self._id})
        if r.status_code != 200:
            raise ClientError(f"Deluge : erreur HTTP {r.status_code}.")
        j = r.json()
        if j.get("error"):
            raise ClientError(f"Deluge : {(j['error'] or {}).get('message', j['error'])}")
        return j.get("result")

    def _connect(self):
        if self._ready:
            return
        if not self._call("auth.login", self.password):
            raise ClientError("Deluge : mot de passe de l'interface web refusé.")
        if not self._call("web.connected"):
            hosts = self._call("web.get_hosts") or []
            if not hosts:
                raise ClientError("Deluge : aucun démon configuré dans l'interface web.")
            self._call("web.connect", hosts[0][0])
        self._ready = True

    def test(self) -> str:
        self._connect()
        return "Deluge connecté"

    def add(self, torrent, save_path, infohash):
        self._connect()
        self._call("core.add_torrent_file", torrent.name, base64.b64encode(torrent.read_bytes()).decode(),
                   {"download_location": str(save_path), "add_paused": False})
        if self.label:
            try:
                self._call("label.set_torrent", infohash.lower(), self.label.lower())
            except ClientError:
                pass                        # extension Label absente : sans conséquence

    def status(self, infohash):
        self._connect()
        t = self._call("core.get_torrent_status", infohash.lower(), ["state", "progress", "message"])
        if not t:
            return None
        state = t.get("state", "")
        labels = {"Checking": "Vérification", "Seeding": "En seed", "Queued": "En file", "Paused": "En pause",
                  "Downloading": "Données incomplètes", "Error": "Erreur"}
        return Status(labels.get(state, state), float(t.get("progress", 0)) / 100, state == "Seeding",
                      t.get("message", "") if state == "Error" else "")


CLASSES = {"qbittorrent": QBittorrent, "transmission": Transmission, "deluge": Deluge}


def map_path(path, local: str = "", remote: str = "") -> str:
    """Chemin vu par le client torrent.

    Pour un client distant (Docker, NAS), le même dossier n'a pas le même chemin des
    deux côtés : « \\\\192.168.1.251\\Torrents\\c411 » pour Windows, « /downloads/c411 » pour le
    conteneur. Sans correspondance (ou hors du dossier indiqué), le chemin reste inchangé."""
    p = str(path)
    local, remote = (local or "").strip(), (remote or "").strip()
    if not local or not remote:
        return p
    norm = lambda s: s.replace("\\", "/").rstrip("/")
    lp, pp = norm(local), norm(p)
    if pp.lower() != lp.lower() and not pp.lower().startswith(lp.lower() + "/"):
        return p
    rest = pp[len(lp):].lstrip("/")
    sep = "\\" if "\\" in remote and "/" not in remote else "/"
    base = remote.rstrip("/\\")
    if not base and sep == "/":                    # client à la racine « / »
        return "/" + rest
    return base + (sep + rest.replace("/", sep) if rest else "")


def save_path(cfg, src_parent) -> str:
    """Dossier des données tel que le client torrent le voit (correspondance des Paramètres)."""
    return map_path(src_parent, cfg.get("client_path_local"), cfg.get("client_path_remote"))


def make(cfg) -> Optional[_Base]:
    """Client configuré dans les Paramètres, ou None."""
    kind = cfg.get("client_kind") or ""
    if kind not in CLASSES:
        return None
    return CLASSES[kind](cfg.get("client_url") or DEFAULT_URLS[kind], cfg.get("client_user"),
                         cfg.get("client_password"), cfg.get("client_label"))


def wait_seeding(client, infohash: str, on_status: Callable[[Status], None], cancel=None,
                 timeout: float = 6 * 3600, interval: float = 3.0) -> Status:
    """Interroge le client jusqu'au seed (ou erreur, annulation, délai dépassé)."""
    start = time.monotonic()
    missing = 0
    while True:
        st = client.status(infohash)
        if st is None:
            missing += 1
            if missing > 10:
                raise ClientError("Le torrent n'apparaît pas dans le client.")
        else:
            on_status(st)
            if st.seeding:
                return st
            if st.error:
                raise ClientError(st.error)
            if st.state in ("Données incomplètes",) and st.progress < 1 and time.monotonic() - start > 60:
                raise ClientError("Le client ne trouve pas toutes les données : vérifie l'emplacement de la source.")
        if cancel is not None and cancel.wait(interval):
            raise ClientError("Suivi annulé.")
        elif cancel is None:
            time.sleep(interval)
        if time.monotonic() - start > timeout:
            raise ClientError("Délai dépassé en attendant le seed.")
