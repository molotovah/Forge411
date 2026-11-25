"""
Configuration persistante (JSON) et historique des uploads.

Stockage : %APPDATA%/Forge411 (Windows), ~/Library/Application Support
(macOS) ou ~/.config (Linux).
"""

import json
import os
import sys
import threading
import time
from pathlib import Path


APP_DIR_NAME = "Forge411"


def config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", str(Path.home()))
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    d = Path(base) / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_PATH = config_dir() / "config.json"
HISTORY_PATH = config_dir() / "history.jsonl"
SESSION_PATH = config_dir() / "session.pkl"               # upload en cours (reprise)
UPLOADS_DIR = config_dir() / "uploads"                    # copie de chaque upload envoyé (corrections)
PROFILE_HISTORY_PATH = config_dir() / "profile-history.jsonl"

DEFAULTS = {
    "c411_api_key": "",
    "tmdb_api_key": "",
    "rawg_api_key": "",
    "google_books_key": "",
    "tpdb_api_key": "",
    "tracker_url": "",
    # Tag de ton équipe, proposé quand la source n'a pas de tag (tes propres releases)
    "team_tag": "",
    "team_tag_auto": True,
    # Dossier où l'app écrit .torrent et .nfo
    "output_dir": str(Path.home() / "Forge411"),
    # Dossier où le client torrent attend les données à seeder (optionnel)
    "seed_dir": "",
    "uploader_note": "",
    "window_geometry": "",
    "tour_done": False,
    # Mises à jour : vérification au démarrage, version ignorée par l'utilisateur
    "check_updates": True,
    "translate_overview": True,  # résumés traduits en français (Google Traduction, sans compte)
    "skip_version": "",
    # Apparence : system | dark | light
    "theme": "dark",
    "theme_chosen": False,      # vrai dès que l'utilisateur a choisi un thème dans les Paramètres
    # Client torrent (API web) : qbittorrent | transmission | deluge
    "client_kind": "",
    "client_url": "",
    "client_user": "",
    "client_password": "",
    "client_label": "C411",
    "client_auto": True,        # ajouter le torrent au client dès sa création
    # Client distant (Docker, NAS) : même dossier vu par Forge411 et par le client
    "client_path_local": "",    # ex. \\192.168.1.251\Torrents
    "client_path_remote": "",   # ex. /downloads
    # Captures d'écran
    "ffmpeg_path": "",
    "screens_count": 4,
    "screens_host": "pixhost",
}

# Pages où récupérer chaque clé (liens cliquables dans l'application)
KEY_LINKS = {
    "c411_api_key": ("Créer une clé API sur C411", "https://c411.org/user/integrations"),
    "tracker_url": ("Trouver ton URL d'annonce (ton profil)", "https://c411.org/user/profile"),
    "tmdb_api_key": ("Obtenir une clé TMDB (gratuite)", "https://www.themoviedb.org/settings/api"),
    "rawg_api_key": ("Obtenir une clé RAWG (gratuite)", "https://rawg.io/apidocs"),
    "tpdb_api_key": ("Créer un jeton ThePornDB", "https://theporndb.net/user/api-tokens"),
    "google_books_key": ("Obtenir une clé Google Books (facultatif)",
                         "https://developers.google.com/books/docs/v1/using#APIKey"),
}

# Clés d'anciennes versions, retirées au chargement
_OBSOLETE = {"radarr_url", "radarr_api_key", "qb_url", "qb_user", "qb_pass",
             "source_tag", "auto_tmdb", "max_uploads", "piece_length_kb"}


class Config:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self._data = dict(DEFAULTS)
        self._lock = threading.Lock()
        self.load()

    def load(self):
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    self._data.update({k: v for k, v in saved.items()
                                       if k not in _OBSOLETE})
                    if not saved.get("theme_chosen"):      # jamais choisi : sombre par défaut
                        self._data["theme"] = "dark"
            except (OSError, ValueError):
                pass

    def save(self):
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False),
                           encoding="utf-8")
            os.replace(tmp, self.path)

    def get(self, key: str, default=None):
        v = self._data.get(key, DEFAULTS.get(key, default))
        return v.strip() if isinstance(v, str) else v

    def set(self, key: str, value):
        self._data[key] = value

    def update(self, values: dict):
        self._data.update(values)
        self.save()

    # ── Dossiers ──────────────────────────────────────────────────────────
    def _sub(self, name: str) -> Path:
        d = Path(self.get("output_dir") or DEFAULTS["output_dir"]) / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def torrents_dir(self) -> Path:
        return self._sub("torrents")

    @property
    def nfo_dir(self) -> Path:
        return self._sub("nfo")

    @property
    def is_configured(self) -> bool:
        return bool(self.get("c411_api_key") and self.get("tracker_url"))


def migrate_legacy():
    """Reprend la configuration de C411 Uploader si Forge411 n'en a pas encore."""
    if CONFIG_PATH.exists():
        return
    legacy = config_dir().parent / "C411Uploader" / "config.json"
    if legacy.exists():
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
            keep = {k: v for k, v in data.items() if k in DEFAULTS and k != "window_geometry"}
            CONFIG_PATH.write_text(json.dumps(keep, indent=2, ensure_ascii=False), encoding="utf-8")
        except (OSError, ValueError):
            pass


def add_history(entry: dict):
    entry = {"date": time.strftime("%Y-%m-%d %H:%M"), **entry}
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_history() -> list:
    if not HISTORY_PATH.exists():
        return []
    out = []
    for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return list(reversed(out))
