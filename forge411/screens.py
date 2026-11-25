"""
Captures d'écran d'une vidéo (ffmpeg) et envoi vers un hébergeur d'images.

Les hébergeurs proposés figurent dans la liste blanche d'images de C411
(files.catbox.moe, pixhost.to). Pour le contenu adulte, pixhost est utilisé
avec le marquage « adulte » (content_type = 1).
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

from . import USER_AGENT

HOSTS = {"pixhost": "pixhost.to", "catbox": "catbox.moe"}


class ScreenError(Exception):
    pass


@dataclass
class Shot:
    path: Path
    url: str = ""          # image en taille réelle
    thumb: str = ""        # vignette (affichée dans la présentation)
    page: str = ""         # page de l'image chez l'hébergeur


def find_ffmpeg(configured: str = "") -> str:
    """Chemin choisi dans les Paramètres, sinon ffmpeg du PATH, sinon celui installé par Forge411."""
    from .ffmpeg_setup import installed
    managed = installed()
    for c in (configured, shutil.which("ffmpeg"), shutil.which("ffmpeg.exe"), str(managed) if managed else ""):
        if c and Path(c).is_file():
            return c
    return ""


def timestamps(duration_ms: int, count: int) -> list:
    """Instants répartis entre 10 % et 90 % de la durée (évite génériques et écrans noirs)."""
    if duration_ms <= 0 or count <= 0:
        return []
    d = duration_ms / 1000
    if count == 1:
        return [d / 2]
    return [d * (0.1 + 0.8 * i / (count - 1)) for i in range(count)]


def extract(ffmpeg: str, video: Path, duration_ms: int, out_dir: Path, count: int = 4,
            progress: Optional[Callable[[int, int], None]] = None) -> list:
    if not ffmpeg:
        raise ScreenError("ffmpeg introuvable : installe-le ou indique son chemin dans les Paramètres.")
    out_dir.mkdir(parents=True, exist_ok=True)
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    shots = []
    for i, t in enumerate(timestamps(duration_ms, count), 1):
        if progress:
            progress(i, count)
        out = out_dir / f"capture-{i:02d}.png"
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video),
               "-frames:v", "1", "-vf", "scale='min(1920,iw)':-2", str(out)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, creationflags=flags)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ScreenError(f"ffmpeg : {e}") from e
        if r.returncode != 0 or not out.is_file():
            raise ScreenError(f"ffmpeg n'a pas pu extraire la capture {i} : {r.stderr.strip()[:200]}")
        shots.append(Shot(out))
    return shots


def upload(shot: Shot, host: str, adult: bool = False) -> Shot:
    """Envoie la capture ; renseigne url, thumb et page."""
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        with open(shot.path, "rb") as f:
            if host == "pixhost":
                r = requests.post("https://api.pixhost.to/images", headers=h, timeout=120,
                                  data={"content_type": "1" if adult else "0", "max_th_size": "350"},
                                  files={"img": (shot.path.name, f, "image/png")})
                if r.status_code != 200:
                    raise ScreenError(f"pixhost : erreur HTTP {r.status_code}.")
                j = r.json()
                shot.page, shot.thumb = j.get("show_url", ""), j.get("th_url", "")
                shot.url = shot.thumb.replace("://t", "://img", 1).replace("/thumbs/", "/images/")
            else:
                r = requests.post("https://catbox.moe/user/api.php", headers=h, timeout=120,
                                  data={"reqtype": "fileupload"}, files={"fileToUpload": (shot.path.name, f, "image/png")})
                url = r.text.strip()
                if r.status_code != 200 or not url.startswith("https://files.catbox.moe/"):
                    raise ScreenError(f"catbox : envoi refusé ({r.status_code} {url[:80]}).")
                shot.url = shot.thumb = shot.page = url
    except requests.RequestException as e:
        raise ScreenError(f"{HOSTS.get(host, host)} injoignable : {e.__class__.__name__}") from e
    except ValueError as e:
        raise ScreenError(f"{HOSTS.get(host, host)} : réponse illisible.") from e
    return shot


def bbcode(shots: list) -> str:
    """Bloc BBCode : vignettes cliquables vers l'image en grand."""
    cells = []
    for s in shots:
        if s.thumb and s.thumb != s.url:
            cells.append(f"[url={s.page or s.url}][img]{s.thumb}[/img][/url]")
        elif s.url:
            cells.append(f"[img]{s.url}[/img]")
    if not cells:
        return ""
    return "\n[b]CAPTURES[/b]\n[center]" + " ".join(cells) + "[/center]\n"
