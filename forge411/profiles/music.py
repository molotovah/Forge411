"""Audio : musique, karaoké, podcasts et radio, samples (règles du wiki C411, catégorie Audio)."""

import re

from .. import audioinfo as ai
from ..model import Check, Detail, Part, fmt_clock, fmt_duration, fmt_size, slug
from ..render import Nfo, Prez
from .base import ARCHIVE_EXT, Profile, banned_team_error, pick, pick_fuzzy, team_of

SOURCES = ["WEB", "CD", "Vinyle", "SACD", "BluRay Audio", "DVD-Audio"]
MB_TYPE = {"album": "Album", "ep": "EP", "single": "Album", "broadcast": "Radio",
           "compilation": "Intégrale/Coffret", "soundtrack": "Bande originale de film/jeu",
           "live": "Live/Concert", "dj-mix": "Mix/Medley", "mixtape/street": "Mix/Medley"}
# Débits minimums (kb/s) ; MP3 : 320 en CBR, sinon VBR avec une moyenne d'au moins 128
MIN_KBPS = {"AAC": 256, "OPUS": 128, "OGG": 192, "WMA": 256}
PARASITES = (".url", ".lnk", ".exe", ".bat", ".scr", ".com")
COVER_NAMES = ("cover", "front", "folder")


def _khz(rate: int) -> str:
    return f"{rate / 1000:g}kHz"


def codec_tag(a: ai.AudioAnalysis) -> str:
    """Partie codec du nom : FLAC[16bit.44.1kHz], MP3[320kbps], MP3[VBR.245kbps], AAC[256kbps]."""
    c = a.codec
    if not c:
        return ""
    if a.lossless:
        inner = ".".join(x for x in (f"{a.bits}bit" if a.bits else "", _khz(a.sample_rate) if a.sample_rate else "") if x)
        return f"{c}[{inner}]" if inner else c
    if a.vbr:
        return f"{c}[VBR.{a.bitrate}kbps]" if a.bitrate else f"{c}[VBR]"
    return f"{c}[{a.bitrate}kbps]" if a.bitrate else c


def format_label(a: ai.AudioAnalysis) -> str:
    """Valeur de l'option « Format Musique »."""
    c = a.codec
    return {"FLAC": f"FLAC ({24 if a.bits > 16 else 16} bit)", "ALAC": "ALAC (M4A)", "AAC": "AAC (M4A)",
            "MP3": "MP3", "OGG": "OGG", "OPUS": "OGG", "AIFF": "AIF", "APE": "Monkey's Audio",
            "DSD": "DSD", "MPC": "MPC", "WV": "WavPack", "WAV": "WAV"}.get(c, c)


class MusicProfile(Profile):
    key = "music"
    label = "Audio"
    icon = "🎵"
    category_id = 3
    subcategories = {18: "Musique", 19: "Podcast Radio", 20: "Samples", 17: "Karaoké"}
    provider = "musicbrainz"
    template = "Artiste.Album.Année.Codec[Bitrate.Fréquence]-TAG · podcast : Nom.Date.[Codec débit]-Team"
    hint = "Artiste et album viennent de MusicBrainz ou des tags ; codec, profondeur, fréquence et débit sont lus dans les fichiers."

    def score(self, src):
        n = len(src.by_ext(*ai.AUDIO_EXT))
        if not n or src.by_ext(".m4b"):
            return 0.0
        return 0.5 + 0.4 * n / max(len(src.files), 1)

    def analyze(self, src, progress=None):
        return ai.analyze(src, progress)

    def summary(self, ctx):
        a = ctx.analysis
        rows = [("Pistes", str(len(a.tracks))), ("Durée", fmt_duration(int(a.duration * 1000)))]
        if a.artist or a.album:
            rows.append(("Tags", " - ".join(x for x in (a.artist, a.album) if x) + (f" ({a.year})" if a.year else "")))
        rows.append(("Qualité", self._quality(a)))
        cover = f"{a.cover} ({a.cover_size[0]}×{a.cover_size[1]})" if a.cover and a.cover_size[0] else a.cover
        extras = [x for x, ok in (("cue", a.has_cue), ("log", a.has_log), (cover, bool(a.cover))) if ok]
        rows.append(("Fichiers annexes", ", ".join(extras) or "aucun"))
        return rows

    def guess_sub(self, ctx):
        stem = ctx.src.stem.lower()
        if "karaok" in stem:
            return 17
        if "podcast" in stem or "radio" in stem or "emission" in stem:
            return 19
        if re.search(r"sample|loops?\b|drum.?kit|\bkit\b|one.?shots?", stem):
            return 20
        return 18

    def issues(self, ctx):
        a, sub, src = ctx.analysis, ctx.sub_id, ctx.src
        c = Check(errors=list(a.errors), warnings=list(a.warnings))
        if not a.tracks:
            return c
        if len(a.codecs) > 1 and sub != 20:
            c.errors.append("Formats audio mélangés (" + ", ".join(sorted(a.codecs)) + ") : un seul format par release.")
        if src.by_ext(*ARCHIVE_EXT) and sub != 20:
            c.errors.append("Archives (RAR, ZIP, 7z) interdites, sauf pack de samples vendu ainsi.")
        parasites = [f.name for f in src.files if f.suffix.lower() in PARASITES]
        if parasites:
            c.errors.append("Fichiers parasites interdits : " + ", ".join(parasites[:3]))
        # Débits
        if sub == 19:
            if a.bitrate and a.bitrate < 125:
                c.errors.append(f"Podcast à {a.bitrate} kb/s : minimum 128 kb/s.")
        elif a.codec == "MP3" and a.bitrate:
            if not a.vbr and a.bitrate < 315:
                c.errors.append(f"MP3 CBR à {a.bitrate} kb/s : sous 320 kb/s, seul le VBR est accepté.")
            elif a.vbr and a.bitrate < 128:
                c.errors.append(f"MP3 VBR à {a.bitrate} kb/s de moyenne : minimum 128 kb/s.")
        elif a.codec in MIN_KBPS and a.bitrate and a.bitrate < MIN_KBPS[a.codec] - 5:
            c.errors.append(f"{a.codec} à {a.bitrate} kb/s : minimum {MIN_KBPS[a.codec]} kb/s sur C411.")
        if sub in (17, 18):
            if len(a.tracks) <= 6 and a.duration < 20 * 60 and all(t.duration < 600 for t in a.tracks):
                c.warnings.append("Single ou maxi-single de moins de 20 minutes : refusé par C411 (les EP sont acceptés).")
            if len(a.tracks) == 1 and a.duration > 20 * 60 and not a.has_cue:
                c.warnings.append("Album en une seule piste : le fichier .cue est obligatoire.")
            if not a.cover:
                c.errors.append("Pochette avant obligatoire à la racine (cover.jpg, front.jpg ou folder.jpg).")
            elif a.cover_size[0] and min(a.cover_size) < 500:
                c.errors.append(f"Pochette trop petite ({a.cover_size[0]}×{a.cover_size[1]}) : 500×500 minimum.")
            missing = a.missing_tags
            if missing:
                c.warnings.append("Tags manquants sur certaines pistes : " + ", ".join(missing) + ".")
            if not a.all_covers_embedded:
                c.warnings.append("Pochette non embarquée dans toutes les pistes (tag obligatoire).")
            badly_named = [t.rel for t in a.tracks if not re.match(r"^(\d-)?\d{2,3} ?[-.] ?\S", t.rel.rsplit("/", 1)[-1])]
            if badly_named:
                c.warnings.append(f"Pistes mal nommées ({len(badly_named)}) : forme attendue « 01 - Titre.flac ».")
        return c

    # ── Identification ────────────────────────────────────────────────────
    def query(self, ctx):
        a = ctx.analysis
        album, artist = a.album, a.artist
        if not album:
            stem = re.sub(r"[._]+", " ", ctx.src.stem)
            stem = re.sub(r"\[.*?\]|\(.*?\)|\b(FLAC|MP3|WEB|CD|\d{2,4}kbps|24bit|16bit)\b|-\w+$", "", stem, flags=re.I)
            if " - " in stem:
                artist, album = [x.strip() for x in stem.split(" - ", 1)]
            else:
                album = stem.strip()
        return {"query": album, "year": a.year, "artist": artist}

    def search(self, client, q):
        return client.search(q.get("query", ""), q.get("year", ""), q.get("artist", ""))

    # ── Nom ───────────────────────────────────────────────────────────────
    def parts(self, ctx):
        a, ident, sub = ctx.analysis, ctx.ident, ctx.sub_id
        artist = (ident.raw.get("artist") if ident and ident.provider == "musicbrainz" else "") or a.artist
        title = (ident.title if ident and ident.title else "") or a.album or ctx.src.stem
        year = (ident.year if ident and ident.year else "") or a.year
        team = team_of(ctx.src.stem.replace(" ", ".")) or "NOTAG"
        if sub == 19:
            fmt = f"[{a.codec} {a.bitrate} kb/s]" if a.bitrate else f"[{a.codec}]"
            return [Part("title", "Émission", slug(title), width=30),
                    Part("integrale", "Intégrale", "", choices=["", "INTEGRALE"], width=10),
                    Part("date", "Date / période", year, width=12, hint="Ex. 2024, 2018-2019 ou 2024.05.12."),
                    Part("format", "Codec et débit", fmt, width=16, hint="Ex. [MP3 192 kb/s]."),
                    Part("team", "Team", team, width=12)]
        if sub == 20:
            return [Part("title", "Nom", slug(title), width=30), Part("year", "Année", year, width=6),
                    Part("codec", "Codec", a.codec, width=8),
                    Part("format", "Débit", f"{a.bitrate}kbps" if a.bitrate and not a.lossless else
                         (f"{a.bits}bit" if a.bits else ""), width=10)]
        return [Part("artist", "Artiste", slug(artist), width=24, hint="Artiste principal ; « VA » pour une compilation."),
                Part("title", "Album", slug(title), width=30),
                Part("year", "Année", year, width=6, hint="Année de l'édition postée."),
                Part("codec", "Codec et qualité", codec_tag(a), width=22,
                     hint="FLAC[16bit.44.1kHz], FLAC[24bit.96kHz], MP3[320kbps]… Lu dans les fichiers."),
                Part("team", "Team", team, width=12, hint="Tag d'origine, sinon NOTAG.")]

    def build(self, parts):
        p = {k: (v or "").strip(". ") for k, v in parts.items()}
        if "artist" in p:
            body = ".".join(x for x in (p.get("artist"), p.get("title"), p.get("year"), p.get("codec")) if x)
        elif "date" in p:
            body = ".".join(x for x in (p.get("title"), p.get("integrale"), p.get("date"), p.get("format")) if x)
        else:
            return ".".join(x for x in (p.get("title"), p.get("year"), p.get("codec"), p.get("format")) if x)
        return f"{body}-{p.get('team') or 'NOTAG'}"

    def validate(self, name, ctx):
        c = Check()
        if not name.strip():
            c.errors.append("Le nom est vide.")
            return c
        outside = re.sub(r"\[[^\]]*\]", "", name)          # le contenu des crochets est libre
        if re.search(r"[^A-Za-z0-9.\-+]", outside):
            c.errors.append("Caractères interdits : lettres sans accents, chiffres, points et le tiret de la team.")
        err = banned_team_error(name)
        if err:
            c.errors.append(err)
        a = ctx.analysis
        if ctx.d("source") == "CD":
            if not a.has_cue or not a.has_log:
                c.errors.append("CD-Rip : le .cue et le .log du ripper (EAC, XLD, whipper) sont obligatoires.")
            c.infos.append("CD-Rip : indique le code-barres (UPC/EAN) ou le numéro de catalogue, et le lien "
                           "MusicBrainz ou Discogs du pressage exact.")
        if ctx.d("source") == "Vinyle" and not ctx.d("hardware"):
            c.warnings.append("Rip vinyle : décris le matériel utilisé (platine, cellule, préampli, logiciel).")
        if ctx.d("source") == "WEB" and not ctx.d("link"):
            c.warnings.append("Release WEB : le lien de la page du store (Qobuz, Bandcamp…) est obligatoire.")
        issues = self.issues(ctx)
        c.errors += issues.errors
        c.warnings += issues.warnings
        return c

    def details(self, ctx):
        a = ctx.analysis
        facts = dict(ctx.ident.facts) if ctx.ident else {}
        link = ctx.ident.url if ctx.ident and ctx.ident.provider == "musicbrainz" else ""
        return [Detail("source", "Source", "CD" if a.has_cue or a.has_log else "WEB", choices=SOURCES,
                       hint="Support d'origine. Pour un WEB, précise la plateforme dans le lien de référence."),
                Detail("platform", "Plateforme (si WEB)", "", hint="Qobuz, Bandcamp, Tidal, Apple Music, Deezer…"),
                Detail("link", "Lien de référence", link,
                       hint="WEB : page du store. CD ou vinyle : MusicBrainz ou Discogs, édition exacte (jamais le "
                            "« master » Discogs)."),
                Detail("label", "Label / référence catalogue", facts.get("Label", ""),
                       hint="Code-barres (UPC/EAN) et/ou numéro de catalogue, seulement s'ils existent."),
                Detail("hardware", "Matériel (rip vinyle)", "", multiline=True,
                       hint="Platine, cellule, préampli, carte son, logiciel et traitements.")]

    # ── NFO / présentation ────────────────────────────────────────────────
    def _quality(self, a):
        q = f"{a.codec} • {'lossless' if a.lossless else 'lossy'}"
        if a.lossless:
            q += f" • {a.bits or '?'} bits"
        if a.bitrate:
            q += f" • {'VBR ~' if a.vbr else 'CBR '}{a.bitrate} kb/s" if not a.lossless else f" • {a.bitrate} kb/s"
        if a.sample_rate:
            q += f" • {a.sample_rate / 1000:g} kHz"
        if a.channels:
            q += f" • {a.channels} canaux"
        return q

    def _tracklist(self, a):
        rows = []
        multi_disc = len({x.disc for x in a.tracks}) > 1
        for i, t in enumerate(a.tracks, 1):
            num = t.number or str(i)
            num = f"{t.disc}-{num.zfill(2)}" if multi_disc and t.disc else num.zfill(2)
            rows.append(f"{num}. {t.title or t.rel}  [{fmt_clock(t.duration)}]")
        rows.append(f"\n{len(a.tracks)} pistes • durée totale {fmt_clock(a.duration)}")
        return "\n".join(rows)

    def _source_line(self, ctx):
        s = ctx.d("source")
        return f"{s} - {ctx.d('platform')}" if s == "WEB" and ctx.d("platform") else s

    def _artist(self, ctx):
        a = ctx.analysis
        return (ctx.ident.raw.get("artist") if ctx.ident and ctx.ident.provider == "musicbrainz" else "") or a.artist

    def nfo(self, ctx):
        a = ctx.analysis
        n = Nfo(ctx.name)
        n.field("Artiste", self._artist(ctx)).field("Album", (ctx.ident.title if ctx.ident else "") or a.album)
        n.field("Année", (ctx.ident.year if ctx.ident else "") or a.year)
        n.field("Genres", ", ".join((ctx.ident.genres if ctx.ident and ctx.ident.genres else a.genres)[:5]))
        n.field("Label / catalogue", ctx.d("label")).field("Lien", ctx.d("link")).blank()
        n.field("Source", self._source_line(ctx)).field("Qualité", self._quality(a))
        n.field("Mode", "VBR" if a.vbr else "CBR" if not a.lossless else "")
        tag_formats = sorted({t.tag_format for t in a.tracks if t.tag_format})
        n.field("Tags", ("Oui (" + ", ".join(tag_formats) + ")") if tag_formats else "Non")
        n.field("Pochette embarquée", "Oui" if a.all_covers_embedded else "Non")
        if a.cover:
            n.field("Pochette", f"{a.cover}" + (f" ({a.cover_size[0]}×{a.cover_size[1]})" if a.cover_size[0] else ""))
        n.field("Pistes", len(a.tracks)).field("Durée totale", fmt_clock(a.duration))
        n.field("Fichiers", len(ctx.src.files)).field("Taille totale", fmt_size(ctx.src.total_size))
        if ctx.d("hardware"):
            n.section("Matériel").text(ctx.d("hardware"))
        n.section("Tracklist").text(self._tracklist(a))
        return n.files(ctx.src).render()

    def description(self, ctx):
        a = ctx.analysis
        kind = dict(ctx.ident.facts).get("Type", "Album") if ctx.ident else "Album"
        p = Prez().header(ctx.ident, ctx.name)
        p.items("Fiche", [("Artiste", self._artist(ctx)), ("Album", (ctx.ident.title if ctx.ident else "") or a.album),
                          ("Année", (ctx.ident.year if ctx.ident else "") or a.year), ("Type", kind),
                          ("Genre", ", ".join((ctx.ident.genres if ctx.ident and ctx.ident.genres else a.genres)[:5])),
                          ("Source", self._source_line(ctx)), ("Label / catalogue", ctx.d("label")),
                          ("Lien", f"[url={ctx.d('link')}]{ctx.d('link')}[/url]" if ctx.d("link") else "")])
        p.items("Informations techniques", [("Release", ctx.name), ("Qualité", self._quality(a)),
                                            ("Fichiers", len(ctx.src.files)), ("Taille", fmt_size(ctx.src.total_size))])
        p.code("Tracklist", self._tracklist(a))
        return p.render()

    # ── Options ───────────────────────────────────────────────────────────
    def auto_options(self, types, ctx):
        a, out = ctx.analysis, {}
        genres = (ctx.ident.genres if ctx.ident else []) + a.genres
        pick(types, out, "Format Musique", format_label(a))
        src = {"CD": "CD", "WEB": "Web", "Vinyle": "Vinyle", "SACD": "SACD",
               "BluRay Audio": "BluRay Audio"}.get(ctx.d("source"), "")
        pick(types, out, "Source", src)
        mb_type = ""
        if ctx.ident and ctx.ident.facts:
            mb_type = dict(ctx.ident.facts).get("Type", "").split(" / ")[-1].lower()
        pick(types, out, "Type Musique", MB_TYPE.get(mb_type, "Album"))
        pick_fuzzy(types, out, "Genre Musique", genres)
        pick(types, out, "Format Podcast", {"AAC": "M4A/AAC"}.get(a.codec, a.codec))
        pick_fuzzy(types, out, "Genre Podcast", genres)
        pick(types, out, "Format Samples", {"AIFF": "AIFF"}.get(a.codec, a.codec))
        pick_fuzzy(types, out, "Genre Samples", genres)
        return out
