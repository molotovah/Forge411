"""Émulation, GPS et impression 3D : inventaire des fichiers et règles propres à chaque catégorie."""

import re
from dataclasses import dataclass, field

from ..model import Check, Detail, Part, fmt_size, slug
from ..render import Nfo, Prez
from .base import ARCHIVE_EXT, Profile

ROM_EXT = {".nes": "NES", ".fds": "Famicom Disk System", ".sfc": "Super Nintendo", ".smc": "Super Nintendo",
           ".gb": "Game Boy", ".gbc": "Game Boy Color", ".gba": "Game Boy Advance", ".n64": "Nintendo 64",
           ".z64": "Nintendo 64", ".v64": "Nintendo 64", ".md": "Mega Drive", ".gen": "Mega Drive",
           ".smd": "Mega Drive", ".sms": "Master System", ".gg": "Game Gear", ".32x": "32X",
           ".pce": "PC Engine", ".ngp": "Neo Geo Pocket", ".ws": "WonderSwan", ".wsc": "WonderSwan Color",
           ".lnx": "Lynx", ".a26": "Atari 2600", ".a78": "Atari 7800", ".col": "ColecoVision",
           ".adf": "Amiga", ".d64": "Commodore 64", ".tap": "ZX Spectrum", ".dsk": "Amstrad CPC",
           ".st": "Atari ST", ".chd": "CD (CHD)", ".cue": "CD (BIN/CUE)", ".gdi": "Dreamcast"}
MODEL_EXT = {".stl", ".obj", ".3mf", ".step", ".stp", ".gcode", ".blend", ".f3d", ".f3z", ".sldprt", ".fcstd", ".ply",
             ".lys", ".chitubox"}
PRINT_OK = {".stl", ".3mf", ".step", ".stp", ".lys", ".chitubox"}      # formats acceptés par C411
GPS_EXT = {".img", ".gmap", ".kmz", ".kml", ".gpx", ".map", ".mapsforge", ".obf", ".ov2", ".poi"}


@dataclass
class Inventory:
    counts: dict = field(default_factory=dict)        # extension → nombre
    platforms: list = field(default_factory=list)
    archives: int = 0
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def inventory(src) -> Inventory:
    inv = Inventory(counts=src.ext_counts())
    inv.archives = sum(n for e, n in inv.counts.items() if e in ARCHIVE_EXT)
    plats = []
    for e in inv.counts:
        if e in ROM_EXT and ROM_EXT[e] not in plats:
            plats.append(ROM_EXT[e])
    inv.platforms = plats
    return inv


def _counts_line(inv: Inventory) -> str:
    return ", ".join(f"{n} × {e.lstrip('.').upper() or '?'}" for e, n in
                     sorted(inv.counts.items(), key=lambda x: -x[1])[:8])


class _InvProfile(Profile):
    provider = None

    def analyze(self, src, progress=None):
        return inventory(src)

    def summary(self, ctx):
        return [("Fichiers", _counts_line(ctx.analysis))]

    def issues(self, ctx):
        inv = ctx.analysis
        return Check(errors=list(inv.errors), warnings=list(inv.warnings))

    def manual_title(self, ctx):
        return re.sub(r"[._]+", " ", re.sub(r"-[A-Za-z0-9]+$", "", ctx.src.stem)).strip()

    def nfo(self, ctx):
        n = Nfo(ctx.name).field("Titre", ctx.d("title") or self.manual_title(ctx))
        for d in self.details(ctx):
            if not d.multiline and d.key != "title":
                n.field(d.label, ctx.d(d.key))
        n.field("Fichiers", len(ctx.src.files)).field("Taille totale", fmt_size(ctx.src.total_size))
        n.field("Formats", _counts_line(ctx.analysis))
        for d in self.details(ctx):
            if d.multiline and ctx.d(d.key):
                n.section(d.label).text(ctx.d(d.key))
        return n.files(ctx.src, limit=5000).render()

    def description(self, ctx):
        p = Prez().header(None, ctx.d("title") or self.manual_title(ctx))
        rows = [("Release", ctx.name)] + [(d.label, ctx.d(d.key)) for d in self.details(ctx)
                                          if not d.multiline and d.key != "title"]
        rows += [("Fichiers", len(ctx.src.files)), ("Taille", fmt_size(ctx.src.total_size))]
        p.items("Informations", rows)
        for d in self.details(ctx):
            if d.multiline:
                p.block(d.label, ctx.d(d.key))
        return p.files(ctx.src).render()


# ═══════════════════════════════════════════════════════════════════════════

class EmulationProfile(_InvProfile):
    key = "emulation"
    label = "Émulation"
    icon = "🕹️"
    category_id = 6
    subcategories = {38: "ROM/ISO", 37: "Émulateur"}
    dotted = False
    rename_on_disk = False
    template = "Nom d'origine (non pointé), ex. Pack NES [Europe] (Fr,En)"
    hint = "Les noms d'émulation ne sont pas pointés. Région et langues viennent des tags « (Europe) (Fr,En) »."

    def score(self, src):
        n = sum(1 for f in src.files if f.suffix.lower() in ROM_EXT and f.suffix.lower() != ".cue")
        if re.search(r"emulat|retroarch|mame|rom.?pack", src.stem, re.I):
            return 0.8
        return 0.0 if not n else 0.75 + 0.2 * n / max(len(src.files), 1)

    def analyze(self, src, progress=None):
        inv = inventory(src)
        exts = set(inv.counts)
        if ".bin" in exts and ".cue" not in exts:
            inv.errors.append("Fichiers .bin sans .cue : ajoute les .cue.")
        if exts & {".ccd", ".sub"} and not {".ccd", ".img", ".sub"} <= exts:
            inv.errors.append("Image CloneCD incomplète : il faut .ccd, .img et .sub.")
        if inv.archives and len(src.files) <= 50:
            inv.errors.append("Archives autorisées seulement dans les packs de plus de 50 fichiers.")
        if len([p for p in inv.platforms if not p.startswith("CD")]) > 1 and "mame" not in src.stem.lower():
            inv.warnings.append("Plusieurs machines dans le même pack : C411 l'interdit (sauf MAME).")
        return inv

    def summary(self, ctx):
        rows = super().summary(ctx)
        if ctx.analysis.platforms:
            rows.insert(0, ("Plateforme", ", ".join(ctx.analysis.platforms)))
        return rows

    def guess_sub(self, ctx):
        return 37 if ctx.src.by_ext(".exe", ".apk", ".dmg", ".appimage") and not ctx.analysis.platforms else 38

    def parts(self, ctx):
        return [Part("name", "Nom", ctx.src.stem, width=60, hint="Nom d'origine, non pointé.")]

    def details(self, ctx):
        stem = ctx.src.stem
        region = re.findall(r"\((Europe|USA|Japan|World|France|Germany|Spain|Italy)\)", stem)
        langs = re.findall(r"\(((?:[A-Z][a-z],?)+)\)", stem)
        return [Detail("title", "Titre", self.manual_title(ctx)),
                Detail("platform", "Machine", ", ".join(ctx.analysis.platforms)),
                Detail("region", "Région", ", ".join(region)),
                Detail("languages", "Langues", ", ".join(langs)),
                Detail("notes", "Notes", "", multiline=True, hint="Émulateur conseillé, BIOS nécessaires…")]

    def validate(self, name, ctx):
        c = Check()
        if not name.strip():
            c.errors.append("Le nom est vide.")
        if re.search(r"[^\x20-\x7e]", name):
            c.errors.append("Accents et caractères spéciaux interdits dans le nom.")
        c.errors += self.issues(ctx).errors
        c.warnings += self.issues(ctx).warnings
        if ctx.analysis.archives:
            c.infos.append("Le NFO liste chaque fichier du pack (exigé avec des archives).")
        return c


# ═══════════════════════════════════════════════════════════════════════════

class GpsProfile(_InvProfile):
    key = "gps"
    label = "GPS"
    icon = "🧭"
    category_id = 7
    subcategories = {40: "Cartes", 39: "Applications", 41: "Divers"}
    template = "Marque.Zone.Année.Support"
    hint = "Ex. Garmin.City.Navigator.Europe.NT.2026.20.IMG. Indique version et activation."

    def score(self, src):
        if re.search(r"garmin|tomtom|navionics|igo|sygic|city.?navigator|osm|openstreetmap|\bgps\b", src.stem, re.I):
            return 0.85
        return 0.4 if src.by_ext(*GPS_EXT) else 0.0

    def guess_sub(self, ctx):
        return 39 if ctx.src.by_ext(".exe", ".apk", ".msi") else 40

    def parts(self, ctx):
        words = re.split(r"[._\s]+", re.sub(r"-[A-Za-z0-9]+$", "", ctx.src.stem))
        brand = next((w for w in words if w.lower() in ("garmin", "tomtom", "navionics", "igo", "sygic")), "")
        year = next((w for w in words if re.fullmatch(r"20\d\d(\.\d+)?", w)), "")
        zone = " ".join(w for w in words if w not in (brand, year) and not re.fullmatch(r"img|gmap|v?\d+(\.\d+)*", w, re.I))
        support = next((e.lstrip(".").upper() for e in (".img", ".gmap", ".obf", ".kmz", ".apk", ".exe")
                        if ctx.src.by_ext(e)), "")
        return [Part("brand", "Marque", brand, width=12), Part("zone", "Zone / produit", slug(zone), width=30),
                Part("year", "Année / version", year, width=10), Part("support", "Support", support, width=8)]

    def build(self, parts):
        return ".".join(slug(parts.get(k, "")) for k in ("brand", "zone", "year", "support") if parts.get(k, "").strip())

    def details(self, ctx):
        return [Detail("title", "Titre", self.manual_title(ctx)),
                Detail("version", "Version", ""),
                Detail("activation", "Activation", "", hint="Débloquée, keygen, aucune…"),
                Detail("install", "Installation", "", multiline=True)]

    def validate(self, name, ctx):
        c = Check()
        if not name.strip():
            c.errors.append("Le nom est vide.")
        if re.search(r"[^A-Za-z0-9.\-+]", name):
            c.errors.append("Caractères interdits : lettres, chiffres et points uniquement.")
        if not ctx.d("activation"):
            c.warnings.append("Indique le mode d'activation (règle C411).")
        c.errors += self.issues(ctx).errors
        return c


# ═══════════════════════════════════════════════════════════════════════════

class PrintProfile(_InvProfile):
    key = "print3d"
    label = "Impression 3D"
    icon = "🧱"
    category_id = 10
    subcategories = {52: "Décoration", 51: "Utilitaire", 53: "Jeux"}
    template = "Createur.Nom[FORMAT1][FORMAT2] · pack : [PACK]Createur.Nom[STL][LYS]"
    hint = "Formats acceptés : STL, 3MF, STEP/STP, LYS, CHITUBOX. GCODE interdit. NFO facultatif, image obligatoire."

    def score(self, src):
        n = len(src.by_ext(*MODEL_EXT))
        return 0.0 if not n else 0.7 + 0.3 * n / max(len(src.files), 1)

    def analyze(self, src, progress=None):
        inv = inventory(src)
        if inv.archives:
            inv.errors.append("Archives interdites : extrais-les.")
        if inv.counts.get(".gcode"):
            inv.errors.append("Le format GCODE est interdit sur C411 : fournis les STL, 3MF ou STEP.")
        if not any(e in PRINT_OK for e in inv.counts):
            inv.errors.append("Aucun format accepté (STL, 3MF, STEP/STP, LYS, CHITUBOX).")
        if inv.counts.get(".blend") or inv.counts.get(".obj") or inv.counts.get(".fbx"):
            inv.warnings.append("Les assets d'infographie 3D ou de jeu vidéo relèvent de la catégorie Nulled.")
        return inv

    def guess_sub(self, ctx):
        stem = ctx.src.stem.lower()
        if re.search(r"game|jeu|chess|dice|d[ée]s\b|figurine|mini|warhammer|wargame|jdr|rpg|dnd", stem):
            return 53
        if re.search(r"holder|support|tool|outil|clip|bracket|hook|crochet|box|bo[iî]te|organizer", stem):
            return 51
        return 52

    def parts(self, ctx):
        inv = ctx.analysis
        fmts = "".join(f"[{e.lstrip('.').upper()}]" for e, _ in sorted(inv.counts.items(), key=lambda x: -x[1])
                       if e in PRINT_OK)
        name = re.sub(r"[._]+", " ", re.sub(r"(\[.*?\])|-[A-Za-z0-9]+$", "", ctx.src.stem))
        pack = len(ctx.src.by_ext(*PRINT_OK)) > 1 and ctx.src.is_dir and \
            len({f.parent for f in ctx.src.by_ext(*PRINT_OK)}) > 1
        return [Part("pack", "Pack", "[PACK]" if pack else "", choices=["", "[PACK]"], width=8,
                     hint="Collection thématique d'une même source ; lister tout le contenu dans la présentation."),
                Part("kind", "Scan / resculpt (Jeux)", "", choices=["", "[SCAN]", "[RESCULPT]"], width=12,
                     hint="Catégorie Jeux : préfixe obligatoire pour un scan ou un resculpt."),
                Part("creator", "Créateur", "", width=18, hint="Créateur ou studio d'origine (le scanneur avant lui)."),
                Part("title", "Nom", slug(name), width=30),
                Part("formats", "Formats", fmts, width=16, hint="Chaque format entre crochets : [STL][3MF]…")]

    def build(self, parts):
        p = {k: (v or "").strip() for k, v in parts.items()}
        body = ".".join(slug(x) for x in (p.get("creator", ""), p.get("title", "")) if x)
        return f"{p.get('pack', '')}{p.get('kind', '')}{body}{p.get('formats', '')}"

    def details(self, ctx):
        return [Detail("title", "Titre", self.manual_title(ctx)),
                Detail("nsfw", "Contenu NSFW", "Non", choices=["Non", "Oui"],
                       hint="Obligatoire dans la présentation : le contenu est-il « not safe for work » ?"),
                Detail("notes", "Notes d'impression", "", multiline=True,
                       hint="Supports, orientation, nombre de pièces, contenu du pack…")]

    def description(self, ctx):
        p = Prez().header(ctx.ident, ctx.d("title") or self.manual_title(ctx))
        if ctx.ident:
            p.block("Description", ctx.ident.overview)
        formats = ", ".join(e.lstrip(".").upper() for e in ctx.analysis.counts if e in PRINT_OK)
        p.items("Informations", [("Release", ctx.name), ("Créateur", ctx.parts.get("creator", "")),
                                 ("Formats", formats), ("NSFW", ctx.d("nsfw") or "Non"),
                                 ("Fichiers", len(ctx.src.files)), ("Taille", fmt_size(ctx.src.total_size))])
        p.block("Notes d'impression", ctx.d("notes"))
        return p.files(ctx.src).render()

    def validate(self, name, ctx):
        c = Check()
        if not name.strip():
            c.errors.append("Le nom est vide.")
        if re.search(r"[^A-Za-z0-9.\-\[\]]", name):
            c.errors.append("Caractères interdits : lettres, chiffres, points et crochets uniquement.")
        if not ctx.parts.get("creator"):
            c.warnings.append("Indique le créateur : le nom commence par Createur.Nom.")
        if ctx.sub_id != 53 and ctx.parts.get("kind"):
            c.warnings.append("[SCAN] et [RESCULPT] concernent la sous-catégorie Jeux.")
        c.infos.append("Évite les modèles d'auteurs indépendants qui en vivent (recommandation C411).")
        c.errors += self.issues(ctx).errors
        c.warnings += self.issues(ctx).warnings
        return c
