"""Fenêtre « Installer ffmpeg » : téléchargement vérifié des builds officiels, avec progression."""

import threading
import tkinter as tk
from tkinter import ttk

from .. import ffmpeg_setup as F
from . import theme as T
from .dialogs import Dialog
from .widgets import UI, Btn, autowrap, label, run_bg


class FfmpegDialog(Dialog):
    """Installe (ou met à jour) ffmpeg ; self.result = chemin de ffmpeg.exe en cas de succès."""

    @classmethod
    def ask(cls, parent) -> str:
        d = cls(parent)
        d.show()
        return d.result

    def __init__(self, parent):
        super().__init__(parent, "Installer ffmpeg", 600, 340)
        self.result = ""
        self.asset = None
        self.cancel = None
        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=22, pady=(20, 0))
        current = F.installed_version()
        label(body, "Mettre à jour ffmpeg" if current else "Installer ffmpeg", font=T.F_BIG).pack(fill="x")
        autowrap(label(body, "ffmpeg sert à extraire les captures d'écran des vidéos. Forge411 télécharge la "
                             "version stable officielle (FFmpeg-Builds, licence LGPL) depuis GitHub, vérifie son "
                             "empreinte SHA-256 et ne garde que ffmpeg et ses bibliothèques.",
                       fg=T.MUTED)).pack(fill="x", pady=(6, 10))
        self.info = autowrap(label(body, "Recherche de la dernière version…", fg=T.TEXT, font=T.F_SMALL))
        self.info.pack(fill="x")
        label(body, f"Dossier : {F.install_dir()}", fg=T.FAINT, font=T.F_SMALL).pack(fill="x", pady=(4, 0))
        if current:
            label(body, f"Version installée : {current}", fg=T.FAINT, font=T.F_SMALL).pack(fill="x")
        self.bar = ttk.Progressbar(body, mode="determinate", maximum=100)
        self.bar.pack(fill="x", pady=(14, 0))
        self.status = autowrap(label(body, "", fg=T.MUTED, font=T.F_SMALL))
        self.status.pack(fill="x", pady=(4, 0))
        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=22, pady=16)
        self.go = Btn(bar, "Installer", self.start, kind="primary")
        self.go.pack(side="right")
        self.go.set_enabled(False)
        self.close_btn = Btn(bar, "Fermer", self.stop_or_close, kind="ghost")
        self.close_btn.pack(side="right", padx=(0, 8))
        self.protocol("WM_DELETE_WINDOW", self.stop_or_close)
        if not F.supported():
            self.info.configure(text="Installation automatique réservée à Windows : installe ffmpeg avec le "
                                     "gestionnaire de paquets de ton système (apt, brew…).", fg=T.WARNING)
            return
        run_bg(F.latest, self._found, lambda e: self.info.configure(text=f"✕  {e}", fg=T.ERROR))

    def _found(self, asset):
        if not self.winfo_exists():
            return
        self.asset = asset
        self.info.configure(text=f"ffmpeg {asset.version} · {asset.size / 1048576:.0f} Mo à télécharger · "
                                 f"{asset.name}", fg=T.TEXT)
        self.go.set_enabled(True)

    def start(self):
        if not self.asset or self.cancel is not None:
            return
        self.cancel = threading.Event()
        self.go.set_enabled(False)
        self.close_btn.set_text("Annuler")
        cancel, asset = self.cancel, self.asset

        def progress(done, total):
            UI.call(self._progress, done, total)

        def ok(path):
            self.cancel = None
            self.result = str(path)
            if self.winfo_exists():
                self.bar.configure(value=100)
                self.status.configure(text=f"✓  Installé et vérifié : {path}", fg=T.SUCCESS)
                self.close_btn.set_text("Fermer")

        def err(e):
            self.cancel = None
            if self.winfo_exists():
                self.bar.configure(value=0)
                self.status.configure(text=f"✕  {e}", fg=T.ERROR)
                self.close_btn.set_text("Fermer")
                self.go.set_text("Réessayer")
                self.go.set_enabled(True)
        run_bg(lambda: F.install(progress, cancel, asset), ok, err)

    def _progress(self, done, total):
        if not self.winfo_exists():
            return
        pct = done * 100 / total if total else 0
        self.bar.configure(value=pct)
        text = f"Téléchargement… {done / 1048576:.1f} / {total / 1048576:.1f} Mo"
        if total and done >= total:
            text = "Vérification et extraction…"
        self.status.configure(text=text, fg=T.MUTED)

    def stop_or_close(self):
        if self.cancel is not None:
            self.cancel.set()
            self.status.configure(text="Annulation…", fg=T.MUTED)
            return
        self.destroy()
