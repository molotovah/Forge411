"""Fenêtre « À propos » : version, auteur, licence et services utilisés."""

import tkinter as tk
import webbrowser

from .. import APP_NAME, AUTHOR, AUTHOR_URL, LICENSE_URL, REPO_URL, __version__
from . import theme as T
from .dialogs import Dialog
from .widgets import Btn, autowrap, label, link

SERVICES = [
    ("TMDB", "https://www.themoviedb.org/",
     "Ce produit utilise l'API TMDB mais n'est ni approuvé ni certifié par TMDB."),
    ("MusicBrainz", "https://musicbrainz.org/", "Données musicales sous licence CC0."),
    ("Open Library", "https://openlibrary.org/", "Fiches de livres de l'Internet Archive."),
    ("RAWG", "https://rawg.io/", "Fiches de jeux vidéo."),
    ("ThePornDB", "https://theporndb.net/", "Fiches des scènes et films adultes."),
    ("MediaInfo", "https://mediaarea.net/MediaInfo", "Analyse des fichiers vidéo (licence BSD)."),
    ("FFmpeg", "https://ffmpeg.org/", "Captures d'écran, installé à la demande (licence LGPL)."),
]


class AboutDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, f"À propos de {APP_NAME}", 620, 600)
        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=26, pady=(24, 0))
        head = tk.Frame(body, bg=T.BG)
        head.pack(fill="x")
        icon = getattr(app, "_icon", None)
        if icon is not None:
            self._logo = icon.subsample(max(1, icon.width() // 64)) if icon.width() > 64 else icon
            tk.Label(head, image=self._logo, bg=T.BG).pack(side="left", padx=(0, 16))
        txt = tk.Frame(head, bg=T.BG)
        txt.pack(side="left", fill="x", expand=True)
        brand = tk.Frame(txt, bg=T.BG)
        brand.pack(anchor="w")
        tk.Label(brand, text="Forge", bg=T.BG, fg=T.TEXT, font=("Segoe UI Black", 20)).pack(side="left")
        tk.Label(brand, text="411", bg=T.BG, fg=T.ACCENT, font=("Segoe UI Black", 20)).pack(side="left")
        label(txt, f"Version {__version__} · du fichier au torrent en seed", fg=T.MUTED).pack(fill="x")
        who = tk.Frame(txt, bg=T.BG)
        who.pack(fill="x", pady=(6, 0))
        label(who, "Développé par ", fg=T.TEXT, font=T.F_UI_B, padx=0).pack(side="left")
        a = label(who, AUTHOR, fg=T.ACCENT, font=T.F_UI_B, cursor="hand2", padx=0)
        a.pack(side="left")
        a.bind("<Button-1>", lambda e: webbrowser.open(AUTHOR_URL))

        links = tk.Frame(body, bg=T.BG)
        links.pack(fill="x", pady=(16, 0))
        link(links, "Code source et nouveautés", REPO_URL, small=False).pack(side="left")
        link(links, "Signaler un problème", f"{REPO_URL}/issues", small=False).pack(side="left", padx=(18, 0))
        lic = tk.Frame(body, bg=T.BG)
        lic.pack(fill="x", pady=(10, 0))
        label(lic, "Licence libre :", fg=T.MUTED, font=T.F_SMALL, padx=0).pack(side="left")
        g = label(lic, "GNU GPL version 3  ↗", fg=T.ACCENT, font=T.F_SMALL_B, cursor="hand2")
        g.pack(side="left", padx=(4, 0))
        g.bind("<Button-1>", lambda e: webbrowser.open(LICENSE_URL))
        autowrap(label(body, "Outil indépendant, non affilié à C411. Tu peux le copier, le modifier et le redistribuer : "
                             "les versions modifiées restent sous "
                             "GPL, gardent la mention « Forge411 par molotovah » visible et se signalent comme "
                             "modifiées (voir NOTICE).", fg=T.FAINT, font=T.F_SMALL)).pack(fill="x", pady=(2, 0))

        label(body, "Services et composants utilisés", font=T.F_H2).pack(fill="x", pady=(18, 6))
        for name, url, note in SERVICES:
            row = tk.Frame(body, bg=T.BG)
            row.pack(fill="x", pady=2)
            n = label(row, name, fg=T.ACCENT, font=T.F_SMALL_B, cursor="hand2", width=13)
            n.pack(side="left", anchor="n")
            n.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            autowrap(label(row, note, fg=T.MUTED, font=T.F_SMALL)).pack(side="left", fill="x", expand=True)

        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=26, pady=16)
        Btn(bar, "Fermer", self.destroy, kind="primary").pack(side="right")
