"""Fenêtre principale : barre latérale des étapes, contenu, navigation."""

import logging
import os
import subprocess
import sys
import time
import tkinter as tk
import traceback
import webbrowser
from tkinter import messagebox

from .. import APP_NAME, AUTHOR, REPO_URL, __version__, updater
from .. import profile as P
from ..api import BASE, C411
from .. import session as SESS
from ..config import PROFILE_HISTORY_PATH, SESSION_PATH, Config, config_dir, migrate_legacy
from ..lookup import LookupFailed
from ..session import Session
from . import theme as T
from .dialogs import HistoryDialog, SettingsDialog, UpdateDialog
from .steps import IdentifyStep, NameStep, NfoStep, PresentStep, PublishStep, SourceStep
from .tour import Tour
from .widgets import UI, Btn, Tooltip, label, run_bg

STEPS = [SourceStep, IdentifyStep, NameStep, NfoStep, PresentStep, PublishStep]
STEP_HELP = ["Choisis le fichier ou le dossier ; le type de contenu est reconnu.",
             "Retrouve la fiche en ligne (film, album, livre, jeu) ou saisis le titre.",
             "Nom conforme aux règles C411 et informations complémentaires.",
             "Fiche technique jointe au torrent, générée automatiquement.",
             "Catégorie, options et description de la page C411.",
             "Création du torrent, puis brouillon ou publication."]


class App(tk.Tk):
    def __init__(self):
        T.enable_dpi_awareness()
        super().__init__()
        migrate_legacy()
        self.cfg = Config()
        self.session = Session()
        self._clients = {}
        self._keys = None
        self._busy = 0
        self.profile_cache = None        # (Profile, horodatage) : profil C411 lu en dernier
        self.title(APP_NAME)
        T.apply(self)
        self._set_icon()
        self.minsize(1080, 720)
        self.geometry(self.cfg.get("window_geometry") or "1320x860")
        self.report_callback_exception = self._on_error
        UI.install(self)

        self._build()
        self.steps = [cls(self) for cls in STEPS]
        self.current = 0
        self.show(0)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(50, lambda: T.dark_title_bar(self))
        self.after(300, self._first_run)

    def _set_icon(self):
        try:
            from importlib.resources import files
            ico = files("forge411") / "assets" / "forge411.png"
            if ico.is_file():
                self._icon = tk.PhotoImage(file=str(ico))
                self.iconphoto(True, self._icon)
        except Exception:
            pass

    def _side_item(self, parent, icon: str, text: str, command) -> tk.Frame:
        """Entrée du menu latéral : icône dans une colonne fixe, libellé aligné, survol sur toute la ligne."""
        row = tk.Frame(parent, bg=T.SIDEBAR, cursor="hand2")
        ic = tk.Label(row, text=icon, bg=T.SIDEBAR, fg=T.FAINT, font=T.F_ICON, width=2, anchor="center")
        ic.pack(side="left", padx=(8, 6), pady=5)
        lb = tk.Label(row, text=text, bg=T.SIDEBAR, fg=T.MUTED, font=T.F_UI_B, anchor="w")
        lb.pack(side="left", fill="x", expand=True)
        parts = (row, ic, lb)

        def hover(on):
            for w in parts:
                w.configure(bg=T.SURFACE2 if on else T.SIDEBAR)
            ic.configure(fg=T.ACCENT if on else T.FAINT)
            lb.configure(fg=T.TEXT if on else T.MUTED)
        for w in parts:
            w.bind("<Enter>", lambda e: hover(True), add="+")
            w.bind("<Leave>", lambda e: hover(row.winfo_containing(e.x_root, e.y_root) in parts), add="+")
            w.bind("<Button-1>", lambda e: command())
        return row

    def _github_link(self, parent) -> tk.Label:
        """Logo GitHub + « GitHub » : ouvre le dépôt de l'application."""
        imgs = {}
        try:
            from importlib.resources import files
            for k, suffix in (("github", ""), ("github_hover", "-hover")):
                f = files("forge411") / "assets" / f"github-{T.MODE}{suffix}.png"
                if f.is_file():
                    imgs[k] = tk.PhotoImage(file=str(f))
        except Exception:
            imgs = {}
        self._github_imgs = imgs                     # références Tk gardées en vie
        lbl = tk.Label(parent, text="", image=imgs.get("github", ""), compound="left",
                       bg=T.SIDEBAR, fg=T.MUTED, font=T.F_SMALL, cursor="hand2")
        lbl.bind("<Button-1>", lambda e: webbrowser.open(REPO_URL))
        if not imgs:
            lbl.configure(text="GitHub")
        lbl.bind("<Enter>", lambda e: lbl.configure(fg=T.TEXT, image=imgs.get("github_hover", "")))
        lbl.bind("<Leave>", lambda e: lbl.configure(fg=T.MUTED, image=imgs.get("github", "")))
        Tooltip(lbl, f"Code source, nouveautés et signalement de bugs : {REPO_URL}")
        return lbl

    def _first_run(self):
        saved = SESS.load(SESSION_PATH)
        if saved and messagebox.askyesno(
                "Reprendre", f"Un upload n'était pas terminé :\n\n{saved.name or saved.src.path.name}\n\nLe reprendre ?",
                parent=self):
            self.load_session(saved)
        elif saved is None:
            SESS.discard(SESSION_PATH)
        if not self.cfg.is_configured:
            self.open_settings(first_run=True)
        if not self.cfg.get("tour_done"):
            self.start_tour()
        elif self.cfg.get("check_updates"):
            self.after(1500, lambda: self.check_updates(manual=False))
        if self.cfg.get("c411_api_key"):
            self.after(800, self.fetch_profile)

    # ── Construction ──────────────────────────────────────────────────────
    def _build(self):
        side = self.sidebar = tk.Frame(self, bg=T.SIDEBAR, width=250)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        brand = tk.Frame(side, bg=T.SIDEBAR)
        brand.pack(fill="x", padx=22, pady=(24, 4))
        tk.Label(brand, text="Forge", bg=T.SIDEBAR, fg=T.TEXT, font=("Segoe UI Black", 20)).pack(side="left")
        tk.Label(brand, text="411", bg=T.SIDEBAR, fg=T.ACCENT, font=("Segoe UI Black", 20)).pack(side="left")
        tk.Label(side, text="Du fichier au torrent en seed", bg=T.SIDEBAR, fg=T.FAINT,
                 font=T.F_SMALL, anchor="w").pack(fill="x", padx=24, pady=(0, 16))
        # Résumé du profil C411 (affiché quand le profil a pu être lu)
        self.chip = tk.Frame(side, bg=T.SURFACE, cursor="hand2", highlightthickness=1, highlightbackground=T.BORDER)
        self.chip_name = tk.Label(self.chip, bg=T.SURFACE, fg=T.TEXT, font=T.F_UI_B, anchor="w")
        self.chip_name.pack(fill="x", padx=12, pady=(8, 0))
        self.chip_meta = tk.Label(self.chip, bg=T.SURFACE, fg=T.MUTED, font=T.F_SMALL, anchor="w")
        self.chip_meta.pack(fill="x", padx=12, pady=(0, 8))
        for w in (self.chip, self.chip_name, self.chip_meta):
            w.bind("<Button-1>", lambda e: self.open_profile())
        Tooltip(self.chip, "Ton profil C411 : niveau, classe, volumes, Zen, freeleech.")
        self.chip_spacer = tk.Frame(side, bg=T.SIDEBAR, height=8)
        self.chip_spacer.pack(fill="x")

        self.nav_frame = tk.Frame(side, bg=T.SIDEBAR)
        self.nav_frame.pack(fill="x")
        self.nav = []
        for i, cls in enumerate(STEPS):
            row = tk.Frame(self.nav_frame, bg=T.SIDEBAR, cursor="hand2")
            row.pack(fill="x", padx=12, pady=2)
            num = tk.Label(row, text=str(i + 1), width=3, bg=T.SURFACE2, fg=T.MUTED, font=T.F_SMALL_B)
            num.pack(side="left", padx=(10, 12), pady=7)
            name = tk.Label(row, text=cls.title, bg=T.SIDEBAR, fg=T.MUTED, font=T.F_UI, anchor="w")
            name.pack(side="left", fill="x", expand=True)
            for w in (row, num, name):
                w.bind("<Button-1>", lambda e, k=i: self.goto(k))
            Tooltip(row, STEP_HELP[i])
            self.nav.append((row, num, name))

        bottom = tk.Frame(side, bg=T.SIDEBAR)
        bottom.pack(side="bottom", fill="x", padx=12, pady=16)
        self.side_buttons = {}
        menu = (
            ("Créer", (
                ("new", "＋", "Nouvel upload", self.restart, "Abandonne l'upload en cours et repart de zéro."),
                ("batch", "▤", "Mode lot", self.open_batch,
                 "Prépare toutes les sources d'un dossier et les envoie en brouillons."))),
            ("Suivre", (
                ("drafts", "✎", "Brouillons C411", self.open_drafts, "Tes brouillons sur C411 (15 au maximum)."),
                ("history", "◷", "Historique", self.open_history, "Ce que tu as envoyé depuis Forge411."),
                ("fix", "⚑", "Corriger une validation", self.open_correction,
                 "« Modification demandée » par la Team Pending : colle son message, Forge411 rouvre l'upload "
                 "avec les points à corriger."),
                ("profile", "◉", "Mon profil", self.open_profile,
                 "Niveau, classe, ratio, Zen et état de ton compte C411."))),
            ("Application", (
                ("settings", "⚙", "Paramètres", self.open_settings,
                 "Clés API, dossiers, équipe, client torrent, captures, apparence."),)),
        )
        for gi, (title, items) in enumerate(menu):
            tk.Label(bottom, text=title.upper(), bg=T.SIDEBAR, fg=T.FAINT, font=("Segoe UI Semibold", 8),
                     anchor="w").pack(fill="x", padx=12, pady=(0 if gi == 0 else 10, 2))
            for key, icon, text, cmd, tip in items:
                row = self._side_item(bottom, icon, text, cmd)
                row.pack(fill="x")
                Tooltip(row, tip)
                self.side_buttons[key] = row
        # Pied : version, puis actions discrètes (visite, mises à jour) et lien GitHub
        meta = tk.Frame(bottom, bg=T.SIDEBAR)
        meta.pack(fill="x", padx=(10, 2), pady=(12, 0))
        credit = tk.Label(meta, text=f"v{__version__} · par {AUTHOR}", bg=T.SIDEBAR, fg=T.MUTED, font=T.F_SMALL,
                          cursor="hand2")
        credit.pack(side="left")
        credit.bind("<Button-1>", lambda e: self.open_about())
        credit.bind("<Enter>", lambda e: credit.configure(fg=T.ACCENT))
        credit.bind("<Leave>", lambda e: credit.configure(fg=T.MUTED))
        Tooltip(credit, f"Forge411, développé par {AUTHOR}. Clic : à propos, licence et services utilisés.")
        self.side_buttons["about"] = credit
        self._github_link(meta).pack(side="right")
        for key, icon, cmd, tip in (("update", "⟳", self.check_updates, "Mises à jour : cherche une nouvelle version sur GitHub."),
                                    ("tour", "✦", self.start_tour, "Visite guidée : relance la présentation de l'interface.")):
            b = tk.Label(meta, text=icon, bg=T.SIDEBAR, fg=T.FAINT, font=T.F_ICON, cursor="hand2", padx=2)
            b.pack(side="right", padx=(0, 2))
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, w=b: w.configure(fg=T.ACCENT))
            b.bind("<Leave>", lambda e, w=b: w.configure(fg=T.FAINT))
            Tooltip(b, tip)
            self.side_buttons[key] = b

        main = tk.Frame(self, bg=T.BG)
        main.pack(side="left", fill="both", expand=True)
        head = tk.Frame(main, bg=T.BG)
        head.pack(fill="x", padx=32, pady=(26, 16))
        self.h_step = label(head, "", fg=T.ACCENT, font=T.F_SMALL_B)
        self.h_step.pack(fill="x")
        self.h_title = label(head, "", font=T.F_TITLE)
        self.h_title.pack(fill="x")
        self.h_sub = label(head, "", fg=T.MUTED)
        self.h_sub.pack(fill="x", pady=(2, 0))
        self.h_sub.bind("<Configure>", lambda e: self.h_sub.configure(wraplength=max(e.width - 4, 200)))
        # Bandeau du mode correction : points de la Team Pending pour l'étape affichée
        self.fix_banner = tk.Frame(main, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.WARNING)
        self.fix_title = label(self.fix_banner, "", fg=T.WARNING, font=T.F_UI_B, bg=T.SURFACE)
        self.fix_title.pack(fill="x", padx=14, pady=(10, 2))
        self.fix_text = label(self.fix_banner, "", bg=T.SURFACE)
        self.fix_text.pack(fill="x", padx=14, pady=(0, 10))
        self.fix_text.bind("<Configure>", lambda e: self.fix_text.configure(wraplength=max(e.width - 4, 200)))
        self._main = main

        foot = tk.Frame(main, bg=T.BG)
        foot.pack(side="bottom", fill="x", padx=32, pady=(10, 20))
        self.status = label(foot, "", fg=T.MUTED, font=T.F_SMALL)
        self.status.pack(side="left")
        self.next_btn = Btn(foot, "Continuer  →", self.next, kind="primary")
        self.next_btn.pack(side="right")
        self.foot_extra = tk.Frame(foot, bg=T.BG)
        self.foot_extra.pack(side="right")
        self.back_btn = Btn(foot, "←  Retour", self.back, kind="ghost")
        self.back_btn.pack(side="right", padx=(0, 8))

        self.body = tk.Frame(main, bg=T.BG)
        self.body.pack(fill="both", expand=True, padx=(32, 18))

    # ── Navigation ────────────────────────────────────────────────────────
    def render_fix_banner(self, i: int):
        from .. import correction as FIX
        fix = getattr(self.session, "correction", None)
        if not fix:
            self.fix_banner.pack_forget()
            return
        here = [p.text for p in fix.get("points", []) if p.step == i]
        other = sorted({FIX.STEP_LABELS[p.step] for p in fix.get("points", []) if p.step != i})
        self.fix_title.configure(text="⚑ Correction demandée par la Team Pending" + (
            f" : {len(here)} point(s) pour cette étape" if here else ""))
        lines = [f"• {t}" for t in here] or ["Rien de signalé pour cette étape."]
        if other:
            lines.append("Autres étapes concernées : " + ", ".join(other) + ".")
        self.fix_text.configure(text="\n".join(lines))
        if not self.fix_banner.winfo_ismapped():
            self.fix_banner.pack(fill="x", padx=32, pady=(0, 12), before=self.body)

    def open_correction(self, entry=None):
        from .dialogs import CorrectionDialog
        res = CorrectionDialog.ask(self, entry)
        if res:
            self.start_correction(*res)

    def start_correction(self, entry, message):
        """Recharge l'upload (copie locale, sinon la source à choisir) en mode correction."""
        from pathlib import Path
        from tkinter import filedialog
        from .. import correction as FIX
        from ..torrent import torrent_info
        if self._busy:
            return
        if self.session.src and not self.session.result and not getattr(self.session, "correction", None) and \
                not messagebox.askyesno("Correction", "Abandonner l'upload en cours ?", parent=self):
            return
        ih = entry.get("infohash", "")
        fix = {"infohash": ih, "url": entry.get("url") or FIX.torrent_page(ih), "message": message,
               "points": FIX.parse(message)}
        torrent = Path(entry["torrent"]) if entry.get("torrent") else None
        if torrent is None or not torrent.exists():
            cand = self.cfg.torrents_dir / f"{entry.get('name', '')}.torrent"
            torrent = cand if entry.get("name") and cand.exists() else None
        snap = SESS.load(Path(entry["snapshot"])) if entry.get("snapshot") else None
        self._stop_seed()
        if snap is not None:
            snap.result, snap.correction = None, fix
            if torrent is not None:
                snap.torrent = torrent
            snap.seed, snap.seeding = "", False
            self.load_session(snap)
            steps = [p.step for p in fix["points"] if self.reachable(p.step)]
            if steps:
                self.show(min(steps))
            return
        # Pas de copie locale (upload antérieur à cette version) : on repart de la source seedée
        guess = None
        if torrent is not None:
            name, t_hash = torrent_info(torrent)
            if ih and t_hash != ih:
                messagebox.showwarning("Correction", f"Le .torrent trouvé ({torrent.name}) n'a pas l'info-hash du "
                                                     "torrent publié : il est ignoré.", parent=self)
                torrent = None
            else:
                ih = ih or t_hash
                seed = self.cfg.get("seed_dir")
                if seed and (Path(seed) / name).exists():
                    guess = Path(seed) / name
        if guess is None:
            messagebox.showinfo("Correction", "Choisis la source de cet upload (le fichier ou le dossier que ton "
                                              "client seed).", parent=self)
            p = filedialog.askopenfilename(parent=self, title="Source de l'upload",
                                           initialdir=self.cfg.get("seed_dir") or self.cfg.get("last_dir") or None)
            if not p:
                p = filedialog.askdirectory(parent=self, title="Ou dossier source",
                                            initialdir=self.cfg.get("seed_dir") or None)
            if not p:
                return
            guess = Path(p)
        fix["infohash"] = ih
        self._pending_fix = (fix, torrent)
        self.session = Session()
        self.show(0)
        self.steps[0].analyze(guess)

    def show(self, i: int):
        Tooltip.hide_all()
        SESS.save(self.session, SESSION_PATH)        # reprise possible après fermeture ou plantage
        self.render_fix_banner(i)
        for st in self.steps:
            st.pack_forget()
        self.current = i
        st = self.steps[i]
        title, sub = st.heading()
        self.h_step.configure(text=f"ÉTAPE {i + 1} SUR {len(STEPS)}")
        self.h_title.configure(text=title)
        self.h_sub.configure(text=sub)
        st.pack(fill="both", expand=True)
        for w in self.foot_extra.winfo_children():
            w.destroy()
        self.foot_extra.configure(width=1, height=1)   # un cadre vidé garde sinon sa taille
        st.footer(self.foot_extra)
        if st.scroll:
            st.sf.to_top()
        try:
            st.on_enter()
        finally:
            self.refresh_nav()

    def reachable(self, i: int) -> bool:
        return all(self.steps[k].ready() for k in range(i))

    def goto(self, i: int):
        if i == self.current or self._busy:
            return
        if i < self.current:
            self.show(i)
        elif self.reachable(i):
            self._advance_to(i)

    def _advance_to(self, target: int):
        def done(ok):
            if ok and self.current < target:
                self.show(self.current + 1)
                if self.current < target and self.steps[self.current].ready():
                    self.after(10, lambda: self._advance_to(target))
        self.steps[self.current].leave(done)

    def next(self):
        if self._busy or not self.steps[self.current].ready() or self.current >= len(STEPS) - 1:
            return
        self._advance_to(self.current + 1)

    def back(self):
        if self.current > 0 and not self._busy:
            self.show(self.current - 1)

    def refresh_nav(self):
        if not hasattr(self, "steps"):
            return
        for i, (row, num, name) in enumerate(self.nav):
            done = i < self.current and self.steps[i].ready()
            if i == self.current:
                bg, nbg, nfg, fg, font = T.SURFACE2, T.ACCENT, T.ON_ACCENT, T.TEXT, T.F_UI_B
            elif done:
                bg, nbg, nfg, fg, font = T.SIDEBAR, T.SUCCESS_SOFT, T.SUCCESS, T.TEXT, T.F_UI
            else:
                reach = self.reachable(i)
                c = T.MUTED if reach else T.FAINT
                bg, nbg, nfg, fg, font = T.SIDEBAR, T.SURFACE2, c, c, T.F_UI
            row.configure(bg=bg)
            num.configure(bg=nbg, fg=nfg, text="✓" if done else str(i + 1))
            name.configure(bg=bg, fg=fg, font=font)
        last = self.current == len(STEPS) - 1
        self.next_btn.set_enabled(not last and not self._busy and self.steps[self.current].ready())
        if last:
            self.next_btn.pack_forget()
        elif not self.next_btn.winfo_ismapped():
            self.next_btn.pack(side="right", before=self.foot_extra)
        self.back_btn.set_enabled(self.current > 0 and not self._busy)

    def busy(self, on: bool):
        self._busy = max(0, self._busy + (1 if on else -1))
        self.configure(cursor="watch" if self._busy else "")
        self.status.configure(text="Traitement en cours…" if self._busy else "")
        self.refresh_nav()

    # ── Session ───────────────────────────────────────────────────────────
    def load_session(self, session):
        """Reprend une session (sauvegarde locale ou mode lot) à la dernière étape atteignable."""
        self._stop_seed()
        self.session = session
        target = 0
        for k in range(1, 5):
            if self.reachable(k):
                target = k
        self.show(target)

    def _stop_seed(self):
        step = self.steps[-1] if hasattr(self, "steps") else None
        if step is not None and getattr(step, "_seed_cancel", None):
            step._seed_cancel.set()

    def new_session(self, src, ranked, profile, analysis):
        self._stop_seed()
        s = self.session = Session(src=src, ranked=ranked, profile=profile, analysis=analysis)
        s.sub_id = profile.guess_sub(s.ctx())
        pending = getattr(self, "_pending_fix", None)
        if pending:                                   # correction d'un upload publié : même torrent, même info-hash
            self._pending_fix = None
            s.correction, s.torrent = pending
            s.infohash = s.correction.get("infohash", "")
            self.render_fix_banner(self.current)

    def invalidate_torrent(self):
        self.session.torrent_for = ""

    def restart(self):
        if self._busy:
            return
        if self.session.src and not self.session.result and not messagebox.askyesno(
                "Nouvel upload", "Abandonner l'upload en cours ?", parent=self):
            return
        self._stop_seed()
        self.session = Session()
        SESS.discard(SESSION_PATH)
        self.show(0)

    # ── Clients API (recréés si les clés changent) ────────────────────────
    def _check_keys(self):
        keys = tuple(self.cfg.get(k) for k in ("tmdb_api_key", "c411_api_key", "rawg_api_key", "google_books_key",
                                               "tpdb_api_key"))
        if keys != self._keys:
            if self._keys is not None and keys[1] != self._keys[1]:
                self.profile_cache = None
                self.chip.pack_forget()
            self._keys, self._clients = keys, {}

    def client(self, provider: str):
        """Client de la base en ligne du profil (lève LookupFailed si la clé manque)."""
        self._check_keys()
        if provider not in self._clients:
            if provider == "tmdb":
                from ..lookup.tmdb import TMDB
                self._clients[provider] = TMDB(self.cfg.get("tmdb_api_key"))
            elif provider == "rawg":
                from ..lookup.rawg import RAWG
                self._clients[provider] = RAWG(self.cfg.get("rawg_api_key"))
            elif provider == "tpdb":
                from ..lookup.tpdb import TPDB
                self._clients[provider] = TPDB(self.cfg.get("tpdb_api_key"))
            elif provider == "musicbrainz":
                from ..lookup.musicbrainz import MusicBrainz
                self._clients[provider] = MusicBrainz()
            elif provider == "books":
                from ..lookup.books import Books
                self._clients[provider] = Books(self.cfg.get("google_books_key"))
            else:
                raise LookupFailed("Aucune base en ligne pour ce type.")
        return self._clients[provider]

    def c411(self) -> C411:
        self._check_keys()
        if "c411" not in self._clients:
            self._clients["c411"] = C411(self.cfg.get("c411_api_key"))
        return self._clients["c411"]

    # ── Fenêtres ──────────────────────────────────────────────────────────
    def open_settings(self, first_run: bool = False):
        theme = self.cfg.get("theme")
        d = SettingsDialog(self, self.cfg, first_run)
        d.show()
        if d.saved:
            self._check_keys()
            self.show(self.current)
            if self.cfg.get("c411_api_key") and self.profile_cache is None:
                self.fetch_profile()
            if self.cfg.get("theme") != theme and T.resolve(self.cfg.get("theme")) != T.MODE:
                lost = " L'upload en cours sera proposé à la reprise." if self.session.src and not self.session.result else ""
                if messagebox.askyesno("Apparence", "Redémarrer Forge411 maintenant pour appliquer le nouveau mode ?"
                                       + lost + "\n\nSinon, il s'appliquera au prochain lancement.", parent=self):
                    self.restart_app()

    def restart_app(self):
        """Relance l'application (nouvelle apparence)."""
        if getattr(sys, "frozen", False):
            cmd = [sys.executable] + sys.argv[1:]
        else:
            cmd = [sys.executable] + sys.argv
        env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
        try:
            subprocess.Popen(cmd, env=env, close_fds=True)
        except OSError as e:
            messagebox.showerror("Redémarrage", f"Relance impossible : {e}. Relance Forge411 à la main.", parent=self)
            return
        self.quit_for_update()

    # ── Profil C411 ───────────────────────────────────────────────────────
    def fetch_profile(self):
        """Lecture discrète au démarrage : le résumé n'apparaît que si la clé a le droit « Profil (lecture) »."""
        def failed(e):
            logging.info("Profil C411 non lu : %s", e)
        run_bg(lambda: P.parse(self.c411().profile(), BASE), self.set_profile, failed)

    def set_profile(self, prof):
        self.profile_cache = (prof, time.time())
        P.record(PROFILE_HISTORY_PATH, prof, time.time())
        self.chip_name.configure(text=prof.username)
        self.chip_meta.configure(text=f"Niveau {prof.level} · Ratio {P.fmt_ratio(prof.ratio)}")
        if not self.chip.winfo_ismapped():
            self.chip.pack(fill="x", padx=16, before=self.chip_spacer)

    def open_profile(self):
        from .profile_view import ProfileDialog
        ProfileDialog(self).show()

    def open_about(self):
        from .about_view import AboutDialog
        AboutDialog(self).show()

    def open_batch(self):
        from .batch_view import BatchDialog
        BatchDialog(self).show()

    def open_drafts(self):
        from .drafts_view import DraftsDialog
        DraftsDialog(self).show()

    def open_history(self):
        HistoryDialog(self).show()

    def check_updates(self, manual: bool = True):
        """Cherche une nouvelle release ; manual : bouton (affiche aussi « à jour » et les erreurs)."""
        if manual:
            self.status.configure(text="Recherche de mise à jour…")

        def found(rel):
            if manual:
                self.status.configure(text="")
            if rel is None:
                if manual:
                    messagebox.showinfo("Mises à jour", f"Forge411 {__version__} est à jour.", parent=self)
                return
            if not manual and rel.version == self.cfg.get("skip_version"):
                return
            self._offer_update(rel)

        def failed(e):
            logging.info("Vérification des mises à jour : %s", e)
            if manual:
                self.status.configure(text="")
                messagebox.showwarning("Mises à jour", str(e), parent=self)

        run_bg(updater.check, found, failed)

    def _offer_update(self, rel):
        if self.grab_current() is not None:          # une autre fenêtre est ouverte : on repasse plus tard
            self.after(3000, lambda: self._offer_update(rel))
            return
        UpdateDialog(self, rel).show()

    def quit_for_update(self):
        """Fermeture immédiate : le script de mise à jour attend la fin du processus."""
        SESS.save(self.session, SESSION_PATH)          # l'upload en cours sera proposé au redémarrage
        self._stop_seed()
        try:
            if self.state() == "normal":
                self.cfg.update({"window_geometry": self.geometry()})
        except Exception:
            pass
        self.destroy()

    def start_tour(self):
        if self.current != 0:
            self.show(0)
        src_step = self.steps[0]
        steps = [
            (lambda: src_step.tiles, "Commence ici",
             "Choisis un fichier ou un dossier à partager. Forge411 reconnaît s'il s'agit d'un film, d'une série, "
             "d'un album, d'un livre, d'un jeu… et l'analyse."),
            (lambda: self.nav_frame, "Six étapes guidées",
             "Source, identification, nom, NFO, présentation, publication. Une étape terminée passe en vert ; "
             "tu peux revenir en arrière à tout moment. Survole une étape pour son rôle."),
            (lambda: self.next_btn, "Avancer",
             "« Continuer » s'active quand l'étape est complète. Les points à corriger sont listés en rouge, "
             "les conseils en orange."),
            (lambda: self.body, "Aide partout",
             "Survole un « ? » ou un champ pour savoir à quoi il sert. Les liens en couleur ouvrent ton navigateur."),
            (lambda: self.side_buttons["batch"], "Mode lot",
             "Plusieurs releases dans un dossier ? Forge411 les prépare toutes, signale celles à vérifier et "
             "envoie les autres en brouillons."),
            (lambda: self.side_buttons["drafts"], "Brouillons C411",
             "Tes brouillons sur C411 (15 au maximum) : compteur, suppression et lien pour les reprendre."),
            (lambda: self.side_buttons["profile"], "Mon profil",
             "Niveau, classe, ratio, Zen et état de ton compte, avec ton évolution depuis la dernière fois. "
             "Demande une clé API avec le droit « Profil (lecture) »."),
            (lambda: self.side_buttons["settings"], "Paramètres",
             "Clés API, URL d'annonce, dossiers, tag d'équipe, client torrent (seed vérifié avant publication), "
             "captures d'écran et apparence (sombre, clair ou système)."),
            (lambda: self.side_buttons["update"], "Mises à jour",
             "Forge411 vérifie les nouvelles versions au démarrage ; ce bouton le fait à la demande. "
             "Le logo GitHub, à côté, mène au code."),
            (lambda: self.side_buttons["about"], "À propos",
             f"Forge411 est développé par {AUTHOR}. Clique ici pour la version, la licence et les services utilisés."),
            (lambda: self.side_buttons["tour"], "Revoir la visite", "Relance cette présentation quand tu veux (✦)."),
        ]
        Tour(self, steps, on_done=lambda: self.cfg.update({"tour_done": True})).start()

    def _on_error(self, exc, val, tb):
        logging.error("Erreur d'interface\n%s", "".join(traceback.format_exception(exc, val, tb)))
        messagebox.showerror("Erreur inattendue", f"{exc.__name__} : {val}\n\nDétails dans {LOG_PATH}", parent=self)

    def _close(self):
        if self._busy and not messagebox.askyesno(
                "Quitter", "Une opération est en cours. Quitter quand même ?", parent=self):
            return
        try:
            if self.state() == "normal":
                self.cfg.update({"window_geometry": self.geometry()})
        except Exception:
            pass
        SESS.save(self.session, SESSION_PATH)
        self._stop_seed()
        self.destroy()


def selftest(path: str):
    """Diagnostic sans interface : `Forge411.exe --selftest rapport.txt`."""
    from .. import audioinfo, videoinfo
    from .widgets import PIL_OK
    lines = [f"{APP_NAME} {__version__}", f"Python {sys.version.split()[0]}",
             f"MediaInfo : {videoinfo.MEDIAINFO_OK}", f"mutagen : {audioinfo.MUTAGEN_OK}", f"Pillow : {PIL_OK}"]
    try:
        import pypdf
        lines.append(f"pypdf : {pypdf.__version__}")
    except ImportError:
        lines.append("pypdf : absent")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


LOG_PATH = config_dir() / "forge411.log"


def main():
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")
    if "--selftest" in sys.argv:
        selftest(sys.argv[sys.argv.index("--selftest") + 1])
        return
    if "--finish-update" in sys.argv:                  # nouvelle version : remplace Forge411.exe puis le relance
        return updater.finish_update(sys.argv[sys.argv.index("--finish-update") + 1:])
    if "--cleanup-update" in sys.argv:
        updater.cleanup_update(sys.argv[sys.argv.index("--cleanup-update") + 1])
    App().mainloop()
    os._exit(0)                                        # aucun thread restant ne retient le processus


if __name__ == "__main__":
    sys.exit(main())
