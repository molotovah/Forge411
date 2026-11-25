"""Fenêtres secondaires : paramètres, choix multiple, historique, mise à jour."""

import tkinter as tk
import webbrowser
from tkinter import filedialog, ttk

from .. import __version__, updater
from ..api import C411
from ..config import KEY_LINKS, Config, read_history
from . import theme as T
from .widgets import UI, Btn, Card, Field, ScrollFrame, TextArea, autowrap, label, run_bg


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
    def __init__(self, parent, cfg: Config, first_run: bool = False):
        super().__init__(parent, "Paramètres", 760, 760)
        self.cfg = cfg
        self.saved = False
        sf = ScrollFrame(self)
        sf.pack(fill="both", expand=True, padx=20, pady=(20, 0))
        root = sf.inner
        if first_run:
            label(root, "Bienvenue dans Forge411 !", font=T.F_BIG).pack(fill="x")
            label(root, "Deux informations suffisent pour commencer : ta clé API C411 et ton URL d'annonce. "
                        "Les autres clés débloquent la recherche automatique des fiches.",
                  fg=T.MUTED, wraplength=640).pack(fill="x", pady=(4, 14))

        keys = ("c411_api_key", "tracker_url", "tmdb_api_key", "rawg_api_key", "google_books_key", "tpdb_api_key",
                "team_tag",
                "output_dir", "seed_dir")
        self.v = {k: tk.StringVar(value=cfg.get(k) or "") for k in keys}

        c = self._card(root, "C411", "Obligatoire.")
        Field(c, "Clé API", self.v["c411_api_key"], show="•", url=KEY_LINKS["c411_api_key"],
              help="Profil C411 › Intégrations. Coche les droits brouillons (drafts:rw), upload (upload:write) "
                   "pour publier directement, et « Profil (lecture) » pour la page Mon profil.").pack(fill="x")
        Field(c, "URL d'annonce (avec passkey)", self.v["tracker_url"], show="•", url=KEY_LINKS["tracker_url"],
              help="Sur ton profil C411 (fais défiler). Ton URL personnelle https://c411.org/announce/… est écrite dans chaque torrent créé. "
                   "Ne la partage jamais : elle identifie ton compte.").pack(fill="x", pady=(12, 0))
        self.c411_msg = self._test_row(c, self.test_c411)

        c = self._card(root, "Bases de données", "Facultatif : sans clé, tu saisis les fiches à la main.")
        Field(c, "TMDB : films et séries", self.v["tmdb_api_key"], show="•", url=KEY_LINKS["tmdb_api_key"],
              help="Clé d'API (v3) ou jeton d'accès en lecture (v4) : les deux fonctionnent.").pack(fill="x")
        self.tmdb_msg = self._test_row(c, self.test_tmdb)
        Field(c, "RAWG : jeux vidéo", self.v["rawg_api_key"], show="•", url=KEY_LINKS["rawg_api_key"],
              help="Crée un compte RAWG puis récupère ta clé sur la page API (gratuite).").pack(fill="x", pady=(12, 0))
        self.rawg_msg = self._test_row(c, self.test_rawg)
        Field(c, "Google Books : livres (facultatif)", self.v["google_books_key"], show="•",
              url=KEY_LINKS["google_books_key"],
              help="Sans clé, Forge411 utilise Open Library. Une clé Google Books ajoute ses fiches.").pack(
            fill="x", pady=(12, 0))
        Field(c, "ThePornDB : XXX Films et VR (facultatif)", self.v["tpdb_api_key"], show="•",
              url=KEY_LINKS["tpdb_api_key"],
              help="Jeton personnel ThePornDB (compte › API Tokens). La fiche choisie est jointe à l'upload "
                   "(tpdbData) pour les sous-catégories XXX Films et VR.").pack(fill="x", pady=(12, 0))
        self.tpdb_msg = self._test_row(c, self.test_tpdb)
        label(c, "Musique : MusicBrainz, sans clé.", fg=T.FAINT, font=T.F_SMALL).pack(fill="x", pady=(10, 0))

        c = self._card(root, "Équipe", "Pour tes propres releases. Une release reprise garde toujours le tag d'origine (règle anti-detag).")
        row = tk.Frame(c, bg=T.SURFACE)
        row.pack(fill="x")
        Field(row, "Tag d'équipe", self.v["team_tag"], width=16,
              help="Ajouté après le dernier tiret du nom, ex. -MONTAG. Lettres et chiffres uniquement.").pack(
            side="left", fill="x", expand=True)
        prof = getattr(parent, "profile_cache", None)
        team = prof[0].team_tag if prof else ""
        if team:
            Btn(row, f"Reprendre « {team} » (profil C411)", lambda: self.v["team_tag"].set(team), small=True).pack(
                side="left", padx=(8, 0), anchor="s", pady=(0, 2))
        self.team_auto = tk.BooleanVar(value=bool(cfg.get("team_tag_auto")))
        ttk.Checkbutton(c, text="Le proposer automatiquement quand la source n'a pas de tag (au lieu de NOTAG)",
                        variable=self.team_auto, style="Card.TCheckbutton").pack(fill="x", pady=(8, 0))

        c = self._card(root, "Dossiers")
        self._dir_field(c, "Dossier de sortie (.torrent et .nfo)", "output_dir",
                        "Les torrents vont dans le sous-dossier « torrents ». Fais-le surveiller par ton client "
                        "torrent pour que le seed démarre tout seul.")
        self._dir_field(c, "Dossier de seed (facultatif)", "seed_dir",
                        "Là où ton client torrent attend les données. Forge411 vérifie que la source s'y trouve "
                        "et propose de l'y déplacer.")

        c = self._card(root, "Note par défaut pour la modération")
        self.note = tk.Text(c, height=3, bg=T.SURFACE2, fg=T.TEXT, insertbackground=T.TEXT,
                            relief="flat", padx=8, pady=6, font=T.F_UI, wrap="word")
        self.note.insert("1.0", cfg.get("uploader_note") or "")
        self.note.pack(fill="x")

        from .. import clients as CL
        from .. import screens as SC
        c = self._card(root, "Client torrent", "Facultatif. Forge411 y ajoute le torrent et attend le seed avant "
                                               "de publier (C411 refuse un torrent qui n'est pas seedé).")
        self.client_kind = tk.StringVar(value=CL.KINDS.get(cfg.get("client_kind") or "", "Aucun"))
        for k in ("client_url", "client_user", "client_password", "client_label", "ffmpeg_path"):
            self.v[k] = tk.StringVar(value=cfg.get(k) or "")
        grid = tk.Frame(c, bg=T.SURFACE)
        grid.pack(fill="x")
        grid.columnconfigure((0, 1), weight=1, uniform="cl")
        Field(grid, "Client", self.client_kind, values=list(CL.KINDS.values()), readonly=True,
              help="Active l'interface web du client (qBittorrent : Options › Interface web).").grid(
            row=0, column=0, sticky="ew", padx=(0, 12))
        Field(grid, "Adresse de l'interface web", self.v["client_url"],
              help="Ex. http://localhost:8080 (qBittorrent), http://localhost:9091 (Transmission), "
                   "http://localhost:8112 (Deluge).").grid(row=0, column=1, sticky="ew")
        Field(grid, "Utilisateur", self.v["client_user"], help="Vide pour Deluge (mot de passe seul).").grid(
            row=1, column=0, sticky="ew", padx=(0, 12), pady=(10, 0))
        Field(grid, "Mot de passe", self.v["client_password"], show="•").grid(row=1, column=1, sticky="ew", pady=(10, 0))
        Field(grid, "Catégorie / étiquette", self.v["client_label"],
              help="Catégorie qBittorrent, étiquette Transmission ou Deluge (facultatif).").grid(
            row=2, column=0, sticky="ew", padx=(0, 12), pady=(10, 0))
        self.client_auto = tk.BooleanVar(value=bool(cfg.get("client_auto")))
        ttk.Checkbutton(c, text="Ajouter le torrent au client dès sa création", variable=self.client_auto,
                        style="Card.TCheckbutton").pack(fill="x", pady=(10, 0))
        self.client_msg = self._test_row(c, self.test_client)

        c = self._card(root, "Captures d'écran", "Pour les vidéos : extraites avec ffmpeg puis envoyées sur un "
                                                  "hébergeur accepté par C411, à ta demande uniquement.")
        row = tk.Frame(c, bg=T.SURFACE)
        row.pack(fill="x")
        Field(row, "ffmpeg", self.v["ffmpeg_path"],
              help="Chemin de ffmpeg.exe. Vide : ffmpeg du PATH, sinon celui installé par Forge411.").pack(
            side="left", fill="x", expand=True)

        def browse_ffmpeg():
            p = filedialog.askopenfilename(parent=self, title="ffmpeg", filetypes=[("ffmpeg", "ffmpeg*"), ("Tous", "*.*")])
            if p:
                self.v["ffmpeg_path"].set(p)
        Btn(row, "Parcourir", browse_ffmpeg, small=True).pack(side="left", padx=(8, 0), anchor="n", pady=(20, 0))
        from .. import ffmpeg_setup as FS
        frow = tk.Frame(c, bg=T.SURFACE)
        frow.pack(fill="x", pady=(8, 0))
        self.ffmpeg_lbl = autowrap(label(frow, "", fg=T.MUTED, font=T.F_SMALL))
        self.ffmpeg_lbl.pack(side="left", fill="x", expand=True)
        self.ffmpeg_btn = Btn(frow, "", self.install_ffmpeg, small=True)
        if FS.supported():
            self.ffmpeg_btn.pack(side="right")
        self._ffmpeg_state()
        self.v["ffmpeg_path"].trace_add("write", lambda *_: self._ffmpeg_state())
        grid = tk.Frame(c, bg=T.SURFACE)
        grid.pack(fill="x", pady=(10, 0))
        grid.columnconfigure((0, 1), weight=1, uniform="sc")
        self.screens_host = tk.StringVar(value=SC.HOSTS.get(cfg.get("screens_host") or "pixhost", "pixhost.to"))
        Field(grid, "Hébergeur", self.screens_host, values=list(SC.HOSTS.values()), readonly=True,
              help="Les deux sont dans la liste blanche d'images de C411. Le contenu XXX passe toujours par "
                   "pixhost, marqué adulte.").grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.screens_count = tk.StringVar(value=str(cfg.get("screens_count") or 4))
        Field(grid, "Nombre de captures", self.screens_count, values=["2", "3", "4", "6", "8"], readonly=True).grid(
            row=0, column=1, sticky="ew")

        c = self._card(root, "Apparence", "Couleurs de C411. Le mode Système suit le réglage clair / sombre de Windows.")
        self.theme = tk.StringVar(value=T.MODES.get(cfg.get("theme") or "system", "Système"))
        Field(c, "Mode", self.theme, values=list(T.MODES.values()), readonly=True,
              help="Appliqué au redémarrage de Forge411.").pack(fill="x")

        c = self._card(root, "Mises à jour")
        self.check_updates = tk.BooleanVar(value=bool(cfg.get("check_updates")))
        ttk.Checkbutton(c, text="Vérifier au démarrage si une nouvelle version est sortie sur GitHub",
                        variable=self.check_updates).pack(fill="x")

        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=20, pady=16)
        Btn(bar, "Enregistrer", self.save, kind="primary").pack(side="right")
        Btn(bar, "Annuler", self.destroy, kind="ghost").pack(side="right", padx=(0, 8))

    def _card(self, parent, title, subtitle=""):
        card = Card(parent)
        card.pack(fill="x", pady=(0, 12), padx=(0, 12))
        label(card.body, title, font=T.F_H2).pack(fill="x")
        if subtitle:
            autowrap(label(card.body, subtitle, fg=T.MUTED, font=T.F_SMALL)).pack(fill="x", pady=(2, 0))
        tk.Frame(card.body, bg=T.SURFACE, height=10).pack(fill="x")
        return card.body

    def _test_row(self, parent, cmd):
        row = tk.Frame(parent, bg=T.SURFACE)
        row.pack(fill="x", pady=(8, 0))
        Btn(row, "Tester", cmd, small=True).pack(side="left")
        msg = label(row, "", fg=T.MUTED, font=T.F_SMALL)
        msg.pack(side="left", padx=(10, 0))
        return msg

    def _dir_field(self, parent, text, key, help_text):
        row = tk.Frame(parent, bg=T.SURFACE)
        row.pack(fill="x", pady=(0, 10))
        f = Field(row, text, self.v[key], help=help_text)
        f.pack(side="left", fill="x", expand=True)

        def browse():
            p = filedialog.askdirectory(parent=self, initialdir=self.v[key].get() or None)
            if p:
                self.v[key].set(p)
        Btn(row, "Parcourir", browse, small=True).pack(side="left", padx=(8, 0), anchor="s", pady=(0, 2))

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
            self.ffmpeg_lbl.configure(text=f"✓  ffmpeg trouvé : {found}", fg=T.SUCCESS)
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
                link = label(card.body, h["url"], fg=T.ACCENT, font=T.F_SMALL, cursor="hand2")
                link.pack(fill="x", pady=(4, 0))
                link.bind("<Button-1>", lambda e, u=h["url"]: webbrowser.open(u))


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
        dest = updater.current_exe().with_name("Forge411.new.exe")

        def progress(done, total):
            pct = done * 100 / total if total else 0
            UI.call(self._progress, pct, f"Téléchargement… {done / 1048576:.1f} Mo"
                    + (f" sur {total / 1048576:.1f} Mo" if total else ""))

        run_bg(lambda: updater.download(self.rel, dest, progress), self._downloaded, self._failed)

    def _progress(self, pct, text):
        if self.winfo_exists():
            self.bar.configure(value=pct)
            self.msg.configure(text=text)

    def _downloaded(self, new):
        try:
            updater.install(new)
        except Exception as e:
            self._failed(e)
            return
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
