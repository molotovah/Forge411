"""
Mode lot : préparation et envoi en brouillons de plusieurs sources d'un dossier.

Chaque élément suit le même chemin que l'assistant (détection, analyse, fiche,
nom, NFO, présentation, options, torrent) sans interface. Les éléments avec
une erreur ou un doute restent « à vérifier » et s'ouvrent dans l'assistant.
Seuls des brouillons sont envoyés : la publication se fait depuis C411.
"""

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import files as fs
from .lookup import LookupFailed
from .profiles import detect, options_payload
from .session import Session
from .torrent import create_torrent

MAX_DRAFTS = 15
READY, CHECK, ERROR, SENT, PENDING = "Prêt", "À vérifier", "Erreur", "Envoyé", "En attente"


@dataclass
class Item:
    path: Path
    status: str = PENDING
    session: Optional[Session] = None
    messages: list = field(default_factory=list)
    url: str = ""

    @property
    def name(self) -> str:
        return self.session.name if self.session and self.session.name else self.path.name


def candidates(folder: Path) -> list:
    """Sous-dossiers et fichiers directs (hors fichiers cachés, NFO et images isolées)."""
    skip = {".nfo", ".txt", ".jpg", ".jpeg", ".png", ".srt", ".sfv", ".torrent", ".url", ".ini", ".db", ".part"}
    out = []
    for p in sorted(folder.iterdir(), key=lambda x: x.name.lower()):
        if p.name.startswith(".") or p.name.lower() in ("desktop.ini", "thumbs.db"):
            continue
        if p.is_file() and p.suffix.lower() in skip:
            continue
        out.append(Item(p))
    return out


def safe_name(name: str) -> str:
    return "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip(" .") or "release"


def _similar(a: str, b: str) -> bool:
    n = lambda s: set(re.findall(r"[a-z0-9]{3,}", s.lower()))
    wa, wb = n(a), n(b)
    return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= 0.6


def prepare(item: Item, cfg, c411, lookup_client: Callable, progress: Callable[[str], None] = lambda m: None):
    """Analyse, fiche, nom, NFO, description et options. Met à jour item.status."""
    item.messages = []
    src = fs.scan(item.path)
    ranked = detect(src)
    prof = ranked[0][1]
    progress(f"Analyse ({prof.label})…")
    s = Session(src=src, ranked=ranked, profile=prof, analysis=prof.analyze(src, progress))
    s.sub_id = prof.guess_sub(s.ctx())
    item.session = s
    doubt = False
    if ranked[0][0] < 0.5:
        item.messages.append(("warning", f"Type deviné avec peu de certitude ({prof.label})."))
        doubt = True
    issues = prof.issues(s.ctx())
    if issues.errors:
        item.status = ERROR
        item.messages += [("error", e) for e in issues.errors]
        return
    # Fiche en ligne : premier résultat si le titre correspond, sinon fiche manuelle
    prov = prof.provider_for(s.ctx())
    if prov:
        try:
            s.query = prof.query(s.ctx())
            matches = prof.search(lookup_client(prov), s.query)
            if matches and _similar(matches[0].title, s.query.get("query", "")):
                s.ident = lookup_client(prov).details(matches[0])
                from .translate import french_overview
                french_overview(s.ident, cfg.get("translate_overview", True))
                if prof.key == "video":
                    s.sub_id = prof.guess_sub(s.ctx())
            else:
                item.messages.append(("warning", "Fiche en ligne non trouvée avec certitude : fiche manuelle."))
                doubt = True
        except LookupFailed as e:
            item.messages.append(("warning", f"Recherche impossible : {e}"))
            doubt = True
    if not s.ident:
        s.ident = prof.manual_ident(s.ctx())
    # Nom
    ctx = s.ctx()
    s.parts = {p.key: p.value for p in prof.parts(ctx)}
    tag = cfg.get("team_tag")
    if tag and cfg.get("team_tag_auto") and "team" in s.parts and (s.parts.get("team") or "").upper() in ("", "NOTAG"):
        s.parts["team"] = tag
    s.details = {d.key: d.value for d in prof.details(s.ctx())}
    s.name = prof.build(s.parts)
    s.built_for = s.ident_key
    check = prof.validate(s.name, s.ctx())
    s.name_ok = not check.errors
    item.messages += [("error", e) for e in check.errors] + [("warning", w) for w in check.warnings]
    if prof.tag_fixes(s.ctx()):
        item.messages.append(("warning", "Des fichiers n'ont pas le tag de team (anti-detag) : à corriger dans l'assistant."))
        doubt = True
    if check.errors:
        item.status = ERROR
        return
    # NFO, présentation, options
    s.nfo = prof.nfo(s.ctx())
    nfo_path = cfg.nfo_dir / f"{safe_name(s.name)}.nfo"
    nfo_path.write_text(s.nfo, encoding="utf-8")
    s.nfo_path = nfo_path
    s.description = prof.description(s.ctx())
    if not (s.ident and s.ident.image) and "[img]" not in s.description.lower():
        item.messages.append(("warning", "Aucune image dans la présentation (exigée par C411)."))
        doubt = True
    types = c411.options(s.sub_id)
    s.options = prof.auto_options(types, s.ctx())
    s.options_for = s.sub_id
    missing = [t.name for t in types if t.required and not s.options.get(t.id)]
    if missing:
        item.messages.append(("warning", "Options obligatoires à choisir : " + ", ".join(missing)))
        doubt = True
    s.note = cfg.get("uploader_note") or ""
    item.status = CHECK if doubt else READY


def send(item: Item, cfg, c411, client=None, progress: Callable[[str], None] = lambda m: None,
         cancel: Optional[threading.Event] = None):
    """Crée le torrent, l'ajoute au client (facultatif) et envoie le brouillon."""
    s = item.session
    announce = cfg.get("tracker_url")
    out = cfg.torrents_dir / f"{safe_name(s.name)}.torrent"
    total = s.src.total_size
    s.infohash = create_torrent(s.src.path, announce, out,
                                lambda f: progress(f"Hachage {f * 100:.0f} %"), cancel)
    s.torrent, s.torrent_for = out, s.torrent_key
    if client is not None:
        progress("Ajout au client torrent…")
        from .clients import save_path
        client.add(out, save_path(cfg, s.src.path.parent), s.infohash)
    progress("Envoi du brouillon…")
    meta_key, meta = s.profile.meta(s.ctx())
    res = c411.save_draft(title=s.name, description=s.description, category_id=s.profile.category_id,
                          subcategory_id=s.sub_id, options=options_payload(s.options), torrent=out,
                          nfo=s.nfo_path, meta_key=meta_key, meta=meta, note=s.note)
    if not res.ok:
        item.status = ERROR
        item.messages.append(("error", res.message))
        return
    s.result = res
    item.status, item.url = SENT, res.url
    item.messages.append(("ok", f"Brouillon enregistré ({total // (1024 * 1024)} Mo)."))
