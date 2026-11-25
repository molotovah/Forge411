"""
Profil de contenu : tout ce qui change d'un type de release à l'autre.

L'assistant est générique ; chaque profil fournit l'analyse, la recherche en
ligne, le nom, le NFO, la présentation et les options C411 de son type.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..api import norm
from ..model import Check, Ident, Part, Source, fmt_size
from ..render import Nfo, Prez


@dataclass
class Ctx:
    """Contexte transmis au profil à chaque étape."""
    src: Source
    analysis: Any = None
    ident: Optional[Ident] = None
    sub_id: int = 0
    parts: dict = field(default_factory=dict)
    details: dict = field(default_factory=dict)
    name: str = ""

    def d(self, key: str, default: str = "") -> str:
        return (self.details.get(key) or default).strip()


class Profile:
    key = ""
    label = ""
    icon = "📦"
    category_id = 0
    subcategories: dict = {}          # id → libellé
    provider: Optional[str] = None    # tmdb | musicbrainz | books | rawg | None
    dotted = True                     # nom séparé par des points
    rename_on_disk = False            # C411 : en réupload, le nom des fichiers d'origine est conservé
    template = ""                     # modèle de nom affiché à l'utilisateur
    hint = ""                         # aide affichée sur l'étape Nom

    # ── Détection / analyse ───────────────────────────────────────────────
    def score(self, src: Source) -> float:
        return 0.0

    def analyze(self, src: Source, progress: Callable[[str], None] = None) -> Any:
        return None

    def summary(self, ctx: Ctx) -> list:
        """Lignes (libellé, valeur) affichées à l'étape Source."""
        return []

    def issues(self, ctx: Ctx) -> Check:
        return Check()

    def guess_sub(self, ctx: Ctx) -> int:
        return next(iter(self.subcategories))

    # ── Identification ────────────────────────────────────────────────────
    def query(self, ctx: Ctx) -> dict:
        """Recherche proposée : {'query': ..., 'year': ..., autres indices}."""
        return {"query": ctx.src.stem.replace(".", " "), "year": ""}

    def provider_for(self, ctx: "Ctx") -> Optional[str]:
        """Base en ligne pour ce contenu (peut dépendre de la sous-catégorie)."""
        return self.provider

    def meta(self, ctx: "Ctx") -> tuple:
        """Fiche jointe à l'envoi : (clé de l'API C411, données), ou ("", None)."""
        i = ctx.ident
        return (i.payload_key, i.payload) if i and i.payload_key and i.payload else ("", None)

    def search(self, client, q: dict) -> list:
        return client.search(q.get("query", ""), q.get("year", ""))

    def manual_ident(self, ctx: Ctx) -> Ident:
        """Fiche minimale quand aucune base n'est utilisée."""
        q = self.query(ctx)
        return Ident(title=ctx.details.get("title", "") or q.get("query", "") or ctx.src.stem,
                     year=q.get("year", ""))

    # ── Nom ───────────────────────────────────────────────────────────────
    def parts(self, ctx: Ctx) -> list:
        return [Part("name", "Nom", ctx.src.stem, width=60)]

    def build(self, parts: dict) -> str:
        return parts.get("name", "").strip()

    def validate(self, name: str, ctx: Ctx) -> Check:
        c = Check()
        if not name.strip():
            c.errors.append("Le nom est vide.")
        return c

    def details(self, ctx: Ctx) -> list:
        """Champs complémentaires (NFO / présentation)."""
        return []

    def rename_target(self, ctx: Ctx) -> Optional[str]:
        """Nouveau nom sur le disque (sans extension), ou None pour ne rien renommer."""
        return ctx.name if self.rename_on_disk else None

    def on_renamed(self, ctx: Ctx, old_name: str, new_name: str):
        """Mise à jour de l'analyse après renommage d'un fichier unique."""

    def tag_fixes(self, ctx: Ctx) -> list:
        """Fichiers à renommer pour porter le tag de team (règle anti-detag) : [(chemin, nouveau nom)]."""
        return []

    # ── NFO / présentation ────────────────────────────────────────────────
    def nfo(self, ctx: Ctx) -> str:
        n = Nfo(ctx.name).ident(ctx.ident)
        n.field("Taille totale", fmt_size(ctx.src.total_size)).field("Fichiers", len(ctx.src.files))
        for d in self.details(ctx):
            if ctx.d(d.key) and not d.multiline:
                n.field(d.label, ctx.d(d.key))
        for d in self.details(ctx):
            if ctx.d(d.key) and d.multiline:
                n.section(d.label).text(ctx.d(d.key))
        return n.files(ctx.src).render()

    def description(self, ctx: Ctx) -> str:
        p = Prez().header(ctx.ident, ctx.name)
        if ctx.ident:
            p.block("Description", ctx.ident.overview).fiche(ctx.ident)
        rows = [("Release", ctx.name), ("Taille", fmt_size(ctx.src.total_size)),
                ("Fichiers", len(ctx.src.files))]
        rows += [(d.label, ctx.d(d.key)) for d in self.details(ctx) if not d.multiline]
        p.items("Informations techniques", rows)
        for d in self.details(ctx):
            if d.multiline:
                p.block(d.label, ctx.d(d.key))
        return p.files(ctx.src).render()

    # ── Options C411 ──────────────────────────────────────────────────────
    def auto_options(self, types: list, ctx: Ctx) -> dict:
        return {}


# ═══════════════════════════════════════════════════════════════════════════
# Règles communes
# ═══════════════════════════════════════════════════════════════════════════

BANNED_TEAMS = {"WAWACITY", "WAWA", "K0RE", "KORE", "P2P", "RARBG", "FYR3N", "ARKAS",
                "R3Z", "BYPLEX", "WEBVISION", "AGROAQC"}
ARCHIVE_EXT = {".rar", ".zip", ".7z", ".tar", ".gz", ".r00", ".001"}


def banned_team_error(name: str):
    team = name.rsplit("-", 1)[-1].strip().upper() if "-" in name else ""
    if team in BANNED_TEAMS:
        return f"La team {team} est bannie sur C411."
    return None


def team_of(name: str) -> str:
    """Tag après le dernier tiret (forme pointée), sinon chaîne vide."""
    last = name.rsplit(".", 1)[-1] if "." in name else name
    if "-" in last:
        t = last.rsplit("-", 1)[-1]
        return t if t.isalnum() else ""
    return ""


# ═══════════════════════════════════════════════════════════════════════════
# Aides pour les options
# ═══════════════════════════════════════════════════════════════════════════

def pick(types: list, out: dict, type_name: str, *labels: str):
    """Sélectionne les valeurs dont le libellé correspond, pour le type nommé."""
    t = next((t for t in types if norm(t.name) == norm(type_name)), None)
    if not t:
        return
    ids = [v for v in (t.find(l) for l in labels if l) if v]
    ids = list(dict.fromkeys(ids))
    if ids:
        out[t.id] = ids if t.multiple else ids[0]


def pick_fuzzy(types: list, out: dict, type_name: str, words: list):
    """Genres : sélectionne les valeurs dont le libellé contient un des mots."""
    t = next((t for t in types if norm(t.name) == norm(type_name)), None)
    if not t:
        return
    ids = []
    for w in words:
        nw = norm(w)
        if len(nw) < 3:
            continue
        for v in t.values:
            nv = norm(v["value"])
            if nw == nv or (len(nw) > 4 and (nw in nv or nv in nw)):
                ids.append(v["id"])
    ids = list(dict.fromkeys(ids))[:6]
    if ids:
        out[t.id] = ids if t.multiple else ids[0]


def options_payload(selected: dict) -> dict:
    """Format API : clés texte, liste pour choix multiple, entier sinon."""
    return {str(k): v for k, v in selected.items() if v not in (None, [], "")}


def lang_from_tag(tag: str) -> str:
    """Tag de langue (nom de release) → libellé d'option C411 « Langue » (type 1)."""
    t = tag.upper()
    if t == "MULTI.VF2":
        return "Multi VF2 (FR + QC inclus)"
    if t == "MULTI.VFQ":
        return "Multi (Québecois inclus)"
    if t.startswith("MULTI"):
        return "Multi (Français inclus)"
    if t == "VFQ":
        return "Québecois (VFQ/French)"
    if t.endswith("VOSTFR"):
        return "VOSTFR"
    if t == "VFSTFR":
        return "VFSTFR"
    if t == "MUET":
        return "Muet"
    if t in ("VFF", "TRUEFRENCH", "VOF", "VFI", "VFB", "FRENCH", "FR"):
        return "Français (VFF/TrueFrench)"
    return "Anglais"
