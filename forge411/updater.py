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


def _wait_pids(pids: list, timeout: float = 90.0, terminate: bool = False):
    """Attend la fin des processus (Windows : WaitForSingleObject ; ailleurs : sondage).

    terminate : l'ancienne version a déjà sauvegardé l'upload en cours avant de se fermer ; si elle reste
    bloquée (cas des versions ≤ 2.1.1), elle est arrêtée pour libérer Forge411.exe."""
    deadline = time.monotonic() + timeout
    if sys.platform == "win32":
        import ctypes
        k32 = ctypes.windll.kernel32
        for pid in pids:
            h = k32.OpenProcess(0x00100000 | 0x0001, False, int(pid))   # SYNCHRONIZE | PROCESS_TERMINATE
            if not h:
                h = k32.OpenProcess(0x00100000, False, int(pid))
            if not h:
                continue                                              # déjà terminé
            try:
                if k32.WaitForSingleObject(h, max(0, int((deadline - time.monotonic()) * 1000))) != 0 and terminate:
                    k32.TerminateProcess(h, 0)
                    k32.WaitForSingleObject(h, 5000)
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


def ready_marker() -> Path:
    """Fichier créé par la nouvelle version dès que sa fenêtre est affichée."""
    from .config import config_dir
    return config_dir() / "update-ready.flag"


def _swap(target: Path, pids: list, status: Callable[[str], None], wait: float = 90.0) -> bool:
    import logging
    import shutil
    status("Fermeture de l'ancienne version…")
    _wait_pids(pids, wait, terminate=True)
    me = Path(sys.executable).resolve()
    tmp = target.with_name(target.name + ".new")
    status("Installation de la nouvelle version…")
    last = None
    for _ in range(60):                       # antivirus ou explorateur : le fichier peut rester pris un moment
        try:
            shutil.copyfile(me, tmp)
            os.replace(tmp, target)
            return True
        except OSError as e:
            last = e
            time.sleep(0.5)
    logging.error("Mise à jour : remplacement de %s impossible (%s)", target, last)
    try:
        tmp.unlink()
    except OSError:
        pass
    return False


def finish_update(args: list, window: bool = True) -> int:
    """Exécuté par la nouvelle version : remplace Forge411.exe par elle-même puis le relance.
    Une petite fenêtre suit l'opération jusqu'à l'ouverture de la nouvelle version."""
    target, pids = Path(args[0]), args[1:]
    me = Path(sys.executable).resolve()
    marker = ready_marker()
    try:
        marker.unlink()
    except OSError:
        pass
    ui = _Splash() if window else None
    result = {}

    def work(retry=False):
        ok = _swap(target, pids, ui.status if ui else (lambda t: None), 5.0 if retry else 15.0)
        result["ok"] = ok
        if not ok and ui:                     # Forge411.exe encore ouvert : on l'explique et on propose de réessayer
            ui.failed(f"Impossible de remplacer {target.name} : une fenêtre de Forge411 est sans doute encore "
                      "ouverte. Ferme-la, puis clique sur Réessayer.",
                      retry=lambda: threading.Thread(target=work, args=(True,), daemon=True).start(),
                      fallback=lambda: (_launch(me), ui.close()))
            return
        if ui:
            ui.status("Ouverture de Forge411…")
        if ok:
            _launch(target, "--cleanup-update", str(me))
        else:
            _launch(me)                       # sans fenêtre : la nouvelle version démarre depuis son propre fichier
        # La fenêtre reste jusqu'à l'affichage de la nouvelle version (au plus 40 s)
        if ui:
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline and not marker.exists():
                time.sleep(0.2)
            ui.close()
    import threading
    if ui is None:
        work()
    else:
        threading.Thread(target=work, daemon=True).start()
        ui.run()
    return 0 if result.get("ok") else 1


class _Splash:
    """Fenêtre minimale (sans dépendance au thème) : titre, étape en cours, barre animée."""

    def __init__(self):
        import queue
        import tkinter as tk
        from tkinter import ttk
        self.q = queue.Queue()
        self.root = r = tk.Tk()
        r.title("Mise à jour de Forge411")
        r.configure(bg="#0a1712")
        r.resizable(False, False)
        w, h = 440, 150
        r.geometry(f"{w}x{h}+{(r.winfo_screenwidth() - w) // 2}+{(r.winfo_screenheight() - h) // 3}")
        r.attributes("-topmost", True)
        r.protocol("WM_DELETE_WINDOW", lambda: None)
        try:
            from importlib.resources import files
            self._icon = tk.PhotoImage(file=str(files("forge411") / "assets" / "forge411.png"))
            r.iconphoto(True, self._icon)
            r.update_idletasks()
            from .ui.theme import dark_title_bar
            dark_title_bar(r)
        except Exception:
            pass
        tk.Label(r, text=f"Mise à jour de Forge411 {__version__}", bg="#0a1712", fg="#d5eadf",
                 font=("Segoe UI Semibold", 12), anchor="w").pack(fill="x", padx=24, pady=(22, 2))
        self.lbl = tk.Label(r, text="Préparation…", bg="#0a1712", fg="#9db9ac", font=("Segoe UI", 9), anchor="w")
        self.lbl.pack(fill="x", padx=24)
        s = ttk.Style(r)
        s.theme_use("clam")
        s.configure("U.Horizontal.TProgressbar", background="#00d492", troughcolor="#19231f", bordercolor="#19231f",
                    lightcolor="#00d492", darkcolor="#00d492")
        self.bar = ttk.Progressbar(r, mode="indeterminate", style="U.Horizontal.TProgressbar")
        self.bar.pack(fill="x", padx=24, pady=(14, 0))
        self.bar.start(12)

    def status(self, text):
        self.q.put(("text", text))

    def failed(self, text, retry, fallback):
        self.q.put(("failed", (text, retry, fallback)))

    def _show_failed(self, text, retry, fallback):
        import tkinter as tk
        self.bar.stop()
        self.bar.pack_forget()
        self.lbl.configure(text=text, fg="#ff637e", wraplength=390, justify="left")
        self.root.geometry("440x190")
        if getattr(self, "btns", None) is None:
            self.btns = tk.Frame(self.root, bg="#0a1712")
            self.btns.pack(fill="x", padx=24, pady=(14, 0))

            def again():
                self.btns.pack_forget()
                self.lbl.configure(fg="#9db9ac")
                self.bar.pack(fill="x", padx=24, pady=(14, 0))
                self.bar.start(12)
                retry()
            for text_, cmd, bg, fg in (("Réessayer", again, "#00d492", "#03140e"),
                                       ("Ouvrir sans remplacer", fallback, "#19231f", "#d5eadf")):
                tk.Button(self.btns, text=text_, command=cmd, bg=bg, fg=fg, relief="flat", padx=12, pady=4,
                          font=("Segoe UI Semibold", 9), cursor="hand2").pack(side="left", padx=(0, 8))
        else:
            self.btns.pack(fill="x", padx=24, pady=(14, 0))

    def close(self):
        self.q.put(("close", None))

    def run(self):
        def poll():
            while not self.q.empty():
                kind, val = self.q.get()
                if kind == "close":
                    self.root.destroy()
                    return
                if kind == "failed":
                    self._show_failed(*val)
                    continue
                self.lbl.configure(text=val)
            self.root.after(100, poll)
        self.root.after(100, poll)
        self.root.mainloop()


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
