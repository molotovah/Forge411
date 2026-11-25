"""État d'un upload en cours, partagé par les étapes de l'assistant."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .api import Result
from .model import Ident, Source
from .profiles import Ctx, Profile


@dataclass
class Session:
    src: Optional[Source] = None
    profile: Optional[Profile] = None
    ranked: list = field(default_factory=list)       # [(score, profil)] détectés
    analysis: Any = None
    sub_id: int = 0
    # Identification
    query: dict = field(default_factory=dict)
    matches: list = field(default_factory=list)
    ident: Optional[Ident] = None
    existing: Optional[list] = None
    # Nom et informations
    parts: dict = field(default_factory=dict)
    details: dict = field(default_factory=dict)
    built_for: str = ""          # fiche pour laquelle les champs ont été proposés
    name: str = ""
    name_ok: bool = False
    # NFO
    nfo: str = ""
    nfo_edited: bool = False
    nfo_for: str = ""
    nfo_path: Optional[Path] = None
    # Présentation
    options: dict = field(default_factory=dict)
    options_for: int = 0
    description: str = ""
    desc_edited: bool = False
    desc_for: str = ""
    note: str = ""
    # Torrent / publication
    torrent: Optional[Path] = None
    torrent_for: str = ""
    infohash: str = ""
    seed: str = ""                 # état dans le client torrent : "", ajouté, vérification, en seed, erreur
    seeding: bool = False
    catalog: Any = None            # catalog.Verdict : releases déjà sur C411
    catalog_for: str = ""
    slot_justification: str = ""
    result: Optional[Result] = None

    def ctx(self) -> Ctx:
        return Ctx(src=self.src, analysis=self.analysis, ident=self.ident, sub_id=self.sub_id,
                   parts=self.parts, details=self.details, name=self.name)

    @property
    def ident_key(self) -> str:
        return f"{self.profile.key if self.profile else ''}|{self.ident.provider if self.ident else ''}|" \
               f"{self.ident.id if self.ident else ''}|{self.sub_id}"

    @property
    def torrent_key(self) -> str:
        return f"{self.name}|{self.src.path if self.src else ''}"

    @property
    def torrent_ready(self) -> bool:
        return bool(self.torrent and self.torrent.exists() and self.torrent_for == self.torrent_key)

    def reset_from_profile(self):
        """Nouveau profil ou nouvelle analyse : tout ce qui suit est recalculé."""
        self.query, self.matches, self.ident, self.existing = {}, [], None, None
        self.reset_from_ident()

    def reset_from_ident(self):
        self.parts, self.details, self.built_for = {}, {}, ""
        self.name, self.name_ok = "", False
        self.nfo_for = self.desc_for = ""
        self.options, self.options_for = {}, 0


# ═══════════════════════════════════════════════════════════════════════════
# Sauvegarde locale de l'upload en cours (reprise après fermeture ou plantage)
# ═══════════════════════════════════════════════════════════════════════════

def save(session: "Session", path: Path) -> bool:
    """Écrit la session (fichier local de l'utilisateur, format pickle). Rien si aucune source."""
    import pickle
    if not session.src or session.result:
        discard(path)
        return False
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL))
        tmp.replace(path)
        return True
    except Exception:            # objet non sérialisable, disque plein… : la sauvegarde est facultative
        return False


def load(path: Path) -> Optional["Session"]:
    """Session sauvegardée si sa source existe encore, sinon None."""
    import pickle
    try:
        s = pickle.loads(path.read_bytes())
    except Exception:
        return None
    if not isinstance(s, Session) or not s.src or not s.src.path.exists():
        return None
    return s


def discard(path: Path):
    try:
        path.unlink()
    except OSError:
        pass
