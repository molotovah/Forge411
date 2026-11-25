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
        c = self._card(root, "Client torrent", "Recommandé. Forge411 ajoute le torrent au client et attend le seed "
                                               "avant de publier : C411 refuse un torrent qui n'est pas seedé.")
        self.client_kind = tk.StringVar(value=CL.KINDS.get(cfg.get("client_kind") or "", "Aucun"))
        for k in ("client_url", "client_user", "client_password", "client_label", "ffmpeg_path", "client_path_local",
                  "client_path_remote"):
            self.v[k] = tk.StringVar(value=cfg.get(k) or "")
        top = tk.Frame(c, bg=T.SURFACE)
        top.pack(fill="x")
        top.columnconfigure(1, weight=1)
        Field(top, "Client", self.client_kind, values=list(CL.KINDS.values()), readonly=True, width=14,
              help="Ton logiciel de torrent. Son interface web doit être activée.").grid(
            row=0, column=0, sticky="ew", padx=(0, 12))
        Field(top, "Adresse de l'interface web", self.v["client_url"],
              help="Ex. http://localhost:8080 (qBittorrent sur ce PC) ou http://192.168.1.10:8080 (NAS). "
                   "« Détecter » cherche les clients sur ce PC et sur la machine de ton dossier de seed.").grid(
            row=0, column=1, sticky="ew")
        Btn(top, "Détecter", self.detect_client, small=True).grid(row=0, column=2, sticky="s", padx=(8, 0), pady=(0, 2))
        self.client_help = autowrap(label(c, "", fg=T.FAINT, font=T.F_SMALL))
        self.client_help.pack(fill="x", pady=(6, 0))
        self.client_fields = tk.Frame(c, bg=T.SURFACE)
        self.client_fields.pack(fill="x")
        grid = tk.Frame(self.client_fields, bg=T.SURFACE)
        grid.pack(fill="x")
        grid.columnconfigure((0, 1), weight=1, uniform="cl")
        self.user_field = Field(grid, "Utilisateur", self.v["client_user"],
                                help="Identifiant de l'interface web (qBittorrent, Transmission).")
        self.user_field.grid(row=0, column=0, sticky="ew", padx=(0, 12), pady=(10, 0))
        Field(grid, "Mot de passe", self.v["client_password"], show="•").grid(row=0, column=1, sticky="ew", pady=(10, 0))
        Field(grid, "Catégorie / étiquette (facultatif)", self.v["client_label"],
              help="Catégorie qBittorrent, étiquette Transmission ou Deluge, pour retrouver tes uploads.").grid(
            row=1, column=0, sticky="ew", padx=(0, 12), pady=(10, 0))
        self.client_remote = tk.BooleanVar(value=bool(cfg.get("client_path_local") or cfg.get("client_path_remote"))
                                           or not CL.is_local(cfg.get("client_url") or ""))
        ttk.Checkbutton(self.client_fields, text="Le client tourne sur un autre appareil (NAS, Docker, seedbox)",
                        variable=self.client_remote, command=self._client_state,
                        style="Card.TCheckbutton").pack(fill="x", pady=(10, 0))
        self.remote_box = tk.Frame(self.client_fields, bg=T.SURFACE)
        autowrap(label(self.remote_box, "Le même dossier n'a pas le même chemin des deux côtés : indique le début du "
                                        "chemin vu par Windows et son équivalent dans le client. « Proposer » le "
                                        "déduit de ton dossier de seed et du dossier par défaut du client.",
                       fg=T.FAINT, font=T.F_SMALL)).pack(fill="x", pady=(6, 0))
        rg = tk.Frame(self.remote_box, bg=T.SURFACE)
        rg.pack(fill="x")
        rg.columnconfigure((0, 1), weight=1, uniform="rm")
        Field(rg, "Dossier vu par Windows", self.v["client_path_local"],
              help="Ex. \\\\192.168.1.251\\Torrents (partage réseau).").grid(
            row=0, column=0, sticky="ew", padx=(0, 12), pady=(6, 0))
        Field(rg, "Même dossier vu par le client", self.v["client_path_remote"],
              help="Ex. /downloads pour un conteneur qui monte ce partage sur /downloads.").grid(
            row=0, column=1, sticky="ew", pady=(6, 0))
        Btn(rg, "Proposer", self.suggest_paths, small=True).grid(row=0, column=2, sticky="s", padx=(8, 0), pady=(0, 2))
        self.path_preview = autowrap(label(self.client_fields, "", fg=T.MUTED, font=T.F_SMALL))
        self.path_preview.pack(fill="x", pady=(8, 0))
        self.client_auto = tk.BooleanVar(value=bool(cfg.get("client_auto", True)))
        ttk.Checkbutton(self.client_fields, text="Ajouter le torrent au client dès sa création (conseillé)",
                        variable=self.client_auto, style="Card.TCheckbutton").pack(fill="x", pady=(10, 0))
        self.client_msg = self._test_row(self.client_fields, self.test_client)
        self._client_prev = self.client_kind.get()
        self.client_kind.trace_add("write", lambda *_: self._client_kind_changed())
        for k in ("client_url", "client_path_local", "client_path_remote", "seed_dir"):
            self.v[k].trace_add("write", lambda *_: self._client_state())
        self._client_state()

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
              help="Les deux sont dans la liste blanche d'images de C411. Pour le XXX, la Team Pending n'accepte que "
                   "postimg.cc ou zupimages.net : Forge411 extrait les captures et tu les déposes sur postimg.cc.").grid(row=0, column=0, sticky="ew", padx=(0, 12))
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
            self.client_help.configure(text="Sans client, tu ajoutes toi-même le torrent et tu confirmes le seed "
                                            "avant de publier.")
            return
        if not self.client_fields.winfo_ismapped():
            self.client_fields.pack(fill="x", after=self.client_help)
        self.client_help.configure(text=CL.ENABLE_HELP.get(kind, ""))
        self.user_field.grid() if kind != "deluge" else self.user_field.grid_remove()
        if self.client_remote.get():
            self.remote_box.pack(fill="x", before=self.path_preview)
        else:
            self.remote_box.pack_forget()
        seed = self.v["seed_dir"].get().strip()
        if not seed:
            self.path_preview.configure(text="Astuce : indique un dossier de seed (carte Dossiers) pour voir le chemin "
                                             "transmis au client.", fg=T.FAINT)
            return
        local, remote = (self.v["client_path_local"].get(), self.v["client_path_remote"].get()) \
            if self.client_remote.get() else ("", "")
        seen = CL.map_path(seed, local, remote)
        if self.client_remote.get() and seen == seed:
            self.path_preview.configure(text=f"⚠ Le dossier de seed ({seed}) n'est pas sous « Dossier vu par Windows » : "
                                             "le client recevra un chemin Windows qu'il ne connaît pas.", fg=T.WARNING)
        else:
            self.path_preview.configure(text=f"Pour le dossier de seed, le client recevra : {seen}", fg=T.MUTED)

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
