"""Fenêtres secondaires : paramètres, choix multiple, historique, mise à jour."""

import tkinter as tk
import webbrowser
from tkinter import filedialog, ttk

from .. import __version__, updater
from ..api import C411
from ..config import KEY_LINKS, Config, read_history
from . import theme as T
from .widgets import UI, Btn, Card, Field, ScrollFrame, TextArea, Tooltip, autowrap, help_icon, label, link, run_bg


class Dialog(tk.Toplevel):
    def __init__(self, parent, title: str, width: int, height: int):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.configure(bg=T.BG)
        self.transient(parent.winfo_toplevel())
        self.resizable(True, True)
        top = parent.winfo_toplevel()
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
    LABEL_W = 165                      # largeur de la colonne des libellés (px)

    def __init__(self, parent, cfg: Config, first_run: bool = False, section: str = ""):
        super().__init__(parent, "Paramètres", 920, 680)
        self.minsize(820, 560)
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
        self.theme = tk.StringVar(value=T.MODES.get(cfg.get("theme") or "system", "Système"))
        self.check_updates = tk.BooleanVar(value=bool(cfg.get("check_updates")))

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

        nav = tk.Frame(self, bg=T.SIDEBAR, width=210)
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
        self._align_tests, self._test_w = False, 62       # largeur réservée au bouton « Tester »

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
        cell = self._row(g, "Thème", "Système suit le réglage clair / sombre de Windows. Appliqué au redémarrage.")
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
        head.configure(height=48 if (sub or url) else 34)
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
        ttk.Checkbutton(parent, text=text, variable=var, style="Card.TCheckbutton", command=command).pack(
            fill="x", padx=16, pady=(4, 8))

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
        values["theme"] = next((k for k, v in T.MODES.items() if v == self.theme.get()), "system")
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
    def _fix(self, entry):
        app = self.master
        self.destroy()
        app.open_correction(entry)

    def __init__(self, parent):
        super().__init__(parent, "Historique", 820, 560)
        sf = ScrollFrame(self)
        sf.pack(fill="both", expand=True, padx=20, pady=20)
        items = read_history()
        if not items:
            label(sf.inner, "Aucun upload pour l'instant.", fg=T.MUTED).pack(fill="x")
        for h in items:
            card = Card(sf.inner, padding=12)
            card.pack(fill="x", pady=(0, 8), padx=(0, 12))
            top = tk.Frame(card.body, bg=T.SURFACE)
            top.pack(fill="x")
            label(top, h.get("name", "?"), font=T.F_UI_B, wraplength=600).pack(side="left", fill="x", expand=True)
            label(top, " • ".join(x for x in (h.get("type", ""), h.get("action", ""), h.get("date", "")) if x), fg=T.MUTED,
                  font=T.F_SMALL).pack(side="right")
            if h.get("url"):
                row = tk.Frame(card.body, bg=T.SURFACE)
                row.pack(fill="x", pady=(4, 0))
                link = label(row, h["url"], fg=T.ACCENT, font=T.F_SMALL, cursor="hand2")
                link.pack(side="left", fill="x", expand=True)
                link.bind("<Button-1>", lambda e, u=h["url"]: webbrowser.open(u))
                if h.get("infohash") and h.get("action") != "Correction":
                    Btn(row, "Corriger", lambda hh=h: self._fix(hh), small=True).pack(side="right")


# ═══════════════════════════════════════════════════════════════════════════

class UpdateDialog(Dialog):
    """Nouvelle version : notes de version, puis téléchargement et redémarrage (exécutable Windows)."""

    def __init__(self, parent, rel: "updater.Release"):
        super().__init__(parent, "Mise à jour", 680, 540)
        self.app, self.rel = parent, rel
        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=20, pady=(20, 0))
        label(body, f"Forge411 {rel.version} est disponible", font=T.F_BIG).pack(fill="x")
        label(body, f"Tu utilises la version {__version__}.", fg=T.MUTED).pack(fill="x", pady=(2, 12))
        notes = TextArea(body, height=12, mono=False, readonly=True)
        notes.set(rel.notes or "Pas de notes de version.")
        notes.pack(fill="both", expand=True)
        self.blocker = updater.self_update_blocker(rel)
        self.msg = autowrap(label(body, self.blocker, fg=T.WARNING if self.blocker else T.MUTED, font=T.F_SMALL))
        self.msg.pack(fill="x", pady=(10, 0))
        self.bar = ttk.Progressbar(body, mode="determinate", maximum=100)

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

    def skip_version(self):
        self.app.cfg.update({"skip_version": self.rel.version})
        self.destroy()

    def start(self):
        if self.app._busy:
            self.msg.configure(text="Une opération est en cours : attends qu'elle se termine.", fg=T.WARNING)
            return
        for b in (self.go, self.later, self.skip):
            b.set_enabled(False)
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.unbind("<Escape>")
        self.bar.pack(fill="x", pady=(8, 0))
        self.msg.configure(text="Téléchargement…", fg=T.MUTED)
        dest = updater.current_exe().with_name(updater.UPDATE_NAME)

        def progress(done, total):
            pct = done * 100 / total if total else 0
            UI.call(self._progress, pct, f"Téléchargement… {done / 1048576:.1f} Mo"
                    + (f" sur {total / 1048576:.1f} Mo" if total else ""))

        def work():
            new = updater.download(self.rel, dest, progress)
            updater.wait_scanned(new, lambda t: UI.call(self._progress, 100, t))
            updater.install(new)              # lancement hors du thread d'interface (fichier parfois retenu)
            return new
        run_bg(work, self._downloaded, self._failed)

    def _progress(self, pct, text):
        if self.winfo_exists():
            self.bar.configure(value=pct)
            self.msg.configure(text=text)

    def _downloaded(self, new):
        self.msg.configure(text="Fichier vérifié. Redémarrage…", fg=T.SUCCESS)
        self.after(400, self.app.quit_for_update)

    def _failed(self, e):
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda ev: self.destroy())
        self.bar.pack_forget()
        self.msg.configure(text=f"✕ {e}", fg=T.ERROR)
        for b in (self.go, self.later, self.skip):
            b.set_enabled(True)
        self.go.set_text("Réessayer")


# ═══════════════════════════════════════════════════════════════════════════

class ShotLinksDialog(Dialog):
    """XXX : liens directs des captures déposées sur postimg.cc (ou zupimages.net)."""

    @classmethod
    def ask(cls, parent, folder, extracted: int, minimum: int):
        d = cls(parent, folder, extracted, minimum)
        d.show()
        return d.result

    def __init__(self, parent, folder, extracted, minimum):
        super().__init__(parent, "Captures XXX : postimg.cc", 720, 560)
        from .. import rules
        self.result, self.minimum, self.hosts = None, minimum, rules.XXX_SHOT_HOSTS
        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=20, pady=(20, 0))
        label(body, "Dépose les captures sur postimg.cc", font=T.F_H2).pack(fill="x")
        steps = (f"1. Le dossier des captures est ouvert ({extracted} image(s)) : {folder}\n"
                 "2. postimages.org est ouvert dans ton navigateur : glisse-y les images (« Ne pas redimensionner », "
                 "« Pas d'expiration »).\n"
                 "3. Une fois l'envoi terminé, choisis « Liens directs », copie la liste et colle-la ci-dessous.\n"
                 f"La Team Pending exige au moins {minimum} captures hors bannière, sur postimg.cc ou zupimages.net.")
        autowrap(label(body, steps, fg=T.MUTED)).pack(fill="x", pady=(6, 10))
        self.text = TextArea(body, height=12)
        self.text.pack(fill="both", expand=True)
        self.text.text.bind("<KeyRelease>", lambda e: self._count())
        self.text.text.bind("<<Paste>>", lambda e: self.after(10, self._count))
        self.msg = label(body, "", fg=T.MUTED, font=T.F_SMALL)
        self.msg.pack(fill="x", pady=(8, 0))
        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=20, pady=16)
        self.ok_btn = Btn(bar, "Ajouter à la description", self.ok, kind="primary")
        self.ok_btn.pack(side="right")
        Btn(bar, "Ouvrir postimg.cc", lambda: webbrowser.open("https://postimages.org/"), kind="ghost").pack(
            side="right", padx=(0, 8))
        Btn(bar, "Annuler", self.destroy, kind="ghost").pack(side="left")
        self._count()

    def _links(self):
        from .. import screens as SC
        return SC.direct_links(self.text.get(), self.hosts)

    def _count(self):
        n = len(self._links())
        ok = n >= self.minimum
        self.msg.configure(text=f"{n} lien(s) direct(s) reconnu(s) sur {self.minimum} minimum.",
                           fg=T.SUCCESS if ok else (T.WARNING if n else T.MUTED))
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
