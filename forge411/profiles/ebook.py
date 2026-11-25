"""Ebook : livres, BD, comics, mangas, presse, partitions, revues, livres audio."""

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from .. import audioinfo as ai
from ..model import Check, Detail, Part, fmt_duration, fmt_size, slug
from ..render import Nfo, Prez
from .base import ARCHIVE_EXT, Profile, banned_team_error, pick, pick_fuzzy, team_of

BOOK_EXT = {".epub", ".pdf", ".mobi", ".azw", ".azw3", ".djvu", ".prc", ".doc", ".docx", ".rtf", ".txt", ".fb2"}
COMIC_EXT = {".cbz", ".cbr", ".cb7", ".cbt", ".cba"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
SCORE_EXT = {".gp", ".gp3", ".gp4", ".gp5", ".gpx", ".mscz", ".musicxml", ".mxl"}
LANGS = ["FR", "FRENCH", "MULTI", "EN"]


@dataclass
class EbookAnalysis:
    books: list = field(default_factory=list)       # fichiers livres / BD (rel)
    formats: list = field(default_factory=list)     # EPUB, PDF, CBZ…
    title: str = ""
    author: str = ""
    language: str = ""
    publisher: str = ""
    date: str = ""
    isbn: str = ""
    pages: int = 0
    images: int = 0
    image_size: tuple = (0, 0)
    audio: ai.AudioAnalysis = None
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def is_audio(self) -> bool:
        return bool(self.audio and self.audio.tracks)


def _epub_meta(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as z:
            container = ElementTree.fromstring(z.read("META-INF/container.xml"))
            opf_path = container.find(".//{*}rootfile").get("full-path")
            opf = ElementTree.fromstring(z.read(opf_path))
    except Exception:
        return {}
    md = opf.find("{*}metadata")
    if md is None:
        return {}
    get = lambda tag: (md.findtext(f"{{http://purl.org/dc/elements/1.1/}}{tag}") or "").strip()
    isbn = ""
    for ident in md.findall("{http://purl.org/dc/elements/1.1/}identifier"):
        digits = re.sub(r"[^0-9Xx]", "", ident.text or "")
        if len(digits) in (10, 13):
            isbn = digits
    return {"title": get("title"), "author": get("creator"), "language": get("language"),
            "publisher": get("publisher"), "date": get("date")[:10], "isbn": isbn}


def _pdf_pages(path: Path) -> int:
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(path)).pages)
    except Exception:
        pass
    try:
        data = path.read_bytes()[:50_000_000]
        return len(re.findall(rb"/Type\s*/Page[^s]", data))
    except OSError:
        return 0


def _cbz_images(path: Path):
    try:
        with zipfile.ZipFile(path) as z:
            names = sorted(n for n in z.namelist() if Path(n).suffix.lower() in IMG_EXT)
            size = (0, 0)
            if names:
                try:
                    from PIL import Image
                    import io
                    with Image.open(io.BytesIO(z.read(names[len(names) // 2]))) as im:
                        size = im.size
                except Exception:
                    pass
            return len(names), size
    except Exception:
        return 0, (0, 0)


def analyze(src, progress=None) -> EbookAnalysis:
    e = EbookAnalysis()
    books = src.by_ext(*(BOOK_EXT | COMIC_EXT | SCORE_EXT))
    e.books = [src.rel(f) for f in books]
    e.formats = sorted({f.suffix.lstrip(".").upper() for f in books})
    if src.by_ext(*ai.AUDIO_EXT):
        e.audio = ai.analyze(src, progress)
    images = src.by_ext(*IMG_EXT)
    if not books and images and len(images) > 3:
        e.formats = ["JPG" if images[0].suffix.lower() in (".jpg", ".jpeg") else "PNG"]
        e.images = len(images)
    if not books and not e.is_audio and not e.images:
        e.errors.append("Aucun livre, BD, partition ni livre audio trouvé.")
    if src.by_ext(*ARCHIVE_EXT):
        e.errors.append("Archives (zip, rar, 7z) interdites : extrais-les avant l'upload.")
    for f in books[:1]:
        if progress:
            progress(f"Lecture de {f.name}")
        ext = f.suffix.lower()
        if ext == ".epub":
            m = _epub_meta(f)
            e.title, e.author, e.language = m.get("title", ""), m.get("author", ""), m.get("language", "")
            e.publisher, e.date, e.isbn = m.get("publisher", ""), m.get("date", ""), m.get("isbn", "")
        elif ext == ".pdf":
            e.pages = _pdf_pages(f)
        elif ext == ".cbz":
            e.images, e.image_size = _cbz_images(f)
    if len(e.formats) > 3:
        e.warnings.append("Plus de trois formats du même livre : C411 en accepte deux ou trois au maximum.")
    return e


class EbookProfile(Profile):
    key = "ebook"
    label = "Ebook"
    icon = "📚"
    category_id = 2
    subcategories = {14: "Livres", 12: "BDs", 13: "Comics", 15: "Manga", 16: "Presse", 11: "Audio",
                     59: "Partitions & Tablatures", 60: "Revues & Manuels techniques",
                     61: "Publications scientifiques"}
    provider = "books"
    template = "Titre.Auteur.Langue.[Format]-Team"
    hint = "Contenu en français uniquement (règle C411). Le titre et l'auteur viennent d'Open Library ou des métadonnées."

    def score(self, src):
        n = len(src.by_ext(*(BOOK_EXT | COMIC_EXT | SCORE_EXT)))
        audiobook = bool(src.by_ext(".m4b")) or bool(re.search(r"livre.?audio|audiobook|lu par", src.stem, re.I))
        if audiobook and src.by_ext(*ai.AUDIO_EXT):
            return 0.95
        return 0.0 if not n else 0.6 + 0.4 * n / max(len(src.files), 1)

    def analyze(self, src, progress=None):
        return analyze(src, progress)

    def summary(self, ctx):
        e = ctx.analysis
        rows = [("Formats", ", ".join(e.formats) or "-"), ("Fichiers", str(len(e.books) or e.images))]
        if e.title:
            rows.append(("Métadonnées", f"{e.title} - {e.author}".strip(" -")))
        if e.pages:
            rows.append(("Pages", str(e.pages)))
        if e.images:
            rows.append(("Images", f"{e.images}" + (f" ({e.image_size[0]}×{e.image_size[1]})" if e.image_size[0] else "")))
        if e.is_audio:
            a = e.audio
            rows += [("Audio", f"{len(a.tracks)} fichier(s) • {a.codec} • {a.bitrate} kb/s"),
                     ("Durée", fmt_duration(int(a.duration * 1000)))]
        return rows

    def issues(self, ctx):
        e = ctx.analysis
        c = Check(errors=list(e.errors), warnings=list(e.warnings))
        if e.is_audio and e.audio.bitrate and e.audio.bitrate < 64:
            c.errors.append(f"Livre audio à {e.audio.bitrate} kb/s : minimum 64 kb/s.")
        if e.language and not e.language.lower().startswith("fr"):
            c.warnings.append(f"Langue du livre : {e.language}. C411 n'accepte que les ebooks en français.")
        return c

    def guess_sub(self, ctx):
        e, stem = ctx.analysis, ctx.src.stem.lower()
        if e.is_audio and not e.books:
            return 11
        if any(f in ("GP", "GP3", "GP4", "GP5", "GPX", "MSCZ", "MUSICXML", "MXL") for f in e.formats):
            return 59
        if "manga" in stem or "tome" in stem and e.images:
            return 15
        if any(f in ("CBZ", "CBR", "CB7") for f in e.formats) or e.images:
            return 13 if "comics" in stem or "marvel" in stem or "dc" in stem.split() else 12
        if re.search(r"\b(magazine|journal|presse|hebdo|n°|no\.?\s?\d)", stem):
            return 16
        return 14

    # ── Identification ────────────────────────────────────────────────────
    def query(self, ctx):
        e = ctx.analysis
        title = e.title or re.sub(r"[._]+", " ", re.sub(r"-[A-Za-z0-9]+$", "", ctx.src.stem))
        title = re.sub(r"\b(EPUB|PDF|CBZ|CBR|MOBI|AZW3|FRENCH|ENGLISH|JAPANESE|MULTI|FR|EN|JP|KR|VF|VO|T\d+.*)\b", "", title, flags=re.I).strip()
        return {"query": title, "year": e.date[:4], "author": e.author, "isbn": e.isbn}

    def search(self, client, q):
        return client.search(q.get("query", ""), q.get("year", ""), q.get("author", ""), q.get("isbn", ""))

    # ── Nom ───────────────────────────────────────────────────────────────
    def parts(self, ctx):
        e, ident = ctx.analysis, ctx.ident
        title = (ident.title if ident and ident.title else "") or e.title or ctx.src.stem
        author = (", ".join((ident.raw.get("authors") or [])[:1]) if ident else "") or e.author
        if e.is_audio and not e.books:
            fmt = f"{e.audio.codec}.{e.audio.bitrate}.kbps" if e.audio.bitrate else e.audio.codec
        else:
            fmt = "+".join(e.formats[:3])
        team = team_of(ctx.src.stem.replace(" ", ".")) or "NOTAG"
        if ctx.sub_id == 16:
            return [Part("title", "Titre", slug(title), width=28), Part("date", "Date / numéro", "", width=14,
                                                                        hint="Ex. 2025-01, ou Mensuel.N°385.Mars.2013 pour un numéro d'une série."),
                    Part("lang", "Langue", "FR", choices=LANGS, width=10),
                    Part("format", "Format", fmt, width=10), Part("team", "Team", team, width=12)]
        return [Part("title", "Titre", slug(title), width=28),
                Part("set", "Tome / pack", "", width=14,
                     hint="Tome d'une série : Tome.23 ou T00.Nom. Pack : [T01 à T07], [INTEGRALE], [ANTHOLOGIE] "
                          "(entre crochets). Vide pour un titre unique."),
                Part("author", "Auteur", slug(author), width=20),
                Part("lang", "Langue", "FR", choices=LANGS, width=10, hint="C411 n'accepte que le français "
                                                                                 "(sauf publications scientifiques)."),
                Part("format", "Format", fmt, width=10, hint="EPUB, PDF, CBZ… (jusqu'à trois formats)."),
                Part("team", "Team", team, width=12)]

    def build(self, parts):
        p = {k: (v or "").strip(". ") for k, v in parts.items()}
        fmt = p.get("format", "")
        if fmt and not fmt.startswith("["):
            fmt = f"[{fmt}]"
        if p.get("set", "").upper().strip("[]") == "ANTHOLOGIE":
            vals = [p.get("author"), "[ANTHOLOGIE]", p.get("lang"), fmt]          # Auteur.[ANTHOLOGIE]…
        else:
            vals = [p.get("title"), p.get("set"), p.get("author"), p.get("date"), p.get("lang"), fmt]
        return ".".join(v for v in vals if v) + f"-{p.get('team') or 'NOTAG'}"

    def validate(self, name, ctx):
        c = Check()
        if not name.strip():
            c.errors.append("Le nom est vide.")
            return c
        if re.search(r"\s", name.replace(" à ", "")):
            c.errors.append("Pas d'espaces : les mots sont séparés par des points.")
        err = banned_team_error(name)
        if err:
            c.errors.append(err)
        if ctx.parts.get("lang") not in ("FR", "FRENCH", "MULTI") and ctx.sub_id != 61:
            c.warnings.append("C411 n'accepte que les ebooks en français (sauf publications scientifiques).")
        c.errors += self.issues(ctx).errors
        return c

    def details(self, ctx):
        e, ident = ctx.analysis, ctx.ident
        facts = dict(ident.facts) if ident else {}
        rows = [Detail("publisher", "Éditeur", e.publisher or facts.get("Éditeur", "")),
                Detail("isbn", "ISBN", e.isbn or facts.get("ISBN", "")),
                Detail("pages", "Pages", str(e.pages or facts.get("Pages", "") or ""))]
        if e.is_audio:
            rows.append(Detail("narrator", "Lu par", "", hint="Narrateur du livre audio."))
        return rows

    # ── NFO / présentation ────────────────────────────────────────────────
    def _tech(self, ctx):
        e = ctx.analysis
        rows = [("Format", ", ".join(e.formats)), ("Langue", ctx.parts.get("lang", "")),
                ("Éditeur", ctx.d("publisher")), ("ISBN", ctx.d("isbn")), ("Pages", ctx.d("pages")),
                ("Fichiers", len(ctx.src.files)), ("Taille", fmt_size(ctx.src.total_size))]
        if e.images:
            rows.append(("Images", f"{e.images}" + (f", {e.image_size[0]}×{e.image_size[1]} px" if e.image_size[0] else "")))
        if e.is_audio:
            a = e.audio
            rows += [("Lu par", ctx.d("narrator")), ("Audio", f"{a.codec} • {a.bitrate} kb/s"),
                     ("Durée", fmt_duration(int(a.duration * 1000)))]
        return rows

    def nfo(self, ctx):
        n = Nfo(ctx.name).ident(ctx.ident)
        for k, v in self._tech(ctx):
            n.field(k, v)
        if ctx.ident and ctx.ident.overview:
            n.section("Résumé").text(ctx.ident.overview)
        return n.files(ctx.src).render()

    def description(self, ctx):
        p = Prez().header(ctx.ident, ctx.name)
        if ctx.ident:
            p.block("Résumé", ctx.ident.overview).fiche(ctx.ident)
        return p.items("Informations techniques", [("Release", ctx.name)] + self._tech(ctx)).files(ctx.src).render()

    # ── Options ───────────────────────────────────────────────────────────
    def auto_options(self, types, ctx):
        e, out = ctx.analysis, {}
        lang = {"FR": "Français", "FRENCH": "Français", "MULTI": "Multi (Français inclus)",
                "EN": "Anglais"}.get(ctx.parts.get("lang", "FR"), "Français")
        pick(types, out, "Format fichier", *(e.formats[:1] or []))
        pick(types, out, "Langue BD/Comics/Manga", lang)
        pick(types, out, "Langue", lang)
        genres = ctx.ident.genres if ctx.ident else []
        pick_fuzzy(types, out, "Genre Ebook", genres)
        if e.is_audio:
            fmt = {"AAC": "M4A/AAC", "ALAC": "M4A/AAC"}.get(e.audio.codec, e.audio.codec)
            if ctx.src.by_ext(".m4b"):
                fmt = "M4B"
            pick(types, out, "Format Audio", fmt)
            pick(types, out, "Type Audio", "Livre audio")
            pick_fuzzy(types, out, "Genre Audio Ebook", genres)
        return out
