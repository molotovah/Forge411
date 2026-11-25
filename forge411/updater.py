"""
Mises à jour : dernière release GitHub, téléchargement vérifié et remplacement de l'exécutable.

Sous Windows (exécutable compilé), la nouvelle version est téléchargée à côté de
Forge411.exe et contrôlée (taille + SHA-256 publié par GitHub). Elle est ensuite
lancée : elle attend la fermeture de l'ancienne, se copie à sa place et relance
Forge411.exe, qui supprime le fichier téléchargé. Aucun script intermédiaire.
Depuis les sources, l'application indique seulement la nouvelle version.
"""

import hashlib
import os
import re
import subprocess
import sys
import time
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


def changelog_sections(text: str, newer_than: str = __version__, up_to: str = "") -> list:
    """Sections « ## [x.y.z] - date » du CHANGELOG plus récentes que newer_than (jusqu'à up_to) :
    [(version, date, texte)], de la plus récente à la plus ancienne."""
    out = []
    parts = re.split(r"^## \[([^\]]+)\](?:\s*-\s*(\S+))?\s*$", text or "", flags=re.M)
    for i in range(1, len(parts) - 2, 3):
        version, date, body = parts[i], parts[i + 1] or "", parts[i + 2].strip()
        if not parse_version(version) or parse_version(version) <= parse_version(newer_than):
            continue
        if up_to and parse_version(version) > parse_version(up_to):
            continue
        out.append((version, date, body))
    return out


def changelog(rel: Release) -> list:
    """Nouveautés depuis la version installée, lues dans le CHANGELOG du tag publié
    (repli : notes de la release GitHub)."""
    try:
        r = requests.get(f"https://raw.githubusercontent.com/{REPO}/{rel.tag}/CHANGELOG.md", timeout=15,
                         headers={"User-Agent": USER_AGENT})
        if r.status_code == 200:
            secs = changelog_sections(r.text, __version__, rel.version)
            if secs:
                return secs
    except requests.RequestException:
        pass
    return [(rel.version, "", rel.notes or "Pas de notes de version.")]


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
    _retry(lambda: os.replace(tmp, dest), "l'antivirus garde le fichier téléchargé")
    return dest


def _retry(fn, what: str, tries: int = 180, delay: float = 0.5):
    """Microsoft Defender peut retenir un nouvel exécutable le temps d'une analyse (jusqu'à ~1 min)."""
    for i in range(tries):
        try:
            return fn()
        except PermissionError as e:
            last = e
            time.sleep(delay)
    raise UpdateError(f"Mise à jour bloquée : {what} ({last}). Réessaie dans un instant.")


def wait_scanned(path: Path, progress: Callable[[str], None] = None):
    """Attend que le fichier soit lisible en exclusivité (fin de l'analyse antivirus)."""
    if progress:
        progress("Vérification par l'antivirus Windows…")

    def probe():
        with open(path, "r+b"):
            pass
    _retry(probe, "l'antivirus analyse encore la nouvelle version")


UPDATE_NAME = "Forge411.update.exe"          # nouvelle version téléchargée à côté de Forge411.exe


def _wait_pids(pids: list, timeout: float = 90.0):
    """Attend la fin des processus (Windows : WaitForSingleObject ; ailleurs : sondage)."""
    deadline = time.monotonic() + timeout
    if sys.platform == "win32":
        import ctypes
        k32 = ctypes.windll.kernel32
        for pid in pids:
            h = k32.OpenProcess(0x00100000, False, int(pid))          # SYNCHRONIZE
            if not h:
                continue                                              # déjà terminé
            try:
                k32.WaitForSingleObject(h, max(0, int((deadline - time.monotonic()) * 1000)))
            finally:
                k32.CloseHandle(h)
        return
    for pid in pids:
        while time.monotonic() < deadline:
            try:
                os.kill(int(pid), 0)
            except OSError:
                break
            time.sleep(0.3)


def _launch(exe: Path, *args: str):
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")   # chaque instance extrait ses propres fichiers
    flags = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(exe), *args], env=env, close_fds=True, cwd=str(exe.parent), creationflags=flags)


def install(new: Path):
    """Lance la nouvelle version en mode « fin de mise à jour » ; l'application doit se fermer juste après.

    Aucun script : la nouvelle version attend la fin de l'ancienne, se copie à sa place,
    relance Forge411.exe puis est supprimée par celui-ci."""
    exe = current_exe()
    if not exe:
        raise UpdateError("Installation automatique réservée à l'exécutable Windows.")
    # Exécutable « onefile » : le chargeur (processus parent) verrouille le .exe jusqu'à la fin.
    pids = [os.getpid()]
    if Path(getattr(sys, "_MEIPASS", exe.parent)).resolve() != exe.parent:
        pids.append(os.getppid())
    try:
        _launch(new, "--finish-update", str(exe), *map(str, pids))
    except OSError as e:
        raise UpdateError(f"Lancement de la nouvelle version impossible : {e}") from e


def finish_update(args: list) -> int:
    """Exécuté par la nouvelle version : remplace Forge411.exe par elle-même puis le relance."""
    import logging
    import shutil
    target, pids = Path(args[0]), args[1:]
    _wait_pids(pids)
    me = Path(sys.executable).resolve()
    tmp = target.with_name(target.name + ".new")
    for _ in range(60):                       # antivirus ou explorateur : le fichier peut rester pris un moment
        try:
            shutil.copyfile(me, tmp)
            os.replace(tmp, target)
            break
        except OSError as e:
            last = e
            time.sleep(0.5)
    else:
        logging.error("Mise à jour : remplacement de %s impossible (%s)", target, last)
        try:
            tmp.unlink()
        except OSError:
            pass
        _launch(me)                           # la nouvelle version démarre quand même, depuis son propre fichier
        return 1
    _launch(target, "--cleanup-update", str(me))
    return 0


def cleanup_update(path: str):
    """Supprime l'exécutable temporaire de la mise à jour (en tâche de fond, il peut être encore ouvert)."""
    import threading

    def work():
        p = Path(path)
        if p.name.lower() != UPDATE_NAME.lower():
            return
        for _ in range(60):
            try:
                p.unlink()
                return
            except FileNotFoundError:
                return
            except OSError:
                time.sleep(0.5)
    threading.Thread(target=work, daemon=True).start()
