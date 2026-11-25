"""Les étapes de l'assistant d'upload (génériques : le profil fournit le contenu)."""

import os
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import catalog as CAT
from .. import clients as CL
from .. import files as fs
from ..api import C411Error
from ..config import KEY_LINKS, add_history
from ..lookup import LookupFailed
from ..model import fmt_size
from ..profiles import PROFILES, detect, get, options_payload
from ..torrent import Cancelled, create_torrent
from . import theme as T
from .widgets import (UI, Btn, Card, Field, Images, IssueList, ScrollFrame, TextArea, Tooltip,
                      autowrap, badge, help_icon, label, link, run_bg)


class Step(tk.Frame):
    title = ""
    subtitle = ""
    scroll = True

    def __init__(self, app):
        super().__init__(app.body, bg=T.BG)
        self.app = app
        if self.scroll:
            self.sf = ScrollFrame(self)
            self.sf.pack(fill="both", expand=True)
            self.root = tk.Frame(self.sf.inner, bg=T.BG)
            self.root.pack(fill="both", expand=True, padx=(0, 14))
        else:
            self.root = self
        self.build()

    @property
    def s(self):
        return self.app.session

    def build(self):
        pass

    def on_enter(self):
        pass

    def ready(self) -> bool:
        return True

    def leave(self, done):
        """Appelé avant de passer à l'étape suivante ; done(True) pour continuer."""
        done(True)

    def footer(self, bar: tk.Frame):
        """Boutons propres à l'étape, placés dans la barre du bas."""

    def heading(self) -> tuple:
        return self.title, self.subtitle

    def section(self, parent, title: str, subtitle: str = "", help: str = "") -> tk.Frame:
        card = Card(parent)
        card.pack(fill="x", pady=(0, 14))
        if title:
            head = tk.Frame(card.body, bg=T.SURFACE)
            head.pack(fill="x")
            label(head, title, font=T.F_H2).pack(side="left")
            if help:
                help_icon(head, help).pack(side="left", padx=(8, 0))
        if subtitle:
            autowrap(label(card.body, subtitle, fg=T.MUTED, font=T.F_SMALL)).pack(fill="x", pady=(2, 0))
        inner = tk.Frame(card.body, bg=T.SURFACE)
        inner.pack(fill="both", expand=True, pady=(12 if title else 0, 0))
        return inner

    def clear(self, w):
        for c in w.winfo_children():
            c.destroy()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Source
# ═══════════════════════════════════════════════════════════════════════════

class SourceStep(Step):
    title = "Source"
    subtitle = ("Choisis ce que tu veux partager : un fichier ou un dossier. "
                "Forge411 reconnaît le type de contenu et l'analyse.")

    def build(self):
        self.tiles = tk.Frame(self.root, bg=T.BG)
        self.tiles.pack(fill="x", pady=(0, 14))
        self.tiles.columnconfigure((0, 1), weight=1, uniform="t")
        self._tile(0, "📄", "Un fichier", "Film, épisode, ebook, application, ISO…", self.pick_file)
        self._tile(1, "📁", "Un dossier", "Saison, album, pack de BD, jeu, collection…", self.pick_dir)
        cats = tk.Frame(self.root, bg=T.BG)
        cats.pack(fill="x", pady=(0, 14))
        label(cats, "Types pris en charge :", fg=T.FAINT, font=T.F_SMALL).pack(side="left", anchor="n", padx=(0, 8))
        flow = tk.Frame(cats, bg=T.BG)
        flow.pack(side="left", fill="x", expand=True)
        badges = [badge(flow, f"{p.icon} {p.label}", "muted") for p in PROFILES]

        def reflow(e):          # les badges passent à la ligne quand la fenêtre est étroite
            x = y = row_h = 0
            for b in badges:
                w, h = b.winfo_reqwidth(), b.winfo_reqheight()
                if x and x + w > e.width:
                    x, y = 0, y + row_h + 6
                b.place(x=x, y=y)
                x, row_h = x + w + 6, max(row_h, h)
            flow.configure(height=y + row_h)
        flow.configure(height=badges[0].winfo_reqheight())
        flow.bind("<Configure>", reflow)

        self.loading = tk.Frame(self.root, bg=T.BG)
        self.loading_lbl = label(self.loading, "", fg=T.MUTED)
        self.loading_lbl.pack(fill="x")
        self.loading_bar = ttk.Progressbar(self.loading, mode="indeterminate")
        self.loading_bar.pack(fill="x", pady=(6, 0))
        self.result = tk.Frame(self.root, bg=T.BG)
        self.result.pack(fill="both", expand=True)

    def _tile(self, col, icon, title, sub, cmd):
        card = Card(self.tiles, padding=22)
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 7, 7 if col == 0 else 0))
        ws = [card, card.body]
        for text, font, fg, pad in ((icon, ("Segoe UI Emoji", 22), T.TEXT, 0), (title, T.F_BIG, T.TEXT, 8),
                                    (sub, T.F_UI, T.MUTED, 0)):
            w = label(card.body, text, font=font, fg=fg)
            w.pack(anchor="w", pady=(pad, 0))
            ws.append(w)

        def hover(on):
            for w in ws[1:]:
                w.configure(bg=T.SURFACE2 if on else T.SURFACE)
            card.configure(highlightbackground=T.ACCENT if on else T.BORDER)
        for w in ws:
            w.configure(cursor="hand2")
            w.bind("<Enter>", lambda e: hover(True))
            w.bind("<Leave>", lambda e: hover(False))
            w.bind("<Button-1>", lambda e: cmd())
        if col == 0:
            self.tile_widget = card

    def _initial_dir(self):
        return self.app.cfg.get("seed_dir") or self.app.cfg.get("last_dir") or str(Path.home())

    def pick_file(self):
        p = filedialog.askopenfilename(parent=self, title="Choisir le fichier", initialdir=self._initial_dir())
        if p:
            self.analyze(Path(p))

    def pick_dir(self):
        p = filedialog.askdirectory(parent=self, title="Choisir le dossier", initialdir=self._initial_dir())
        if p:
            self.analyze(Path(p))

    def _start_loading(self, text):
        self.clear(self.result)
        self.loading.pack(fill="x", pady=(0, 14), before=self.result)
        self.loading_lbl.configure(text=text)
        self.loading_bar.configure(mode="indeterminate")
        self.loading_bar.start(12)
        self.app.busy(True)

    def _stop_loading(self):
        self.loading_bar.stop()
        self.loading.pack_forget()
        self.app.busy(False)

    def _progress(self, msg):
        UI.call(self.loading_lbl.configure, {"text": msg})

    def analyze(self, path: Path, profile_key: str = ""):
        self.app.cfg.update({"last_dir": str(path.parent)})
        self._start_loading(f"Analyse de {path.name}…")

        def work():
            src = fs.scan(path)
            ranked = detect(src)
            prof = get(profile_key) if profile_key else ranked[0][1]
            return src, ranked, prof, prof.analyze(src, self._progress)

        def ok(res):
            self._stop_loading()
            src, ranked, prof, analysis = res
            self.app.new_session(src, ranked, prof, analysis)
            self.render()

        def err(e):
            self._stop_loading()
            messagebox.showerror("Analyse impossible", str(e), parent=self)
        run_bg(work, ok, err)

    def change_profile(self, key):
        s = self.s
        if not s.src or (s.profile and s.profile.key == key):
            return
        prof = get(key)
        self._start_loading(f"Analyse en tant que {prof.label}…")

        def ok(analysis):
            self._stop_loading()
            s.profile, s.analysis = prof, analysis
            s.sub_id = prof.guess_sub(s.ctx())
            s.reset_from_profile()
            self.app.invalidate_torrent()
            self.render()
        run_bg(lambda: prof.analyze(s.src, self._progress), ok,
               lambda e: (self._stop_loading(), messagebox.showerror("Analyse impossible", str(e), parent=self)))

    def on_enter(self):
        self.render()

    def render(self):
        self.clear(self.result)
        s = self.s
        if not s.src:
            return
        src, prof = s.src, s.profile
        body = self.section(self.result, "")
        autowrap(label(body, src.path.name, font=T.F_BIG)).pack(fill="x")
        autowrap(label(body, str(src.path.parent), fg=T.FAINT, font=T.F_SMALL)).pack(fill="x")
        chips = tk.Frame(body, bg=T.SURFACE)
        chips.pack(fill="x", pady=(10, 0))
        for text, tone in ((f"{prof.icon} {prof.label}", "accent"), (fmt_size(src.total_size), "muted"),
                           (f"{len(src.files)} fichier{'s' if len(src.files) > 1 else ''}", "muted")):
            badge(chips, text, tone).pack(side="left", padx=(0, 6))

        # Type de contenu
        kind = tk.Frame(body, bg=T.SURFACE)
        kind.pack(fill="x", pady=(16, 0))
        kind.columnconfigure((0, 1), weight=1, uniform="k")
        pv = tk.StringVar(value=f"{prof.icon}  {prof.label}")
        labels = {f"{p.icon}  {p.label}": p.key for p in PROFILES}
        f1 = Field(kind, "Type de contenu", pv, values=list(labels), readonly=True,
                   help="Détecté d'après les fichiers. Change-le si Forge411 s'est trompé : l'analyse est relancée.")
        f1.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        f1.input.bind("<<ComboboxSelected>>", lambda e: self.change_profile(labels[pv.get()]))
        sv = tk.StringVar(value=prof.subcategories.get(s.sub_id, ""))
        f2 = Field(kind, "Sous-catégorie C411", sv, values=list(prof.subcategories.values()), readonly=True,
                   help="Où la release sera rangée sur C411. Proposée automatiquement, modifiable aussi à l'étape Présentation.")
        f2.grid(row=0, column=1, sticky="ew")

        def sub_changed(_):
            new = next(k for k, v in prof.subcategories.items() if v == sv.get())
            if new != s.sub_id:
                s.sub_id = new
                s.reset_from_ident()
        f2.input.bind("<<ComboboxSelected>>", sub_changed)

        rows = prof.summary(s.ctx())
        if rows:
            grid = tk.Frame(body, bg=T.SURFACE)
            grid.pack(fill="x", pady=(16, 0))
            grid.columnconfigure(1, weight=1)
            for i, (k, v) in enumerate(rows):
                label(grid, k, fg=T.MUTED, font=T.F_SMALL_B).grid(row=i, column=0, sticky="nw", padx=(0, 16), pady=2)
                autowrap(label(grid, v)).grid(row=i, column=1, sticky="ew", pady=2)

        issues = prof.issues(s.ctx()).items()
        seed = fs.seed_location_issue(src, self.app.cfg.get("seed_dir"))
        if seed:
            issues.append(("warning", seed))
        il = IssueList(body)
        il.pack(fill="x", pady=(14, 0))
        il.show(issues or [("ok", "Source exploitable.")])
        if seed and Path(self.app.cfg.get("seed_dir") or "").exists():
            row = tk.Frame(body, bg=T.SURFACE)
            row.pack(fill="x", pady=(10, 0))
            Btn(row, "Déplacer dans le dossier de seed", self.move_to_seed, small=True).pack(side="left")
        self.app.refresh_nav()

    def move_to_seed(self):
        src, dest = self.s.src, Path(self.app.cfg.get("seed_dir"))
        old_path = src.path
        if not messagebox.askyesno("Déplacer", f"Déplacer « {src.path.name} » vers\n{dest} ?", parent=self):
            return
        self._start_loading("Déplacement…")
        self.loading_bar.stop()
        self.loading_bar.configure(mode="determinate", value=0)

        def ok(_):
            self._stop_loading()
            fs.remap_paths(self.s.analysis, old_path, src.path)   # captures, NFO… lisent la vidéo au nouvel endroit
            self.app.invalidate_torrent()
            self.render()
        import time
        total, t0 = src.total_size, time.monotonic()

        def progress(f):
            el = max(time.monotonic() - t0, 0.001)
            speed = total * f / el
            eta = (total * (1 - f) / speed) if speed > 0 else 0
            UI.call(self.loading_bar.configure, {"value": f * 100})
            UI.call(self.loading_lbl.configure, {"text": f"Déplacement… {fmt_size(int(total * f))} / {fmt_size(total)}"
                                                         f" · {fmt_size(int(speed))}/s · reste {int(eta // 60)} min "
                                                         f"{int(eta % 60):02d} s"})
        run_bg(lambda: fs.move(src, dest, progress),
               ok, lambda e: (self._stop_loading(), messagebox.showerror("Déplacement impossible", str(e), parent=self)))

    def ready(self):
        s = self.s
        return bool(s.src and s.profile and not s.profile.issues(s.ctx()).errors)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Identification
# ═══════════════════════════════════════════════════════════════════════════

class IdentifyStep(Step):
    title = "Identification"
    scroll = False

    def heading(self):
        prov = self.s.profile.provider_for(self.s.ctx()) if self.s.profile else None
        names = {"tmdb": "TMDB", "musicbrainz": "MusicBrainz", "books": "Open Library", "rawg": "RAWG",
                 "tpdb": "ThePornDB"}
        if prov:
            return self.title, (f"Retrouve la fiche sur {names[prov]} : titre, résumé, image et genres "
                                "rempliront le nom, le NFO et la présentation.")
        return self.title, "Pas de base en ligne pour ce type de contenu : indique simplement le titre."

    def build(self):
        self.bar = tk.Frame(self, bg=T.BG)
        self.bar.pack(fill="x", pady=(0, 12))
        self.q = tk.StringVar()
        self.year = tk.StringVar()
        self.hint_var = tk.StringVar()
        e = ttk.Entry(self.bar, textvariable=self.q)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<Return>", lambda _: self.search())
        Tooltip(e, "Titre à chercher. Appuie sur Entrée pour lancer la recherche.")
        self.hint_entry = ttk.Entry(self.bar, textvariable=self.hint_var, width=18)
        self.hint_entry.bind("<Return>", lambda _: self.search())
        self.hint_tip = Tooltip(self.hint_entry, "")
        ye = ttk.Entry(self.bar, textvariable=self.year, width=6)
        ye.pack(side="left", padx=(8, 0))
        ye.bind("<Return>", lambda _: self.search())
        Tooltip(ye, "Année (facultative) : affine la recherche.")
        Btn(self.bar, "Rechercher", self.search, kind="primary").pack(side="left", padx=(8, 0))
        Btn(self.bar, "Saisie manuelle", self.manual, kind="ghost").pack(side="left", padx=(8, 0))

        cols = tk.Frame(self, bg=T.BG)
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=3, uniform="c")
        cols.columnconfigure(1, weight=2, uniform="c")
        cols.rowconfigure(0, weight=1)
        self.results = ScrollFrame(cols)
        self.results.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.detail_sf = ScrollFrame(cols)
        self.detail_sf.grid(row=0, column=1, sticky="nsew")
        self.detail = self.detail_sf.inner

    def on_enter(self):
        s = self.s
        prov = s.profile.provider_for(s.ctx())
        hint_key = {"musicbrainz": ("artist", "Artiste"), "books": ("author", "Auteur")}.get(prov)
        self.hint_entry.pack_forget()
        if hint_key:
            self.hint_entry.pack(side="left", padx=(8, 0), after=self.bar.winfo_children()[0])
            self.hint_tip.text = f"{hint_key[1]} (facultatif) : affine la recherche."
        self._hint_key = hint_key[0] if hint_key else ""
        if not prov:
            self.bar.pack_forget()
            if not s.ident:
                s.ident = s.profile.manual_ident(s.ctx())
            self.manual()
            return
        if not self.bar.winfo_ismapped():
            self.bar.pack(fill="x", pady=(0, 12), before=self.bar.master.winfo_children()[1])
        if not s.query:
            s.query = s.profile.query(s.ctx())
        self.q.set(s.query.get("query", ""))
        self.year.set(s.query.get("year", ""))
        self.hint_var.set(s.query.get(self._hint_key, "") if self._hint_key else "")
        if s.ident and not s.ident.provider:
            self.manual()
        elif not s.matches and not s.ident:
            self.clear(self.results.inner)
            self.render_detail()                  # efface la fiche d'un upload précédent
            self.search(auto=True)
        else:
            self.render_results()
            self.render_detail()

    def _client_or_message(self):
        try:
            return self.app.client(self.s.profile.provider_for(self.s.ctx()))
        except LookupFailed as e:
            self.clear(self.results.inner)
            box = Card(self.results.inner)
            box.pack(fill="x")
            label(box.body, str(e), fg=T.WARNING, font=T.F_UI_B).pack(fill="x")
            key = {"tmdb": "tmdb_api_key", "rawg": "rawg_api_key",
                   "tpdb": "tpdb_api_key"}.get(self.s.profile.provider_for(self.s.ctx()))
            if key:
                link(box.body, *KEY_LINKS[key]).pack(fill="x", pady=(8, 0))
            row = tk.Frame(box.body, bg=T.SURFACE)
            row.pack(fill="x", pady=(10, 0))
            Btn(row, "Ouvrir les paramètres", self.app.open_settings, small=True).pack(side="left")
            Btn(row, "Continuer sans base (saisie manuelle)", self.manual, kind="ghost", small=True).pack(side="left", padx=(8, 0))
            return None

    def search(self, auto=False):
        s = self.s
        q = self.q.get().strip()
        if not q and not self.hint_var.get().strip():
            return
        client = self._client_or_message()
        if not client:
            return
        s.query = {**s.query, "query": q, "year": self.year.get().strip()}
        if self._hint_key:
            s.query[self._hint_key] = self.hint_var.get().strip()
        self.clear(self.results.inner)
        label(self.results.inner, "Recherche…", fg=T.MUTED).pack(fill="x")
        self.app.busy(True)
        prof, query = s.profile, dict(s.query)

        def ok(matches):
            self.app.busy(False)
            s.matches = matches
            self.render_results()
            if auto and matches and not s.ident:
                self.select(matches[0])

        def err(e):
            self.app.busy(False)
            self.clear(self.results.inner)
            label(self.results.inner, f"Erreur : {e}", fg=T.ERROR).pack(fill="x")
        run_bg(lambda: prof.search(client, query), ok, err)

    def render_results(self):
        inner = self.results.inner
        self.clear(inner)
        s = self.s
        if not s.matches:
            label(inner, "Aucun résultat. Essaie un autre titre, sans l'année, ou passe en saisie manuelle.",
                  fg=T.MUTED).pack(fill="x")
            return
        for m in s.matches:
            chosen = bool(s.ident and s.ident.provider and s.ident.id == m.id.split(":", 1)[-1])
            bg = T.SURFACE2 if chosen else T.SURFACE
            card = tk.Frame(inner, bg=bg, highlightbackground=T.ACCENT if chosen else T.BORDER,
                            highlightthickness=1, cursor="hand2")
            card.pack(fill="x", pady=(0, 8))
            img = tk.Label(card, bg=bg, image=Images.placeholder(62, 93))
            img.pack(side="left", padx=10, pady=10)
            Images.load(m.image, 62, 93, lambda p, w=img: w.winfo_exists() and w.configure(image=p))
            txt = tk.Frame(card, bg=bg)
            txt.pack(side="left", fill="both", expand=True, pady=10, padx=(0, 10))
            top = tk.Frame(txt, bg=bg)
            top.pack(fill="x")
            label(top, m.title, font=T.F_UI_B).pack(side="left")
            if m.year:
                label(top, f"  {m.year}", fg=T.MUTED).pack(side="left")
            if m.kind:
                badge(top, m.kind, "accent").pack(side="right")
            if m.subtitle:
                autowrap(label(txt, m.subtitle, fg=T.MUTED, font=T.F_SMALL)).pack(fill="x")
            if m.overview:
                ov = m.overview[:220] + ("…" if len(m.overview) > 220 else "")
                autowrap(label(txt, ov, fg=T.FAINT, font=T.F_SMALL)).pack(fill="x", pady=(4, 0))
            for w in (card, img, txt, top, *txt.winfo_children(), *top.winfo_children()):
                w.bind("<Button-1>", lambda e, mm=m: self.select(mm))

    def select(self, m):
        s = self.s
        client = self.app.client(s.profile.provider_for(s.ctx()))
        self.app.busy(True)
        self.clear(self.detail)
        label(self.detail, "Chargement de la fiche…", fg=T.MUTED).pack(fill="x")

        def work():
            ident = client.details(m)
            from ..translate import french_overview
            french_overview(ident, self.app.cfg.get("translate_overview", True))
            existing = None
            if ident.provider == "tmdb":
                try:
                    existing = self.app.c411().existing(int(ident.id), ident.kind)
                except Exception:
                    existing = None
            return ident, existing

        def ok(res):
            self.app.busy(False)
            ident, existing = res
            changed = not s.ident or s.ident.id != ident.id
            s.ident, s.existing = ident, existing
            if changed:
                s.sub_id = s.profile.guess_sub(s.ctx()) if s.profile.key == "video" else s.sub_id
                s.reset_from_ident()
            self.render_results()
            self.render_detail()
            self.app.refresh_nav()

        def err(e):
            self.app.busy(False)
            self.clear(self.detail)
            label(self.detail, f"Erreur : {e}", fg=T.ERROR).pack(fill="x")
        run_bg(work, ok, err)

    def manual(self):
        """Fiche saisie à la main (aucune base, ou rien trouvé)."""
        s = self.s
        if not s.ident or s.ident.provider:
            base = s.profile.manual_ident(s.ctx())
            base.title = base.title or self.q.get().strip()
            base.year = self.year.get().strip()
            s.ident = base
            s.reset_from_ident()
        self.clear(self.detail)
        self.clear(self.results.inner)
        card = Card(self.results.inner)
        card.pack(fill="x")
        label(card.body, "Fiche manuelle", font=T.F_H2).pack(fill="x", pady=(0, 10))
        tv, yv = tk.StringVar(value=s.ident.title), tk.StringVar(value=s.ident.year)
        dv = tk.StringVar(value=s.ident.overview)
        iv = tk.StringVar(value=s.ident.image)
        Field(card.body, "Titre", tv, help="Titre complet, tel qu'il apparaîtra dans le NFO et la présentation.").pack(fill="x")
        Field(card.body, "Année", yv, width=8).pack(fill="x", pady=(10, 0))
        Field(card.body, "Image (URL)", iv,
              help="Obligatoire sur C411 : image ou bannière représentative du contenu. Héberge-la sur un service "
                   "d'images (imgbb…) et colle ici son adresse directe (.jpg, .png).").pack(fill="x", pady=(10, 0))
        Field(card.body, "Description", dv, multiline=True,
              help="Résumé ou description du contenu, repris dans la présentation (obligatoire sur C411).").pack(
            fill="x", pady=(10, 0))

        def sync(*_):
            s.ident.title, s.ident.year, s.ident.overview = tv.get().strip(), yv.get().strip(), dv.get().strip()
            s.ident.image = iv.get().strip()
            s.reset_from_ident()
            self.app.refresh_nav()
        for v in (tv, yv, dv, iv):
            v.trace_add("write", sync)
        self.app.refresh_nav()

    def render_detail(self):
        self.clear(self.detail)
        d = self.s.ident
        if not d or not d.provider:
            if self.s.profile.provider_for(self.s.ctx()):
                label(self.detail, "Sélectionne un résultat.", fg=T.MUTED).pack(fill="x")
            return
        card = Card(self.detail)
        card.pack(fill="x", padx=(0, 14))
        b = card.body
        top = tk.Frame(b, bg=T.SURFACE)
        top.pack(fill="x")
        wide = d.provider == "rawg"
        w, h = (200, 112) if wide else (120, 180)
        img = tk.Label(top, bg=T.SURFACE, image=Images.placeholder(w, h))
        img.pack(side="top" if wide else "left", anchor="w")
        Images.load(d.image, w, h, lambda p: img.winfo_exists() and img.configure(image=p))
        info = tk.Frame(top, bg=T.SURFACE)
        info.pack(side="top" if wide else "left", fill="both", expand=True, padx=(0 if wide else 14, 0),
                  pady=(10 if wide else 0, 0))
        autowrap(label(info, d.title, font=T.F_BIG)).pack(fill="x")
        if d.original_title and d.original_title != d.title:
            autowrap(label(info, d.original_title, fg=T.MUTED)).pack(fill="x")
        kinds = {"movie": "Film", "tv": "Série", "album": "Album", "livre": "Livre", "jeu": "Jeu"}
        meta = " • ".join(x for x in (d.year, kinds.get(d.kind, d.kind.capitalize() if d.kind else "")) if x)
        label(info, meta, fg=T.MUTED, font=T.F_SMALL).pack(fill="x", pady=(6, 0))
        for role, names in d.people[:2]:
            autowrap(label(info, f"{role} : {names}", fg=T.FAINT, font=T.F_SMALL)).pack(fill="x")
        if d.genres:
            autowrap(label(info, ", ".join(d.genres[:6]), fg=T.FAINT, font=T.F_SMALL)).pack(fill="x", pady=(2, 0))
        if d.url:
            link(info, "Voir la fiche", d.url).pack(fill="x", pady=(8, 0))
        if d.overview:
            ov = d.overview if len(d.overview) < 900 else d.overview[:900] + "…"
            autowrap(label(b, ov, fg=T.TEXT, font=T.F_SMALL)).pack(fill="x", pady=(12, 0))

        if self.s.existing is None:
            return
        ex = Card(self.detail)
        ex.pack(fill="x", padx=(0, 14), pady=(12, 0))
        eb = ex.body
        n = len(self.s.existing)
        label(eb, f"Déjà sur C411 ({n})" if n else "Aucune release sur C411 pour cette fiche",
              font=T.F_H2).pack(fill="x")
        if n:
            autowrap(label(eb, "Vérifie que ta release occupe un emplacement libre ou en remplace un moins bon.",
                           fg=T.MUTED, font=T.F_SMALL)).pack(fill="x", pady=(2, 8))
        from ..videoinfo import resolution_tag
        res = resolution_tag(self.s.analysis.main) if self.s.profile.key == "video" else ""
        for r in self.s.existing:
            same = res and r.get("resolution", "").lower() == res.lower()
            row = tk.Frame(eb, bg=T.SURFACE2 if same else T.SURFACE)
            row.pack(fill="x", pady=1)
            autowrap(label(row, r.get("name", "?"), font=T.F_SMALL)).pack(fill="x", padx=6, pady=(4, 0))
            info = f"{fmt_size(r.get('size') or 0)} • {r.get('seeders', 0)} seeders" + (" • même résolution" if same else "")
            label(row, info, fg=T.WARNING if same else T.FAINT, font=T.F_SMALL).pack(fill="x", padx=6, pady=(0, 4))

    def ready(self):
        return self.s.ident is not None and bool(self.s.ident.title)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Nom et informations
# ═══════════════════════════════════════════════════════════════════════════

class NameStep(Step):
    title = "Nom et informations"

    def heading(self):
        p = self.s.profile
        return self.title, f"Modèle C411 : {p.template}" if p and p.template else ""

    def build(self):
        self.name_body = self.section(self.root, "Nom de la release",
                                      help="C'est le titre du torrent sur C411. Il suit le modèle de la catégorie ; "
                                           "il est vérifié pendant que tu tapes.")
        self.name = tk.StringVar()
        self.name_entry = ttk.Entry(self.name_body, textvariable=self.name, font=(T.F_MONO[0], 11))
        self.name_entry.pack(fill="x")
        self.name.trace_add("write", lambda *_: self.validate())
        self.issues = IssueList(self.name_body)
        self.issues.pack(fill="x", pady=(10, 0))
        row = tk.Frame(self.name_body, bg=T.SURFACE)
        row.pack(fill="x", pady=(10, 0))
        Btn(row, "Reconstruire depuis les champs", self.rebuild, small=True).pack(side="left")
        self.parts_box = self.section(self.root, "Composants",
                                      "Modifie un champ pour reconstruire le nom. Survole le « ? » pour l'aide.")
        self.details_card = Card(self.root)
        self.details_box = self.details_card.body
        self.disk_card = Card(self.root)
        b = self.disk_card.body
        label(b, "Fichiers sur le disque", font=T.F_H2).pack(fill="x")
        self.disk_lbl = autowrap(label(b, "", font=T.F_SMALL))
        self.disk_lbl.pack(fill="x", pady=(8, 0))
        self.do_rename = tk.BooleanVar(value=True)
        self.rename_chk = ttk.Checkbutton(b, text="Renommer automatiquement en continuant",
                                          variable=self.do_rename, style="Card.TCheckbutton")
        self.rename_chk.pack(anchor="w", pady=(8, 0))
        Tooltip(self.rename_chk, "Le titre, le NFO et les fichiers doivent porter le même tag de team (règle anti-detag). "
                                 "Ferme ton lecteur ou ton client torrent s'il utilise les fichiers.")
        self._loading = False
        self.vars = {}
        self.dvars = {}

    def on_enter(self):
        s = self.s
        ctx = s.ctx()
        if s.built_for != s.ident_key:
            s.parts = {p.key: p.value for p in s.profile.parts(ctx)}
            tag = self.app.cfg.get("team_tag")
            if tag and self.app.cfg.get("team_tag_auto") and (s.parts.get("team") or "").upper() in ("", "NOTAG") and "team" in s.parts:
                s.parts["team"] = tag              # source sans tag : ta release, ton tag d'équipe
            self._published_hints()
            s.details = {d.key: d.value for d in s.profile.details(s.ctx())}
            s.built_for = s.ident_key
            s.name = s.profile.build(s.parts)
        self._render_parts()
        self._render_details()
        self._loading = True
        self.name.set(s.name)
        self._loading = False
        self.validate()

    def _published_hints(self):
        """Correction : les éléments absents du nom du fichier (catégorie, langue…) sont repris du titre publié."""
        import dataclasses
        s = self.s
        pub = (getattr(s, "correction", None) or {}).get("published", "")
        if not pub or not s.src:
            return
        alt_src = dataclasses.replace(s.src, path=s.src.path.with_name(pub + ("" if s.src.is_dir else s.src.path.suffix)))
        try:
            alt = s.profile.parts(dataclasses.replace(s.ctx(), src=alt_src, parts={}))
        except Exception:
            return
        for p in alt:
            if p.value and not (s.parts.get(p.key) or "").strip():
                s.parts[p.key] = p.value

    def _render_parts(self):
        self.clear(self.parts_box)
        s = self.s
        self.vars = {}
        defs = s.profile.parts(s.ctx())
        cols = 4 if len(defs) > 3 else max(len(defs), 1)
        row = col = 0
        tag = self.app.cfg.get("team_tag")
        for p in defs:
            var = tk.StringVar(value=s.parts.get(p.key, p.value))
            self.vars[p.key] = var
            choices, hint = p.choices, p.hint
            if p.key == "team" and tag:            # liste : tag détecté, ton tag d'équipe, NOTAG
                choices = list(dict.fromkeys(x for x in (s.parts.get("team"), p.value, tag, "NOTAG") if x))
                hint = (hint + " " if hint else "") + f"Ton tag ({tag}) seulement pour tes propres releases : " \
                                                      "une release reprise garde le tag d'origine."
            f = Field(self.parts_box, p.label, var, values=choices, width=p.width, help=hint)
            span = min(cols, 2 if p.width >= 40 else 1) if cols > 1 else 1
            if p.width >= 60:
                span = cols
            if col + span > cols:
                row, col = row + 1, 0
            f.grid(row=row, column=col, columnspan=span, sticky="ew", padx=(0, 12), pady=(0, 10))
            col += span
            if col >= cols:
                row, col = row + 1, 0
            var.trace_add("write", lambda *_: None if self._loading else self.rebuild())
        for c in range(max(cols, 1)):
            self.parts_box.columnconfigure(c, weight=1, uniform="p")

    def _render_details(self):
        self.clear(self.details_box)
        s = self.s
        defs = s.profile.details(s.ctx())
        self.dvars = {}
        if not defs:
            self.details_card.pack_forget()
            return
        self.details_card.pack(fill="x", pady=(0, 14), before=self.disk_card if self.disk_card.winfo_ismapped() else None)
        label(self.details_box, "Informations complémentaires", font=T.F_H2).pack(fill="x")
        autowrap(label(self.details_box, "Reprises dans le NFO et la présentation.", fg=T.MUTED,
                       font=T.F_SMALL)).pack(fill="x", pady=(2, 10))
        grid = tk.Frame(self.details_box, bg=T.SURFACE)
        grid.pack(fill="x")
        grid.columnconfigure((0, 1), weight=1, uniform="d")
        row = col = 0
        for d in defs:
            var = tk.StringVar(value=s.details.get(d.key, d.value))
            self.dvars[d.key] = var
            f = Field(grid, d.label, var, values=d.choices, help=d.hint, multiline=d.multiline)
            if d.multiline:
                if col:
                    row, col = row + 1, 0
                f.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
                row += 1
            else:
                f.grid(row=row, column=col, sticky="ew", padx=(0, 12) if col == 0 else 0, pady=(0, 10))
                row, col = (row, 1) if col == 0 else (row + 1, 0)
            var.trace_add("write", lambda *_, k=d.key, v=var: self._detail_changed(k, v))

    def _detail_changed(self, key, var):
        self.s.details[key] = var.get()
        self.validate()

    def rebuild(self):
        s = self.s
        for k, v in self.vars.items():
            s.parts[k] = v.get().strip()
        self.name.set(s.profile.build(s.parts))

    def validate(self):
        s = self.s
        if not s.profile:
            return
        s.name = self.name.get().strip()
        c = s.profile.validate(s.name, s.ctx())
        self.issues.show(c.items() or [("ok", "Nom conforme.")])
        s.name_ok = c.ok
        self._render_disk()
        self.app.refresh_nav()

    def _render_disk(self):
        s = self.s
        if getattr(s, "correction", None):         # correction : les fichiers seedés ne bougent pas
            self.disk_card.pack_forget()
            return
        fixes = s.profile.tag_fixes(s.ctx()) if s.name_ok else []
        target = s.profile.rename_target(s.ctx())
        src = s.src
        self._fixes = fixes
        if fixes:
            if not self.disk_card.winfo_ismapped():
                self.disk_card.pack(fill="x", pady=(0, 14))
            team = s.name.rsplit("-", 1)[-1]
            names = "\n".join(f"{p.name}  →  {n}" for p, n in fixes[:6])
            more = f"\n… et {len(fixes) - 6} autres" if len(fixes) > 6 else ""
            self.disk_lbl.configure(
                text=f"Règle anti-detag : chaque fichier vidéo doit finir par le tag de team (-{team}). "
                     f"Le reste du nom d'origine est conservé.\n{names}{more}", fg=T.TEXT)
            self.rename_chk.configure(text=f"Ajouter -{team} à ces fichiers en continuant")
            self.rename_chk.state(["!disabled"])
        elif target is not None and src.path.name != target + ("" if src.is_dir else src.path.suffix):
            if not self.disk_card.winfo_ismapped():
                self.disk_card.pack(fill="x", pady=(0, 14))
            what = "Dossier" if src.is_dir else "Fichier"
            full = target + ("" if src.is_dir else src.path.suffix)
            self.disk_lbl.configure(text=f"{what} actuel : {src.path.name}\nNouveau nom : {full}", fg=T.TEXT)
            self.rename_chk.configure(text="Renommer automatiquement en continuant")
            self.rename_chk.state(["!disabled"])
        else:
            self.disk_card.pack_forget()

    def ready(self):
        return self.s.name_ok

    def leave(self, done):
        s = self.s
        for k, v in self.dvars.items():
            s.details[k] = v.get()
        if not self.do_rename.get() or getattr(s, "correction", None):
            done(True)
            return
        fixes = s.profile.tag_fixes(s.ctx())
        target = s.profile.rename_target(s.ctx())
        try:
            if fixes:
                for old_path, new_path in fs.rename_files(s.src, fixes):
                    s.profile.on_renamed(s.ctx(), old_path.name, new_path.name)
            elif target is not None and s.src.path.name != target + ("" if s.src.is_dir else s.src.path.suffix):
                old, old_path = s.src.path.name, s.src.path
                fs.rename(s.src, target)
                if not s.src.is_dir:
                    s.profile.on_renamed(s.ctx(), old, s.src.path.name)
                fs.remap_paths(s.analysis, old_path, s.src.path)
            else:
                done(True)
                return
        except OSError as e:
            messagebox.showerror("Renommage impossible", f"{e}\n\nFerme les programmes qui utilisent "
                                 "le fichier (lecteur, client torrent) puis réessaie.", parent=self)
            done(False)
            return
        self.app.invalidate_torrent()
        done(True)


# ═══════════════════════════════════════════════════════════════════════════
# 4. NFO
# ═══════════════════════════════════════════════════════════════════════════

class NfoStep(Step):
    title = "NFO"
    subtitle = "Fiche technique jointe au torrent, exigée par C411. Générée automatiquement, modifiable ou importable."
    scroll = False

    def build(self):
        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", pady=(0, 10))
        b1 = Btn(bar, "Régénérer", self.regenerate, small=True)
        b1.pack(side="left")
        Tooltip(b1, "Refait le NFO à partir de l'analyse et des informations saisies (tes modifications sont perdues).")
        b2 = Btn(bar, "Importer un .nfo…", self.import_nfo, small=True)
        b2.pack(side="left", padx=(8, 0))
        Tooltip(b2, "Pour une release existante, reprends son NFO d'origine (DUPEFR, page de la release…).")
        self.state_lbl = label(bar, "", fg=T.MUTED, font=T.F_SMALL)
        self.state_lbl.pack(side="right")
        self.editor = TextArea(self, height=30)
        self.editor.pack(fill="both", expand=True)
        self.editor.text.bind("<<Modified>>", self._modified)

    def _modified(self, _=None):
        if self.editor.text.edit_modified():
            self.s.nfo_edited = True
            self.s.nfo = self.editor.get()
            self.state_lbl.configure(text="Modifié à la main")
            self.editor.text.edit_modified(False)
            self.app.refresh_nav()

    def on_enter(self):
        s = self.s
        key = s.name + "|" + repr(sorted(s.details.items()))
        if not s.nfo or (not s.nfo_edited and s.nfo_for != key):
            self.regenerate()
        else:
            self.editor.set(s.nfo)
            self.state_lbl.configure(text="Modifié à la main" if s.nfo_edited else "Généré automatiquement")

    def regenerate(self):
        s = self.s
        s.nfo = s.profile.nfo(s.ctx())
        s.nfo_for, s.nfo_edited = s.name + "|" + repr(sorted(s.details.items())), False
        self.editor.set(s.nfo)
        self.state_lbl.configure(text="Généré automatiquement")
        self.app.refresh_nav()

    def import_nfo(self):
        p = filedialog.askopenfilename(parent=self, title="Importer un NFO",
                                       filetypes=[("NFO", "*.nfo *.txt"), ("Tous", "*.*")])
        if not p:
            return
        raw = Path(p).read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp437", errors="replace")
        self.s.nfo, self.s.nfo_edited = text, True
        self.editor.set(text)
        self.state_lbl.configure(text=f"Importé : {Path(p).name}")
        self.app.refresh_nav()

    def ready(self):
        return bool(self.s.nfo.strip())

    def leave(self, done):
        s = self.s
        s.nfo = self.editor.get()
        path = self.app.cfg.nfo_dir / f"{fs_safe(s.name)}.nfo"
        try:
            path.write_text(s.nfo, encoding="utf-8")
        except OSError as e:
            messagebox.showerror("NFO", f"Écriture impossible : {e}", parent=self)
            done(False)
            return
        s.nfo_path = path
        done(True)


def fs_safe(name: str) -> str:
    """Nom utilisable comme fichier sous Windows."""
    return "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip(" .") or "release"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Présentation
# ═══════════════════════════════════════════════════════════════════════════

class PresentStep(Step):
    title = "Présentation"
    subtitle = "Catégorie, options C411 et description BBCode, préremplies à partir de l'analyse et de la fiche."
    scroll = False

    def build(self):
        cols = tk.Frame(self, bg=T.BG)
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=2, uniform="c")
        cols.columnconfigure(1, weight=3, uniform="c")
        cols.rowconfigure(0, weight=1)
        left = ScrollFrame(cols)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.left = tk.Frame(left.inner, bg=T.BG)
        self.left.pack(fill="both", expand=True, padx=(0, 12))
        cat = self.section(self.left, "Catégorie", help="Catégorie et sous-catégorie C411 où la release sera rangée.")
        self.cat_lbl = label(cat, "", fg=T.MUTED, font=T.F_SMALL)
        self.cat_lbl.pack(fill="x")
        self.sub = tk.StringVar()
        self.sub_combo = ttk.Combobox(cat, textvariable=self.sub, state="readonly")
        self.sub_combo.pack(fill="x", pady=(4, 0))
        self.sub_combo.bind("<<ComboboxSelected>>", lambda e: self._sub_changed())
        self.opts_box = self.section(self.left, "Options", "* obligatoire",
                                     help="Champs de classement de C411, lus en direct depuis le site. "
                                          "Forge411 les préremplit ; vérifie-les.")
        note = self.section(self.left, "Note pour la modération",
                            "Facultatif, visible uniquement par la Team Pending.")
        self.note = TextArea(note, height=4, mono=False)
        self.note.pack(fill="x")
        right = tk.Frame(cols, bg=T.BG)
        right.grid(row=0, column=1, sticky="nsew")
        bar = tk.Frame(right, bg=T.BG)
        bar.pack(fill="x", pady=(0, 10))
        label(bar, "Description (BBCode)", font=T.F_H2).pack(side="left")
        help_icon(bar, "Texte de la page du torrent. [b]gras[/b], [img]image[/img], [quote]citation[/quote], "
                       "[spoiler=titre]…[/spoiler]. Modifiable librement.").pack(side="left", padx=(8, 0))
        Btn(bar, "Régénérer", self.regen_desc, small=True).pack(side="right")
        self.shots_btn = Btn(bar, "Ajouter des captures", self.add_screens, small=True)
        Tooltip(self.shots_btn, "Vidéo : extrait des images avec ffmpeg. Sinon : choisis des images sur le disque. "
                                "Elles sont envoyées sur un hébergeur accepté par C411 (XXX : postimg.cc, en "
                                "glisser-déposer) puis ajoutées à la description.")
        self.shots_btn.pack(side="right", padx=(0, 8))
        self.shots_lbl = label(bar, "", fg=T.MUTED, font=T.F_SMALL)
        self.shots_lbl.pack(side="right", padx=(0, 8))
        self.desc_issues = IssueList(right)
        self.desc_issues.pack(fill="x", pady=(0, 8))
        self.desc = TextArea(right, height=30, mono=False)
        self.desc.pack(fill="both", expand=True)
        self.desc.text.bind("<<Modified>>", self._desc_modified)
        self.types = []

    def _desc_modified(self, _=None):
        if self.desc.text.edit_modified():
            self.s.description = self.desc.get()
            self.s.desc_edited = True
            self.desc.text.edit_modified(False)
            self.render_desc_checks()
            self.app.refresh_nav()

    def regen_desc(self):
        s = self.s
        s.description = s.profile.description(s.ctx())
        s.desc_for, s.desc_edited = s.name + "|" + repr(sorted(s.details.items())), False
        self.desc.set(s.description)
        self.render_desc_checks()
        self.app.refresh_nav()

    def desc_check(self):
        """Images affichables et captures exigées par la catégorie (rules.py)."""
        from .. import rules
        s = self.s
        return rules.check_description(s.description, s.profile.shot_rule(s.ctx()), s.ident.image if s.ident else "")

    def render_desc_checks(self):
        c = self.desc_check()
        rule = self.s.profile.shot_rule(self.s.ctx())
        items = c.items()
        if not items and rule.minimum:
            items = [("ok", f"Captures d'écran : {rule.minimum} minimum, atteint.")]
        self.desc_issues.show(items, wrap=520)

    def on_enter(self):
        s = self.s
        key = s.name + "|" + repr(sorted(s.details.items()))
        if not s.description or (not s.desc_edited and s.desc_for != key):
            self.regen_desc()
        else:
            self.desc.set(s.description)
        self.note.set(s.note or self.app.cfg.get("uploader_note") or "")
        prof = s.profile
        self.cat_lbl.configure(text=f"{prof.icon}  {prof.label}")
        self.sub_combo.configure(values=list(prof.subcategories.values()))
        self.sub.set(prof.subcategories.get(s.sub_id, ""))
        self._load_options()
        self.render_desc_checks()

    def _main_video(self):
        """MediaFile de la vidéo principale (profil vidéo ou XXX vidéo), sinon None."""
        a = self.s.analysis
        va = getattr(a, "video", None) if self.s.profile.key == "xxx" else (a if self.s.profile.key == "video" else None)
        return va.main if va is not None and getattr(va, "main", None) is not None else None

    def add_screens(self):
        from .. import screens as SC
        s, cfg = self.s, self.app.cfg
        rule = s.profile.shot_rule(s.ctx())
        adult = s.profile.key == "xxx"
        count = max(int(cfg.get("screens_count") or 4), rule.minimum)
        mf = self._main_video()
        out = cfg.nfo_dir.parent / "captures" / fs_safe(s.name)
        if mf is not None:
            ffmpeg = self._ffmpeg()
            if not ffmpeg:
                return
            files = None
        else:
            picked = filedialog.askopenfilenames(parent=self, title=f"Captures ({count} conseillées)",
                                                 filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.gif"),
                                                            ("Tous", "*.*")])
            if not picked:
                return
            files = [Path(f) for f in picked]
        if adult:                         # Team Pending XXX : postimg.cc ou zupimages.net uniquement
            self._screens_manual(mf, files, out, count, rule.minimum)
            return
        host = cfg.get("screens_host") or "pixhost"
        what = f"Extraire {count} captures de {mf.path.name}" if mf is not None else f"Envoyer {len(files)} image(s)"
        if not messagebox.askyesno("Captures", f"{what} et les envoyer sur {SC.HOSTS[host]} ?\n\n"
                                               "Les images seront publiques chez l'hébergeur.", parent=self):
            return
        self.shots_btn.set_enabled(False)
        self.app.busy(True)

        def work():
            shots = self._extract(SC, mf, out, count) if mf is not None else [SC.Shot(f) for f in files]
            for i, sh in enumerate(shots, 1):
                UI.call(self.shots_lbl.configure, {"text": f"Envoi {i}/{len(shots)}…"})
                SC.upload(sh, host, False)
            return SC.bbcode(shots)

        def err(e):
            self.app.busy(False)
            self.shots_btn.set_enabled(True)
            self.shots_lbl.configure(text="", fg=T.MUTED)
            messagebox.showerror("Captures", str(e), parent=self)
        run_bg(work, self._append_shots, err)

    def _ffmpeg(self):
        from .. import screens as SC
        ffmpeg = SC.find_ffmpeg(self.app.cfg.get("ffmpeg_path"))
        if ffmpeg:
            return ffmpeg
        from .. import ffmpeg_setup as FS
        if not FS.supported():
            messagebox.showwarning("Captures", "ffmpeg est introuvable : installe-le avec le gestionnaire de "
                                               "paquets de ton système ou indique son chemin dans les Paramètres.",
                                   parent=self)
            return ""
        if not messagebox.askyesno("Captures", "Les captures demandent ffmpeg, absent de ce PC.\n\n"
                                               "L'installer maintenant (environ 75 Mo, version officielle vérifiée) ?",
                                   parent=self):
            return ""
        from .ffmpeg_view import FfmpegDialog
        return FfmpegDialog.ask(self) or ""

    def _extract(self, SC, mf, out, count):
        return SC.extract(self._ffmpeg_path, mf.path, mf.duration_ms, out, count,
                          lambda i, n: UI.call(self.shots_lbl.configure, {"text": f"Capture {i}/{n}…"}))

    @property
    def _ffmpeg_path(self):
        from .. import screens as SC
        return SC.find_ffmpeg(self.app.cfg.get("ffmpeg_path"))

    def _append_shots(self, block):
        s = self.s
        self.app.busy(False)
        self.shots_btn.set_enabled(True)
        if not block:
            self.shots_lbl.configure(text="", fg=T.MUTED)
            return
        self.shots_lbl.configure(text="✓ Captures ajoutées", fg=T.SUCCESS)
        text = self.desc.get().rstrip() + "\n" + block
        self.desc.set(text)
        s.description, s.desc_edited = text, True
        self.render_desc_checks()
        self.app.refresh_nav()

    def _screens_manual(self, mf, files, out, count, minimum):
        """XXX : captures déposées à la main sur postimg.cc (pas d'envoi automatique), liens collés ensuite."""
        from .. import screens as SC
        from .dialogs import ShotLinksDialog

        def ready(paths):
            self.app.busy(False)
            self.shots_btn.set_enabled(True)
            self.shots_lbl.configure(text="", fg=T.MUTED)
            folder = paths[0].parent if paths else out
            SC.open_folder(folder)
            webbrowser.open(SC.POSTIMG_URL)
            urls = ShotLinksDialog.ask(self, folder, len(paths), minimum)
            if urls:
                self._append_shots(SC.bbcode([SC.Shot(Path(""), url=u, thumb=u, page=u) for u in urls]))

        if mf is None:
            ready(files)
            return
        self.shots_btn.set_enabled(False)
        self.app.busy(True)

        def err(e):
            self.app.busy(False)
            self.shots_btn.set_enabled(True)
            self.shots_lbl.configure(text="", fg=T.MUTED)
            messagebox.showerror("Captures", str(e), parent=self)
        run_bg(lambda: [sh.path for sh in self._extract(SC, mf, out, count)], ready, err)

    def _sub_changed(self):
        s = self.s
        new = next((k for k, v in s.profile.subcategories.items() if v == self.sub.get()), s.sub_id)
        if new != s.sub_id:
            s.sub_id = new
            s.options, s.options_for = {}, 0
            self._load_options()

    def _load_options(self):
        try:
            api = self.app.c411()
        except C411Error as e:
            self._opts_message(str(e), T.ERROR)
            return
        self._opts_message("Chargement des options…", T.MUTED)
        s = self.s

        def ok(types):
            self.types = types
            if s.options_for != s.sub_id:
                s.options = s.profile.auto_options(types, s.ctx())
                s.options_for = s.sub_id
            self.render_options()
        run_bg(lambda: api.options(s.sub_id), ok, lambda e: self._opts_message(str(e), T.ERROR))

    def _opts_message(self, msg, color):
        self.clear(self.opts_box)
        autowrap(label(self.opts_box, msg, fg=color)).pack(fill="x")
        self.app.refresh_nav()

    def render_options(self):
        box = self.opts_box
        self.clear(box)
        if not self.types:
            label(box, "Aucune option pour cette catégorie.", fg=T.MUTED).pack(fill="x")
        for t in self.types:
            row = tk.Frame(box, bg=T.SURFACE)
            row.pack(fill="x", pady=(0, 10))
            missing = t.required and not self.s.options.get(t.id)
            label(row, t.name + (" *" if t.required else ""), fg=T.ERROR if missing else T.MUTED,
                  font=T.F_SMALL_B).pack(fill="x")
            cur = self.s.options.get(t.id)
            if t.multiple:
                ids = cur or []
                names = [v["value"] for v in t.values if v["id"] in ids]
                line = tk.Frame(row, bg=T.SURFACE)
                line.pack(fill="x", pady=(3, 0))
                autowrap(label(line, ", ".join(names) or "Aucun", fg=T.TEXT if names else T.FAINT)).pack(
                    side="left", fill="x", expand=True)
                Btn(line, "Choisir…", lambda tt=t: self.pick_multi(tt), small=True).pack(side="right")
            else:
                var = tk.StringVar(value=next((v["value"] for v in t.values if v["id"] == cur), ""))
                cb = ttk.Combobox(row, textvariable=var, state="readonly",
                                  values=[""] + [v["value"] for v in t.values])
                cb.pack(fill="x", pady=(3, 0))
                cb.bind("<<ComboboxSelected>>", lambda e, tt=t, vv=var: self._set_single(tt, vv.get()))
        self.app.refresh_nav()

    def _set_single(self, t, value):
        vid = next((v["id"] for v in t.values if v["value"] == value), None)
        if vid:
            self.s.options[t.id] = vid
        else:
            self.s.options.pop(t.id, None)
        self.render_options()

    def pick_multi(self, t):
        from .dialogs import MultiSelectDialog
        chosen = MultiSelectDialog.ask(self, t.name, t.values, self.s.options.get(t.id) or [])
        if chosen is not None:
            if chosen:
                self.s.options[t.id] = chosen
            else:
                self.s.options.pop(t.id, None)
            self.render_options()

    def ready(self):
        s = self.s
        if not s.description.strip() or not s.sub_id or s.options_for != s.sub_id:
            return False
        if self.desc_check().errors:
            return False
        return all(s.options.get(t.id) for t in self.types if t.required)

    def leave(self, done):
        self.s.description = self.desc.get()
        self.s.note = self.note.get().strip()
        done(True)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Publication
# ═══════════════════════════════════════════════════════════════════════════

class PublishStep(Step):
    title = "Publication"
    subtitle = "Le torrent est créé, puis envoyé sur C411 en brouillon (à relire sur le site) ou publié directement."

    def build(self):
        self.result_box = tk.Frame(self.root, bg=T.BG)
        self.result_box.pack(fill="x")
        self.recap = self.section(self.root, "Récapitulatif")
        tor = self.section(self.root, "Torrent", "Privé, source C411, taille de pièce selon le guide d'upload.",
                           help="Le champ source = C411 est celui que C411 ajoute à la publication : le torrent que "
                                "tu seedes a donc exactement la même empreinte que celui publié.")
        self.tor_lbl = autowrap(label(tor, ""))
        self.tor_lbl.pack(fill="x")
        self.tor_bar = ttk.Progressbar(tor, mode="determinate", maximum=100)
        self.tor_bar.pack(fill="x", pady=(8, 0))
        row = tk.Frame(tor, bg=T.SURFACE)
        row.pack(fill="x", pady=(10, 0))
        self.tor_btn = Btn(row, "Créer le torrent", self.make_torrent, small=True)
        self.tor_btn.pack(side="left")
        self.cancel_btn = Btn(row, "Annuler", self.cancel_torrent, kind="ghost", small=True)
        seed = self.section(self.root, "Seed", "C411 refuse un torrent qui n'est pas déjà seedé.",
                            help="Avec un client configuré (Paramètres › Client torrent), Forge411 y ajoute le "
                                 "torrent, avec le dossier de la source comme emplacement, et suit la vérification.")
        self.seed_lbl = autowrap(label(seed, ""))
        self.seed_lbl.pack(fill="x")
        self.seed_bar = ttk.Progressbar(seed, mode="determinate", maximum=100)
        row = tk.Frame(seed, bg=T.SURFACE)
        row.pack(fill="x", pady=(10, 0))
        self.seed_btn = Btn(row, "Ajouter au client torrent", self.add_to_client, small=True)
        self.seed_btn.pack(side="left")
        self.seed_confirm = tk.BooleanVar(value=False)
        self.seed_check = ttk.Checkbutton(seed, text="Mon client torrent seed ce torrent (statut « En partage » / "
                                                     "Seeding, données vérifiées à 100 %)",
                                          variable=self.seed_confirm, command=self.render_checks,
                                          style="Card.TCheckbutton")
        self._seed_cancel = None
        self.cat_box = self.section(self.root, "Déjà sur C411", "Doublons et slots, d'après le catalogue du site.",
                                    help="Recherche des releases existantes (API Torznab). L'attribution d'un slot "
                                         "est décidée par C411 : l'avis affiché ici est une estimation.")
        self.cat_list = tk.Frame(self.cat_box, bg=T.SURFACE)
        self.cat_list.pack(fill="x")
        self.just_box = tk.Frame(self.cat_box, bg=T.SURFACE)
        label(self.just_box, "Justification hors slot", font=T.F_SMALL_B, fg=T.MUTED).pack(fill="x", pady=(10, 0))
        autowrap(label(self.just_box, "Obligatoire (30 caractères minimum) quand aucun slot ne correspond : ce que "
                                      "ta version apporte que les versions en place n'ont pas. Visible par la Team Pending.",
                       fg=T.FAINT, font=T.F_SMALL)).pack(fill="x")
        self.just = TextArea(self.just_box, height=3, mono=False)
        self.just.pack(fill="x", pady=(4, 0))
        self.just.text.bind("<KeyRelease>", lambda e: self._just_changed())
        self.just_count = label(self.just_box, "", fg=T.FAINT, font=T.F_SMALL)
        self.just_count.pack(anchor="e")
        self.fix_box = self.section(self.root, "Correction pour la Team Pending",
                                    "Le torrent et le seed restent les mêmes : seuls le titre, la description et le "
                                    "NFO changent sur la page du torrent.",
                                    help="L'API C411 ne permet pas de modifier un torrent : copie chaque élément, "
                                         "colle-le dans « Modifier » sur la page du torrent, enregistre, puis clique "
                                         "« Soumettre pour re-examen ».")
        self.fix_lbl = autowrap(label(self.fix_box, ""))
        self.fix_lbl.pack(fill="x")
        row = tk.Frame(self.fix_box, bg=T.SURFACE)
        row.pack(fill="x", pady=(10, 0))
        for text, cmd in (("Copier le titre", lambda: self._copy(self.s.name, "Titre")),
                          ("Copier la description", lambda: self._copy(self.s.description, "Description")),
                          ("Copier le NFO", lambda: self._copy(self.s.nfo, "NFO")),
                          ("Ouvrir la page du torrent", self._open_torrent_page)):
            Btn(row, text, cmd, small=True).pack(side="left", padx=(0, 8))
        self.fix_msg = label(self.fix_box, "", fg=T.MUTED, font=T.F_SMALL)
        self.fix_msg.pack(fill="x", pady=(8, 0))
        Btn(self.fix_box, "J'ai soumis la correction", self._correction_done, kind="primary", small=True).pack(
            anchor="w", pady=(10, 0))
        self.fix_box.master.master.pack_forget()
        self.checks_box = self.section(self.root, "Vérifications")
        self.checks = IssueList(self.checks_box)
        self.checks.pack(fill="x")
        self.publish_btn = self.draft_btn = None
        self._cancel = None

    def footer(self, bar):
        self.draft_btn = Btn(bar, "Enregistrer en brouillon", self.save_draft)
        self.draft_btn.pack(side="left", padx=(0, 8))
        Tooltip(self.draft_btn, "Envoie tout sur C411 sans publier : tu relis et publies depuis la page d'upload du site.")
        self.publish_btn = Btn(bar, "Publier sur C411", self.publish, kind="primary")
        self.publish_btn.pack(side="left")
        Tooltip(self.publish_btn, "Publie directement. Ton client torrent doit déjà seeder le torrent.")
        self.render_checks()

    def _copy(self, text, what):
        self.clipboard_clear()
        self.clipboard_append(text or "")
        self.fix_msg.configure(text=f"✓ {what} copié(e) dans le presse-papiers.", fg=T.SUCCESS)

    def _open_torrent_page(self):
        from .. import correction as FIX
        url = (self.s.correction or {}).get("url") or FIX.torrent_page(self.s.infohash)
        if url:
            webbrowser.open(url)

    def _correction_done(self):
        from .. import session as SESS
        from ..config import UPLOADS_DIR
        s = self.s
        add_history({"name": s.name, "type": s.profile.label, "action": "Correction",
                     "url": (s.correction or {}).get("url", ""), "torrent": str(s.torrent), "infohash": s.infohash,
                     "snapshot": str(UPLOADS_DIR / f"{s.infohash}.pkl")})
        fix, s.correction = s.correction, None
        SESS.snapshot(s, UPLOADS_DIR / f"{s.infohash}.pkl")
        s.correction = fix
        self.fix_msg.configure(text="✓ Correction enregistrée dans l'historique. Surveille la discussion de "
                                    "modération sur la page du torrent.", fg=T.SUCCESS)

    def render_correction(self):
        s = self.s
        fix = getattr(s, "correction", None)
        box = self.fix_box.master.master            # carte de la section
        if not fix:
            box.pack_forget()
            if self.publish_btn is not None and self.publish_btn.winfo_exists():
                self.publish_btn.pack(side="left")
                self.draft_btn.pack(side="left", padx=(0, 8), before=self.publish_btn)
            return
        if not box.winfo_ismapped():
            box.pack(fill="x", pady=(0, 14), before=self.recap.master.master)   # action principale : en tête
        self.fix_lbl.configure(text=f"Titre corrigé : {s.name}\nPage : {fix.get('url') or '?'}\n\n"
                                    "1. Ouvre la page du torrent et clique « Modifier ».\n"
                                    "2. Colle le titre, la description et, s'il a changé, le NFO.\n"
                                    "3. Enregistre, vérifie que ton client seed toujours, puis « Soumettre pour re-examen ».")
        if self.publish_btn is not None and self.publish_btn.winfo_exists():
            self.publish_btn.pack_forget()
            self.draft_btn.pack_forget()
        self.tor_btn.pack_forget()
        if s.torrent_ready:
            self.tor_bar.configure(value=100)
            self.tor_lbl.configure(text=f"✓  Torrent publié conservé : {s.torrent.name}\nInfo-hash : {s.infohash}",
                                   fg=T.SUCCESS)
        else:
            self.tor_lbl.configure(text="Torrent d'origine introuvable sur ce PC : le seed ne peut pas être vérifié "
                                        "ici. Vérifie-le dans ton client.", fg=T.WARNING)

    def on_enter(self):
        self.render_correction()
        self.render_recap()
        self.render_checks()
        s = self.s
        if getattr(s, "correction", None) and CL.make(self.app.cfg) and s.torrent_ready and not s.seeding \
                and self._seed_cancel is None:
            self.after(300, self.add_to_client)     # correction : le seed est vérifié dans le client
        self.render_result()
        self.just.set(self.s.slot_justification)
        self._just_changed()
        self.render_seed()
        self.load_catalog()
        if not self.s.torrent_ready and self._cancel is None and self.s.result is None \
                and not getattr(self.s, "correction", None):
            self.make_torrent()

    def render_recap(self):
        self.clear(self.recap)
        s = self.s
        wide = s.ident and s.ident.provider == "rawg"
        w, h = (142, 80) if wide else (80, 120)
        img = tk.Label(self.recap, bg=T.SURFACE, image=Images.placeholder(w, h))
        img.pack(side="left", anchor="n")
        if s.ident and s.ident.image:
            Images.load(s.ident.image, w, h, lambda p: img.winfo_exists() and img.configure(image=p))
        info = tk.Frame(self.recap, bg=T.SURFACE)
        info.pack(side="left", fill="both", expand=True, padx=(14, 0))
        autowrap(label(info, s.name, font=(T.F_MONO[0], 11))).pack(fill="x")
        facts = [f"{s.profile.label} › {s.profile.subcategories.get(s.sub_id, '?')}", fmt_size(s.src.total_size),
                 f"{len(s.src.files)} fichier{'s' if len(s.src.files) > 1 else ''}"]
        label(info, " • ".join(facts), fg=T.MUTED).pack(fill="x", pady=(6, 0))
        if s.ident and s.ident.title:
            label(info, f"{s.ident.title}" + (f" ({s.ident.year})" if s.ident.year else ""),
                  fg=T.FAINT, font=T.F_SMALL).pack(fill="x", pady=(2, 0))

    def render_checks(self):
        s = self.s
        if not s.src:
            return
        items = [("ok", "Nom conforme") if s.name_ok else ("error", "Nom non conforme")]
        missing = s.profile.tag_fixes(s.ctx())
        if missing:
            items.append(("warning", f"{len(missing)} fichier(s) sans le tag de team (règle anti-detag) : "
                                     "retourne à l'étape Nom pour l'ajouter."))
        if not (s.ident and s.ident.image) and "[img]" not in s.description.lower():
            items.append(("warning", "Aucune image dans la présentation : C411 en exige une "
                                     "(ajoute une URL d'image dans la fiche ou la description)."))
        from .. import rules
        dc = rules.check_description(s.description, s.profile.shot_rule(s.ctx()), s.ident.image if s.ident else "")
        items += dc.items()
        items.append(("ok", "NFO enregistré") if s.nfo_path else ("error", "NFO manquant"))
        items.append(("ok", "Description prête") if s.description.strip() else ("error", "Description vide"))
        seed = fs.seed_location_issue(s.src, self.app.cfg.get("seed_dir"))
        if seed:
            items.append(("warning", seed))
        elif self.app.cfg.get("seed_dir"):
            items.append(("ok", "Données dans le dossier de seed"))
        if not self.app.cfg.get("tracker_url"):
            items.append(("error", "URL d'annonce manquante (Paramètres)."))
        items.append(("ok", "Torrent prêt") if s.torrent_ready else ("info", "Torrent pas encore créé"))
        if CL.make(self.app.cfg):
            items.append(("ok", "En seed dans le client") if s.seeding else
                         ("error", "Pas encore en seed dans le client : C411 refuse un torrent sans seed."))
        else:
            items.append(("ok", "Seed confirmé par toi") if self.seed_confirm.get() else
                         ("error", "Confirme que ton client seed ce torrent (case de la section Seed)."))
        v = s.catalog
        if v is not None and v.exact:
            items.append(("error", "Une release du même nom existe déjà sur C411 (doublon)."))
        elif v is not None and v.needs_justification:
            j = len(s.slot_justification.strip())
            items.append(("ok", "Justification hors slot rédigée") if j >= 30 else
                         ("warning", "Slot probablement occupé : rédige une justification hors slot (30 caractères min.)."))
        self.checks.show(items)
        if self.publish_btn is None or not self.publish_btn.winfo_exists():
            return
        can = s.torrent_ready and s.name_ok and bool(s.nfo_path) and s.result is None and self._cancel is None
        seeded = s.seeding if CL.make(self.app.cfg) else self.seed_confirm.get()
        self.publish_btn.set_enabled(can and seeded and not dc.errors)
        self.draft_btn.set_enabled(can)

    # ── Torrent ───────────────────────────────────────────────────────────
    def make_torrent(self):
        s = self.s
        if getattr(s, "correction", None):
            self.tor_lbl.configure(text="Correction : le torrent publié ne change pas (un nouveau torrent aurait un "
                                        "autre info-hash et ne serait pas celui que C411 attend).", fg=T.MUTED)
            return
        announce = self.app.cfg.get("tracker_url")
        if not announce:
            self.tor_lbl.configure(text="Renseigne ton URL d'annonce (passkey) dans les Paramètres.", fg=T.ERROR)
            return
        out = self.app.cfg.torrents_dir / f"{fs_safe(s.name)}.torrent"
        cancel = threading.Event()
        self._cancel = cancel
        self.tor_btn.pack_forget()
        self.cancel_btn.pack(side="left")
        self.tor_bar.configure(value=0)
        self.tor_lbl.configure(text=f"Hachage de {fmt_size(s.src.total_size)}…", fg=T.TEXT)
        self.app.busy(True)
        self.render_checks()
        src_path = s.src.path

        def ok(infohash):
            self._done_torrent()
            s.torrent, s.torrent_for, s.infohash = out, s.torrent_key, infohash
            self.tor_bar.configure(value=100)
            self.tor_lbl.configure(text=f"✓  {out.name}\nDossier : {out.parent}\nInfo-hash : {infohash}", fg=T.SUCCESS)
            s.seed, s.seeding = "", False
            self.seed_confirm.set(False)
            self.render_checks()
            self.render_seed()
            if CL.make(self.app.cfg) and self.app.cfg.get("client_auto"):
                self.add_to_client()

        def err(e):
            self._done_torrent()
            self.tor_bar.configure(value=0)
            self.tor_lbl.configure(text="Création annulée." if isinstance(e, Cancelled) else f"Erreur : {e}",
                                   fg=T.MUTED if isinstance(e, Cancelled) else T.ERROR)
            self.render_checks()
        run_bg(lambda: create_torrent(src_path, announce, out, lambda f: UI.call(self._progress, f), cancel), ok, err)

    def _progress(self, f):
        total = self.s.src.total_size
        self.tor_bar.configure(value=f * 100)
        self.tor_lbl.configure(text=f"Hachage… {f * 100:.0f} %  ({fmt_size(int(total * f))} / {fmt_size(total)})")

    def _done_torrent(self):
        self._cancel = None
        self.cancel_btn.pack_forget()
        self.tor_btn.set_text("Recréer le torrent")
        self.tor_btn.pack(side="left")
        self.app.busy(False)

    def cancel_torrent(self):
        if self._cancel:
            self._cancel.set()

    # ── Envoi ─────────────────────────────────────────────────────────────
    def _payload(self):
        s = self.s
        meta_key, meta = s.profile.meta(s.ctx())
        mi = s.analysis.main.text if s.profile.key == "video" and s.analysis.main else ""
        return dict(title=s.name, description=s.description, category_id=s.profile.category_id,
                    subcategory_id=s.sub_id, options=options_payload(s.options), torrent=s.torrent,
                    nfo=s.nfo_path, meta_key=meta_key, meta=meta, note=s.note, mediainfo=mi,
                    slot_justification=s.slot_justification.strip())

    def save_draft(self):
        self._send("Brouillon", lambda api: api.save_draft(**self._payload()))

    def publish(self):
        s = self.s
        j = len(s.slot_justification.strip())
        if 0 < j < 30:
            messagebox.showwarning("Justification hors slot", "La justification doit faire au moins 30 caractères.",
                                   parent=self)
            return
        if CL.make(self.app.cfg) and not s.seeding:
            messagebox.showwarning("Publier", "Le torrent n'est pas en seed dans ton client : C411 le refuserait.\n\n"
                                              "Ajoute-le au client (section Seed) et attends « En seed ».", parent=self)
            return
        if not messagebox.askyesno("Publier", f"Publier maintenant sur C411 ?\n\n{self.s.name}", parent=self):
            return
        self._send("Publication", lambda api: api.upload(**self._payload()))

    def _send(self, what, fn):
        try:
            api = self.app.c411()
        except C411Error as e:
            self.render_result(None, str(e))
            return
        self.publish_btn.set_enabled(False)
        self.draft_btn.set_enabled(False)
        self.app.busy(True)

        def ok(res):
            self.app.busy(False)
            if res.ok:
                from .. import session as SESS
                from ..config import UPLOADS_DIR
                snap = UPLOADS_DIR / f"{self.s.infohash}.pkl"
                SESS.snapshot(self.s, snap)
                self.s.result = res
                add_history({"name": self.s.name, "type": self.s.profile.label, "action": what, "url": res.url,
                             "torrent": str(self.s.torrent), "infohash": self.s.infohash, "snapshot": str(snap)})
            self.render_result(res)
            self.render_checks()

        def err(e):
            self.app.busy(False)
            self.render_result(None, str(e))
            self.render_checks()
        run_bg(lambda: fn(api), ok, err)

    # ── Seed (client torrent) ─────────────────────────────────────────────
    def render_seed(self):
        s = self.s
        client = CL.make(self.app.cfg)
        if not client:
            self.seed_lbl.configure(text="Aucun client configuré : ajoute toi-même le torrent à ton client, avec le "
                                         "dossier de la source comme emplacement (ou configure-le dans les Paramètres), "
                                         "puis coche la case une fois le seed démarré.",
                                    fg=T.MUTED)
            self.seed_btn.pack_forget()
            self.seed_bar.pack_forget()
            if not self.seed_check.winfo_ismapped():
                self.seed_check.pack(fill="x", pady=(10, 0))
            return
        self.seed_check.pack_forget()
        if not self.seed_btn.winfo_ismapped():
            self.seed_btn.pack(side="left")
        self.seed_btn.set_enabled(s.torrent_ready and self._seed_cancel is None and not s.seeding)
        if s.seeding:
            self.seed_lbl.configure(text=f"✓  En seed dans {client.name}.", fg=T.SUCCESS)
        elif s.seed:
            self.seed_lbl.configure(text=s.seed, fg=T.ERROR if s.seed.startswith("✕") else T.TEXT)
        else:
            self.seed_lbl.configure(text=f"{client.name} : le torrent sera ajouté avec "
                                         f"{CL.save_path(self.app.cfg, s.src.path.parent)} comme emplacement des données.",
                                    fg=T.MUTED)

    def add_to_client(self):
        s = self.s
        client = CL.make(self.app.cfg)
        if not client or not s.torrent_ready or self._seed_cancel is not None:
            return
        cancel = threading.Event()
        self._seed_cancel = cancel
        s.seed = f"Ajout à {client.name}…"
        self.seed_bar.configure(value=0)
        self.seed_bar.pack(fill="x", pady=(8, 0), before=self.seed_btn.master)
        self.render_seed()
        torrent, save, ih = s.torrent, CL.save_path(self.app.cfg, s.src.path.parent), s.infohash

        def on_status(st):
            UI.call(self._seed_status, st)

        def work():
            try:
                client.add(torrent, save, ih)
            except CL.ClientError as e:
                if "déjà présent" not in str(e):
                    raise
            return CL.wait_seeding(client, ih, on_status, cancel)

        def ok(st):
            self._seed_cancel = None
            s.seeding, s.seed = True, ""
            self.seed_bar.configure(value=100)
            self.render_seed()
            self.render_checks()

        def err(e):
            self._seed_cancel = None
            s.seed = f"✕  {e}"
            self.seed_bar.pack_forget()
            self.render_seed()
            self.render_checks()
        run_bg(work, ok, err)

    def _seed_status(self, st):
        if not self.winfo_exists():
            return
        self.s.seed = f"{st.state} : {st.progress * 100:.0f} %"
        self.seed_bar.configure(value=st.progress * 100)
        self.render_seed()

    # ── Catalogue C411 (doublons, slots) ──────────────────────────────────
    def load_catalog(self):
        s = self.s
        key = s.name
        if s.catalog_for == key and s.catalog is not None:
            self.render_catalog()
            return
        try:
            api = self.app.c411()
        except C411Error as e:
            self._cat_message(str(e), T.ERROR)
            return
        self._cat_message("Recherche sur C411…", T.MUTED)
        ident = s.ident
        tmdb = int(ident.id) if ident and ident.provider == "tmdb" and str(ident.id).isdigit() else 0
        kind = ident.kind if tmdb else ""
        query = (ident.title if ident and ident.title else s.name.split(".")[0]) + \
            (f" {ident.year}" if ident and ident.year and not tmdb else "")

        def work():
            rel = api.search(tmdb_id=tmdb, kind=kind) if tmdb else api.search(query)
            return CAT.compare(s.name, rel)

        def ok(v):
            s.catalog, s.catalog_for = v, key
            if self.winfo_exists():
                self.render_catalog()
                self.render_checks()
        run_bg(work, ok, lambda e: self._cat_message(f"Recherche impossible : {e}", T.WARNING))

    def _cat_message(self, text, color):
        self.clear(self.cat_list)
        autowrap(label(self.cat_list, text, fg=color)).pack(fill="x")

    def render_catalog(self):
        s, v = self.s, self.s.catalog
        self.clear(self.cat_list)
        video = s.profile.category_id == 1
        if video:
            self.just_box.pack(fill="x")
        else:
            self.just_box.pack_forget()
        if v is None:
            return
        if not (v.exact or v.same_slot or v.others):
            label(self.cat_list, "✓  Aucune release similaire trouvée.", fg=T.SUCCESS).pack(fill="x")
            return
        if v.family and video:
            label(self.cat_list, f"Profil estimé de ta release : {CAT.FAMILY_LABELS.get(v.family, v.family)}",
                  fg=T.MUTED, font=T.F_SMALL).pack(fill="x", pady=(0, 6))
        rows = [("error", r, "même nom") for r in v.exact] + [("warning", r, "même slot probable") for r in v.same_slot] + \
               [("muted", r, "") for r in v.others[:8]]
        colors = {"error": T.ERROR, "warning": T.WARNING, "muted": T.MUTED}
        for tone, r, why in rows[:14]:
            line = tk.Frame(self.cat_list, bg=T.SURFACE, cursor="hand2")
            line.pack(fill="x", pady=1)
            name = label(line, r.name, fg=T.TEXT if tone != "muted" else T.MUTED, font=T.F_SMALL)
            name.pack(side="left", fill="x", expand=True)
            meta = " · ".join(x for x in (why, r.slot, f"{r.seeders} seeds", fmt_size(r.size)) if x)
            label(line, meta, fg=colors[tone], font=T.F_SMALL).pack(side="right")
            for w in (line, name):
                w.bind("<Button-1>", lambda e, u=r.url: u and webbrowser.open(u))

    def _just_changed(self):
        self.s.slot_justification = self.just.get()
        n = len(self.s.slot_justification.strip())
        self.just_count.configure(text=f"{n}/30" if n < 30 else f"{n} caractères",
                                  fg=T.WARNING if 0 < n < 30 else T.FAINT)
        self.render_checks()

    def render_result(self, res=None, error: str = ""):
        self.clear(self.result_box)
        res = res or self.s.result
        if not res and not error:
            return
        ok = res is not None and res.ok
        card = Card(self.result_box, bg=T.SUCCESS_SOFT if ok else T.ERROR_SOFT)
        card.pack(fill="x", pady=(0, 14))
        b = card.body
        msg = res.message if ok else (error or (res.message if res else ""))
        autowrap(label(b, ("✓  " if ok else "✕  ") + msg, fg=T.SUCCESS if ok else T.ERROR, font=T.F_H2)).pack(fill="x")
        if ok:
            row = tk.Frame(b, bg=b.cget("bg"))
            row.pack(fill="x", pady=(10, 0))
            if res.url:
                draft = res.url.rstrip("/").endswith("/upload")
                Btn(row, "Ouvrir la page d'upload ↗" if draft else "Ouvrir sur C411 ↗", lambda: webbrowser.open(res.url),
                    kind="success", small=True).pack(side="left")
            Btn(row, "Nouvel upload", self.app.restart, small=True).pack(side="left", padx=(8, 0))
            if hasattr(os, "startfile"):
                Btn(row, "Ouvrir le dossier des torrents", lambda: os.startfile(self.app.cfg.torrents_dir),
                    kind="ghost", small=True).pack(side="left", padx=(8, 0))
        self.sf.to_top()

    def ready(self):
        return False
