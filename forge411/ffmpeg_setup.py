"""
Installation de ffmpeg à la demande (Windows 64 bits).

Source : builds officiels FFmpeg-Builds publiés sur GitHub (version stable, LGPL,
« shared »). L'archive est vérifiée avec l'empreinte SHA-256 publiée par GitHub,
puis seuls ffmpeg.exe et ses DLL sont extraits dans le dossier de Forge411.
"""

import hashlib
import os
import re
import shutil
import sys
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

from . import USER_AGENT
from .config import config_dir

API = "https://api.github.com/repos/FFmpeg-Builds/FFmpeg-Builds/releases/latest"
ASSET_RE = re.compile(r"^ffmpeg-n(\d+(?:\.\d+)*)-latest-win64-lgpl-shared-\1\.zip$")


class SetupError(Exception):
    pass


@dataclass
class Asset:
    name: str
    version: str
    url: str
    size: int
    sha256: str


def install_dir() -> Path:
    return config_dir() / "ffmpeg"


def installed() -> Optional[Path]:
    exe = install_dir() / "ffmpeg.exe"
    return exe if exe.is_file() else None


def installed_version() -> str:
    try:
        return (install_dir() / "version.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def supported() -> bool:
    return sys.platform == "win32"


def _version_key(v: str) -> tuple:
    return tuple(int(x) for x in v.split("."))


def pick(assets: list) -> Asset:
    """Archive stable la plus récente (win64, LGPL, shared) avec son empreinte."""
    found = []
    for a in assets:
        m = ASSET_RE.match(a.get("name", ""))
        digest = a.get("digest") or ""
        if m and digest.startswith("sha256:"):
            found.append(Asset(a["name"], m.group(1), a["browser_download_url"], int(a.get("size") or 0),
                               digest.split(":", 1)[1].lower()))
    if not found:
        raise SetupError("Aucune archive ffmpeg Windows vérifiable dans la dernière publication.")
    return max(found, key=lambda x: _version_key(x.version))


def latest() -> Asset:
    try:
        r = requests.get(API, timeout=20, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    except requests.RequestException as e:
        raise SetupError(f"GitHub injoignable : {e.__class__.__name__}") from e
    if r.status_code != 200:
        raise SetupError(f"GitHub : erreur HTTP {r.status_code}.")
    return pick(r.json().get("assets", []))


def extract(archive: Path, dest: Path) -> Path:
    """Extrait bin/ffmpeg.exe et bin/*.dll (à plat : aucun chemin de l'archive n'est suivi)."""
    tmp = dest.with_name(dest.name + ".new")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            parts = info.filename.replace("\\", "/").split("/")
            name = parts[-1]
            if len(parts) < 2 or parts[-2] != "bin" or not name:
                continue
            if name.lower() != "ffmpeg.exe" and not name.lower().endswith(".dll"):
                continue
            with z.open(info) as src, open(tmp / name, "wb") as out:
                shutil.copyfileobj(src, out)
    if not (tmp / "ffmpeg.exe").is_file():
        shutil.rmtree(tmp, ignore_errors=True)
        raise SetupError("ffmpeg.exe absent de l'archive.")
    old = dest.with_name(dest.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if dest.exists():
        os.replace(dest, old)
    os.replace(tmp, dest)
    shutil.rmtree(old, ignore_errors=True)
    return dest / "ffmpeg.exe"


def install(progress: Callable[[int, int], None] = None, cancel: Optional[threading.Event] = None,
            asset: Optional[Asset] = None) -> Path:
    """Télécharge, vérifie et installe ffmpeg ; renvoie le chemin de ffmpeg.exe."""
    asset = asset or latest()
    dest = install_dir()
    part = dest.with_name("ffmpeg-download.zip.part")
    h = hashlib.sha256()
    done = 0
    try:
        with requests.get(asset.url, stream=True, timeout=60, headers={"User-Agent": USER_AGENT}) as r:
            if r.status_code != 200:
                raise SetupError(f"Téléchargement refusé : HTTP {r.status_code}.")
            with open(part, "wb") as f:
                for chunk in r.iter_content(512 * 1024):
                    if cancel is not None and cancel.is_set():
                        raise SetupError("Installation annulée.")
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, asset.size)
        if asset.size and done != asset.size:
            raise SetupError(f"Archive incomplète ({done} octets sur {asset.size}).")
        if h.hexdigest() != asset.sha256:
            raise SetupError("Empreinte SHA-256 différente de celle publiée : archive rejetée.")
        exe = extract(part, dest)
        (dest / "version.txt").write_text(f"{asset.version} ({asset.name})\n", encoding="utf-8")
        return exe
    except requests.RequestException as e:
        raise SetupError(f"Téléchargement interrompu : {e.__class__.__name__}") from e
    finally:
        part.unlink(missing_ok=True)
