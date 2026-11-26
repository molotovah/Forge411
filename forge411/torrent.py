"""
Création de .torrent (fichier unique ou dossier), sans dépendance externe.

Règles C411 appliquées :
- flag private et champ info.source = "C411" (C411 l'ajoute à la publication :
  le mettre dès la création garde le même info-hash, donc le seed reste valide) ;
- taille de pièce choisie selon la taille totale (table du guide d'upload).
"""

import hashlib
import queue
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .files import list_files

SOURCE_TAG = "C411"

MiB = 1024 * 1024
GiB = 1024 * MiB


class Cancelled(Exception):
    pass


def piece_length_for(total_size: int) -> int:
    if total_size < 1 * GiB:
        return 1 * MiB
    if total_size < 2 * GiB:
        return 2 * MiB
    if total_size < 3 * GiB:
        return 4 * MiB
    if total_size < 8 * GiB:
        return 8 * MiB
    return 16 * MiB


def bencode(v) -> bytes:
    if isinstance(v, bool):
        v = int(v)
    if isinstance(v, int):
        return b"i%de" % v
    if isinstance(v, (bytes, bytearray)):
        return str(len(v)).encode() + b":" + bytes(v)
    if isinstance(v, str):
        e = v.encode("utf-8")
        return str(len(e)).encode() + b":" + e
    if isinstance(v, list):
        return b"l" + b"".join(bencode(i) for i in v) + b"e"
    if isinstance(v, dict):
        items = sorted((k.encode() if isinstance(k, str) else k, val)
                       for k, val in v.items())
        return b"d" + b"".join(bencode(k) + bencode(val) for k, val in items) + b"e"
    raise TypeError(f"Type non encodable : {type(v)}")


def _hash_pieces(files, plen: int, total: int, progress=None, cancel=None) -> bytes:
    """Empreintes SHA-1 des pièces, lecture et calcul en parallèle : ce thread lit le disque dans des tampons
    réutilisés (readinto, sans copie), un second calcule les empreintes (hashlib libère le GIL). Sur un disque
    rapide, la lecture de la pièce suivante n'attend plus la fin du calcul de la précédente."""
    free: "queue.Queue[bytearray]" = queue.Queue()
    for _ in range(3):
        free.put(bytearray(plen))
    work: queue.Queue = queue.Queue()
    digests: list = []
    failure: list = []

    def hasher():
        while True:
            item = work.get()
            if item is None:
                return
            buf, n = item
            try:
                if not failure:
                    digests.append(hashlib.sha1(memoryview(buf)[:n]).digest())
            except Exception as e:          # ne doit pas arriver ; le lecteur le relance après coup
                failure.append(e)
            finally:
                free.put(buf)

    th = threading.Thread(target=hasher, daemon=True)
    th.start()
    done = 0
    last_report = 0.0
    try:
        buf = free.get()
        view, fill = memoryview(buf), 0
        for f in files:
            with open(f, "rb", buffering=0) as fh:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    n = fh.readinto(view[fill:])
                    if not n:
                        break
                    fill += n
                    done += n
                    if fill == plen:
                        view.release()
                        work.put((buf, plen))
                        buf = free.get()
                        view, fill = memoryview(buf), 0
                    now = time.monotonic()
                    if progress and now - last_report > 0.2:
                        last_report = now
                        progress(done / total if total else 1.0)
        view.release()
        if fill:
            work.put((buf, fill))
    finally:
        work.put(None)
        th.join()
    if failure:
        raise failure[0]
    return b"".join(digests)


def create_torrent(
    source: Path,
    announce: str,
    output: Path,
    progress: Optional[Callable[[float], None]] = None,
    cancel: Optional[threading.Event] = None,
) -> str:
    """Crée le .torrent et renvoie son info-hash (hex)."""
    source = Path(source)
    if source.is_dir():
        files = list_files(source)
        if not files:
            raise ValueError("Le dossier ne contient aucun fichier.")
    elif source.is_file():
        files = [source]
    else:
        raise FileNotFoundError(f"Introuvable : {source}")

    sizes = [f.stat().st_size for f in files]
    total = sum(sizes)
    plen = piece_length_for(total)

    pieces = _hash_pieces(files, plen, total, progress, cancel)

    info = {
        "name": source.name,
        "piece length": plen,
        "pieces": bytes(pieces),
        "private": 1,
        "source": SOURCE_TAG,
    }
    if source.is_dir():
        info["files"] = [
            {"length": size, "path": list(f.relative_to(source).parts)}
            for f, size in zip(files, sizes)
        ]
    else:
        info["length"] = total

    meta = {
        "announce": announce,
        "info": info,
        "created by": "Forge411",
        "creation date": int(time.time()),
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".tmp")
    tmp.write_bytes(bencode(meta))
    tmp.replace(output)
    if progress:
        progress(1.0)
    return hashlib.sha1(bencode(info)).hexdigest()


def bdecode(data: bytes):
    """Décodage bencode minimal (lecture d'un .torrent existant)."""
    def at(i):
        c = data[i:i + 1]
        if c == b"i":
            j = data.index(b"e", i)
            return int(data[i + 1:j]), j + 1
        if c in (b"l", b"d"):
            i += 1
            items = []
            while data[i:i + 1] != b"e":
                v, i = at(i)
                items.append(v)
            if c == b"l":
                return items, i + 1
            return {items[k]: items[k + 1] for k in range(0, len(items), 2)}, i + 1
        j = data.index(b":", i)
        n = int(data[i:j])
        return data[j + 1:j + 1 + n], j + 1 + n
    return at(0)[0]


def torrent_info(path: Path) -> tuple:
    """(nom des données, info-hash) d'un .torrent."""
    meta = bdecode(Path(path).read_bytes())
    info = meta[b"info"]
    return info[b"name"].decode("utf-8", "replace"), hashlib.sha1(bencode(info)).hexdigest()
