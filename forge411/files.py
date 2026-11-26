"""Lecture de la source, renommage, déplacement, emplacement de seed."""

import functools
import os
import shutil
import socket
from pathlib import Path
from typing import Callable, Optional

from .model import Source

IGNORED_FILES = {"thumbs.db", "desktop.ini", ".ds_store"}


def list_files(root: Path) -> list:
    """Fichiers d'un dossier, triés, sans fichiers cachés ni fichiers système."""
    files = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if p.name.lower() in IGNORED_FILES:
            continue
        files.append(p)
    return sorted(files, key=lambda p: [s.lower() for s in p.relative_to(root).parts])


def scan(path: Path) -> Source:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Introuvable : {path}")
    if path.is_dir():
        files = list_files(path)
        if not files:
            raise ValueError("Le dossier est vide.")
    else:
        files = [path]
    return Source(path=path, is_dir=path.is_dir(), files=files,
                  total_size=sum(f.stat().st_size for f in files))


@functools.lru_cache(maxsize=64)
def _host_addrs(host: str) -> frozenset:
    """Adresses d'une machine réseau (nom ou IP), en cache : NAS → {192.168.1.251, …}."""
    try:
        return frozenset({host} | {ai[4][0].lower() for ai in socket.getaddrinfo(host, None)})
    except (OSError, UnicodeError):
        return frozenset({host})


def same_host(a: str, b: str) -> bool:
    """Même machine sous deux noms : \\\\NAS et \\\\192.168.1.251 désignent le même serveur."""
    a, b = a.lower(), b.lower()
    return a == b or bool(_host_addrs(a) & _host_addrs(b))


def _clean(p) -> str:
    """Chemin à séparateurs Windows, sans « .. » ni séparateur final (casse conservée)."""
    s = str(p).replace("/", "\\")
    unc = s.startswith("\\\\")
    s = os.path.normpath(s) if os.name == "nt" else s
    while "\\\\" in s[2:]:
        s = s[:2] + s[2:].replace("\\\\", "\\")
    s = s.rstrip("\\")
    return ("\\\\" + s.lstrip("\\")) if unc else s


def rel_under(path, base) -> Optional[str]:
    """Partie de path située sous base ("" si c'est le même dossier), sinon None. Insensible à la casse ;
    un partage réseau est reconnu sous le nom de la machine comme sous son IP."""
    p, b = _clean(path), _clean(base)
    if not b:
        return None
    if p.startswith("\\\\") and b.startswith("\\\\"):
        ph, _, pr = p[2:].partition("\\")
        bh, _, br = b[2:].partition("\\")
        pl, bl = pr.lower(), br.lower()
        # Résolution réseau seulement si le reste du chemin correspond déjà (évite des requêtes DNS inutiles)
        if ph.lower() != bh.lower() and (pl == bl or pl.startswith(bl + "\\")) and same_host(ph, bh):
            p = "\\\\" + bh + ("\\" + pr if pr else "")
    pl, bl = p.lower(), b.lower()
    if pl == bl:
        return ""
    if pl.startswith(bl + "\\"):
        return p[len(b) + 1:]
    return None


def same_dir(a, b) -> bool:
    return rel_under(a, b) == ""


def seed_location_issue(src: Source, seed_dir: str) -> Optional[str]:
    if not seed_dir:
        return None
    if not Path(seed_dir).exists():
        return f"Dossier de seed introuvable : {seed_dir} (Paramètres)."
    if not same_dir(src.path.parent, seed_dir):
        what = "Le dossier" if src.is_dir else "Le fichier"
        return (f"{what} n'est pas directement dans le dossier de seed ({seed_dir}) : "
                "ton client torrent ne trouvera pas les données.")
    return None


def _relocate(src: Source, new_path: Path):
    old = src.path
    src.path = new_path
    src.files = [new_path / f.relative_to(old) for f in src.files] if src.is_dir else [new_path]


def remap_paths(obj, old: Path, new: Path, _seen: set = None):
    """Après un déplacement ou un renommage de la source : remplace, dans un objet d'analyse (dataclasses,
    listes, dicts imbriqués), chaque chemin situé sous old par son équivalent sous new."""
    old, new = Path(old), Path(new)
    if old == new:
        return obj

    def conv(v):
        if isinstance(v, Path):
            if v == old:
                return new
            try:
                return new / v.relative_to(old)
            except ValueError:
                return v
        walk(v)
        return v

    def walk(o):
        if o is None or isinstance(o, (str, bytes, int, float, bool)) or id(o) in seen:
            return
        seen.add(id(o))
        if isinstance(o, list):
            o[:] = [conv(v) for v in o]
        elif isinstance(o, dict):
            for k in list(o):
                o[k] = conv(o[k])
        elif isinstance(o, tuple):
            for v in o:
                walk(v)
        elif hasattr(o, "__dict__") and not isinstance(o, type):
            for k, v in list(vars(o).items()):
                nv = conv(v)
                if nv is not v:
                    setattr(o, k, nv)

    seen = _seen if _seen is not None else set()
    walk(obj)
    return obj


def rename(src: Source, new_name: str) -> Path:
    """Renomme le fichier (en gardant l'extension) ou le dossier."""
    target = src.path.with_name(new_name + ("" if src.is_dir else src.path.suffix))
    if target == src.path:
        return target
    if target.exists():
        raise FileExistsError(f"Existe déjà : {target.name}")
    src.path.rename(target)
    _relocate(src, target)
    return target


def rename_files(src: Source, fixes: list) -> list:
    """Renomme des fichiers dans leur dossier : fixes = [(chemin, nouveau nom)]. Renvoie [(ancien, nouveau)]."""
    done = []
    for path, new_name in fixes:
        target = path.with_name(new_name)
        if target.exists():
            raise FileExistsError(f"Existe déjà : {target.name}")
        path.rename(target)
        done.append((path, target))
        if src.is_dir:
            src.files = [target if f == path else f for f in src.files]
        else:
            src.path, src.files = target, [target]
    if src.is_dir:
        src.files.sort(key=lambda p: [s.lower() for s in p.relative_to(src.path).parts])
    return done


def move(src: Source, dest_dir: Path, progress: Callable[[float], None] = None) -> Path:
    """Déplace la source dans dest_dir (copie + suppression si volumes différents)."""
    dest = Path(dest_dir) / src.path.name
    if dest.exists():
        raise FileExistsError(f"Existe déjà dans le dossier de seed : {dest.name}")
    try:
        os.rename(src.path, dest)
        _relocate(src, dest)
        return dest
    except OSError:
        pass
    # Tout copier (y compris les fichiers ignorés par le torrent) avant de supprimer
    files = [p for p in src.path.rglob("*") if p.is_file()] if src.is_dir else [src.path]
    total = sum(f.stat().st_size for f in files) or 1
    done = 0
    for f in files:
        target = dest / f.relative_to(src.path) if src.is_dir else dest
        target.parent.mkdir(parents=True, exist_ok=True)
        base = done
        copy_file(f, target, (lambda n, b=base: progress((b + n) / total)) if progress else None)
        done += f.stat().st_size
    if src.is_dir:
        shutil.rmtree(src.path)
    else:
        src.path.unlink()
    _relocate(src, dest)
    return dest


def copy_file(src: Path, dst: Path, progress: Callable[[int], None] = None):
    """Copie rapide : CopyFileExW sous Windows (copie native, efficace vers un partage réseau),
    sinon blocs de 16 Mo. progress reçoit le nombre d'octets copiés."""
    if os.name == "nt":
        try:
            _copy_win(src, dst, progress)
            return
        except OSError:
            if dst.exists():
                dst.unlink()
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        n = 0
        while True:
            chunk = fi.read(16 * 1024 * 1024)
            if not chunk:
                break
            fo.write(chunk)
            n += len(chunk)
            if progress:
                progress(n)
    shutil.copystat(src, dst)


def _copy_win(src: Path, dst: Path, progress):
    import ctypes
    from ctypes import wintypes
    LARGE = ctypes.c_longlong
    Routine = ctypes.WINFUNCTYPE(wintypes.DWORD, LARGE, LARGE, LARGE, LARGE, wintypes.DWORD, wintypes.DWORD,
                                 wintypes.HANDLE, wintypes.HANDLE, wintypes.LPVOID)
    last = [0.0]

    def cb(total, done, *_):
        import time
        now = time.monotonic()
        if progress and (now - last[0] > 0.2 or done == total):
            last[0] = now
            progress(int(done))
        return 0                                    # PROGRESS_CONTINUE
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CopyFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, Routine, wintypes.LPVOID,
                                ctypes.POINTER(wintypes.BOOL), wintypes.DWORD]
    k32.CopyFileExW.restype = wintypes.BOOL
    flags = 0x1000 if src.stat().st_size > 256 * 1024 * 1024 else 0     # COPY_FILE_NO_BUFFERING : gros fichiers
    routine = Routine(cb)
    if not k32.CopyFileExW(str(src), str(dst), routine, None, None, flags):
        raise ctypes.WinError(ctypes.get_last_error())
