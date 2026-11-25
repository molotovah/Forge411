"""Films & Vidéos : films, séries, animation, documentaires, émissions, concerts, sport."""

import re

from .. import videoinfo as vi
from ..model import Check, Detail, Part, fmt_duration, fmt_size, lang_name, slug
from ..render import Nfo, Prez
from ..scanner import (VALID_AUDIO_CODECS, VALID_HDR_FLAGS, VALID_LANGUAGES,
                       VALID_RESOLUTIONS, VALID_SOURCES, VALID_VIDEO_CODECS,
                       validate_filename)
from .base import Profile, banned_team_error, lang_from_tag, pick

# Sources admises par C411 (wiki Films & Vidéos). Un WEB-DL s'écrit WEB ; TVRip s'écrit SDTV.
SOURCES = ["WEB", "WEBRip", "BluRay", "UHD.BluRay", "BluRay.REMUX", "UHD.BluRay.REMUX", "BluRay.BDMV",
           "UHD.BluRay.BDMV", "BluRay.ISO", "UHD.BluRay.ISO", "HDTV", "PDTV", "SDTV", "DVD", "VIDEO_TS",
           "DVDRip"]
_SOURCE_ALIASES = {"web-dl": "WEB", "webdl": "WEB", "web": "WEB",
                   "webrip": "WEBRip", "bluray": "BluRay", "blu-ray": "BluRay",
                   "bdrip": "BluRay", "remux": "BluRay.REMUX", "bdremux": "BluRay.REMUX",
                   "uhd": "UHD.BluRay", "hdtv": "HDTV", "pdtv": "PDTV", "sdtv": "SDTV", "tvrip": "SDTV",
                   "dvdrip": "DVDRip", "dvd": "DVD", "video_ts": "VIDEO_TS"}
PURE = ("REMUX", "BDMV", "ISO")

# Débit vidéo (kb/s) : (plancher, seuil) : sous le plancher refusé, entre les deux HDLight / 4KLight obligatoire
BITRATE_RULES = {("1080p", "x264"): (2500, 8000), ("1080p", "x265"): (1200, 6000), ("1080p", "AV1"): (800, 4000),
                 ("2160p", "x265"): (2800, 12000), ("2160p", "AV1"): (2200, 8000)}
GPU_ENCODERS = ("nvenc", "qsv", "amf", "vce", "quicksync")
PLATFORMS = {"NF": "Netflix", "AMZN": "Amazon Prime Video", "DSNP": "Disney+",
             "ATVP": "Apple TV+", "HMAX": "Max", "MAX": "Max", "PMTP": "Paramount+",
             "IP": "BBC iPlayer", "HULU": "Hulu", "CRAV": "Crave", "CR": "Crunchyroll",
             "ADN": "ADN", "CANALPLUS": "Canal+", "CPLUS": "Canal+", "MYCANAL": "Canal+",
             "FTV": "France.tv", "ARTE": "Arte", "TF1": "TF1+", "M6": "M6+",
             "SKST": "SkyShowtime", "STAN": "Stan", "PCOK": "Peacock"}
SPECIAL = ("PROPER", "REPACK", "REPACK2", "RERIP", "FIX", "EXTENDED", "UNCUT",
           "UNRATED", "DC", "IMAX", "REMASTERED", "INTEGRALE", "COLLECTION", "DOC")
KIND_LABEL = {"movie": "Film", "episode": "Épisode", "season": "Saison complète",
              "pack": "Pack multi-saisons"}

# Genres TMDB (fr-FR) → libellés d'options C411
GENRE_MAP = {
    "action & adventure": ["Action", "Aventure"],
    "science-fiction & fantastique": ["Science Fiction", "Fantastique"],
    "science-fiction": ["Science Fiction"],
    "war & politics": ["Guerre", "Politique & Géopolitique"],
    "guerre & politique": ["Guerre", "Politique & Géopolitique"],
    "familial": ["Famille"], "kids": ["Famille"], "enfants": ["Famille"],
    "histoire": ["Historique"], "horreur": ["Épouvante & Horreur"], "musique": ["Musical"],
    "mystère": ["Enquête"], "reality": ["Télé-réalité"], "téléfilm": ["Fiction"],
    "talk": ["Variétés TV"],
}

_KNOWN = (VALID_LANGUAGES | VALID_RESOLUTIONS | VALID_SOURCES | VALID_VIDEO_CODECS
          | VALID_AUDIO_CODECS | VALID_HDR_FLAGS | {"hevc", "avc", "dl", "web"})


def detect_source(raw: str) -> str:
    tokens = [t.lower() for t in re.split(r"[.\s_]+", raw)]
    joined = "." + ".".join(tokens) + "."
    uhd = ".uhd." in joined
    for pure in ("remux", "bdmv", "iso"):
        if f".{pure}." in joined:
            return f"{'UHD.' if uhd else ''}BluRay.{pure.upper()}"
    if uhd and ".bluray." in joined:
        return "UHD.BluRay"
    for t in tokens:
        if t in _SOURCE_ALIASES:
            return _SOURCE_ALIASES[t]
    return ""


def detect_platform(raw: str) -> str:
    for t in re.split(r"[.\s_-]+", raw):
        if t.upper() in PLATFORMS:
            return PLATFORMS[t.upper()]
    return ""


def detect_team(raw: str, parsed_team) -> str:
    """Tag de team : après le dernier tiret, sinon dernier mot non technique."""
    if parsed_team and parsed_team.lower() not in ("dl",):
        return re.sub(r"[^A-Za-z0-9]", "", parsed_team)
    last = re.split(r"[.\s_]+", raw.strip())[-1] if raw.strip() else ""
    if (last and last.isalnum() and last.lower() not in _KNOWN
            and not re.fullmatch(r"(19|20)\d{2}|S\d+E?\d*|\d+(\.\d)?", last, re.I)):
        return last
    return ""


def video_kbps(mf) -> int:
    """Débit vidéo en kb/s (piste vidéo, sinon débit global du fichier)."""
    if not mf or not mf.video:
        return 0
    if mf.video.bitrate:
        return mf.video.bitrate // 1000
    if mf.duration_ms:
        return int(mf.size * 8 / (mf.duration_ms / 1000) / 1000)
    return 0


def light_tag(mf, resolution: str, codec: str) -> str:
    """HDLight / 4KLight obligatoire entre le plancher et le seuil de débit (encodes)."""
    rule = BITRATE_RULES.get((resolution, codec))
    kbps = video_kbps(mf)
    if not rule or not kbps:
        return ""
    floor, threshold = rule
    if floor <= kbps < threshold:
        return "HDLight" if resolution == "1080p" else "4KLight"
    return ""


def _video_desc(mf) -> str:
    v = mf.video
    if not v:
        return "Inconnue"
    parts = [v.format + (f" ({v.library.split()[0]})" if v.library else ""), f"{v.width}x{v.height}"]
    if v.fps:
        try:
            parts.append(f"{float(v.fps):g} fps")
        except ValueError:
            parts.append(v.fps)
    if v.bitrate:
        parts.append(f"{v.bitrate // 1000} kb/s")
    elif mf.duration_ms:
        parts.append(f"~{int(mf.size * 8 / (mf.duration_ms / 1000) / 1000)} kb/s (global)")
    if v.bit_depth:
        parts.append(f"{v.bit_depth} bits")
    hdr = vi.hdr_tag(mf)
    parts.append(hdr.replace(".", " + ") if hdr else "SDR")
    return " • ".join(parts)


def _audio_desc(a) -> str:
    ch = vi._CHANNELS.get(a.channels, str(a.channels))
    s = f"{lang_name(a.language)} • {vi._audio_codec(a).replace('.', ' ')} {ch}"
    if a.bitrate:
        s += f" • {a.bitrate // 1000} kb/s"
    return s + (f" ({a.title})" if a.title else "")


def _sub_desc(s) -> str:
    return f"{lang_name(s.language)} • {s.format} • {'forcés' if s.forced else 'complets'}" + \
        (f" ({s.title})" if s.title else "")


class VideoProfile(Profile):
    key = "video"
    label = "Films & Vidéos"
    icon = "🎬"
    category_id = 1
    subcategories = {6: "Film", 7: "Série TV", 1: "Animation", 2: "Animation Série", 4: "Documentaire",
                     57: "Série Documentaire", 5: "Emission TV", 3: "Concert", 8: "Spectacle",
                     9: "Sport", 10: "Vidéo-clips", 54: "Collection"}
    provider = "tmdb"
    template = "Titre.Année.[SxxEyy].Langue.Résolution.Source.[HDLight].[HDR].Audio.Vidéo-TEAM"
    hint = ("Titre en français (fiche TMDB). Langue, résolution, codecs et HDR sont lus dans les pistes ; "
            "vérifie la source et la plateforme.")

    def score(self, src):
        n = len(src.by_ext(*vi.VIDEO_EXT))
        return 0.0 if not n else 0.6 + 0.4 * n / max(len(src.files), 1)

    def analyze(self, src, progress=None):
        return vi.analyze(src, progress)

    def summary(self, ctx):
        va = ctx.analysis
        rows = [("Type", KIND_LABEL.get(va.kind, va.kind))]
        if va.duration_ms:
            rows.append(("Durée", fmt_duration(va.duration_ms)))
        if va.seasons:
            rows.append(("Saison", ", ".join(str(s) for s in va.seasons)))
        mf = va.main
        if mf:
            rows.append(("Vidéo", _video_desc(mf)))
            rows += [("Audio", _audio_desc(a)) for a in mf.audios] or [("Audio", "Aucune piste")]
            rows += [("Sous-titres", _sub_desc(s)) for s in mf.subs] or [("Sous-titres", "Aucun")]
        return rows

    def issues(self, ctx):
        va = ctx.analysis
        return Check(errors=list(va.errors), warnings=list(va.warnings))

    def guess_sub(self, ctx):
        va, ident = ctx.analysis, ctx.ident
        genres = set(g.get("id") for g in (ident.raw.get("genres", []) if ident else []))
        tv = (ident.kind == "tv") if ident and ident.kind else va.is_tv
        if tv:
            if 16 in genres:
                return 2
            if 99 in genres:
                return 57
            if genres & {10764, 10767, 10763}:
                return 5
            return 7
        if 16 in genres:
            return 1
        if 99 in genres:
            return 4
        return 6

    # ── Identification ────────────────────────────────────────────────────
    def query(self, ctx):
        p = ctx.analysis.parsed
        return {"query": (p.title if p else ctx.src.stem).replace(".", " "), "year": (p.year if p else "") or "",
                "kind": "tv" if ctx.analysis.is_tv else "movie"}

    def search(self, client, q):
        return client.search(q.get("query", ""), q.get("year", ""), q.get("kind", ""))

    # ── Nom ───────────────────────────────────────────────────────────────
    def _season_episode(self, va):
        if va.kind == "episode" and va.seasons and va.episode is not None:
            return f"S{va.seasons[0]:02d}E{va.episode:02d}"
        if va.kind == "season" and va.seasons:
            return f"S{va.seasons[0]:02d}"
        if va.kind == "pack" and len(va.seasons) > 1:
            return f"S{va.seasons[0]:02d}S{va.seasons[-1]:02d}"
        return ""

    def parts(self, ctx):
        va, ident, src = ctx.analysis, ctx.ident, ctx.src
        p, mf, raw = va.parsed, va.main, src.stem
        title = slug(ident.title) if ident and ident.title else (p.title if p else "")
        year = ""
        if not va.is_tv:
            year = (ident.year if ident else "") or (p.year if p else "") or ""
        elif p and p.year:
            year = (ident.year if ident else "") or p.year
        upper = [t.upper() for t in re.split(r"[.\s_]+", raw)]
        source = detect_source(raw)
        resolution, codec = vi.resolution_tag(mf), vi.video_codec_tag(mf, source)
        light = light_tag(mf, resolution, codec) or next((t for t in ("HDLight", "4KLight", "mHD")
                                                          if t.upper() in upper), "")
        return [
            Part("title", "Titre (français)", title, width=30, hint="Titre français de la fiche TMDB, mots séparés par des points."),
            Part("year", "Année", year, width=6, hint="Obligatoire pour un film ; facultative pour une série."),
            Part("se", "Saison / épisode", self._season_episode(va), width=8, hint="S01E02, S01 (saison complète) ou S01S03."),
            Part("special", "Édition", ".".join(s for s in SPECIAL if s in upper), width=10,
                 hint="PROPER, REPACK, EXTENDED, IMAX… Laisse vide sinon."),
            Part("language", "Langue", vi.language_tag(mf, p), width=12,
                 hint="VFF, VFQ, MULTI.VFF, MULTI.VF2, VOSTFR… Déduite des pistes audio et sous-titres."),
            Part("resolution", "Résolution", vi.resolution_tag(mf), width=8, hint="Déduite de la taille de l'image."),
            Part("source", "Source", source, choices=SOURCES, width=12,
                 hint="WEB : fichier de plateforme non retouché (WEB-DL s'écrit WEB). WEBRip : capture ou ré-encodage. "
                      "REMUX, BDMV, ISO : source Blu-ray pure."),
            Part("light", "Version allégée", light, choices=["", "HDLight", "4KLight"], width=8,
                 hint="Obligatoire pour un encode sous le seuil de débit : 1080p x264 < 8 000 kb/s, "
                      "x265 < 6 000, AV1 < 4 000 ; 2160p x265 < 12 000, AV1 < 8 000. Calculé d'après le débit vidéo."),
            Part("hdr", "HDR", vi.hdr_tag(mf), width=10, hint="HDR10, HDR10PLUS, DV, DV.HDR10. Vide pour du SDR."),
            Part("audio", "Audio", vi.audio_tag(mf), width=12, hint="Piste française la plus riche : EAC3.5.1, AAC.2.0…"),
            Part("video", "Codec vidéo", codec, width=8,
                 hint="x264/x265 = encodage ; H264/H265 = WEB non retouché ; AVC/HEVC = source pure."),
            Part("team", "Team", detect_team(raw, p.team if p else None), width=12,
                 hint="Tag de l'équipe d'origine. NOTAG si introuvable."),
        ]

    def build(self, parts):
        p = {k: (v or "").strip(". ") for k, v in parts.items()}
        special = [x for x in p.get("special", "").split(".") if x]
        # Collection : Nom.COLLECTION.Années… ; autres éditions après l'année / la saison
        head = [p.get("title", "")] + (["COLLECTION"] if "COLLECTION" in special else [])
        special = [x for x in special if x != "COLLECTION"]
        keys = ["year", "se"]
        body = head + [p.get(k, "") for k in keys] + special + \
            [p.get(k, "") for k in ("language", "resolution", "source", "light", "hdr", "audio", "video")]
        return ".".join(x for x in body if x) + f"-{p.get('team') or 'NOTAG'}"

    def details(self, ctx):
        raw = ctx.src.stem
        return [Detail("platform", "Plateforme VOD", detect_platform(raw),
                       choices=[""] + sorted(set(PLATFORMS.values())),
                       hint="Obligatoire pour une source WEB encodée en x264/x265, recommandée sinon : "
                            "C411 vérifie la plateforme d'origine.")]

    def validate(self, name, ctx):
        va = ctx.analysis
        c = Check()
        name = name.strip()
        if not name:
            c.errors.append("Le nom est vide.")
            return c
        r = validate_filename(name + ".mkv")
        for e in r.errors:
            if "Codec vidéo non détecté" in e and re.search(r"\.(H264|H265|AV1|XviD|MPEG2)\b", name, re.I):
                continue
            c.errors.append(e)
        for w in r.warnings:
            if "Tirets détectés" in w and name.count("-") == name.count("WEB-DL") + 1:
                continue
            if "Année non détectée" in w and va.is_tv:
                continue
            c.warnings.append(w)
        if re.search(r"[^A-Za-z0-9.\-+]", name):
            c.errors.append("Caractères interdits : uniquement lettres, chiffres, points et le tiret de la team.")
        err = banned_team_error(name)
        if err:
            c.errors.append(err)
        up = f".{name.upper()}."
        if ".WEB-DL." in up or ".WEBDL." in up:
            c.errors.append("C411 refuse WEB-DL : écris simplement WEB comme source.")
        if ".TVRIP." in up:
            c.errors.append("TVRip n'est pas accepté : écris SDTV.")
        encoded = re.search(r"[.]X26[45][.-]", up) is not None
        pure = any(f".{t}." in up for t in PURE)
        if pure and encoded:
            c.errors.append("x264/x265 interdit sur une version pure (REMUX, BDMV, ISO) : écris AVC ou HEVC.")
        if pure and re.search(r"[.]H26[45][.-]", up):
            c.errors.append("Version pure (REMUX, BDMV, ISO) : le codec s'écrit AVC ou HEVC, pas H264/H265.")
        if ".WEB." in up and encoded and not ctx.d("platform"):
            c.errors.append("Source WEB avec x264/x265 : la plateforme VOD est obligatoire (sinon requalifié WEBRip). "
                            "Si tu as ré-encodé toi-même, la source est WEBRip.")
        mf = va.main
        if mf is not None and vi.MEDIAINFO_OK and mf.video:
            lib = mf.video.library.lower()
            if any(g in lib for g in GPU_ENCODERS):
                c.errors.append("Encodage GPU (NVENC, QSV, AMF) interdit sur C411.")
            res = vi.resolution_tag(mf)
            codec = "x264" if ".X264" in up else "x265" if ".X265" in up else "AV1" if ".AV1" in up else ""
            kbps = video_kbps(mf)
            rule = BITRATE_RULES.get((res, codec))
            if rule and kbps:
                floor, threshold = rule
                tag = "HDLight" if res == "1080p" else "4KLight"
                if kbps < floor:
                    c.errors.append(f"Débit vidéo {kbps} kb/s sous le minimum C411 ({floor} kb/s en {res} {codec}).")
                elif kbps < threshold and f".{tag.upper()}." not in up:
                    c.errors.append(f"Débit vidéo {kbps} kb/s (< {threshold}) : le marqueur {tag} est obligatoire "
                                    "après la source.")
                elif kbps >= threshold and f".{tag.upper()}." in up:
                    c.warnings.append(f"Débit vidéo {kbps} kb/s (≥ {threshold}) : le marqueur {tag} ne doit pas être utilisé.")
            if ctx.d("platform") == "Netflix" and ".WEB." in up and res == "1080p" and kbps and not 5000 <= kbps <= 7500:
                c.warnings.append(f"WEB Netflix 1080p : débit attendu entre 5 000 et 7 500 kb/s ({kbps} kb/s).")
            if mf.audios and max(a.channels for a in mf.audios) < 2:
                c.warnings.append("Son stéréo obligatoire (sauf vieux films en mono).")
            if res and any(vi._audio_codec(a) == "MP3" for a in mf.audios):
                c.errors.append("Audio MP3 réservé aux vidéos SD.")
            expected = vi.resolution_tag(mf)
            if expected and f".{expected}." not in f".{name}.":
                c.warnings.append(f"La vidéo fait {mf.video.width}×{mf.video.height} : le tag attendu est {expected}.")
            if not vi.language_tag(mf, va.parsed):
                c.errors.append("Aucune piste audio française ni sous-titres français complets : C411 refuse la vidéo.")
        if va.kind == "season" and va.seasons and ctx.ident and ctx.ident.provider == "tmdb":
            for s in ctx.ident.raw.get("seasons", []):
                if s.get("season_number") == va.seasons[0] and (s.get("episode_count") or 0) > len(va.videos):
                    c.warnings.append(f"Saison {va.seasons[0]} incomplète : {len(va.videos)} vidéo(s) pour "
                                      f"{s['episode_count']} épisodes sur TMDB. C411 refuse les saisons incomplètes.")
        if ctx.parts.get("source", "").upper() == "WEB" and not ctx.d("platform") and not encoded:
            c.warnings.append("Indique la plateforme VOD : recommandée pour une source WEB.")
        teams = {self._file_team(v.path.stem) for v in va.videos} - {""}
        if len(teams) > 1:
            c.errors.append("Plusieurs teams dans le pack (" + ", ".join(sorted(teams)) + ") : multi-tag interdit.")
        team = name.rsplit("-", 1)[-1] if "-" in name else ""
        for v in va.videos:
            ft = self._file_team(v.path.stem)
            if ft and team and ft.upper() != team.upper():
                c.errors.append(f"DETAG de cohérence : le fichier « {v.path.name} » porte le tag {ft}, "
                                f"le titre porte {team}. Garde le tag d'origine.")
                break
        if not ctx.parts.get("source"):
            c.warnings.append("Source inconnue : choisis-la (WEB, WEBRip, BluRay…).")
        return c

    @staticmethod
    def _file_team(stem: str) -> str:
        m = re.search(r"-([A-Za-z0-9]+)$", stem)
        if not m or m.group(1).upper() in ("DL", "LC", "HE", "MA"):
            return ""
        return m.group(1)

    def tag_fixes(self, ctx):
        team = ctx.name.rsplit("-", 1)[-1] if "-" in ctx.name else ""
        if not team:
            return []
        fixes = []
        for f in ctx.src.files:
            if f.suffix.lower() not in vi.VIDEO_EXT:
                continue
            if not self._file_team(f.stem):
                fixes.append((f, f"{f.stem}-{team}{f.suffix}"))
        return fixes

    def on_renamed(self, ctx, old_name, new_name):
        for v in ctx.analysis.videos:
            if v.path.name == old_name:
                v.text = v.text.replace(old_name, new_name)
                v.path = v.path.with_name(new_name)

    # ── NFO / présentation ────────────────────────────────────────────────
    def _source_line(self, ctx):
        s = ctx.parts.get("source") or "Non précisée"
        return s + (f" ({ctx.d('platform')})" if ctx.d("platform") else "")

    def nfo(self, ctx):
        va, mf = ctx.analysis, ctx.analysis.main
        n = Nfo(ctx.name).ident(ctx.ident)
        n.field("Source", self._source_line(ctx)).field("Conteneur", mf.container if mf else "")
        n.field("Durée totale", fmt_duration(va.duration_ms) if va.duration_ms else "")
        n.field("Taille totale", fmt_size(ctx.src.total_size)).field("Fichiers", len(ctx.src.files)).blank()
        if mf:
            n.field("Vidéo", _video_desc(mf))
            for i, a in enumerate(mf.audios, 1):
                n.field(f"Audio #{i}", _audio_desc(a))
            for i, s in enumerate(mf.subs, 1):
                n.field(f"Sous-titres #{i}", _sub_desc(s))
            if not mf.subs:
                n.field("Sous-titres", "Aucun")
        n.files(ctx.src)
        if mf and mf.text:
            n.section(f"MediaInfo : {mf.path.name}").text(mf.text, indent=0)
        return n.render()

    def description(self, ctx):
        va, mf = ctx.analysis, ctx.analysis.main
        p = Prez().header(ctx.ident, ctx.name)
        if ctx.ident:
            p.block("Synopsis", ctx.ident.overview).fiche(ctx.ident)
        rows = [("Release", ctx.name), ("Source", self._source_line(ctx))]
        if mf:
            rows += [("Conteneur", mf.container), ("Vidéo", _video_desc(mf))]
            rows += [("Audio", _audio_desc(a)) for a in mf.audios]
            rows.append(("Sous-titres", ", ".join(_sub_desc(s) for s in mf.subs) or "Aucun"))
        rows += [("Durée", fmt_duration(va.duration_ms) if va.duration_ms else ""),
                 ("Taille", fmt_size(ctx.src.total_size)), ("Fichiers", len(ctx.src.files))]
        return p.items("Informations techniques", rows).files(ctx.src).render()

    # ── Options ───────────────────────────────────────────────────────────
    def auto_options(self, types, ctx):
        va, out = ctx.analysis, {}
        pick(types, out, "Langue", lang_from_tag(ctx.parts.get("language", "")))
        if ctx.ident:
            labels = []
            for g in ctx.ident.genres:
                labels += GENRE_MAP.get(g.lower(), [g])
            pick(types, out, "Genre", *labels)
        pick(types, out, "Type", "2D")
        if va.kind == "episode" and va.episode is not None:
            pick(types, out, "Episode", f"Épisode {va.episode:02d}")
        elif va.kind in ("season", "pack"):
            pick(types, out, "Episode", "Saison complète")
        if va.kind in ("episode", "season") and va.seasons:
            pick(types, out, "Saison", f"Saison {va.seasons[0]:02d}")
        return out
