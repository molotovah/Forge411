"""
XXX (adulte, -18) : scènes et films de studios, VR, JAV, hentai, images, ebooks, jeux.

Règles du wiki C411 (pages « Adulte » et « Le Nommage de l'upload ») :
- vidéo : [Studio].Titre.Acteur.[Catégorie].Résolution.Codec ; pack : [Studio][PACK]… ;
  JAV : JAV.[CODE].Titre.Romanise ; hentai vidéo : règles des séries + préfixe [HENTAI] ;
- images : [Studio].Titre.Acteur.[Catégorie][JPG]-Tag, un seul critère d'unification ;
- manga / doujinshi et magazines : règles des ebooks, en français, anglais ou japonais (coréen pour un manhwa) ;
- jeux : règles des jeux vidéo, archives autorisées ;
- vidéo : .MOV accepté (sauf hentai), multi-tag autorisé, pas de minimum de débit audio, toute langue ;
- interdits : amateur, rips d'hébergeurs (PornHub…), archives hors jeux, SWF / FLV / RM, contenus tolérance zéro.
"""

import dataclasses
import re
from dataclasses import dataclass, field
from typing import Any

from .. import videoinfo as vi
from ..model import Check, Detail, Part, fmt_size, slug
from ..render import Nfo, Prez
from .base import ARCHIVE_EXT, Profile, banned_team_error, lang_from_tag, pick
from .ebook import BOOK_EXT, COMIC_EXT, IMG_EXT, EbookProfile
from .software import GameProfile
from .video import VideoProfile, detect_source, detect_team

VIDEO_EXT = vi.VIDEO_EXT | {".mov"}
BANNED_EXT = {".swf", ".flv", ".rm"}
SUB_EXT = {".srt", ".sub", ".ass", ".ssa", ".idx", ".vtt"}
PICTURE_EXT = IMG_EXT | {".gif", ".bmp", ".tif", ".tiff", ".heic"}
GAME_HINT_EXT = {".exe", ".apk", ".rpa", ".rpy", ".swf"}

SUB_FILMS, SUB_VR, SUB_HENTAI, SUB_IMAGES, SUB_EBOOKS, SUB_GAMES = 43, 56, 44, 45, 42, 46
TPDB_SUBS = (SUB_FILMS, SUB_VR)

# Hébergeurs dont les rips sont interdits
TUBE_SITES = ("pornhub", "xhamster", "youporn", "xvideos", "xnxx", "redtube", "tube8", "spankbang", "eporner",
              "youjizz", "beeg", "motherless")
# Tolérance zéro (bannissement immédiat) : signalé dès le nom
ZERO_TOLERANCE = re.compile(r"\b(loli(con)?|shota(con)?|zoo(phil\w*)?|bestiality|beastiality|p(a)?edo\w*|"
                            r"preteen|underage|mineure?s?|jailbait)\b", re.I)
XXX_MARKERS = re.compile(
    r"\b(xxx|jav|hentai|doujin(shi)?|eroge|onlyfans|fansly|manyvids|siterip|brazzers|bangbros|realitykings|"
    r"naughtyamerica|tushy|blacked|badoinkvr|vrbangers|wankzvr|vrcosplayx|sexlikereal|nubilefilms|"
    r"dorcel|evilangel|julesjordan|digitalplayground|teamskeet|mofos|metart|porn\w*)\b", re.I)
STUDIO_DATE = re.compile(r"^\[[^\]]+\][. ]?(19|20)\d\d[.\-]\d\d[.\-]\d\d")
JAV_CODE = re.compile(r"\b([A-Z]{2,6})-?(\d{3,5})\b")
VR_MARKERS = re.compile(r"\b(vr|vr180|vr360|180x180|360|sbs|3dh|oculus|quest|gearvr|[5-8]k)\b", re.I)

LANGS = ["ENGLISH", "FRENCH", "MULTI", "VO", "JAPANESE", "GERMAN", "SPANISH", "ITALIAN", "VOSTFR"]
_LANG_CODES = {"en": "ENGLISH", "fr": "FRENCH", "ja": "JAPANESE", "de": "GERMAN", "es": "SPANISH",
               "it": "ITALIAN"}
CATEGORIES = ["", "GAY", "LESBIAN", "TRANS", "BI", "FETISH", "BDSM"]
BOOK_LANGS = ["FR", "EN", "JP", "KR"]          # KR : manhwa uniquement

# Qualité C411 (sous-catégorie Films) : (source, résolution) → libellé d'option
QUALITY = {("WEB", "2160p"): "WEB-DL 4K", ("WEB", "1080p"): "WEB-DL 1080", ("WEB", "720p"): "WEB-DL 720",
           ("WEB", ""): "WEB-DL", ("WEBRip", "2160p"): "WEBRip 4K", ("WEBRip", "1080p"): "WEBRip 1080",
           ("WEBRip", "720p"): "WEBRip 720", ("WEBRip", ""): "WEBRip", ("DVDRip", ""): "DVDRip",
           ("DVD", ""): "DVD-R 9 [DVD > 4.37GB]", ("BluRay", "1080p"): "HDRip 1080 [Rip HD depuis BluRay]",
           ("BluRay", "720p"): "HDRip 720 [Rip HD depuis BluRay]", ("BluRay", "2160p"): "HDRip 4K [Rip HD 4K depuis source 4K]",
           ("BluRay.REMUX", ""): "BluRay [Remux]", ("UHD.BluRay.REMUX", ""): "BluRay 4K [Full ou Remux]",
           ("HDTV", "1080p"): "TVRipHD 1080 [Rip HD depuis source TV HD]",
           ("HDTV", "720p"): "TVRipHD 720 [Rip HD depuis source TV HD]", ("SDTV", ""): "TVRip [Rip SD depuis source TV HD/SD]"}
OPTION_LANG = {"ENGLISH": "Anglais", "VO": "Anglais", "FRENCH": "Français (VFF/TrueFrench)",
               "MULTI": "Multi (Français inclus)", "VOSTFR": "VOSTFR", "MUET": "Muet"}


@dataclass
class XxxAnalysis:
    kind: str = "video"              # video | book | images | game
    video: Any = None                # VideoAnalysis
    book: Any = None                 # EbookAnalysis
    game: Any = None                 # SoftAnalysis
    counts: dict = field(default_factory=dict)
    images: int = 0
    movs: int = 0
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def _kind(src) -> str:
    counts = src.ext_counts()
    n = lambda exts: sum(v for e, v in counts.items() if e in exts)
    if n(VIDEO_EXT):
        return "video"
    if n(BOOK_EXT | COMIC_EXT):
        return "book"
    if n({".exe", ".apk", ".rpa", ".rpy"}) or (n(ARCHIVE_EXT) and not n(PICTURE_EXT)):
        return "game"
    if n(PICTURE_EXT):
        return "images"
    return "video"


def analyze(src, progress=None) -> XxxAnalysis:
    a = XxxAnalysis(kind=_kind(src), counts=src.ext_counts())
    exts = set(a.counts)
    if exts & BANNED_EXT:
        a.errors.append("Formats interdits en XXX : " + ", ".join(sorted(e.upper().lstrip(".") for e in exts & BANNED_EXT)) + ".")
    if a.kind != "game" and exts & ARCHIVE_EXT:
        a.errors.append("Archives RAR / ZIP / 7Z interdites en XXX (sauf jeux) : extrais-les.")
    if a.kind == "video":
        va = vi.analyze(src, progress)
        # Règles XXX : .MOV accepté, archives et formats traités ci-dessus
        va.errors = [e for e in va.errors if not e.startswith(("Formats refusés", "Aucune vidéo"))]
        movs = src.by_ext(".mov")
        a.movs = len(movs)
        for i, f in enumerate(movs):
            if progress:
                progress(f"Analyse MediaInfo : {f.name}")
            va.videos.append(vi.read_media(f, with_text=not va.videos))
        if ".wmv" in exts:
            a.errors.append("Format WMV non accepté (AVI, TS, MP4, M4V, MKV, M2TS, MOV).")
        if re.match(r"^\[hentai\]", src.stem, re.I):       # analyse du nom sans le préfixe
            from ..scanner import parse_release_name
            va.parsed = parse_release_name(vi.normalize_name(re.sub(r"^\[hentai\][. ]?", "", src.stem, flags=re.I)))
        a.video = va
        a.errors += va.errors
        a.warnings += [w for w in va.warnings if "pas toutes les mêmes caractéristiques" not in w]
        if len(va.videos) > 1 and len({v.path.suffix.lower() for v in va.videos}) > 1:
            a.errors.append("Pack vidéo : tous les fichiers doivent avoir le même format (même conteneur).")
        videos = {f.stem for f in src.by_ext(*VIDEO_EXT)}
        for s in src.by_ext(*SUB_EXT):
            if not any(s.stem == v or s.stem.startswith(v + ".") for v in videos):
                a.warnings.append(f"Sous-titres « {s.name} » : nomme-les comme le fichier vidéo.")
                break
    elif a.kind == "book":
        from .ebook import analyze as book_analyze
        a.book = book_analyze(src, progress)
        a.errors += [e for e in a.book.errors if not e.startswith("Archives")]
        a.warnings += a.book.warnings
    elif a.kind == "game":
        from .software import analyze as soft_analyze
        a.game = soft_analyze(src, progress)
        a.game.errors = [e for e in a.game.errors if not e.startswith("Archives")]     # permises en XXX
        a.errors += a.game.errors
        a.warnings += a.game.warnings
    else:
        a.images = len(src.by_ext(*PICTURE_EXT))
    return a


def content_errors(name: str) -> list:
    """Interdits détectables dans un nom (source ou titre)."""
    out = []
    low = name.lower()
    if ZERO_TOLERANCE.search(name):
        out.append("Contenu interdit (tolérance zéro, bannissement immédiat) : mineurs, lolicon / shotacon, "
                   "zoophilie. Vérifie le nom : C411 refuse ce contenu sans exception.")
    tube = next((t for t in TUBE_SITES if t in low), "")
    if tube:
        out.append(f"Rip d'hébergeur vidéo ({tube}) interdit en XXX.")
    if re.search(r"\bamateur\b", low):
        out.append("Le porno amateur (non professionnel) est interdit en XXX.")
    return out


def _lang(mf, raw: str) -> str:
    up = [t.upper() for t in re.split(r"[.\s_\-\[\]]+", raw)]
    for t in LANGS:
        if t in up:
            return t
    fr = vi.language_tag(mf, None) if mf else ""
    if fr:
        return fr
    if mf and mf.audios:
        return _LANG_CODES.get((mf.audios[0].language or "")[:2].lower(), "VO")
    return "VO"


def _slug(text: str) -> str:
    """slug() qui garde les tirets internes (ex. Siterip.2019-2024)."""
    return "-".join(x for x in (slug(t) for t in (text or "").split("-")) if x)


def _bracket(v: str) -> str:
    v = v.strip().strip("[]").strip()
    return f"[{v}]" if v else ""


class XxxProfile(Profile):
    key = "xxx"
    label = "XXX"
    icon = "🔞"
    category_id = 8
    subcategories = {SUB_FILMS: "Films", SUB_VR: "VR", SUB_HENTAI: "Hentai", SUB_IMAGES: "Images",
                     SUB_EBOOKS: "Ebooks", SUB_GAMES: "Jeux"}
    provider = None
    template = ("[Studio].Titre.Acteur.[Catégorie].Langue.Source.Résolution.Audio.Codec-Team · "
                "[Studio][PACK]… · JAV.[CODE].Titre.Romanise · [HENTAI].Titre.S01… · [Studio].Titre.Acteur.[JPG]-Tag")
    hint = ("Productions professionnelles uniquement : amateur, rips d'hébergeurs et contenus tolérance zéro interdits. "
            "Précise la catégorie si elle n'est pas hétéro.")

    _video = VideoProfile()
    _book = EbookProfile()
    _game = GameProfile()

    # ── Délégation selon le contenu ───────────────────────────────────────
    def _mode(self, ctx) -> str:
        """studio | jav | hentai (vidéo) | book | images | game."""
        a = ctx.analysis
        if a.kind == "video":
            if ctx.sub_id == SUB_HENTAI:
                return "hentai"
            mode = ctx.parts.get("mode") if ctx.parts else ""
            if mode in ("Studio", "JAV"):
                return mode.lower()
            return "jav" if re.match(r"^jav\b", ctx.src.stem, re.I) else "studio"
        return a.kind

    def _inner(self, ctx):
        a = ctx.analysis
        return dataclasses.replace(ctx, analysis={"video": a.video, "book": a.book, "game": a.game}.get(a.kind))

    # ── Détection / analyse ───────────────────────────────────────────────
    def score(self, src):
        names = src.stem + " " + " ".join(src.rel(f) for f in src.files[:50])
        if STUDIO_DATE.search(src.stem) or re.match(r"^(jav[. ]|\[hentai\])", src.stem, re.I):
            return 1.1
        return 1.05 if XXX_MARKERS.search(names.replace("_", " ")) else 0.0

    def analyze(self, src, progress=None):
        return analyze(src, progress)

    def summary(self, ctx):
        a = ctx.analysis
        kinds = {"video": "Vidéo", "book": "Manga / doujinshi / magazine", "images": "Pack d'images", "game": "Jeu"}
        rows = [("Contenu", kinds[a.kind])]
        if a.kind == "video" and a.video:
            rows += self._video.summary(self._inner(ctx))
        elif a.kind == "book":
            rows += self._book.summary(self._inner(ctx))
        elif a.kind == "game":
            rows += self._game.summary(self._inner(ctx))
        else:
            rows.append(("Images", str(a.images)))
        return rows

    def issues(self, ctx):
        a = ctx.analysis
        c = Check(errors=list(a.errors), warnings=list(a.warnings))
        c.errors += content_errors(ctx.src.stem)
        if a.movs and ctx.sub_id == SUB_HENTAI:
            c.errors.append("Format MOV interdit pour le hentai.")
        if a.kind == "book" and a.book and a.book.language:
            lang = a.book.language.lower()[:2]
            if lang not in ("fr", "en", "ja", "ko"):
                c.errors.append(f"Langue du livre : {a.book.language}. Manga / doujinshi : français, anglais ou japonais "
                                "uniquement (coréen pour un manhwa).")
        return c

    def guess_sub(self, ctx):
        a, stem = ctx.analysis, ctx.src.stem
        if re.search(r"hentai|doujin|\bmanga\b|manhwa|\becchi\b", stem, re.I):
            return SUB_HENTAI
        if a.kind == "video":
            return SUB_VR if VR_MARKERS.search(stem.replace("_", " ")) else SUB_FILMS
        return {"book": SUB_EBOOKS, "images": SUB_IMAGES, "game": SUB_GAMES}[a.kind]

    def provider_for(self, ctx):
        """ThePornDB pour les vidéos des sous-catégories Films et VR (seules acceptées par C411 avec tpdbData)."""
        return "tpdb" if ctx.analysis and ctx.analysis.kind == "video" and ctx.sub_id in TPDB_SUBS else None

    def meta(self, ctx):
        key, data = super().meta(ctx)
        if key == "tpdbData" and ctx.sub_id not in TPDB_SUBS:
            return "", None
        return key, data

    def query(self, ctx):
        from ..lookup.tpdb import clean_query
        a = ctx.analysis
        if a and a.kind in ("book", "game"):           # règles ebook ou jeux : leur propre analyse du nom
            return (self._book if a.kind == "book" else self._game).query(self._inner(ctx))
        if self.provider_for(ctx) != "tpdb":         # pas de fiche en ligne : titre tiré du nom (hentai, images…)
            parsed = a.video.parsed if a and a.kind == "video" and a.video else None
            title = parsed.title.replace(".", " ") if parsed and parsed.title else \
                re.sub(r"[._]+", " ", re.sub(r"^(\[[^\]]*\][. ]?)+|-[A-Za-z0-9]+$", "", ctx.src.stem)).strip()
            return {"query": title, "year": ""}
        date = (re.search(r"\b(19|20)\d\d(?=[.\-]\d\d[.\-]\d\d)", ctx.src.stem) or [""])[0]
        return {"query": clean_query(re.sub(r"-[A-Za-z0-9]+$", "", ctx.src.stem)), "year": date}

    def search(self, client, q):
        return client.search(q.get("query", ""), q.get("year", ""))

    # ── Nom ───────────────────────────────────────────────────────────────
    def parts(self, ctx):
        mode = self._mode(ctx)
        if mode == "book":
            parts = self._book.parts(self._inner(ctx))
            for p in parts:
                if p.key == "lang":
                    p.value = "EN" if p.value == "FR" and not re.search(r"\b(fr|french|vf)\b", ctx.src.stem, re.I) else p.value
                    p.choices = BOOK_LANGS
                    p.hint = "XXX : français, anglais ou japonais (coréen pour un manhwa). Titre romanisé ou traduit."
            return parts
        if mode == "game":
            return self._game.parts(self._inner(ctx))
        if mode == "images":
            return self._image_parts(ctx)
        if mode == "hentai":
            parts = self._video.parts(self._inner(ctx))
            for p in parts:
                if p.key == "title":
                    p.value = re.sub(r"^\[?hentai\]?\.?", "", p.value, flags=re.I)
            return [Part("prefix", "Préfixe", "[HENTAI]", choices=["[HENTAI]"], width=10,
                         hint="Obligatoire pour une vidéo hentai.")] + parts
        return self._scene_parts(ctx)

    def _scene_parts(self, ctx):
        va, src = ctx.analysis.video, ctx.src
        mf, raw = va.main, src.stem
        studio = (re.match(r"^\[([^\]]+)\]", raw) or [None, ""])[1]
        date = (re.search(r"\b((19|20)\d\d)[.\-](\d\d)[.\-](\d\d)\b", raw) or [""])[0].replace("-", ".")
        jav = JAV_CODE.search(raw.upper())
        rest = re.sub(r"^\[[^\]]*\][. ]?|^jav[. ]", "", raw, flags=re.I)
        rest = rest.replace(date, "") if date else rest
        if jav:
            rest = rest.replace(jav.group(0), "")
        tokens = [t for t in re.split(r"[.\s_]+", re.sub(r"-[A-Za-z0-9]+$", "", rest)) if t]
        stop = {"WEB", "WEBRIP", "WEB-DL", "1080P", "720P", "2160P", "4K", "5K", "6K", "7K", "8K", "X264", "X265",
                "H264", "H265", "HEVC", "AVC", "AAC", "AAC2", "MP4", "MKV", "SBS", "LR", "180", "360"} | set(LANGS)
        title = ".".join(t for t in tokens if t.upper() not in stop and t.strip("[]").upper() != "PACK"
                         and not re.fullmatch(r"\d\.\d|\d{3,4}p", t, re.I))
        performers = ""
        ident = ctx.ident if ctx.ident and ctx.ident.provider == "tpdb" else None
        if ident:                                  # fiche ThePornDB : studio, date, titre, interprètes
            studio = studio or ident.raw.get("site") or ""     # le studio du nom d'origine reste prioritaire
            date = (ident.raw.get("date") or "").replace("-", ".") or date
            title = ident.title or title
            performers = ".".join(slug(n) for n in ident.raw.get("performers", [])[:3])
        source = detect_source(raw) or "WEB"
        resolution = vi.resolution_tag(mf) or (re.search(r"\b([5-8]K)\b", raw.upper()) or [None, ""])[1]
        multi = len(va.videos) > 1
        mode = "JAV" if re.match(r"^jav\b", raw, re.I) or (jav and not studio) else "Studio"
        return [
            Part("mode", "Modèle", mode, choices=["Studio", "JAV"], width=8,
                 hint="Studio : [Studio].Titre.Acteur… JAV : JAV.[CODE].Titre.Romanise (code obligatoire)."),
            Part("studio", "Studio / site", studio, width=18,
                 hint="Nom du studio entre crochets en tête du nom, ex. [Brazzers], [Nubile Films]."),
            Part("pack", "Pack", "[PACK]" if multi else "", choices=["", "[PACK]"], width=8,
                 hint="Obligatoire dès que le torrent contient plusieurs médias (même studio ou même interprète, même format)."),
            Part("code", "Code JAV", f"{jav.group(1)}-{jav.group(2)}" if jav else "", width=10,
                 hint="Référence du JAV, ex. SSIS-123. Obligatoire en JAV."),
            Part("date", "Date", date, width=10, hint="Date de sortie de la scène (AAAA.MM.JJ), si le studio en donne une."),
            Part("title", "Titre", slug(title.replace(".", " ")), width=30,
                 hint="Titre de la scène ou du film ; romanisé pour un JAV."),
            Part("performers", "Interprètes", performers, width=24,
                 hint="Acteur(s) / actrice(s) ou réalisateur, ex. Kenna.James. Obligatoire pour un pack par interprète."),
            Part("category", "Catégorie (si non hétéro)", "", choices=CATEGORIES, width=10,
                 hint="Obligatoire si le contenu n'est pas hétéro : GAY, LESBIAN, TRANS…"),
            Part("language", "Langue", _lang(mf, raw), choices=LANGS, width=10,
                 hint="Toutes les langues sont acceptées en XXX."),
            Part("source", "Source", source, choices=["WEB", "WEBRip", "DVD", "DVDRip", "BluRay", "HDTV", "SDTV"], width=8),
            Part("resolution", "Résolution", resolution, width=8, hint="1080p, 2160p… En VR : 5K, 6K, 7K, 8K."),
            Part("audio", "Audio", vi.audio_tag(mf), width=10, hint="Pas de débit audio minimum en XXX."),
            Part("video", "Codec vidéo", vi.video_codec_tag(mf, source), width=8),
            Part("team", "Team", self._team(raw, va, jav), width=12,
                 hint="Tag de l'équipe d'origine. NOTAG si introuvable."),
        ]

    @staticmethod
    def _team(raw, va, jav) -> str:
        team = detect_team(raw, va.parsed.team if va.parsed else None)
        if jav and team and team == jav.group(2):          # « SSIS-123 » : le numéro n'est pas une team
            return ""
        return team

    def _image_parts(self, ctx):
        stem = ctx.src.stem
        studio = (re.match(r"^\[([^\]]+)\]", stem) or [None, ""])[1]
        exts = []
        for e, _ in sorted(ctx.analysis.counts.items(), key=lambda x: -x[1]):
            if e in PICTURE_EXT:
                tag = "JPG" if e in (".jpg", ".jpeg") else e.lstrip(".").upper()
                if tag not in exts:
                    exts.append(tag)
        title = re.sub(r"^(\[[^\]]*\])+|-[A-Za-z0-9]+$|\[(JPG|PNG|WEBP|GIF)\]", "", stem, flags=re.I)
        team = (re.search(r"-([A-Za-z0-9]+)$", stem) or [None, "NOTAG"])[1]
        return [
            Part("studio", "Studio / site", studio, width=18,
                 hint="Studio, site ou plateforme entre crochets, ex. [ONLYFANS]."),
            Part("pack", "Pack", "[PACK]" if ctx.src.is_dir else "", choices=["", "[PACK]"], width=8),
            Part("title", "Titre", slug(title.replace(".", " ")), width=26,
                 hint="Un seul critère d'unification, écrit dans le titre : artiste, photographe, studio, scène ou interprète."),
            Part("performers", "Interprète / artiste", "", width=22),
            Part("category", "Catégorie (si non hétéro)", "", choices=CATEGORIES, width=10),
            Part("formats", "Formats", "".join(f"[{e}]" for e in exts[:3]), width=12, hint="Chaque format entre crochets : [JPG][PNG]."),
            Part("team", "Team", team, width=12),
        ]

    def build(self, parts):
        p = {k: (v or "").strip() for k, v in parts.items()}
        if "prefix" in p:                                   # hentai vidéo
            return f"{p['prefix']}." + self._video.build({k: v for k, v in parts.items() if k != "prefix"})
        if "formats" in p and "mode" not in p and "studio" in p:   # images
            head = _bracket(p.get("studio", "")) + p.get("pack", "")
            name = ".".join(x for x in [head] + [_slug(p.get(k, "")) for k in ("title", "performers")]
                            + [p.get("category", "")] if x)
            return f"{name}{'.' if name else ''}{p.get('formats', '')}-{p.get('team') or 'NOTAG'}"
        if "mode" in p and "studio" in p:                   # scène / film / JAV
            tech = [p.get(k, "").strip(". ") for k in ("language", "source", "resolution", "audio", "video")]
            cat = p.get("category", "")
            if p.get("mode") == "JAV":
                head = "JAV" + (f".[{p['code'].strip('[]').upper()}]" if p.get("code") else "") + p.get("pack", "")
                body = [_slug(p.get("title", "")), _slug(p.get("performers", "")), cat] + tech
            else:
                head = _bracket(p.get("studio", "")) + p.get("pack", "")
                body = [p.get("date", ""), _slug(p.get("title", "")), _slug(p.get("performers", "")), cat] + tech
            name = ".".join(x for x in [head] + body if x)
            return f"{name}-{p.get('team') or 'NOTAG'}"
        if "set" in p or "date" in p and "format" in p:     # ebook délégué
            return self._book.build(parts)
        return self._game.build(parts)

    def validate(self, name, ctx):
        mode = self._mode(ctx)
        c = Check()
        name = name.strip()
        if not name:
            c.errors.append("Le nom est vide.")
            return c
        c.errors += content_errors(name)
        if mode == "book":
            inner = self._book.validate(name, self._inner(ctx))
            c.errors += [e for e in inner.errors if not e.startswith("Archives")]
            c.warnings += [w for w in inner.warnings if "français" not in w]
            if ctx.parts.get("lang") == "KR":
                c.infos.append("Coréen accepté uniquement pour un manhwa.")
        elif mode == "game":
            inner = self._game.validate(name, self._inner(ctx))
            c.errors += inner.errors
            c.warnings += inner.warnings
            c.infos += inner.infos
        elif mode == "hentai":
            if not name.startswith("[HENTAI]."):
                c.errors.append("Vidéo hentai : le nom commence par [HENTAI].")
            inner = self._video.validate(name[len("[HENTAI]."):] if name.startswith("[HENTAI].") else name, self._inner(ctx))
            c.errors += [e for e in inner.errors if "française" not in e and "multi-tag" not in e
                         and not e.startswith("DETAG de cohérence")]
            c.warnings += inner.warnings
        elif mode == "images":
            if not re.search(r"\[(JPG|JPEG|PNG|WEBP|GIF|BMP|TIFF?|HEIC)\]", name, re.I):
                c.errors.append("Indique le format des images entre crochets : [JPG], [PNG]…")
            if not (ctx.parts.get("title") or ctx.parts.get("performers") or ctx.parts.get("studio")):
                c.errors.append("Pack d'images : le titre doit nommer le critère unique (artiste, photographe, studio, "
                                "scène ou interprète). Les packs « random » sont interdits.")
            c.infos.append("Un seul critère d'unification par pack ; images sans lien entre elles interdites.")
        else:
            self._validate_scene(name, ctx, mode, c)
        err = banned_team_error(name)
        if err:
            c.errors.append(err)
        c.errors += [e for e in self.issues(ctx).errors if e not in c.errors]
        c.warnings += [w for w in self.issues(ctx).warnings if w not in c.warnings]
        c.infos.append("Doublons interdits ; un pack complet reste permis si les scènes existent déjà seules (même format).")
        return c

    def _validate_scene(self, name, ctx, mode, c):
        p, va = ctx.parts, ctx.analysis.video
        if mode == "jav":
            if not re.match(r"^JAV\.\[[A-Z0-9]+-\d+\]", name):
                c.errors.append("JAV : le code référence est obligatoire, au format JAV.[CODE-123].Titre.")
        elif not name.startswith("["):
            c.warnings.append("Commence par le studio entre crochets : [Studio].Titre.Acteur…")
        if va and len(va.videos) > 1 and "[PACK]" not in name.upper():
            c.errors.append("Plusieurs médias dans le torrent : c'est un pack, ajoute [PACK] après le studio.")
        if re.search(r"[^A-Za-z0-9À-ÿ.\-+\[\]& ]", name):
            c.errors.append("Caractères interdits : lettres, chiffres, points, crochets et le tiret de la team.")
        if " " in re.sub(r"\[[^\]]*\]", "", name):
            c.errors.append("Pas d'espaces hors des crochets du studio : les mots sont séparés par des points.")
        if not p.get("title") and not p.get("performers"):
            c.errors.append("Indique au moins le titre ou l'interprète.")
        if not p.get("resolution"):
            c.warnings.append("Résolution inconnue : ajoute-la (1080p, 2160p, 7K…).")
        if not p.get("video"):
            c.warnings.append("Codec vidéo inconnu : ajoute-le (x264, x265, H264…).")
        mf = va.main if va else None
        if mf is not None and vi.MEDIAINFO_OK and mf.video:
            if any(g in mf.video.library.lower() for g in ("nvenc", "qsv", "amf", "vce", "quicksync")):
                c.errors.append("Encodage GPU (NVENC, QSV, AMF) interdit sur C411.")
        if not p.get("category"):
            c.infos.append("Contenu non hétéro : la catégorie (GAY, LESBIAN, TRANS…) est obligatoire dans le nom.")

    def details(self, ctx):
        mode = self._mode(ctx)
        if mode == "book":
            return self._book.details(self._inner(ctx))
        if mode == "game":
            return self._game.details(self._inner(ctx))
        rows = [Detail("synopsis", "Description", "", multiline=True, hint="Résumé de la scène, du film ou du pack.")]
        if mode in ("studio", "jav", "images"):
            cast = ", ".join(ctx.ident.raw.get("performers", [])) if ctx.ident and ctx.ident.provider == "tpdb" else ""
            rows.insert(0, Detail("cast", "Interprètes", cast or (ctx.parts or {}).get("performers", "").replace(".", " "),
                                  hint="Noms complets, séparés par des virgules."))
            rows.insert(1, Detail("link", "Lien officiel", "", hint="Page du studio ou de la scène (facultatif)."))
        return rows

    def tag_fixes(self, ctx):
        return self._video.tag_fixes(ctx) if self._mode(ctx) == "hentai" else []

    def on_renamed(self, ctx, old_name, new_name):
        if ctx.analysis.kind == "video":
            self._video.on_renamed(self._inner(ctx), old_name, new_name)

    # ── NFO / présentation ────────────────────────────────────────────────
    def _facts(self, ctx):
        p = ctx.parts or {}
        return [("Studio", p.get("studio", "")), ("Code", p.get("code", "")), ("Date", p.get("date", "")),
                ("Interprètes", ctx.d("cast")), ("Catégorie", p.get("category", "")), ("Lien", ctx.d("link"))]

    def nfo(self, ctx):
        mode = self._mode(ctx)
        if mode == "book":
            return self._book.nfo(self._inner(ctx))
        if mode == "game":
            return self._game.nfo(self._inner(ctx))
        if mode == "images":
            n = Nfo(ctx.name)
            for k, v in self._facts(ctx):
                n.field(k, v)
            n.field("Images", ctx.analysis.images).field("Taille totale", fmt_size(ctx.src.total_size))
            if ctx.d("synopsis"):
                n.section("Description").text(ctx.d("synopsis"))
            return n.files(ctx.src, limit=5000).render()
        text = self._video.nfo(self._inner(ctx))
        facts = Nfo("")
        for k, v in self._facts(ctx):
            facts.field(k, v)
        facts = facts.lines[6:]
        if facts:                                   # informations de la scène avant la fiche technique
            lines = text.split("\n")
            bar = [i for i, ln in enumerate(lines) if ln == "=" * len(ln) and len(ln) > 20][1]
            lines[bar + 2:bar + 2] = facts + [""]
            text = "\n".join(lines)
        return text

    def description(self, ctx):
        mode = self._mode(ctx)
        if mode == "book":
            return self._book.description(self._inner(ctx))
        if mode == "game":
            return self._game.description(self._inner(ctx))
        p = Prez().header(ctx.ident, ctx.name)
        p.items("Fiche", self._facts(ctx)).block("Description", ctx.d("synopsis") or (ctx.ident.overview if ctx.ident else ""))
        if ctx.ident and ctx.ident.url:
            p.items("Liens", [("Fiche ThePornDB" if ctx.ident.provider == "tpdb" else "Fiche",
                               f"[url={ctx.ident.url}]{ctx.ident.url}[/url]")])
        if mode == "images":
            p.items("Informations", [("Release", ctx.name), ("Images", ctx.analysis.images),
                                     ("Formats", ctx.parts.get("formats", "")), ("Taille", fmt_size(ctx.src.total_size))])
            return p.files(ctx.src).render()
        tech = self._video.description(self._inner(ctx))
        tech = tech[tech.find("\n[b]INFORMATIONS TECHNIQUES"):] if "[b]INFORMATIONS TECHNIQUES" in tech else tech
        return p.render().rstrip("\n") + "\n" + tech

    # ── Options C411 ──────────────────────────────────────────────────────
    def auto_options(self, types, ctx):
        out = {}
        if ctx.analysis.kind != "video":
            return out
        p = ctx.parts or {}
        lang = p.get("language", "").upper()
        if lang in OPTION_LANG:
            pick(types, out, "Langue", OPTION_LANG[lang])
        elif re.search(r"VF|MULTI|VOSTFR|VFSTFR|VFQ", lang):
            pick(types, out, "Langue", lang_from_tag(lang))
        src, res = p.get("source", ""), p.get("resolution", "")
        res = {"4K": "2160p"}.get(res.upper(), res) if res else ""
        pick(types, out, "Qualité", QUALITY.get((src, res)) or QUALITY.get((src, "")) or "")
        return out
