"""Fenêtres secondaires : paramètres, choix multiple, historique, mise à jour."""

import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import __version__, updater
from ..api import C411
from ..config import KEY_LINKS, Config, read_history, remove_history
from . import theme as T
from .widgets import (UI, Btn, Field, ScrollFrame, TextArea, Tooltip, autowrap, help_icon, label, link, run_bg,
                      style_tree, wrap_check)


class Dialog(tk.Toplevel):
    def __init__(self, parent, title: str, width: int, height: int):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.configure(bg=T.BG)
        self.transient(parent.winfo_toplevel())
        self.resizable(True, True)
        top = parent.winfo_toplevel()
        width = min(T.px(self, width), self.winfo_screenwidth() - 40)
        height = min(T.px(self, height), self.winfo_screenheight() - 80)
        x = top.winfo_rootx() + (top.winfo_width() - width) // 2
        y = top.winfo_rooty() + (top.winfo_height() - height) // 3
        self.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
        self.bind("<Escape>", lambda e: self.destroy())

    def show(self):
        self.deiconify()
        T.dark_title_bar(self)
        self.grab_set()
        self.focus_set()
        self.wait_window()


# ═══════════════════════════════════════════════════════════════════════════

class SettingsDialog(Dialog):
    """Paramètres : navigation par sections, lignes compactes libellé / champ, tests intégrés."""

    SECTIONS = (("account", "◆", "Compte C411"), ("sources", "◎", "Bases en ligne"), ("uploads", "▤", "Uploads"),
                ("client", "⇅", "Client torrent"), ("shots", "▣", "Captures"), ("general", "⚙", "Général"))
    LABEL_W = 165                      # largeur de la colonne des libellés (px à 100 %, mise à l'échelle du DPI)

    def __init__(self, parent, cfg: Config, first_run: bool = False, section: str = ""):
        super().__init__(parent, "Paramètres", 920, 680)
        self.LABEL_W = T.px(self, self.LABEL_W)
        self.minsize(min(T.px(self, 820), self.winfo_screenwidth() - 40),
                     min(T.px(self, 560), self.winfo_screenheight() - 80))
        self.cfg = cfg
        self.saved = False
        from .. import clients as CL
        from .. import screens as SC
        keys = ("c411_api_key", "tracker_url", "tmdb_api_key", "rawg_api_key", "google_books_key", "tpdb_api_key",
                "team_tag", "output_dir", "seed_dir", "client_url", "client_user", "client_password", "client_label",
                "ffmpeg_path", "client_path_local", "client_path_remote")
        self.v = {k: tk.StringVar(value=cfg.get(k) or "") for k in keys}
        self.client_kind = tk.StringVar(value=CL.KINDS.get(cfg.get("client_kind") or "", "Aucun"))
        self.team_auto = tk.BooleanVar(value=bool(cfg.get("team_tag_auto")))
        self.client_remote = tk.BooleanVar(value=bool(cfg.get("client_path_local") or cfg.get("client_path_remote"))
                                           or not CL.is_local(cfg.get("client_url") or ""))
        self.client_auto = tk.BooleanVar(value=bool(cfg.get("client_auto", True)))
        self.screens_host = tk.StringVar(value=SC.HOSTS.get(cfg.get("screens_host") or "pixhost", "pixhost.to"))
        self.screens_count = tk.StringVar(value=str(cfg.get("screens_count") or 4))
        self.theme = tk.StringVar(value=T.MODES.get(cfg.get("theme") or "dark", "Sombre"))
        self.check_updates = tk.BooleanVar(value=bool(cfg.get("check_updates")))
        self.translate = tk.BooleanVar(value=bool(cfg.get("translate_overview", True)))

        # ── Structure : navigation | contenu, pied de page ───────────────────
        foot = tk.Frame(self, bg=T.SIDEBAR, highlightthickness=0)
        foot.pack(side="bottom", fill="x")
        tk.Frame(foot, bg=T.BORDER, height=1).pack(fill="x", side="top")
        fbar = tk.Frame(foot, bg=T.SIDEBAR)
        fbar.pack(fill="x", padx=20, pady=12)
        Btn(fbar, "Enregistrer", self.save, kind="primary").pack(side="right")
        Btn(fbar, "Annuler", self.destroy, kind="ghost").pack(side="right", padx=(0, 8))
        label(fbar, "Enregistrés sur ce PC uniquement · Ctrl+S pour enregistrer", fg=T.FAINT, font=T.F_SMALL,
              bg=T.SIDEBAR).pack(side="left")
        self.bind("<Control-s>", lambda e: self.save())

        nav = tk.Frame(self, bg=T.SIDEBAR, width=T.px(self, 210))
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        tk.Frame(self, bg=T.BORDER, width=1).pack(side="left", fill="y")
        label(nav, "PARAMÈTRES", fg=T.FAINT, font=("Segoe UI Semibold", 8), bg=T.SIDEBAR).pack(
            fill="x", padx=20, pady=(20, 8))
        self.nav = {}
        for key, icon, text in self.SECTIONS:
            row = tk.Frame(nav, bg=T.SIDEBAR, cursor="hand2")
            row.pack(fill="x", padx=10, pady=1)
            bar = tk.Frame(row, bg=T.SIDEBAR, width=3)
            bar.pack(side="left", fill="y")
            ic = tk.Label(row, text=icon, bg=T.SIDEBAR, fg=T.MUTED, font=T.F_ICON, width=2)
            ic.pack(side="left", padx=(8, 6), pady=8)
            tx = tk.Label(row, text=text, bg=T.SIDEBAR, fg=T.TEXT, font=T.F_UI, anchor="w")
            tx.pack(side="left", fill="x", expand=True)
            dot = tk.Label(row, text="●", bg=T.SIDEBAR, fg=T.SIDEBAR, font=("Segoe UI", 8))
            dot.pack(side="right", padx=(0, 10))
            for w in (row, ic, tx, dot):
                w.bind("<Button-1>", lambda e, k=key: self.select(k))
                w.bind("<Enter>", lambda e, k=key: self._hover(k, True))
                w.bind("<Leave>", lambda e, k=key: self._hover(k, False))
            self.nav[key] = (row, bar, ic, tx, dot)

        self.content = tk.Frame(self, bg=T.BG)
        self.content.pack(side="left", fill="both", expand=True)
        self.pages, self.current = {}, ""
        self._align_tests, self._test_w = False, T.px(self, 62)       # largeur réservée au bouton « Tester »

        # ── Compte C411 ───────────────────────────────────────────────────────
        pg = self._page("account", "Compte C411", "Les deux informations indispensables pour publier.")
        if first_run:
            self._notice(pg, "Bienvenue dans Forge411 ! Renseigne ta clé API et ton URL d'annonce : les autres réglages "
                             "sont facultatifs et peuvent attendre.")
        g = self._group(pg, "Accès")
        self._secret_row(g, "Clé API", "c411_api_key", url=KEY_LINKS["c411_api_key"],
                         help="Profil C411 › Intégrations. Droits à cocher : brouillons (drafts:rw), upload "
                              "(upload:write) pour publier, « Profil (lecture) » pour Mon profil. Un droit ne s'ajoute "
                              "pas à une clé existante : crée une nouvelle clé.")
        self._secret_row(g, "URL d'annonce", "tracker_url", url=KEY_LINKS["tracker_url"],
                         help="Ton URL personnelle https://c411.org/announce/…, sur ton profil C411. Elle est écrite dans "
                              "chaque torrent créé : ne la partage jamais.")
        self.c411_msg = self._test_line(g, self.test_c411, "Vérifie la clé et ses droits.")

        # ── Bases en ligne ────────────────────────────────────────────────────
        pg = self._page("sources", "Bases en ligne", "Remplissent automatiquement fiches, noms et présentations. "
                                                     "Sans clé, tu saisis la fiche à la main.")
        g = self._group(pg, "Clés d'API")
        self.tmdb_msg = self._secret_row(g, "TMDB", "tmdb_api_key", url=KEY_LINKS["tmdb_api_key"], sub="Films, séries",
                                         help="Clé d'API (v3) ou jeton de lecture (v4), gratuits.", test=self.test_tmdb)
        self.rawg_msg = self._secret_row(g, "RAWG", "rawg_api_key", url=KEY_LINKS["rawg_api_key"], sub="Jeux vidéo",
                                         help="Gratuite : compte RAWG › page API.", test=self.test_rawg)
        self._align_tests = True
        self.tpdb_msg = self._secret_row(g, "ThePornDB", "tpdb_api_key", url=KEY_LINKS["tpdb_api_key"],
                                         sub="XXX Films et VR", test=self.test_tpdb,
                                         help="Jeton personnel (compte › API Tokens). La fiche est jointe à l'upload.")
        self._secret_row(g, "Google Books", "google_books_key", url=KEY_LINKS["google_books_key"], sub="Facultatif",
                         help="Sans clé, Forge411 utilise Open Library.")
        g = self._group(pg, "Résumés")
        self._check_row(g, self.translate, "Traduire en français les résumés rédigés dans une autre langue "
                                           "(Google Traduction, gratuit et sans compte)")
        label(pg, "Musique : MusicBrainz et livres : Open Library, sans clé.", fg=T.FAINT, font=T.F_SMALL).pack(
            fill="x", pady=(2, 0))

        # ── Uploads ───────────────────────────────────────────────────────────
        pg = self._page("uploads", "Uploads", "Où Forge411 range ses fichiers et ce qu'il ajoute à tes releases.")
        g = self._group(pg, "Dossiers")
        self._dir_row(g, "Sortie", "output_dir", "Reçoit les .torrent (sous-dossier « torrents ») et les .nfo.")
        self._dir_row(g, "Seed", "seed_dir", "Là où ton client attend les données. Forge411 vérifie que la source s'y "
                                             "trouve et propose de l'y déplacer.", sub="Facultatif")
        g = self._group(pg, "Équipe")
        cell = self._row(g, "Tag d'équipe", "Pour tes propres releases : ajouté après le dernier tiret (-MONTAG). "
                                            "Une release reprise garde toujours son tag d'origine.")
        ttk.Entry(cell, textvariable=self.v["team_tag"], width=18).pack(side="left")
        prof = getattr(parent, "profile_cache", None)
        team = prof[0].team_tag if prof else ""
        if team:
            Btn(cell, f"Reprendre « {team} »", lambda: self.v["team_tag"].set(team), small=True).pack(
                side="left", padx=(8, 0))
        self._check_row(g, self.team_auto, "Le proposer quand la source n'a pas de tag (au lieu de NOTAG)")
        g = self._group(pg, "Note pour la modération")
        self.note = tk.Text(g, height=3, bg=T.SURFACE2, fg=T.TEXT, insertbackground=T.TEXT, relief="flat", padx=8,
                            pady=6, font=T.F_UI, wrap="word", highlightthickness=1, highlightbackground=T.BORDER,
                            highlightcolor=T.ACCENT)
        self.note.insert("1.0", cfg.get("uploader_note") or "")
        self.note.pack(fill="x", padx=16, pady=(4, 14))

        # ── Client torrent ────────────────────────────────────────────────────
        pg = self._page("client", "Client torrent", "Forge411 ajoute le torrent au client et attend le seed avant de "
                                                     "publier : C411 refuse un torrent qui n'est pas seedé.")
        g = self._group(pg, "Connexion")
        cell = self._row(g, "Client", "Ton logiciel de torrent ; son interface web doit être activée.")
        ttk.Combobox(cell, textvariable=self.client_kind, values=list(CL.KINDS.values()), state="readonly",
                     width=16).pack(side="left")
        Btn(cell, "Détecter", self.detect_client, small=True).pack(side="left", padx=(8, 0))
        self.client_help = autowrap(label(g, "", fg=T.FAINT, font=T.F_SMALL))
        self.client_help.pack(fill="x", padx=(16 + self.LABEL_W, 16), pady=(0, 8))
        self.client_fields = tk.Frame(g, bg=T.SURFACE)
        self.client_fields.pack(fill="x")
        cf = self.client_fields
        cell = self._row(cf, "Adresse", "Ex. http://localhost:8080 (ce PC) ou http://192.168.1.10:8080 (NAS).")
        ttk.Entry(cell, textvariable=self.v["client_url"]).pack(side="left", fill="x", expand=True)
        self.user_row = self._row_frame(cf)
        cell = self._row(self.user_row, "Utilisateur", "Identifiant de l'interface web.", wrap=False)
        ttk.Entry(cell, textvariable=self.v["client_user"]).pack(side="left", fill="x", expand=True)
        self.pass_row = self._row_frame(cf)
        self._secret_cell(self._row(self.pass_row, "Mot de passe", wrap=False), "client_password")
        cell = self._row(cf, "Catégorie", "Catégorie qBittorrent ou étiquette Transmission / Deluge, pour retrouver "
                                          "tes uploads.", sub="Facultatif")
        ttk.Entry(cell, textvariable=self.v["client_label"], width=18).pack(side="left")
        self.client_msg = self._test_line(cf, self.test_client, "Vérifie l'adresse et l'identifiant.")
        self.user_field = self.user_row

        self.remote_group = self._group(pg, "Emplacement des données")
        rg = self.remote_group
        self._check_row(rg, self.client_remote, "Le client tourne sur un autre appareil (NAS, Docker, seedbox)",
                        command=self._client_state)
        self.remote_box = tk.Frame(rg, bg=T.SURFACE)
        cell = self._row(self.remote_box, "Vu par Windows", "Début du chemin côté PC, ex. \\\\192.168.1.251\\Torrents.")
        ttk.Entry(cell, textvariable=self.v["client_path_local"]).pack(side="left", fill="x", expand=True)
        cell = self._row(self.remote_box, "Vu par le client", "Le même dossier dans le client, ex. /downloads.")
        ttk.Entry(cell, textvariable=self.v["client_path_remote"]).pack(side="left", fill="x", expand=True)
        Btn(cell, "Proposer", self.suggest_paths, small=True).pack(side="left", padx=(8, 0))
        self.path_preview = autowrap(label(rg, "", fg=T.MUTED, font=T.F_SMALL))
        self.path_preview.pack(fill="x", padx=16, pady=(2, 10))
        self._check_row(rg, self.client_auto, "Ajouter le torrent au client dès sa création (conseillé)")
        self._client_prev = self.client_kind.get()
        self.client_kind.trace_add("write", lambda *_: self._client_kind_changed())
        for k in ("client_url", "client_path_local", "client_path_remote", "seed_dir"):
            self.v[k].trace_add("write", lambda *_: self._client_state())

        # ── Captures ──────────────────────────────────────────────────────────
        pg = self._page("shots", "Captures d'écran", "Extraites des vidéos avec ffmpeg et hébergées sur un site accepté "
                                                     "par C411, uniquement à ta demande.")
        from .. import ffmpeg_setup as FS
        g = self._group(pg, "ffmpeg")
        cell = self._row(g, "Programme", "Vide : ffmpeg du PATH, sinon celui installé par Forge411.")
        ttk.Entry(cell, textvariable=self.v["ffmpeg_path"]).pack(side="left", fill="x", expand=True)

        def browse_ffmpeg():
            p = filedialog.askopenfilename(parent=self, title="ffmpeg", filetypes=[("ffmpeg", "ffmpeg*"), ("Tous", "*.*")])
            if p:
                self.v["ffmpeg_path"].set(p)
        Btn(cell, "Parcourir", browse_ffmpeg, small=True).pack(side="left", padx=(8, 0))
        line = tk.Frame(g, bg=T.SURFACE)
        line.pack(fill="x", padx=(16 + self.LABEL_W, 16), pady=(0, 12))
        self.ffmpeg_btn = Btn(line, "", self.install_ffmpeg, small=True)
        if FS.supported():
            self.ffmpeg_btn.pack(side="right", padx=(8, 0))
        self.ffmpeg_lbl = autowrap(label(line, "", fg=T.MUTED, font=T.F_SMALL))
        self.ffmpeg_lbl.pack(side="left", fill="x", expand=True)
        self._ffmpeg_tip = Tooltip(self.ffmpeg_lbl, "")
        self._ffmpeg_state()
        self.v["ffmpeg_path"].trace_add("write", lambda *_: self._ffmpeg_state())
        g = self._group(pg, "Envoi")
        cell = self._row(g, "Hébergeur", "pixhost.to et catbox.moe sont acceptés par C411.")
        ttk.Combobox(cell, textvariable=self.screens_host, values=list(SC.HOSTS.values()), state="readonly",
                     width=16).pack(side="left")
        cell = self._row(g, "Nombre de captures", "Relevé automatiquement au minimum exigé par la catégorie.")
        ttk.Combobox(cell, textvariable=self.screens_count, values=["2", "3", "4", "6", "8"], state="readonly",
                     width=6).pack(side="left")
        self._notice(pg, "XXX : la Team Pending ne compte que postimg.cc et zupimages.net. Forge411 extrait les captures, "
                         "tu les déposes sur postimg.cc et tu colles les liens directs.", tone="info")

        # ── Général ───────────────────────────────────────────────────────────
        pg = self._page("general", "Général", "Apparence et mises à jour.")
        g = self._group(pg, "Apparence")
        cell = self._row(g, "Thème", "Sombre par défaut. Système suit le réglage clair / sombre de Windows. "
                                     "Ton choix est conservé ; appliqué au redémarrage.")
        ttk.Combobox(cell, textvariable=self.theme, values=list(T.MODES.values()), state="readonly",
                     width=16).pack(side="left")
        g = self._group(pg, "Mises à jour")
        self._check_row(g, self.check_updates, "Vérifier au démarrage si une nouvelle version est sortie")
        label(g, f"Version installée : {__version__}", fg=T.FAINT, font=T.F_SMALL).pack(
            fill="x", padx=16, pady=(0, 12))

        for var in self.v.values():
            var.trace_add("write", lambda *_: self._refresh_dots())
        self.client_kind.trace_add("write", lambda *_: self._refresh_dots())
        self._client_state()
        self._refresh_dots()
        self.select(section or ("account" if first_run or not cfg.is_configured else "account"))

    # ── Mise en page ──────────────────────────────────────────────────────
    def _page(self, key, title, subtitle):
        sf = ScrollFrame(self.content)
        inner = tk.Frame(sf.inner, bg=T.BG)
        inner.pack(fill="both", expand=True, padx=(28, 24), pady=(22, 16))
        label(inner, title, font=T.F_BIG).pack(fill="x")
        autowrap(label(inner, subtitle, fg=T.MUTED, font=T.F_SMALL)).pack(fill="x", pady=(2, 14))
        self.pages[key] = sf
        return inner

    def _group(self, parent, title):
        label(parent, title.upper(), fg=T.FAINT, font=("Segoe UI Semibold", 8)).pack(fill="x", pady=(4, 4))
        box = tk.Frame(parent, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER)
        box.pack(fill="x", pady=(0, 14))
        tk.Frame(box, bg=T.SURFACE, height=6).pack(fill="x")
        return box

    def _notice(self, parent, text, tone="accent"):
        bg, fg = (T.ACCENT_SOFT, T.TEXT) if tone == "accent" else (T.SURFACE2, T.MUTED)
        box = tk.Frame(parent, bg=bg)
        box.pack(fill="x", pady=(0, 14))
        autowrap(label(box, text, fg=fg, bg=bg, font=T.F_SMALL)).pack(fill="x", padx=12, pady=8)

    def _row_frame(self, parent):
        f = tk.Frame(parent, bg=T.SURFACE)
        f.pack(fill="x")
        return f

    def _row(self, parent, text, help="", sub="", url=None, wrap=True):
        """Ligne « libellé | champ » ; renvoie le cadre où placer le champ."""
        row = tk.Frame(parent, bg=T.SURFACE)
        row.pack(fill="x", padx=16, pady=5)
        head = tk.Frame(row, bg=T.SURFACE, width=self.LABEL_W)
        head.pack(side="left", fill="y")
        head.pack_propagate(False)
        top = tk.Frame(head, bg=T.SURFACE)
        top.pack(fill="x", pady=(4, 0))
        label(top, text, font=T.F_UI_B, bg=T.SURFACE).pack(side="left")
        if help:
            help_icon(top, help).pack(side="left", padx=(6, 0))
        if sub:
            label(head, sub, fg=T.FAINT, font=T.F_SMALL, bg=T.SURFACE).pack(fill="x")
        body = tk.Frame(row, bg=T.SURFACE)
        body.pack(side="left", fill="x", expand=True)
        cell = tk.Frame(body, bg=T.SURFACE)
        cell.pack(fill="x")
        if url:
            link(body, url[0], url[1]).pack(fill="x", pady=(2, 0))
        head.configure(height=T.px(self, 48 if (sub or url) else 34))
        return cell

    def _secret_cell(self, cell, key):
        e = ttk.Entry(cell, textvariable=self.v[key], show="•")
        e.pack(side="left", fill="x", expand=True)
        eye = tk.Label(cell, text="Afficher", bg=T.SURFACE, fg=T.FAINT, cursor="hand2", font=T.F_SMALL, width=8)
        eye.pack(side="left", padx=(6, 0))

        def toggle(_=None):
            hidden = e.cget("show") == "•"
            e.configure(show="" if hidden else "•")
            eye.configure(text="Masquer" if hidden else "Afficher", fg=T.ACCENT if hidden else T.FAINT)
        eye.bind("<Button-1>", toggle)
        return e

    def _secret_row(self, parent, text, key, help="", sub="", url=None, test=None):
        cell = self._row(parent, text, help, sub, url)
        self._secret_cell(cell, key)
        if not test:
            tk.Frame(cell, bg=T.SURFACE, width=self._test_w).pack(side="left") if self._align_tests else None
            return None
        b = Btn(cell, "Tester", test, small=True)
        b.pack(side="left", padx=(8, 0))
        msg = label(parent, "", fg=T.MUTED, font=T.F_SMALL)
        msg.pack(fill="x", padx=(16 + self.LABEL_W, 16))
        return msg

    def _test_line(self, parent, cmd, hint):
        line = tk.Frame(parent, bg=T.SURFACE)
        line.pack(fill="x", padx=(16 + self.LABEL_W, 16), pady=(4, 12))
        Btn(line, "Tester", cmd, small=True).pack(side="left")
        msg = label(line, hint, fg=T.FAINT, font=T.F_SMALL)
        msg.pack(side="left", padx=(10, 0), fill="x", expand=True)
        return msg

    def _check_row(self, parent, var, text, command=None):
        wrap_check(parent, var, text, command).pack(fill="x", padx=16, pady=(4, 8))

    def _dir_row(self, parent, text, key, help_text, sub=""):
        cell = self._row(parent, text, help_text, sub)
        ttk.Entry(cell, textvariable=self.v[key]).pack(side="left", fill="x", expand=True)

        def browse():
            p = filedialog.askdirectory(parent=self, initialdir=self.v[key].get() or None)
            if p:
                self.v[key].set(p)
        Btn(cell, "Parcourir", browse, small=True).pack(side="left", padx=(8, 0))

    # ── Navigation ────────────────────────────────────────────────────────
    def select(self, key):
        if self.current:
            self.pages[self.current].pack_forget()
        self.current = key
        self.pages[key].pack(fill="both", expand=True)
        self.pages[key].to_top()
        for k, (row, bar, ic, tx, dot) in self.nav.items():
            on = k == key
            bg = T.SURFACE2 if on else T.SIDEBAR
            for w in (row, ic, tx, dot):
                w.configure(bg=bg)
            bar.configure(bg=T.ACCENT if on else bg)
            ic.configure(fg=T.ACCENT if on else T.MUTED)
            tx.configure(font=T.F_UI_B if on else T.F_UI)
        self._refresh_dots()

    def _hover(self, key, on):
        if key == self.current:
            return
        row, bar, ic, tx, dot = self.nav[key]
        bg = T.HOVER if on else T.SIDEBAR
        for w in (row, bar, ic, tx, dot):
            w.configure(bg=bg)
        self._refresh_dots()

    def _refresh_dots(self):
        """Pastille par section : rouge = obligatoire manquant, orange = conseillé, rien = complet."""
        g = lambda k: self.v[k].get().strip()
        state = {
            "account": T.ERROR if not (g("c411_api_key") and g("tracker_url")) else None,
            "sources": T.WARNING if not (g("tmdb_api_key") or g("rawg_api_key") or g("tpdb_api_key")) else None,
            "uploads": None,
            "client": T.WARNING if self._kind() == "" else None,
            "shots": None,
            "general": None,
        }
        for k, (row, bar, ic, tx, dot) in self.nav.items():
            dot.configure(fg=state[k] or dot.cget("bg"))

    def _run_test(self, msg_lbl, fn):
        msg_lbl.configure(text="Test…", fg=T.MUTED)
        run_bg(fn, lambda r: msg_lbl.configure(text="✓ " + r, fg=T.SUCCESS),
               lambda e: msg_lbl.configure(text="✕ " + str(e), fg=T.ERROR))

    def test_c411(self):
        key = self.v["c411_api_key"].get()
        self._run_test(self.c411_msg, lambda: C411(key).test())

    def test_tmdb(self):
        from ..lookup.tmdb import TMDB
        key = self.v["tmdb_api_key"].get()
        self._run_test(self.tmdb_msg, lambda: TMDB(key).test())

    def _ffmpeg_state(self):
        from .. import ffmpeg_setup as FS
        from .. import screens as SC
        found = SC.find_ffmpeg(self.v["ffmpeg_path"].get().strip())
        if found:
            from pathlib import Path as _P
            parts = _P(found).parts
            short = found if len(found) <= 48 else "…\\" + "\\".join(parts[-3:])
            self.ffmpeg_lbl.configure(text=f"✓  ffmpeg trouvé : {short}", fg=T.SUCCESS)
            self._ffmpeg_tip.text = found
        else:
            self.ffmpeg_lbl.configure(text="ffmpeg introuvable : installe-le en un clic (Windows) ou indique son chemin.",
                                      fg=T.WARNING)
        self.ffmpeg_btn.set_text("Mettre à jour ffmpeg" if FS.installed() else "Installer ffmpeg")

    def install_ffmpeg(self):
        from .ffmpeg_view import FfmpegDialog
        path = FfmpegDialog.ask(self)
        if path and not self.v["ffmpeg_path"].get().strip():
            self._ffmpeg_state()
        elif path:
            self.v["ffmpeg_path"].set(path)
        self.grab_set()

    def test_client(self):
        from .. import clients as CL
        kind = next((k for k, v in CL.KINDS.items() if v == self.client_kind.get()), "")
        if kind not in CL.CLASSES:
            self.client_msg.configure(text="Choisis d'abord un client.", fg=T.MUTED)
            return
        url = self.v["client_url"].get() or CL.DEFAULT_URLS[kind]
        args = (url, self.v["client_user"].get(), self.v["client_password"].get(), self.v["client_label"].get())
        self._run_test(self.client_msg, lambda: CL.CLASSES[kind](*args).test())

    def _kind(self):
        from .. import clients as CL
        return next((k for k, v in CL.KINDS.items() if v == self.client_kind.get()), "")

    def _client_kind_changed(self):
        from .. import clients as CL
        kind, prev = self._kind(), next((k for k, v in CL.KINDS.items() if v == self._client_prev), "")
        self._client_prev = self.client_kind.get()
        url = self.v["client_url"].get().strip()
        if kind in CL.DEFAULT_URLS and (not url or url == CL.DEFAULT_URLS.get(prev)):
            self.v["client_url"].set(CL.DEFAULT_URLS[kind])
        self._client_state()

    def _client_state(self):
        from .. import clients as CL
        kind = self._kind()
        if not kind:
            self.client_fields.pack_forget()
            self._show_remote(False)
            self.client_help.configure(text="Sans client, tu ajoutes toi-même le torrent et tu confirmes le seed "
                                            "avant de publier.", fg=T.FAINT)
            return
        self._show_remote(True)
        if not self.client_fields.winfo_ismapped():
            self.client_fields.pack(fill="x", after=self.client_help)
        self.client_help.configure(text=CL.ENABLE_HELP.get(kind, ""))
        if kind == "deluge":
            self.user_row.pack_forget()
        elif not self.user_row.winfo_ismapped():
            self.user_row.pack(fill="x", before=self.pass_row)
        if self.client_remote.get():
            self.remote_box.pack(fill="x", before=self.path_preview)
        else:
            self.remote_box.pack_forget()
        seed = self.v["seed_dir"].get().strip()
        if not seed:
            self.path_preview.configure(text="Astuce : indique un dossier de seed (section Uploads) pour voir le "
                                             "chemin transmis au client.", fg=T.FAINT)
            return
        local, remote = (self.v["client_path_local"].get(), self.v["client_path_remote"].get()) \
            if self.client_remote.get() else ("", "")
        seen = CL.map_path(seed, local, remote)
        if self.client_remote.get() and seen == seed:
            self.path_preview.configure(text=f"⚠ Le dossier de seed ({seed}) n'est pas sous « Dossier vu par Windows » : "
                                             "le client recevra un chemin Windows qu'il ne connaît pas.", fg=T.WARNING)
        else:
            self.path_preview.configure(text=f"Pour le dossier de seed, le client recevra : {seen}", fg=T.MUTED)

    def _show_remote(self, on):
        g = self.remote_group
        title = g.master.winfo_children()[g.master.winfo_children().index(g) - 1]
        if on and not g.winfo_ismapped():
            title.pack(fill="x", pady=(4, 4))
            g.pack(fill="x", pady=(0, 14), after=title)
        elif not on:
            title.pack_forget()
            g.pack_forget()

    def detect_client(self):
        from .. import clients as CL
        hosts = ["localhost"] + [CL.unc_host(self.v[k].get()) for k in ("seed_dir", "output_dir")]
        cur = self.v["client_url"].get().strip()
        self.client_msg_or_help("Recherche des clients…", T.MUTED)

        def work():
            found = CL.detect(list(dict.fromkeys(h for h in hosts if h)))
            if cur and not any(u == cur.rstrip("/") for _, u in found):
                k = CL.probe(cur, 2)
                if k:
                    found.insert(0, (k, cur.rstrip("/")))
            return found

        def ok(found):
            if not found:
                self.client_msg_or_help("Aucun client trouvé sur les ports par défaut : active son interface web, "
                                        "ou saisis son adresse.", T.WARNING)
                return
            kind, url = found[0]
            self.client_kind.set(CL.KINDS[kind])
            self.v["client_url"].set(url)
            self.client_remote.set(not CL.is_local(url))
            self._client_state()
            more = f" (+{len(found) - 1} autre(s))" if len(found) > 1 else ""
            self.client_msg_or_help(f"✓ {CL.KINDS[kind]} trouvé : {url}{more}. Renseigne l'identifiant puis Tester.",
                                    T.SUCCESS)
        run_bg(work, ok, lambda e: self.client_msg_or_help(f"✕ {e}", T.ERROR))

    def client_msg_or_help(self, text, color):
        if self.client_fields.winfo_ismapped():
            self.client_msg.configure(text=text, fg=color)
        else:
            self.client_help.configure(text=text, fg=color)

    def suggest_paths(self):
        from .. import clients as CL
        kind = self._kind()
        if kind not in CL.CLASSES:
            return
        args = (self.v["client_url"].get() or CL.DEFAULT_URLS[kind], self.v["client_user"].get(),
                self.v["client_password"].get(), "")
        seed = self.v["seed_dir"].get().strip()
        self.client_msg.configure(text="Lecture du dossier par défaut du client…", fg=T.MUTED)

        def ok(client_dir):
            local, remote = CL.suggest_mapping(seed, client_dir)
            if not local:
                self.client_msg.configure(text=f"Dossier par défaut du client : {client_dir or '?'}. Indique la "
                                               "correspondance à la main (dossier de seed sur un partage réseau ?).",
                                          fg=T.WARNING)
                return
            self.v["client_path_local"].set(local)
            self.v["client_path_remote"].set(remote)
            self.client_msg.configure(text=f"Proposé d'après le dossier du client ({client_dir}) : vérifie puis Tester.",
                                      fg=T.SUCCESS)
        run_bg(lambda: CL.CLASSES[kind](*args).default_dir(), ok,
               lambda e: self.client_msg.configure(text=f"✕ {e}", fg=T.ERROR))

    def test_tpdb(self):
        from ..lookup.tpdb import TPDB
        key = self.v["tpdb_api_key"].get()
        self._run_test(self.tpdb_msg, lambda: TPDB(key).test())

    def test_rawg(self):
        from ..lookup.rawg import RAWG
        key = self.v["rawg_api_key"].get()
        self._run_test(self.rawg_msg, lambda: RAWG(key).test())

    def save(self):
        values = {k: v.get().strip() for k, v in self.v.items()}
        values["uploader_note"] = self.note.get("1.0", "end-1c").strip()
        values["check_updates"] = self.check_updates.get()
        values["translate_overview"] = self.translate.get()
        from .. import clients as CL
        from .. import screens as SC
        values["client_kind"] = next((k for k, v in CL.KINDS.items() if v == self.client_kind.get()), "")
        values["client_auto"] = self.client_auto.get()
        if not self.client_remote.get():
            values["client_path_local"] = values["client_path_remote"] = ""
        values["screens_host"] = next((k for k, v in SC.HOSTS.items() if v == self.screens_host.get()), "pixhost")
        values["screens_count"] = int(self.screens_count.get() or 4)
        values["team_tag_auto"] = self.team_auto.get()
        values["team_tag"] = "".join(ch for ch in values.get("team_tag", "") if ch.isalnum())
        values["theme"] = next((k for k, v in T.MODES.items() if v == self.theme.get()), "dark")
        if values["theme"] != (self.cfg.get("theme") or "dark") or self.cfg.get("theme_chosen"):
            values["theme_chosen"] = True            # choix de l'utilisateur : conservé aux lancements suivants
        self.cfg.update(values)
        self.saved = True
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════

class MultiSelectDialog(Dialog):
    @classmethod
    def ask(cls, parent, title, values, selected):
        d = cls(parent, title, values, selected)
        d.show()
        return d.result

    def __init__(self, parent, title, values, selected):
        super().__init__(parent, title, 640, 560)
        self.result = None
        self.vars = []
        sf = ScrollFrame(self)
        sf.pack(fill="both", expand=True, padx=20, pady=(20, 0))
        grid = sf.inner
        for i, v in enumerate(values):
            var = tk.BooleanVar(value=v["id"] in selected)
            self.vars.append((v["id"], var))
            ttk.Checkbutton(grid, text=v["value"], variable=var).grid(
                row=i // 3, column=i % 3, sticky="w", padx=(0, 16), pady=3)
        for c in range(3):
            grid.columnconfigure(c, weight=1, uniform="m")
        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=20, pady=16)
        Btn(bar, "Valider", self.ok, kind="primary").pack(side="right")
        Btn(bar, "Tout décocher", lambda: [v.set(False) for _, v in self.vars], kind="ghost").pack(side="left")

    def ok(self):
        self.result = [i for i, v in self.vars if v.get()]
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════

class HistoryDialog(Dialog):
    """Historique des uploads : tableau triable et filtrable, sélection multiple, retrait des entrées
    (une par une ou toutes celles dont le .torrent n'existe plus)."""

    COLS = (("date", "Date", 130, False), ("name", "Release", 380, True), ("type", "Type", 150, False),
            ("action", "Action", 130, False), ("state", "Torrent", 100, False))
    FILTERS = ("Tout", "Publiés", "Brouillons", "Corrections", "Torrent introuvable")

    def __init__(self, parent):
        super().__init__(parent, "Historique", 980, 600)
        self.minsize(T.px(self, 760), T.px(self, 420))
        self.app = parent
        self.sort_col, self.sort_desc = "date", True

        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=20, pady=(18, 10))
        title = tk.Frame(head, bg=T.BG)
        title.pack(side="left")
        label(title, "Historique", font=T.F_BIG).pack(anchor="w")
        self.count = label(title, "", fg=T.MUTED, font=T.F_SMALL)
        self.count.pack(anchor="w")
        self.filter = tk.StringVar(value=self.FILTERS[0])
        fc = ttk.Combobox(head, textvariable=self.filter, values=self.FILTERS, state="readonly", width=20)
        fc.pack(side="right")
        fc.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        self.query = tk.StringVar()
        q = ttk.Entry(head, textvariable=self.query, width=28)
        q.pack(side="right", padx=(0, 8))
        Tooltip(q, "Filtrer par nom de release ou type.")
        self.query.trace_add("write", lambda *_: self.refresh())
        label(head, "Rechercher", fg=T.MUTED, font=T.F_SMALL).pack(side="right", padx=(0, 8))

        mid = tk.Frame(self, bg=T.BORDER)          # liseré d'un pixel autour du tableau
        mid.pack(fill="both", expand=True, padx=20)
        inner = tk.Frame(mid, bg=T.SURFACE)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        style_tree(self)
        self.tree = ttk.Treeview(inner, columns=[c[0] for c in self.COLS], show="headings", selectmode="extended")
        for key, text, w, stretch in self.COLS:
            self.tree.heading(key, text=text, anchor="w", command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=T.px(self, w), minwidth=T.px(self, 60), stretch=stretch, anchor="w")
        sb = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("missing", foreground=T.FAINT)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._sel_changed())
        self.tree.bind("<Double-1>", lambda e: self.open_url())
        self.tree.bind("<Delete>", lambda e: self.remove_selected())
        self.tree.bind("<Button-3>", self._menu)
        self.empty = label(inner, "", fg=T.MUTED, bg=T.SURFACE)

        self.sel_lbl = label(self, "", fg=T.MUTED, font=T.F_SMALL)      # nom complet de la ligne choisie
        self.sel_lbl.pack(fill="x", padx=22, pady=(6, 0))
        foot = tk.Frame(self, bg=T.BG)
        foot.pack(fill="x", padx=20, pady=(8, 14))
        self.clean_btn = Btn(foot, "", self.remove_missing, kind="ghost")
        self.clean_btn.pack(side="left")
        Tooltip(self.clean_btn, "Retire de l'historique les uploads dont le fichier .torrent a été supprimé ou déplacé.")
        self.open_btn = Btn(foot, "Ouvrir sur C411  ↗", self.open_url, kind="primary")
        self.open_btn.pack(side="right")
        self.fix_btn = Btn(foot, "Corriger", self.fix)
        self.fix_btn.pack(side="right", padx=(0, 8))
        Tooltip(self.fix_btn, "Reprendre cet upload après un retour de la Team Pending.")
        self.del_btn = Btn(foot, "Retirer", self.remove_selected, kind="danger")
        self.del_btn.pack(side="right", padx=(0, 8))
        Tooltip(self.del_btn, "Retire les lignes sélectionnées de l'historique (touche Suppr). "
                              "Rien n'est supprimé sur C411 ni sur le disque.")
        self.load()

    # ── Données ───────────────────────────────────────────────────────────
    def _torrent_exists(self, h) -> bool:
        if h.get("torrent") and Path(h["torrent"]).exists():
            return True
        try:
            return bool(h.get("name")) and (self.app.cfg.torrents_dir / f"{h['name']}.torrent").exists()
        except Exception:
            return False

    def load(self):
        self.items = read_history()
        for h in self.items:
            h["_ok"] = self._torrent_exists(h)
        self.refresh()

    def _visible(self):
        q = self.query.get().strip().lower()
        f = self.filter.get()
        out = []
        for h in self.items:
            act = h.get("action", "")
            if f == "Publiés" and ("Brouillon" in act or act == "Correction"):
                continue
            if f == "Brouillons" and "Brouillon" not in act:
                continue
            if f == "Corrections" and act != "Correction":
                continue
            if f == "Torrent introuvable" and h["_ok"]:
                continue
            if q and q not in f"{h.get('name', '')} {h.get('type', '')}".lower():
                continue
            out.append(h)
        key = self.sort_col if self.sort_col != "state" else "_ok"
        out.sort(key=lambda h: str(h.get(key, "")).lower(), reverse=self.sort_desc)
        return out

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        for h in self._visible():
            iid = self.tree.insert("", "end", values=(h.get("date", ""), h.get("name", "?"), h.get("type", ""),
                                                      h.get("action", ""), "Présent" if h["_ok"] else "Introuvable"),
                                   tags=() if h["_ok"] else ("missing",))
            self.rows[iid] = h
        for key, text, *_ in self.COLS:
            arrow = (" ▾" if self.sort_desc else " ▴") if key == self.sort_col else ""
            self.tree.heading(key, text=text + arrow)
        n, shown = len(self.items), len(self.rows)
        missing = sum(1 for h in self.items if not h["_ok"])
        self.count.configure(text=f"{n} upload{'s' if n > 1 else ''}" + (f" · {shown} affiché{'s' if shown > 1 else ''}"
                                                                         if shown != n else ""))
        if not self.rows:
            self.empty.configure(text="Aucun upload pour l'instant." if not n else "Aucun résultat.")
            self.empty.place(relx=0.5, rely=0.45, anchor="center")
        else:
            self.empty.place_forget()
        self.clean_btn.set_text(f"Retirer les introuvables ({missing})")
        self.clean_btn.set_enabled(missing > 0)
        self._sel_changed()

    def sort_by(self, col):
        self.sort_desc = not self.sort_desc if col == self.sort_col else col == "date"
        self.sort_col = col
        self.refresh()

    def _selected(self) -> list:
        return [self.rows[i] for i in self.tree.selection() if i in self.rows]

    def _sel_changed(self):
        sel = self._selected()
        one = sel[0] if len(sel) == 1 else None
        self.open_btn.set_enabled(bool(one and one.get("url")))
        self.fix_btn.set_enabled(bool(one and one.get("infohash") and one.get("action") != "Correction"))
        self.del_btn.set_enabled(bool(sel))
        self.del_btn.set_text(f"Retirer ({len(sel)})" if len(sel) > 1 else "Retirer")
        if one:
            where = one.get("torrent") or ""
            self.sel_lbl.configure(text=one.get("name", "") + (f"   ·   {where}" if where else ""))
        else:
            self.sel_lbl.configure(text=f"{len(sel)} uploads sélectionnés" if sel else
                                   "Double-clic : ouvrir sur C411 · Suppr : retirer · clic droit : plus d'actions")

    # ── Actions ───────────────────────────────────────────────────────────
    def open_url(self):
        sel = self._selected()
        if len(sel) == 1 and sel[0].get("url"):
            webbrowser.open(sel[0]["url"])

    def fix(self):
        sel = self._selected()
        if len(sel) == 1 and sel[0].get("infohash"):
            entry = {k: v for k, v in sel[0].items() if not k.startswith("_")}
            self.destroy()
            self.app.open_correction(entry)

    def _remove(self, entries, question):
        if not entries or not messagebox.askyesno("Historique", question, parent=self):
            return
        remove_history([{k: v for k, v in h.items() if not k.startswith("_")} for h in entries])
        self.load()

    def remove_selected(self):
        sel = self._selected()
        what = f"« {sel[0].get('name', '?')} »" if len(sel) == 1 else f"ces {len(sel)} uploads"
        self._remove(sel, f"Retirer {what} de l'historique ?\n\nRien n'est supprimé sur C411 ni sur le disque.")

    def remove_missing(self):
        gone = [h for h in self.items if not h["_ok"]]
        n = len(gone)
        self._remove(gone, f"Retirer {n} upload{'s' if n > 1 else ''} dont le fichier .torrent n'existe plus ?")

    def _menu(self, e):
        iid = self.tree.identify_row(e.y)
        if not iid:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        sel = self._selected()
        m = tk.Menu(self, tearoff=0, bg=T.SURFACE2, fg=T.TEXT, activebackground=T.ACCENT_SOFT,
                    activeforeground=T.TEXT, bd=0)
        one = sel[0] if len(sel) == 1 else None
        if one and one.get("url"):
            m.add_command(label="Ouvrir sur C411", command=self.open_url)
        if one:
            m.add_command(label="Copier le nom", command=lambda: (self.clipboard_clear(),
                                                                  self.clipboard_append(one.get("name", ""))))
            t = Path(one["torrent"]) if one.get("torrent") else None
            if t and t.exists():
                m.add_command(label="Afficher le .torrent", command=lambda: _reveal(t))
            if one.get("infohash") and one.get("action") != "Correction":
                m.add_command(label="Corriger…", command=self.fix)
            m.add_separator()
        m.add_command(label="Retirer de l'historique", command=self.remove_selected)
        m.tk_popup(e.x_root, e.y_root)


def _reveal(path: Path):
    """Ouvre l'explorateur sur le fichier (sélectionné sous Windows)."""
    import subprocess
    import sys
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        webbrowser.open(path.parent.as_uri())


# ═══════════════════════════════════════════════════════════════════════════

class UpdateDialog(Dialog):
    """Nouvelle version : notes de version, puis téléchargement et redémarrage (exécutable Windows)."""

    def __init__(self, parent, rel: "updater.Release"):
        super().__init__(parent, "Mise à jour", 760, 620)
        self.app, self.rel = parent, rel
        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=20, pady=(20, 0))
        label(body, f"Forge411 {rel.version} est disponible", font=T.F_BIG).pack(fill="x")
        self.head_sub = label(body, f"Tu utilises la version {__version__}. Voici ce qui change avant d'installer :",
                              fg=T.MUTED)
        self.head_sub.pack(fill="x", pady=(2, 12))
        box = self.notes_box = tk.Frame(body, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER)
        box.pack(fill="both", expand=True)
        self.body = body
        self.notes = tk.Text(box, height=10, bg=T.SURFACE, fg=T.TEXT, relief="flat", wrap="word", padx=16, pady=12,
                             font=T.F_UI, cursor="arrow", highlightthickness=0, spacing1=2, spacing3=2)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.notes.yview)
        self.notes.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.notes.pack(fill="both", expand=True)
        n = self.notes
        n.tag_configure("ver", font=T.F_H2, foreground=T.ACCENT, spacing1=10, spacing3=4)
        n.tag_configure("date", font=T.F_SMALL, foreground=T.FAINT)
        n.tag_configure("sec", font=T.F_SMALL_B, foreground=T.MUTED, spacing1=8, spacing3=2)
        n.tag_configure("li", lmargin1=8, lmargin2=24)
        n.tag_configure("b", font=T.F_UI_B)
        n.tag_configure("code", font=T.F_MONO, foreground=T.ACCENT)
        n.tag_configure("muted", foreground=T.MUTED)
        n.insert("end", "Chargement des nouveautés…", "muted")
        n.configure(state="disabled")
        run_bg(lambda: updater.changelog(rel), self._show_notes,
               lambda e: self._show_notes([(rel.version, "", rel.notes or "Pas de notes de version.")]))
        self.blocker = updater.self_update_blocker(rel)
        self.msg = autowrap(label(body, self.blocker, fg=T.WARNING if self.blocker else T.MUTED, font=T.F_SMALL))
        self.msg.pack(fill="x", pady=(10, 0))

        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=20, pady=16)
        if self.blocker:
            Btn(bar, "Ouvrir la page de la release", lambda: webbrowser.open(rel.page), kind="primary").pack(side="right")
        else:
            self.go = Btn(bar, "Installer et redémarrer", self.start, kind="primary")
            self.go.pack(side="right")
            Btn(bar, "Page de la release", lambda: webbrowser.open(rel.page), kind="ghost").pack(side="right", padx=(0, 8))
        self.later = Btn(bar, "Plus tard", self.destroy, kind="ghost")
        self.later.pack(side="left")
        self.skip = Btn(bar, "Ignorer cette version", self.skip_version, kind="ghost")
        self.skip.pack(side="left", padx=(8, 0))

    def _show_notes(self, sections):
        import re
        if not self.winfo_exists():
            return
        n = self.notes
        n.configure(state="normal")
        n.delete("1.0", "end")
        for version, date, text in sections:
            n.insert("end", f"Version {version}", "ver")
            n.insert("end", f"   {date}\n" if date else "\n", ("ver", "date") if date else "ver")
            for line in text.splitlines():
                line = line.rstrip()
                if not line:
                    continue
                if line.startswith("### "):
                    n.insert("end", line[4:].upper() + "\n", "sec")
                    continue
                bullet = line.lstrip().startswith(("- ", "* "))
                body = line.lstrip()[2:] if bullet else line
                if bullet:
                    n.insert("end", "•  ", "li")
                for k, part in enumerate(re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", body)):
                    if part.startswith("**") and part.endswith("**"):
                        n.insert("end", part[2:-2], ("b", "li") if bullet else "b")
                    elif part.startswith("`") and part.endswith("`"):
                        n.insert("end", part[1:-1], ("code", "li") if bullet else "code")
                    elif part:
                        n.insert("end", part, "li" if bullet else ())
                n.insert("end", "\n", "li" if bullet else ())
        n.configure(state="disabled")

    def skip_version(self):
        self.app.cfg.update({"skip_version": self.rel.version})
        self.destroy()

    # ── Installation : trois étapes visibles ─────────────────────────────
    PHASES = ("Téléchargement", "Vérification par l'antivirus Windows", "Installation et redémarrage")

    def _build_progress(self):
        self.prog = tk.Frame(self.body, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER)
        inner = tk.Frame(self.prog, bg=T.SURFACE)
        inner.pack(fill="both", expand=True, padx=24, pady=20)
        label(inner, f"Installation de Forge411 {self.rel.version}", font=T.F_H2, bg=T.SURFACE).pack(fill="x")
        autowrap(label(inner, "Ne ferme pas Forge411 : il redémarre tout seul à la fin.", fg=T.MUTED,
                       font=T.F_SMALL, bg=T.SURFACE)).pack(fill="x", pady=(2, 16))
        self.rows = []
        for i, name in enumerate(self.PHASES):
            row = tk.Frame(inner, bg=T.SURFACE)
            row.pack(fill="x", pady=(0, 12))
            icon = tk.Label(row, text=str(i + 1), width=3, bg=T.SURFACE2, fg=T.FAINT, font=T.F_SMALL_B)
            icon.pack(side="left", anchor="n", pady=(1, 0))
            col = tk.Frame(row, bg=T.SURFACE)
            col.pack(side="left", fill="x", expand=True, padx=(12, 0))
            title = label(col, name, fg=T.FAINT, font=T.F_UI_B, bg=T.SURFACE)
            title.pack(fill="x")
            detail = autowrap(label(col, "", fg=T.MUTED, font=T.F_SMALL, bg=T.SURFACE))
            detail.pack(fill="x")
            bar = ttk.Progressbar(col, mode="determinate", maximum=100)
            self.rows.append((icon, title, detail, bar))

    def _phase(self, i, state, detail=""):
        """state : active | done | error."""
        icon, title, det, bar = self.rows[i]
        if state == "active":
            icon.configure(bg=T.ACCENT, fg=T.ON_ACCENT, text=str(i + 1))
            title.configure(fg=T.TEXT)
            if not bar.winfo_ismapped():
                bar.pack(fill="x", pady=(6, 0))
        elif state == "done":
            icon.configure(bg=T.SUCCESS_SOFT, fg=T.SUCCESS, text="✓")
            title.configure(fg=T.MUTED)
            bar.stop()
            bar.pack_forget()
        else:
            icon.configure(bg=T.ERROR_SOFT, fg=T.ERROR, text="✕")
            title.configure(fg=T.ERROR)
            bar.stop()
            bar.pack_forget()
        det.configure(text=detail, fg=T.ERROR if state == "error" else T.MUTED)

    def start(self):
        import time
        if self.app._busy:
            self.msg.configure(text="Une opération est en cours : attends qu'elle se termine.", fg=T.WARNING)
            return
        for b in (self.go, self.later, self.skip):
            b.set_enabled(False)
        self.btn_bar = self.go.master
        self.btn_bar.pack_forget()                    # rien à cliquer pendant l'installation
        self.head_sub.configure(text="Installation en cours : suis les étapes ci-dessous.")
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.unbind("<Escape>")
        if not hasattr(self, "prog"):
            self._build_progress()
        self.notes_box.pack_forget()
        self.prog.pack(fill="both", expand=True, before=self.msg)
        self.msg.configure(text="")
        for k in range(3):
            icon, title, det, bar = self.rows[k]
            icon.configure(bg=T.SURFACE2, fg=T.FAINT, text=str(k + 1))
            title.configure(fg=T.FAINT)
            det.configure(text="")
            bar.pack_forget()
        self._phase(0, "active", "Connexion à GitHub…")
        dest = updater.current_exe().with_name(updater.UPDATE_NAME)
        t0, last = time.monotonic(), [0.0]

        def progress(done, total):
            now = time.monotonic()
            if now - last[0] < 0.15 and done != total:
                return
            last[0] = now
            el = max(now - t0, 0.001)
            speed = done / el
            pct = done * 100 / total if total else 0
            text = f"{pct:.0f} %  ·  {done / 1048576:.1f} Mo" + (f" sur {total / 1048576:.1f} Mo" if total else "")
            if speed > 0 and total:
                eta = (total - done) / speed
                text += f"  ·  {speed / 1048576:.1f} Mo/s  ·  reste {int(eta)} s"
            UI.call(self._download_progress, pct, text)

        def scanning(_):
            UI.call(self._scan_started)

        def work():
            new = updater.download(self.rel, dest, progress)
            updater.wait_scanned(new, scanning)
            UI.call(self._install_started)
            updater.install(new)              # lancement hors du thread d'interface (fichier parfois retenu)
            return new
        run_bg(work, self._downloaded, self._failed)

    def _download_progress(self, pct, text):
        if self.winfo_exists():
            self.rows[0][3].configure(value=pct)
            self._phase(0, "active", text)

    def _scan_started(self):
        if not self.winfo_exists():
            return
        self._phase(0, "done", "Fichier vérifié (SHA-256).")
        self._phase(1, "active", "Windows analyse le nouveau programme : cela peut prendre jusqu'à une minute.")
        bar = self.rows[1][3]
        bar.configure(mode="indeterminate")
        bar.start(12)

    def _install_started(self):
        if not self.winfo_exists():
            return
        self._phase(1, "done", "Aucun blocage.")
        self._phase(2, "active", "Forge411 va se fermer ; une fenêtre suit l'installation, puis la nouvelle "
                                 "version s'ouvre.")
        bar = self.rows[2][3]
        bar.configure(mode="indeterminate")
        bar.start(12)

    def _downloaded(self, new):
        self.after(1500, self.app.quit_for_update)

    def _failed(self, e):
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda ev: self.destroy())
        for k, (icon, title, det, bar) in enumerate(self.rows):
            if title.cget("fg") == T.TEXT:                 # étape en cours
                self._phase(k, "error", str(e))
        self.msg.configure(text="La mise à jour n'a pas été installée : ta version actuelle est intacte.", fg=T.MUTED)
        self.btn_bar.pack(fill="x", padx=20, pady=16)
        for b in (self.go, self.later, self.skip):
            b.set_enabled(True)
        self.go.set_text("Réessayer")


# ═══════════════════════════════════════════════════════════════════════════

class ShotLinksDialog(Dialog):
    """XXX : liens directs des captures déposées sur postimg.cc (ou zupimages.net), en trois étapes."""

    PLACEHOLDER = "Colle ici les liens directs, par exemple :\nhttps://i.postimg.cc/Xyz12345/capture-01.png"

    @classmethod
    def ask(cls, parent, folder, extracted: int, minimum: int):
        d = cls(parent, folder, extracted, minimum)
        d.show()
        return d.result

    def __init__(self, parent, folder, extracted, minimum):
        super().__init__(parent, "Captures XXX : postimg.cc", 660, 560)
        from .. import rules
        from .. import screens as SC
        self.result, self.minimum, self.hosts, self.folder = None, minimum, rules.XXX_SHOT_HOSTS, folder
        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=24, pady=(20, 0))
        label(body, "Héberger les captures sur postimg.cc", font=T.F_BIG).pack(fill="x")
        label(body, f"La Team Pending exige au moins {minimum} captures, hors bannière, sur postimg.cc ou zupimages.net.",
              fg=T.MUTED, font=T.F_SMALL).pack(fill="x", pady=(2, 14))

        steps = tk.Frame(body, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER)
        steps.pack(fill="x")
        self._step(steps, 1, "Ouvre le dossier des captures", f"{extracted} image(s) prête(s)",
                   "Ouvrir le dossier", lambda: SC.open_folder(folder))
        self._step(steps, 2, "Glisse-les sur postimages.org", "Ne pas redimensionner  ·  Pas d'expiration",
                   "Ouvrir postimages.org", lambda: webbrowser.open(SC.POSTIMG_URL))
        self._step(steps, 3, "Copie les liens directs", "Après l'envoi : liste « Liens directs », bouton Copier",
                   None, None, last=True)

        head = tk.Frame(body, bg=T.BG)
        head.pack(fill="x", pady=(16, 4))
        label(head, "Liens directs", font=T.F_UI_B).pack(side="left")
        self.badge = tk.Label(head, text="", font=T.F_SMALL_B, padx=8, pady=1)
        self.badge.pack(side="right")
        self.text = TextArea(body, height=6)
        self.text.pack(fill="both", expand=True)
        self.text.text.configure(wrap="none")
        self._placeholder(True)
        self.text.text.bind("<FocusIn>", lambda e: self._placeholder(False))
        self.text.text.bind("<FocusOut>", lambda e: self._placeholder(not self.text.get().strip()))
        self.text.text.bind("<KeyRelease>", lambda e: self._count())
        self.text.text.bind("<<Paste>>", lambda e: (self._placeholder(False), self.after(10, self._count)))
        self.msg = label(body, "", fg=T.MUTED, font=T.F_SMALL)
        self.msg.pack(fill="x", pady=(6, 0))

        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=24, pady=16)
        self.ok_btn = Btn(bar, "Ajouter à la description", self.ok, kind="primary")
        self.ok_btn.pack(side="right")
        Btn(bar, "Annuler", self.destroy, kind="ghost").pack(side="left")
        self._count()

    def _step(self, parent, n, title, detail, btn_text, cmd, last=False):
        row = tk.Frame(parent, bg=T.SURFACE)
        row.pack(fill="x", padx=16, pady=(12, 12 if last else 0))
        tk.Label(row, text=str(n), width=3, bg=T.ACCENT_SOFT, fg=T.ACCENT, font=T.F_SMALL_B).pack(
            side="left", anchor="n", pady=(2, 0))
        col = tk.Frame(row, bg=T.SURFACE)
        col.pack(side="left", fill="x", expand=True, padx=(12, 0))
        label(col, title, font=T.F_UI_B, bg=T.SURFACE).pack(fill="x")
        label(col, detail, fg=T.MUTED, font=T.F_SMALL, bg=T.SURFACE).pack(fill="x")
        if btn_text:
            Btn(row, btn_text, cmd, small=True).pack(side="right")
        if not last:
            tk.Frame(parent, bg=T.BORDER, height=1).pack(fill="x", padx=16, pady=(12, 0))

    def _is_placeholder(self):
        return self.text.text.get("1.0", "end-1c") == self.PLACEHOLDER

    def _placeholder(self, on):
        t = self.text.text
        if on and not t.get("1.0", "end-1c").strip():
            t.insert("1.0", self.PLACEHOLDER)
            t.configure(fg=T.FAINT)
        elif not on and self._is_placeholder():
            t.delete("1.0", "end")
            t.configure(fg=T.TEXT)

    def _links(self):
        from .. import screens as SC
        if self._is_placeholder():
            return []
        return SC.direct_links(self.text.get(), self.hosts)

    def _count(self):
        import re
        links = self._links()
        n = len(links)
        if not self._is_placeholder():
            self.text.text.configure(fg=T.TEXT)
        raw = [] if self._is_placeholder() else re.findall(r"https?://\S+", self.text.get())
        ignored = len(raw) - n
        ok = n >= self.minimum
        self.badge.configure(text=f"{n} / {self.minimum}",
                             bg=T.SUCCESS_SOFT if ok else (T.WARNING_SOFT if n else T.SURFACE2),
                             fg=T.SUCCESS if ok else (T.WARNING if n else T.MUTED))
        if ignored > 0:
            self.msg.configure(text=f"{ignored} lien(s) ignoré(s) : ce ne sont pas des liens directs d'image "
                                    "(choisis « Liens directs », pas « Page de l'image »).", fg=T.WARNING)
        elif n and not ok:
            self.msg.configure(text=f"Encore {self.minimum - n} capture(s) à ajouter pour atteindre le minimum.",
                               fg=T.WARNING)
        elif ok:
            self.msg.configure(text="✓ Minimum atteint.", fg=T.SUCCESS)
        else:
            self.msg.configure(text="", fg=T.MUTED)
        self.ok_btn.set_text(f"Ajouter {n} capture(s)" if n else "Ajouter à la description")
        self.ok_btn.set_enabled(n > 0)

    def ok(self):
        self.result = self._links()
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════

class CorrectionDialog(Dialog):
    """Retour de la Team Pending : choix de l'upload et message à corriger."""

    @classmethod
    def ask(cls, parent, entry=None):
        d = cls(parent, entry)
        d.show()
        return d.result

    def __init__(self, parent, entry=None):
        super().__init__(parent, "Corriger une validation", 780, 640)
        self.result = None
        self.entries = [h for h in read_history() if h.get("infohash") and h.get("action") != "Correction"]
        seen, uniq = set(), []
        for h in self.entries:
            if h["infohash"] not in seen:
                seen.add(h["infohash"])
                uniq.append(h)
        self.entries = uniq
        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=20, pady=(20, 0))
        label(body, "Corriger un upload après « Modification demandée »", font=T.F_H2).pack(fill="x")
        autowrap(label(body, "Choisis l'upload, colle le message de la Team Pending (page du torrent › Discussion de "
                             "modération), puis Forge411 rouvre l'assistant avec les points à corriger. Le .torrent "
                             "et le seed restent les mêmes.", fg=T.MUTED)).pack(fill="x", pady=(4, 12))
        names = [f"{h.get('name', '?')}  ·  {h.get('date', '')}" for h in self.entries]
        self.pick = tk.StringVar()
        Field(body, "Upload (historique Forge411)", self.pick, values=names, readonly=True,
              help="Uploads envoyés depuis Forge411. Absent ? Colle l'adresse de la page du torrent ci-dessous : "
                   "Forge411 te demandera la source.").pack(fill="x")
        if entry is not None:
            k = next((i for i, h in enumerate(self.entries) if h.get("infohash") == entry.get("infohash")), None)
            if k is not None:
                self.pick.set(names[k])
        elif names:
            self.pick.set(names[0])
        self.url = tk.StringVar()
        Field(body, "Ou adresse de la page du torrent", self.url,
              help="Ex. https://c411.org/torrents/9fb0a873… (l'info-hash suffit).").pack(fill="x", pady=(10, 0))
        label(body, "Message de la Team Pending", fg=T.MUTED, font=T.F_SMALL_B).pack(fill="x", pady=(12, 0))
        self.msg = TextArea(body, height=10, mono=False)
        self.msg.pack(fill="both", expand=True, pady=(3, 0))
        self.err = label(body, "", fg=T.ERROR, font=T.F_SMALL)
        self.err.pack(fill="x", pady=(6, 0))
        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=20, pady=16)
        Btn(bar, "Commencer la correction", self.ok, kind="primary").pack(side="right")
        Btn(bar, "Annuler", self.destroy, kind="ghost").pack(side="left")
        self.names = names

    def ok(self):
        from .. import correction as FIX
        ih = FIX.infohash_of(self.url.get())
        entry = None
        if ih:
            entry = next((h for h in self.entries if h.get("infohash") == ih), {"infohash": ih})
        elif self.pick.get() in self.names:
            entry = self.entries[self.names.index(self.pick.get())]
        if not entry:
            self.err.configure(text="Choisis un upload ou colle l'adresse de la page du torrent.")
            return
        message = self.msg.get().strip()
        if not message:
            self.err.configure(text="Colle le message de la Team Pending (il liste les points à corriger).")
            return
        self.result = (entry, message)
        self.destroy()
