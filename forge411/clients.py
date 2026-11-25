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

    def default_dir(self) -> str:
        """Dossier de téléchargement par défaut du client (aide à la correspondance des chemins)."""
        return ""


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
        # qBittorrent 4.x : 200 « Ok. » ou « Fails. » ; 5.x : 204 sans contenu, cookie QBT_SID_<port>
        if r.status_code not in (200, 204) or r.text.strip() not in ("Ok.", ""):
            raise ClientError("qBittorrent : identifiant ou mot de passe refusé.")

    def _api(self, method, path, **kw):
        r = self._req(method, path, **kw)
        if r.status_code == 403:
            self._login()
            r = self._req(method, path, **kw)
        if not 200 <= r.status_code < 300:
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
        # Octets et non fichier ouvert : après un 403 (session expirée), _api rejoue la
        # requête, et un fichier déjà lu partirait vide (HTTP 415 « not a valid torrent file »).
        try:
            r = self._api("POST", "/api/v2/torrents/add", data=data,
                          files={"torrents": (Path(torrent).name, Path(torrent).read_bytes(),
                                              "application/x-bittorrent")})
        except ClientError as e:
            if "HTTP 409" in str(e):               # qBittorrent 5.x : torrent déjà présent
                raise ClientError("qBittorrent a refusé le torrent (déjà présent ?).") from e
            raise
        if "fail" in r.text.lower():
            raise ClientError("qBittorrent a refusé le torrent (déjà présent ?).")

    def default_dir(self):
        try:
            return self._api("GET", "/api/v2/app/defaultSavePath").text.strip()
        except ClientError:
            return ""

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

    def default_dir(self):
        try:
            return self._rpc("session-get", {"fields": ["download-dir"]}).get("download-dir", "")
        except ClientError:
            return ""

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

    def default_dir(self):
        try:
            self._connect()
            return self._call("core.get_config_value", "download_location") or ""
        except ClientError:
            return ""

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


# ═══════════════════════════════════════════════════════════════════════════
# Aide à la configuration
# ═══════════════════════════════════════════════════════════════════════════

ENABLE_HELP = {
    "qbittorrent": "qBittorrent : Outils › Options › Interface web › cocher « Interface utilisateur Web » "
                   "(port 8080 par défaut), puis renseigner un identifiant et un mot de passe.",
    "transmission": "Transmission : Édition › Préférences › Distant › « Autoriser l'accès distant » (port 9091).",
    "deluge": "Deluge : lancer deluge-web (port 8112) ; seul le mot de passe de l'interface web est demandé.",
}


def is_local(url: str) -> bool:
    from urllib.parse import urlparse
    h = (urlparse(url or "").hostname or "").lower()
    return h in ("", "localhost", "127.0.0.1", "::1")


def unc_host(path: str) -> str:
    """Machine d'un chemin réseau Windows (\\\\NAS\\partage\\…), sinon chaîne vide."""
    p = (path or "").replace("/", "\\")
    return p[2:].split("\\", 1)[0] if p.startswith("\\\\") else ""


def probe(url: str, timeout: float = 0.8) -> str:
    """Type de client qui répond à cette adresse (« qbittorrent », « transmission », « deluge »), sinon ""."""
    url = url.rstrip("/")
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    try:
        r = s.get(url + "/api/v2/app/version", timeout=timeout)
        # qBittorrent : « v4.6.2 » (accès sans mot de passe) ou 403 « Forbidden » (connexion requise)
        if (r.status_code == 200 and r.text.strip().startswith("v")) or \
                (r.status_code == 403 and r.text.strip() == "Forbidden"):
            return "qbittorrent"
    except requests.RequestException:
        return ""
    try:
        r = s.post(url + "/transmission/rpc", timeout=timeout)
        if r.status_code in (401, 409) and ("X-Transmission-Session-Id" in r.headers or "Transmission" in r.text):
            return "transmission"
        r = s.post(url + "/json", json={"method": "auth.check_session", "params": [], "id": 1}, timeout=timeout)
        if r.status_code == 200 and "result" in r.text:
            return "deluge"
    except requests.RequestException:
        pass
    return ""


def detect(hosts: list) -> list:
    """Clients joignables sur ces machines, ports par défaut : [(type, adresse)]."""
    from concurrent.futures import ThreadPoolExecutor
    ports = {"qbittorrent": (8080, 8090), "transmission": (9091,), "deluge": (8112,)}
    urls = list(dict.fromkeys(f"http://{h}:{p}" for h in hosts if h for ps in ports.values() for p in ps))
    with ThreadPoolExecutor(8) as ex:
        kinds = list(ex.map(probe, urls))
    return [(k, u) for k, u in zip(kinds, urls) if k]


def suggest_mapping(seed_dir: str, client_dir: str) -> tuple:
    """Correspondance proposée pour un client distant : (dossier vu par Windows, même dossier vu par le client).

    Partage réseau \\\\NAS\\Torrents\\… et client sur /downloads/… : le partage correspond au premier
    dossier du client (/downloads). Rien si le dossier de seed n'est pas un partage réseau."""
    p = (seed_dir or "").replace("/", "\\")
    if not unc_host(p) or not client_dir:
        return "", ""
    parts = p[2:].split("\\")
    if len(parts) < 2:
        return "", ""
    local = "\\\\" + "\\".join(parts[:2])
    cd = client_dir.replace("\\", "/")
    if cd.startswith("/"):
        first = cd.strip("/").split("/")[0]
        remote = "/" + first if first else "/"
    else:
        remote = cd.rstrip("\\/")
    return local, remote
