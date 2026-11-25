"""
Mises à jour : dernière release GitHub, téléchargement vérifié et remplacement de l'exécutable.

Sous Windows (exécutable compilé), la nouvelle version est téléchargée à côté de
Forge411.exe, contrôlée (taille + SHA-256 publié par GitHub), puis un petit
script attend la fermeture de l'application, échange les fichiers et relance.
Depuis les sources, l'application indique seulement la nouvelle version.
"""

import hashlib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

from . import REPO_URL, USER_AGENT, __version__

REPO = REPO_URL.rstrip("/").split("github.com/", 1)[1]
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"{REPO_URL}/releases"
ASSET_NAME = "Forge411.exe"


class UpdateError(Exception):
    pass


@dataclass
class Release:
    version: str
    tag: str
    notes: str
    page: str
    asset_url: str = ""
    asset_size: int = 0
    sha256: str = ""                # empreinte publiée par GitHub (vide si absente)


def parse_version(v: str) -> tuple:
    """« v1.2.3 » → (1, 2, 3) ; les suffixes (-beta…) sont ignorés."""
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)", v or "")
    if not m:
        return ()
    parts = [int(x) for x in m.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def is_newer(remote: str, local: str = __version__) -> bool:
    r = parse_version(remote)
    return bool(r) and r > parse_version(local)


def latest() -> Release:
    """Dernière release publiée (hors brouillons et préversions)."""
    try:
        r = requests.get(API_LATEST, timeout=15,
                         headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    except requests.RequestException as e:
        raise UpdateError(f"GitHub injoignable : {e.__class__.__name__}") from e
    if r.status_code == 404:
        raise UpdateError("Aucune release publiée.")
    if r.status_code == 403:
        raise UpdateError("GitHub limite les requêtes : réessaie dans une heure.")
    if r.status_code != 200:
        raise UpdateError(f"GitHub : erreur HTTP {r.status_code}.")
    try:
        j = r.json()
    except ValueError as e:
        raise UpdateError("GitHub : réponse illisible.") from e
    tag = j.get("tag_name") or ""
    rel = Release(version=tag.lstrip("vV"), tag=tag, notes=(j.get("body") or "").strip(),
                  page=j.get("html_url") or RELEASES_URL)
    asset = next((a for a in j.get("assets", []) if a.get("name") == ASSET_NAME), None)
    if asset:
        rel.asset_url = asset.get("browser_download_url") or ""
        rel.asset_size = int(asset.get("size") or 0)
        digest = asset.get("digest") or ""
        if digest.startswith("sha256:"):
            rel.sha256 = digest.split(":", 1)[1].lower()
    return rel


def check() -> Optional[Release]:
    """Release plus récente que la version en cours, sinon None."""
    rel = latest()
    return rel if is_newer(rel.version) else None


# ═══════════════════════════════════════════════════════════════════════════
# Installation (exécutable Windows)
# ═══════════════════════════════════════════════════════════════════════════

def current_exe() -> Optional[Path]:
    """Chemin de Forge411.exe si l'application tourne en exécutable compilé, sinon None."""
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        return Path(sys.executable).resolve()
    return None


def self_update_blocker(rel: Release) -> str:
    """Raison pour laquelle l'installation automatique est impossible (chaîne vide sinon)."""
    exe = current_exe()
    if not exe:
        return "Lancé depuis les sources : mets à jour avec git pull ou télécharge la release."
    if not rel.asset_url:
        return f"La release {rel.tag} ne contient pas {ASSET_NAME}."
    if re.search(r'[%"^!]', str(exe)):
        return "Le chemin de Forge411.exe contient un caractère spécial : installe la mise à jour à la main."
    if not os.access(exe.parent, os.W_OK):
        return f"Pas de droit d'écriture dans {exe.parent} : installe la mise à jour à la main."
    return ""


def download(rel: Release, dest: Path, progress: Callable[[int, int], None] = None) -> Path:
    """Télécharge l'exécutable dans dest et vérifie taille et SHA-256."""
    tmp = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    done = 0
    try:
        with requests.get(rel.asset_url, stream=True, timeout=60, headers={"User-Agent": USER_AGENT}) as r:
            if r.status_code != 200:
                raise UpdateError(f"Téléchargement refusé : HTTP {r.status_code}.")
            total = int(r.headers.get("Content-Length") or rel.asset_size or 0)
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(256 * 1024):
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except requests.RequestException as e:
        tmp.unlink(missing_ok=True)
        raise UpdateError(f"Téléchargement interrompu : {e.__class__.__name__}") from e
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if rel.asset_size and done != rel.asset_size:
        tmp.unlink(missing_ok=True)
        raise UpdateError(f"Fichier incomplet ({done} octets sur {rel.asset_size}).")
    if rel.sha256 and h.hexdigest() != rel.sha256:
        tmp.unlink(missing_ok=True)
        raise UpdateError("Empreinte SHA-256 différente de celle publiée sur GitHub : fichier rejeté.")
    with open(tmp, "rb") as f:
        if f.read(2) != b"MZ":
            tmp.unlink(missing_ok=True)
            raise UpdateError("Le fichier téléchargé n'est pas un exécutable Windows.")
    os.replace(tmp, dest)
    return dest


def swap_script(exe: Path, new: Path, pids: list) -> str:
    """Script batch : attend la fin des processus, remplace l'exécutable, relance."""
    old = exe.with_name(exe.name + ".old")
    waits = "\n".join(
        f':wait{p}\ntasklist /FI "PID eq {p}" /NH 2>NUL | find " {p} " >NUL || goto done{p}\n'
        f'set /a n+=1\nif %n% GEQ 120 goto done{p}\nping -n 2 127.0.0.1 >NUL\ngoto wait{p}\n:done{p}'
        for p in pids)
    return f"""@echo off
setlocal
set n=0
{waits}
set n=0
:swap
del /F /Q "{old}" >NUL 2>&1
move /Y "{exe}" "{old}" >NUL 2>&1 && goto place
set /a n+=1
if %n% GEQ 30 goto fail
ping -n 2 127.0.0.1 >NUL
goto swap
:place
move /Y "{new}" "{exe}" >NUL 2>&1 || (move /Y "{old}" "{exe}" >NUL 2>&1 & goto fail)
start "" "{exe}"
ping -n 4 127.0.0.1 >NUL
del /F /Q "{old}" >NUL 2>&1
goto end
:fail
start "" "{exe}"
:end
(goto) 2>NUL & del "%~f0"
"""


def install(new: Path):
    """Lance l'échange des fichiers ; l'application doit se fermer juste après."""
    exe = current_exe()
    if not exe:
        raise UpdateError("Installation automatique réservée à l'exécutable Windows.")
    # Exécutable « onefile » : le chargeur (processus parent) verrouille le .exe jusqu'à la fin.
    pids = [os.getpid()]
    if Path(getattr(sys, "_MEIPASS", exe.parent)).resolve() != exe.parent:
        pids.append(os.getppid())
    fd, script = tempfile.mkstemp(prefix="forge411-update-", suffix=".cmd")
    with os.fdopen(fd, "w", encoding="mbcs", newline="\r\n") as f:
        f.write(swap_script(exe, new, pids))
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")   # la nouvelle instance extrait ses propres fichiers
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(["cmd.exe", "/c", script], creationflags=flags, close_fds=True, env=env,
                     cwd=str(exe.parent))
