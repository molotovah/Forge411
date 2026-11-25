"""Jeux vidéo et applications : type de release déduit des fichiers, NFO d'installation."""

import re
from dataclasses import dataclass, field

from ..model import Check, Detail, Part, clean_free, fmt_size, slug
from ..render import Nfo, Prez
from .base import ARCHIVE_EXT, Profile, banned_team_error, pick, pick_fuzzy, team_of

TRUSTED_GAME_TAGS = ["TENOKE", "RUNE", "Mephisto", "ElAmigos", "FitGirl", "DODI", "Chovka", "ARMGDDN",
                     "RIDDICK", "EMPRESS", "KaOs", "M4CKD0GE", "voices38", "LinuxRulez", "CODEX", "PLAZA",
                     "SKIDROW", "FLT", "DOGE", "TiNYiSO", "RAZOR1911", "GOLDBERG"]
CONSOLE_EXT = {".nsp": "Switch", ".xci": "Switch", ".nsz": "Switch", ".xcz": "Switch", ".nds": "DS",
               ".3ds": "3DS", ".cia": "3DS", ".wbfs": "Wii", ".rvz": "Wii", ".gcm": "GameCube",
               ".wux": "WiiU", ".wua": "WiiU", ".pkg": "PS4", ".vpk": "Vita", ".cso": "PSP",
               ".xex": "Xbox 360", ".xbe": "Xbox"}
CONSOLE_SUB = {"Switch": 32, "DS": 32, "3DS": 32, "Wii": 32, "GameCube": 32, "WiiU": 32,
               "PS4": 34, "PS5": 34, "Vita": 34, "PSP": 34, "PS3": 34, "PS2": 34, "PS1": 34,
               "Xbox 360": 31, "Xbox": 31, "Xbox One": 31, "Xbox Series": 31}
CONSOLE_NAME = {"Switch": "SWITCH", "Xbox 360": "XBOX360", "Xbox": "XBOX", "Xbox One": "XBOXONE",
                "Xbox Series": "XBOXSERIES"}
CONSOLE_OPTION = {"Switch": "Switch", "DS": "DS", "3DS": "3DS", "Wii": "Wii", "GameCube": "GameCube",
                  "WiiU": "WiiU", "PS4": "PlayStation 4", "PS5": "PlayStation 5", "Vita": "Vita", "PSP": "PSP",
                  "PS3": "PlayStation 3", "PS2": "PlayStation 2", "PS1": "PlayStation",
                  "Xbox 360": "Xbox 360", "Xbox": "Xbox", "Xbox One": "Xbox One",
                  "Xbox Series": "Xbox Series X/S"}
INSTALLER_EXT = {".msi", ".dmg", ".pkg", ".deb", ".rpm", ".apk", ".xapk", ".ipa", ".appimage"}
OS_LIST = ["Windows", "macOS", "Linux", "Android", "iOS"]
LANG_LIST = ["MULTI", "FR", "EN"]
GAME_MODES = ["Nom d'origine (scène / repack)", "Portable", "GOG", "DRM Free", "Console"]


@dataclass
class SoftAnalysis:
    names: list = field(default_factory=list)     # noms de fichiers (minuscules)
    exes: list = field(default_factory=list)
    install_size: int = 0
    trusted_tag: str = ""
    crack: bool = False
    keygen: bool = False
    patch: bool = False
    iso: bool = False
    setup: bool = False
    installer: bool = False
    steam_api: bool = False
    gog: bool = False
    portable_word: bool = False
    preactivated_word: bool = False
    console: str = ""
    os: str = ""
    nfo_text: str = ""         # NFO d'origine trouvé dans la release
    nfo_name: str = ""
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp437", errors="replace")


def analyze(src, progress=None) -> SoftAnalysis:
    s = SoftAnalysis(install_size=src.total_size)
    rels = [src.rel(f).lower() for f in src.files]
    s.names = rels
    base = lambda r: r.rsplit("/", 1)[-1]
    s.exes = [r for r in rels if r.endswith(".exe")]
    s.crack = any(re.search(r"crack|activator|loader|kmspico|steam_emu|codex\.ini|crackfix", base(r)) for r in rels)
    s.keygen = any(re.search(r"keygen|keymaker|serialfish", base(r)) for r in rels)
    s.patch = any(re.search(r"\bpatch(er)?\b", base(r)) for r in rels)
    s.iso = any(r.endswith(".iso") for r in rels)
    s.setup = any(re.search(r"(setup|install(er)?|inst)[^/]*\.exe$", base(r)) for r in rels)
    s.installer = s.setup or any(r.endswith(tuple(INSTALLER_EXT)) for r in rels)
    s.steam_api = any(re.search(r"steam_api(64)?\.dll|steamrip|goldberg|preactivated", base(r)) for r in rels)
    s.gog = any("goggame-" in base(r) or "gog" in base(r).split(".")[0] for r in rels)
    stem = src.stem
    s.portable_word = "portable" in stem.lower()
    s.preactivated_word = "preactivated" in stem.lower() or "pre-activated" in stem.lower()
    for tag in TRUSTED_GAME_TAGS:
        if re.search(rf"(?<![a-z]){re.escape(tag)}(?![a-z])", stem, re.I):
            s.trusted_tag = tag
            break
    for f in src.files:
        c = CONSOLE_EXT.get(f.suffix.lower())
        if c:
            s.console = c
            break
    if re.search(r"\bPPSA\d+", stem, re.I):
        s.console = "PS5"
    if any(r.endswith((".dmg", ".pkg", ".app")) for r in rels) and not s.console:
        s.os = "macOS"
    elif any(r.endswith((".deb", ".rpm", ".appimage", ".sh")) for r in rels):
        s.os = "Linux"
    elif any(r.endswith((".apk", ".xapk")) for r in rels):
        s.os = "Android"
    elif any(r.endswith(".ipa") for r in rels):
        s.os = "iOS"
    elif s.exes or any(r.endswith(".msi") for r in rels):
        s.os = "Windows"
    nfos = src.by_ext(".nfo")
    if nfos:
        s.nfo_name = nfos[0].name
        s.nfo_text = _decode(nfos[0].read_bytes())
    archives = [r for r in rels if r.endswith(tuple(ARCHIVE_EXT))]
    if archives and not s.console:
        s.errors.append("Archives (rar, zip, 7z) interdites pour les jeux PC et applications : extrais-les.")
    if any(re.search(r"downloader|web.?setup|online.?installer|stub", base(r)) for r in s.exes):
        s.errors.append("Installateur en ligne (downloader) détecté : interdit sur C411.")
    if any(re.search(r"trainer|cheat.?engine|hack.?tool", base(r)) for r in rels):
        s.errors.append("Trainer ou outil de triche détecté : interdit sur C411.")
    return s


def game_mode(s: SoftAnalysis) -> tuple:
    """Table de décision C411 → (mode, tags, avertissement éventuel)."""
    if s.console:
        return "Console", [], ""
    if s.trusted_tag:
        if s.iso or s.setup:
            return GAME_MODES[0], [], ""
        return "Portable", ["PORTABLE", "PREACTIVATED"], ""
    if s.steam_api and not s.setup and not s.crack:
        return "Portable", ["PORTABLE", "PREACTIVATED"], ""
    if s.crack and (s.iso or s.setup):
        return GAME_MODES[0], [], "Crack détecté : reprends le nom du cracker ou du repacker d'origine."
    if s.iso and not s.setup:
        return GAME_MODES[0], [], "Un .iso n'est accepté que pour une release scène, crack ou repack (sinon extrais-le)."
    if s.gog:
        return ("GOG", ["GOG"], "") if s.setup else ("Portable", ["PORTABLE", "GOG"], "")
    if s.setup:
        return "DRM Free", ["DRM FREE"], ""
    return "Portable", ["PORTABLE", "DRM FREE"], ""


def app_tags(s: SoftAnalysis) -> list:
    """Table de décision C411 des applications."""
    if s.keygen:
        tags = ["KEYGEN"]
    elif s.crack:
        tags = ["CRACK"]
    elif s.patch:
        tags = ["PATCH"]
    else:
        tags = ["PREACTIVATED" if s.preactivated_word else "UNLOCKED"]
    if not s.installer or s.portable_word:
        tags.append("PORTABLE")
    return tags


def _version(stem: str) -> str:
    m = re.search(r"\bv?(\d+(?:\.\d+){1,3}[a-z]?)\b", stem.replace("_", " "), re.I)
    return m.group(1) if m else ""


_NOISE = r"(portable|setup|installer|repack|multi\d*|x64|x86|win(dows)?(64|32)?|macos|mac|linux|android|ios|" \
         r"french|english|fr|en|preactivated|pre-activated|cracked?|keygen|patch(ed)?|incl|gog|drm.?free)"


def _clean_title(stem: str) -> str:
    """'VLC media player 3.0.21 Windows x64' → 'VLC media player' ; 'Hades.v1.38-GOG' → 'Hades'."""
    t = re.sub(r"[\[(].*?[\])]", " ", stem)
    t = re.sub(r"(?:^|[ ._-])v?\d+(?:\.\d+){1,3}[a-z]?(?=$|[ ._-]).*$", "", t, flags=re.I)  # version et suite
    t = re.sub(r"-\w+$", "", t)
    if " " not in t.strip():                      # nom pointé : les points séparent les mots
        t = t.replace(".", " ").replace("_", " ")
    t = re.sub(rf"\b{_NOISE}\b", " ", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" -_")


class _SoftBase(Profile):
    dotted = False
    rename_on_disk = False

    def analyze(self, src, progress=None):
        return analyze(src, progress)

    def issues(self, ctx):
        s = ctx.analysis
        return Check(errors=list(s.errors), warnings=list(s.warnings))

    def query(self, ctx):
        return {"query": _clean_title(ctx.src.stem), "year": ""}

    def _common_details(self, ctx, install_default: str, reqs: str = ""):
        s = ctx.analysis
        return [
            Detail("version", "Version", _version(ctx.src.stem)),
            Detail("os", "Système", s.os or "Windows", choices=OS_LIST),
            Detail("languages", "Langues", "Français", hint="Langues du texte et des voix, ex. « Texte : FR, EN – Voix : EN »."),
            Detail("protection", "Protection / activation", "",
                   hint="Crack, loader, keygen, préactivé… Ce que contient la release."),
            Detail("requirements", "Configuration requise", reqs, multiline=True,
                   hint="Système, processeur, mémoire, carte graphique, espace disque."),
            Detail("install", "Installation", install_default, multiline=True,
                   hint="Étapes d'installation en français (obligatoire sauf version portable)."),
        ]

    def validate(self, name, ctx):
        c = Check()
        if not name.strip():
            c.errors.append("Le nom est vide.")
        err = banned_team_error(name)
        if err:
            c.errors.append(err)
        if re.search(r"[^\x20-\x7e]", name):
            c.errors.append("Accents et caractères spéciaux interdits dans le nom.")
        c.errors += self.issues(ctx).errors
        if ctx.analysis.nfo_text:
            c.infos.append(f"NFO d'origine trouvé ({ctx.analysis.nfo_name}) : il sera repris tel quel.")
        if not ctx.d("install") and "PORTABLE" not in name.upper():
            c.warnings.append("Instructions d'installation manquantes : C411 les exige (sauf version portable).")
        return c

    def nfo(self, ctx):
        s = ctx.analysis
        if s.nfo_text:
            return s.nfo_text
        n = Nfo(ctx.name).ident(ctx.ident)
        for key, label in (("version", "Version"), ("os", "Système"), ("languages", "Langues"),
                           ("protection", "Protection")):
            n.field(label, ctx.d(key))
        n.field("Taille", fmt_size(ctx.src.total_size)).field("Fichiers", len(ctx.src.files))
        if ctx.d("requirements"):
            n.section("Configuration requise").text(ctx.d("requirements"))
        if ctx.d("install"):
            n.section("Installation").text(ctx.d("install"))
        return n.files(ctx.src).render()

    def description(self, ctx):
        p = Prez().header(ctx.ident, ctx.name)
        if ctx.ident:
            p.block("Description", ctx.ident.overview).fiche(ctx.ident)
        p.items("Informations", [("Release", ctx.name), ("Version", ctx.d("version")), ("Système", ctx.d("os")),
                                 ("Langues", ctx.d("languages")), ("Activation", ctx.d("protection")),
                                 ("Taille", fmt_size(ctx.src.total_size))])
        p.block("Configuration requise", ctx.d("requirements")).block("Installation", ctx.d("install"))
        return p.files(ctx.src).render()


# ═══════════════════════════════════════════════════════════════════════════

class GameProfile(_SoftBase):
    key = "game"
    label = "Jeux Vidéo"
    icon = "🎮"
    category_id = 5
    subcategories = {36: "Windows", 29: "Linux", 30: "MacOS", 32: "Nintendo", 34: "Sony", 31: "Microsoft",
                     33: "Smartphone", 35: "Tablette", 55: "VR", 28: "Autre"}
    provider = "rawg"
    template = "Nom d'origine (scène, repack) · Nom V1.0 [WIN X64 MULTI PORTABLE] · Nom (V1.0) [MULTI WIN X64][GOG] · [SWITCH]Nom [EUR - MULTI] NSP"
    hint = "Une release scène ou repack garde son nom d'origine. Les autres cas suivent les modèles C411 ci-dessus."

    def score(self, src):
        s_names = " ".join(src.rel(f).lower() for f in src.files[:3000])
        sc = 0.0
        if any(f.suffix.lower() in CONSOLE_EXT for f in src.files):
            sc = 0.9
        if re.search(r"steam_api|goggame-|\bfitgirl|\bdodi|\belamigos|\brune\b|\btenoke\b|unityplayer|unrealengine|"
                     r"\.pak\b|data\.win|\bcodex\b", s_names):
            sc = max(sc, 0.85)
        if re.search(r"\b(game|jeu|repack|gog)\b", src.stem, re.I):
            sc = max(sc, 0.6)
        if src.by_ext(".exe") and src.total_size > 4 * 1024 ** 3:
            sc = max(sc, 0.55)
        return sc

    def summary(self, ctx):
        s = ctx.analysis
        mode, tags, _ = game_mode(s)
        rows = [("Type de release", mode + (f" [{' / '.join(tags)}]" if tags else ""))]
        if s.console:
            rows.append(("Console", s.console))
        if s.trusted_tag:
            rows.append(("Team reconnue", s.trusted_tag))
        found = [k for k, v in (("crack", s.crack), ("ISO", s.iso), ("setup.exe", s.setup),
                                ("steam_api", s.steam_api), ("GOG", s.gog)) if v]
        if found:
            rows.append(("Détecté", ", ".join(found)))
        if s.nfo_name:
            rows.append(("NFO d'origine", s.nfo_name))
        return rows

    def issues(self, ctx):
        c = super().issues(ctx)
        _, _, warn = game_mode(ctx.analysis)
        if warn:
            c.warnings.append(warn)
        return c

    def guess_sub(self, ctx):
        s = ctx.analysis
        if s.console:
            return CONSOLE_SUB.get(s.console, 28)
        if re.search(r"\bVR\b", ctx.src.stem):
            return 55
        return {"Windows": 36, "Linux": 29, "macOS": 30, "Android": 33, "iOS": 33}.get(s.os, 36)

    def parts(self, ctx):
        s = ctx.analysis
        mode, tags, _ = game_mode(s)
        title = clean_free(ctx.ident.title) if ctx.ident and ctx.ident.title else _clean_title(ctx.src.stem)
        os_token = CONSOLE_NAME.get(s.console, s.console) if s.console else \
            {"Windows": "WIN X64", "macOS": "MACOS", "Linux": "LINUX"}.get(s.os, "WIN X64")
        ps_id = (re.search(r"\b(CUSA|PPSA)\d{5}\b", ctx.src.stem, re.I) or [""])[0].upper()
        return [Part("vr", "Préfixe VR", "[VR]" if ctx.sub_id == 55 else "", choices=["", "[VR]"], width=6,
                     hint="Obligatoire pour un jeu VR."),
                Part("mode", "Modèle", mode, choices=GAME_MODES, width=26,
                     hint="Déduit des fichiers (table C411). Scène et repack de confiance gardent leur nom d'origine."),
                Part("original", "Nom d'origine", ctx.src.stem, width=50,
                     hint="Utilisé tel quel pour une release scène ou repack."),
                Part("title", "Nom du jeu", title, width=30),
                Part("version", "Version", _version(ctx.src.stem), width=10, hint="Version complète, ex. 1.0.132."),
                Part("os", "Système / console", os_token, width=10,
                     hint="WIN X64, MACOS, LINUX ; console : SWITCH, PS4, PS5, XBOX360, 3DS…"),
                Part("lang", "Langue", "MULTI" if re.search(r"multi", ctx.src.stem, re.I) else "FR",
                     choices=LANG_LIST, width=8),
                Part("tags", "Tags", ", ".join(t for t in tags if t != "PORTABLE"), width=24,
                     hint="Après le crochet principal : PREACTIVATED, DRM FREE, GOG… (séparés par des virgules)."),
                Part("region", "Région (console)", "", choices=["", "EUR", "PAL", "US", "JP", "HK"], width=6),
                Part("container", "Conteneur (console)", "", width=8, hint="NSP, XCI, WUA, ISO…"),
                Part("ps_id", "ID PS4 / PS5", ps_id, width=10, hint="Obligatoire pour PS4/PS5 : CUSA… ou PPSA…"),
                Part("firmware", "Firmware (PS5)", "", width=8, hint="Fortement recommandé pour la PS5, ex. 5.xx.")]

    def build(self, parts):
        p = {k: (v or "").strip() for k, v in parts.items()}
        mode, t, os_, lang = p.get("mode", ""), p.get("title", ""), p.get("os", ""), p.get("lang", "")
        v = p.get("version", "")
        vv = (v if v.upper().startswith("V") else f"V{v}") if v else ""
        tags = [x.strip().upper() for x in p.get("tags", "").split(",") if x.strip()]
        vr = "[VR] " if p.get("vr") else ""
        if mode.startswith("Nom d'origine"):
            name = p.get("original", "")
        elif mode == "Console":
            region = " - ".join(x for x in (p.get("region"), lang) if x)
            if os_.upper() in ("PS4", "PS5"):
                name = " ".join(x for x in (f"[{os_.upper()}]", t, f"({vv.lower()})" if vv else "", p.get("firmware"))
                                if x) + (f"[{region}]" if region else "") + (f"-{p['ps_id']}" if p.get("ps_id") else "")
            else:
                name = f"[{os_}]{t}" + (f" [{region}]" if region else "") + (f" {p['container']}" if p.get("container") else "")
        elif mode in ("GOG", "DRM Free"):
            name = f"{t}" + (f" ({vv})" if vv else "") + f" [{' '.join(x for x in (lang, os_) if x)}]" + \
                f"[{'GOG' if mode == 'GOG' else 'DRM FREE'}]"
        else:
            inner = " ".join(x for x in (os_, lang, "PORTABLE") if x)
            name = " ".join(x for x in (t, vv) if x) + f" [{inner}]" + "".join(f" [{x}]" for x in tags)
        return (vr + name).strip()

    def validate(self, name, ctx):
        c = super().validate(name, ctx)
        if ctx.sub_id == 55 and not name.startswith("[VR]"):
            c.errors.append("Jeu VR : le nom commence par [VR].")
        if ctx.parts.get("os", "").upper() in ("PS4", "PS5") and ctx.parts.get("mode") == "Console" \
                and not ctx.parts.get("ps_id"):
            c.errors.append("Jeu PS4 / PS5 : l'identifiant CUSA… ou PPSA… est obligatoire.")
        return c

    def details(self, ctx):
        s = ctx.analysis
        mode, _, _ = game_mode(s)
        reqs = ""
        if ctx.ident and ctx.ident.provider == "rawg":
            r = ctx.ident.raw.get("requirements") or {}
            reqs = re.sub(r"\n{2,}", "\n", (r.get("minimum") or "").strip())
        if mode == "Portable" or s.console:
            install = "1. Extraire ou copier le dossier.\n2. Lancer le jeu."
        elif s.iso:
            install = "1. Monter l'image ISO.\n2. Lancer setup.exe et installer le jeu.\n3. Copier le contenu du dossier crack dans le dossier d'installation.\n4. Lancer le jeu."
        else:
            install = "1. Lancer setup.exe.\n2. Suivre l'installation.\n3. Lancer le jeu."
        return self._common_details(ctx, install, reqs)

    def auto_options(self, types, ctx):
        s, out = ctx.analysis, {}
        lang = ctx.parts.get("lang", "FR")
        pick(types, out, "Langue", {"FR": "Français (VFF/TrueFrench)", "MULTI-FR": "Multi (Français inclus)",
                                    "MULTI": "Multi (Français inclus)", "EN": "Anglais"}.get(lang, "Anglais"))
        pick_fuzzy(types, out, "Genre Jeux", ctx.ident.genres if ctx.ident else [])
        c = CONSOLE_OPTION.get(s.console or ctx.parts.get("os", ""), "")
        for t in ("Console Nintendo", "Console Sony", "Console Microsoft"):
            pick(types, out, t, c)
        pick(types, out, "Système Mobile", {"Android": "Android", "iOS": "iOS"}.get(ctx.parts.get("os", ""), ""))
        return out


# ═══════════════════════════════════════════════════════════════════════════

class AppProfile(_SoftBase):
    key = "app"
    label = "Applications"
    icon = "🧩"
    category_id = 4
    subcategories = {27: "Windows", 24: "MacOS", 23: "Linux", 25: "Smartphone", 26: "Tablette",
                     22: "Formation", 21: "Autre"}
    provider = None
    template = "Nom.Version-TEAM [WINx64 LANGUE TYPE] · mobile : [Android] Nom.Version LANGUE [APK]"
    hint = "Le type (KEYGEN, CRACK, PATCH, UNLOCKED, PORTABLE…) est déduit des fichiers selon la table C411."

    def score(self, src):
        rels = " ".join(src.rel(f).lower() for f in src.files[:3000])
        sc = 0.0
        if src.by_ext(*INSTALLER_EXT) or src.by_ext(".exe"):
            sc = 0.5
        if re.search(r"keygen|crack|patch|setup|install|activator|portable", rels):
            sc = max(sc, 0.65)
        return sc

    def summary(self, ctx):
        s = ctx.analysis
        rows = [("Système", s.os or "?"), ("Type de release", " ".join(f"[{t}]" for t in app_tags(s)))]
        found = [k for k, v in (("keygen", s.keygen), ("crack", s.crack), ("patch", s.patch),
                                ("installateur", s.installer)) if v]
        if found:
            rows.append(("Détecté", ", ".join(found)))
        if s.nfo_name:
            rows.append(("NFO d'origine", s.nfo_name))
        return rows

    def guess_sub(self, ctx):
        s = ctx.analysis
        if re.search(r"formation|course|tuto|udemy|training", ctx.src.stem, re.I):
            return 22
        return {"Windows": 27, "macOS": 24, "Linux": 23, "Android": 25, "iOS": 25}.get(s.os, 21)

    def parts(self, ctx):
        s = ctx.analysis
        title = _clean_title(ctx.src.stem)
        mobile = s.os in ("Android", "iOS")
        ext = next((e.upper().lstrip(".") for e in (".apk", ".xapk", ".ipa") if any(n.endswith(e) for n in s.names)), "")
        stem = ctx.src.stem.lower()
        if s.os == "macOS":
            os_token = "MACOSarm64" if re.search(r"arm64|apple.?silicon|\bm1\b", stem) else "MACOSx64"
        elif s.os == "Linux":
            os_token = "LINUX"
        elif mobile:
            os_token = s.os
        else:
            os_token = "WINx86" if re.search(r"x86|32.?bit|win32", stem) else \
                "WINARM64" if "arm64" in stem else "WINx64"
        v = _version(ctx.src.stem)
        team = team_of(ctx.src.stem.replace(" ", ".")) if "-" in ctx.src.stem else ""
        return [Part("title", "Nom", slug(title) if not mobile else slug(title), width=30,
                     hint="Mots séparés par des points ; un tiret dans un nom de produit devient un point."),
                Part("version", "Version", f"v{v}" if v else "", width=12,
                     hint="Version complète et exacte (v7.3.6.10441, pas v7)."),
                Part("host", "Logiciel hôte (plugin)", "", width=18,
                     hint="Pour un plugin ou une extension : nom du logiciel hôte, ex. DaVinci.Resolve."),
                Part("team", "Team", team, width=12, hint="Tag d'origine, sinon NOTAG. Jamais un nom de site."),
                Part("os", "Système", os_token, choices=["WINx64", "WINx86", "WINARM64", "WIN", "MACOSx64",
                                                          "MACOSarm64", "MACOS", "LINUX", "Android", "iOS"], width=10,
                     hint="Architecture collée : WINx64, MACOSarm64… Sans architecture si multi-architecture."),
                Part("lang", "Langue", "MULTI" if re.search(r"multi", stem) else "FR", choices=["FR", "MULTI", "EN"],
                     width=8),
                Part("type", "Type", " ".join(app_tags(s)), width=24,
                     hint="Un seul parmi CRACK, KEYGEN, PATCH, UNLOCKED, PREACTIVATED, puis PORTABLE en dernier."),
                Part("ext", "Extension (mobile)", ext if mobile else "", width=6)]

    def build(self, parts):
        p = {k: (v or "").strip() for k, v in parts.items()}
        t, v, os_, lang = p.get("title", ""), p.get("version", ""), p.get("os", ""), p.get("lang", "")
        name = ".".join(x for x in (t, v) if x)
        if p.get("host"):
            name += f".({slug(p['host'])})"
        if os_ in ("Android", "iOS"):
            return " ".join(x for x in (f"[{os_}]", name, lang, f"[{p['ext']}]" if p.get("ext") else "") if x)
        if p.get("team"):
            name += f"-{p['team']}"
        inner = " ".join(x for x in (os_, lang, p.get("type", "")) if x)
        return name + (f" [{inner}]" if inner else "")

    def details(self, ctx):
        s = ctx.analysis
        if "PORTABLE" in app_tags(s):
            install = "1. Extraire le dossier.\n2. Lancer l'exécutable."
        elif s.keygen:
            install = "1. Installer le logiciel (setup).\n2. Lancer le keygen et générer une clé.\n3. Activer le logiciel avec la clé."
        elif s.crack or s.patch:
            install = "1. Installer le logiciel (setup).\n2. Copier le crack / appliquer le patch dans le dossier d'installation.\n3. Lancer le logiciel."
        else:
            install = "1. Installer le logiciel (setup).\n2. Lancer le logiciel (déjà activé)."
        return self._common_details(ctx, install)

    def validate(self, name, ctx):
        c = super().validate(name, ctx)
        head = name.split(" [", 1)[0]
        if ctx.parts.get("os") not in ("Android", "iOS") and re.search(r"[ _+]", head):
            c.errors.append("Applications : les mots du nom et de la version sont séparés par des points.")
        if re.search(r"\b(VFF|VFI|VFQ|VOSTFR|TRUEFRENCH|VF2|VOF)\b", name):
            c.errors.append("Les tags de langue vidéo (VFF, VOSTFR…) n'existent pas en Applications : FR, EN ou MULTI.")
        typ = ctx.parts.get("type", "").upper().split()
        if len([x for x in typ if x in ("CRACK", "KEYGEN", "PATCH", "CRACKFIX")]) > 1:
            c.errors.append("Un seul type d'activation par release : CRACK, KEYGEN et PATCH sont exclusifs.")
        if "PORTABLE" in typ and typ[-1] != "PORTABLE":
            c.errors.append("PORTABLE se place en dernier dans le crochet.")
        if re.search(r"\b(DMG|EXE|ISO|MSI|PKG|20\d\d)\b", name.split("[", 1)[-1]) and ctx.parts.get("os") not in ("Android", "iOS"):
            c.errors.append("Le crochet ne contient ni année ni extension de fichier (DMG, EXE, ISO, MSI…).")
        if re.search(r"\b(alpha|early.?access)\b", name, re.I):
            c.warnings.append("Versions alpha et early access refusées par C411.")
        if re.search(r"\biptv\b", name, re.I):
            c.errors.append("Logiciels IPTV interdits sur C411.")
        if re.search(r"plugin|extension|addon", name, re.I):
            c.infos.append("Plugin : le logiciel hôte doit être sur C411 ; mets son lien dans la description.")
        return c

    def auto_options(self, types, ctx):
        out = {}
        lang = {"FR": "Français", "Multi": "Multi (Français inclus)", "EN": "Anglais"}.get(ctx.parts.get("lang", "FR"))
        pick(types, out, "Langue", lang)
        pick(types, out, "Système Mobile", {"Android": "Android", "iOS": "iOS"}.get(ctx.parts.get("os", ""), ""))
        return out
