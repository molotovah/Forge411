"""Lecture de la source, renommage, déplacement, emplacement de seed."""

import os
import shutil
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


def same_dir(a, b) -> bool:
    norm = lambda p: os.path.normcase(os.path.normpath(str(p))).rstrip("\\/")
    return norm(a) == norm(b)


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
        with open(f, "rb") as fi, open(target, "wb") as fo:
            while True:
                chunk = fi.read(8 * 1024 * 1024)
                if not chunk:
                    break
                fo.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done / total)
        shutil.copystat(f, target)
    if src.is_dir:
        shutil.rmtree(src.path)
    else:
        src.path.unlink()
    _relocate(src, dest)
    return dest
