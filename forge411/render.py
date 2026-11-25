"""Briques communes de mise en forme : NFO texte et présentation BBCode."""

from .model import Ident, Source, fmt_size

LOGO = r"""
       ______                      __ __ ______
      / ____/___  _________ ____  / // /<  <  /
     / /_  / __ \/ ___/ __ `/ _ \/ // /_/ // /
    / __/ / /_/ / /  / /_/ /  __/__  __/ // /
   /_/    \____/_/   \__, /\___/  /_/ /_//_/
                    /____/
""".strip("\n")

WIDTH = 78


# ═══════════════════════════════════════════════════════════════════════════
# NFO
# ═══════════════════════════════════════════════════════════════════════════

class Nfo:
    def __init__(self, name: str):
        self.lines = [LOGO, "", "=" * WIDTH, f"  {name}", "=" * WIDTH, ""]

    def field(self, label: str, value) -> "Nfo":
        if value not in (None, ""):
            self.lines.append(f"  {label} {'.' * max(2, 18 - len(label))} : {value}")
        return self

    def blank(self) -> "Nfo":
        if self.lines and self.lines[-1] != "":
            self.lines.append("")
        return self

    def section(self, title: str) -> "Nfo":
        self.blank()
        self.lines += ["-" * WIDTH, f"  {title.upper()}", "-" * WIDTH, ""]
        return self

    def text(self, text: str, indent: int = 2) -> "Nfo":
        pad = " " * indent
        for ln in (text or "").splitlines():
            self.lines.append(pad + ln if ln.strip() else "")
        return self

    def ident(self, ident: Ident) -> "Nfo":
        if not ident or not ident.title:
            return self
        title = ident.title
        if ident.original_title and ident.original_title != ident.title:
            title += f" ({ident.original_title})"
        self.field("Titre", title).field("Année", ident.year)
        for role, names in ident.people:
            self.field(role, names)
        if ident.genres:
            self.field("Genres", ", ".join(ident.genres[:6]))
        self.field("Lien", ident.url)
        return self.blank()

    def files(self, src: Source, limit: int = 400) -> "Nfo":
        if not src.is_dir:
            return self
        self.section(f"Contenu ({len(src.files)} fichiers)")
        for f in src.files[:limit]:
            self.lines.append(f"  {src.rel(f)}  [{fmt_size(f.stat().st_size)}]")
        if len(src.files) > limit:
            self.lines.append(f"  … et {len(src.files) - limit} autres fichiers")
        return self

    def render(self) -> str:
        return "\n".join(self.blank().lines + ["=" * WIDTH, ""])


# ═══════════════════════════════════════════════════════════════════════════
# BBCode
# ═══════════════════════════════════════════════════════════════════════════

class Prez:
    def __init__(self):
        self.parts = []

    def header(self, ident: Ident, fallback_title: str = "") -> "Prez":
        if ident and ident.image:
            self.parts.append(f"[center][img]{ident.image}[/img][/center]\n")
        title = (ident.title if ident and ident.title else fallback_title)
        head = f"[center][b]{title.upper()}[/b]"
        if ident and ident.year:
            head += f" ({ident.year})"
        if ident and ident.original_title and ident.original_title != ident.title:
            head += f"\n[i]{ident.original_title}[/i]"
        if ident and ident.genres:
            head += "\n" + ", ".join(ident.genres[:6])
        self.parts.append(head + "[/center]\n")
        return self

    def block(self, title: str, text: str) -> "Prez":
        if text and text.strip():
            self.parts.append(f"\n[b]{title.upper()}[/b]\n[quote]{text.strip()}[/quote]\n")
        return self

    def items(self, title: str, rows: list) -> "Prez":
        rows = [(k, v) for k, v in rows if v not in (None, "")]
        if rows:
            body = "\n".join(f"[*][b]{k} :[/b] {v}" for k, v in rows)
            self.parts.append(f"\n[b]{title.upper()}[/b]\n[list]\n{body}\n[/list]\n")
        return self

    def fiche(self, ident: Ident) -> "Prez":
        if not ident:
            return self
        rows = list(ident.people) + list(ident.facts)
        if ident.url:
            rows.append(("Lien", f"[url={ident.url}]{ident.url}[/url]"))
        return self.items("Fiche", rows)

    def code(self, title: str, text: str) -> "Prez":
        if text and text.strip():
            self.parts.append(f"\n[spoiler={title}][code]{text.strip()}[/code][/spoiler]\n")
        return self

    def files(self, src: Source, limit: int = 300) -> "Prez":
        if src.is_dir and len(src.files) > 1:
            rows = "\n".join(f"{src.rel(f)} ({fmt_size(f.stat().st_size)})" for f in src.files[:limit])
            if len(src.files) > limit:
                rows += f"\n… et {len(src.files) - limit} autres fichiers"
            self.code(f"Contenu ({len(src.files)} fichiers)", rows)
        return self

    def render(self) -> str:
        return "".join(self.parts).strip() + "\n"
