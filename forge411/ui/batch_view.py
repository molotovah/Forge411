"""Fenêtre « Mode lot » : prépare toutes les sources d'un dossier puis les envoie en brouillons."""

import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import batch as B
from .. import clients as CL
from . import theme as T
from .dialogs import Dialog
from .widgets import UI, Btn, IssueList, label, run_bg, style_tree

TONES = {B.READY: "ok", B.SENT: "ok", B.CHECK: "warning", B.ERROR: "error", B.PENDING: "info"}


class BatchDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "Mode lot", 1100, 720)
        self.app = app
        self.items = []
        self.cancel = None
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=20, pady=(20, 10))
        Btn(top, "Choisir un dossier…", self.pick, kind="primary").pack(side="left")
        self.folder_lbl = label(top, "Chaque sous-dossier ou fichier du dossier devient une release.", fg=T.MUTED)
        self.folder_lbl.pack(side="left", padx=(12, 0))

        mid = tk.Frame(self, bg=T.BG)
        mid.pack(fill="both", expand=True, padx=20)
        cols = ("status", "type", "name")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="extended", height=14)
        for c, title, w in (("status", "État", 100), ("type", "Type", 230), ("name", "Nom de release", 650)):
            self.tree.heading(c, text=title, anchor="w")
            self.tree.column(c, width=w, stretch=c == "name")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        for st, color in ((B.READY, T.SUCCESS), (B.SENT, T.SUCCESS), (B.CHECK, T.WARNING), (B.ERROR, T.ERROR),
                          (B.PENDING, T.MUTED)):
            self.tree.tag_configure(st, foreground=color)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_messages())
        self.tree.bind("<Double-1>", lambda e: self.open_in_wizard())
        style_tree(self)

        self.msgs = IssueList(self)
        self.msgs.configure(bg=T.BG)
        self.msgs.pack(fill="x", padx=20, pady=(10, 0))
        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=20, pady=14)
        self.status = label(bar, "", fg=T.MUTED, font=T.F_SMALL)
        self.status.pack(side="left")
        self.send_btn = Btn(bar, "Envoyer les « Prêt » en brouillons", self.send, kind="primary")
        self.send_btn.pack(side="right")
        self.open_btn = Btn(bar, "Ouvrir dans l'assistant", self.open_in_wizard)
        self.open_btn.pack(side="right", padx=(0, 8))
        self.stop_btn = Btn(bar, "Arrêter", self.stop, kind="ghost")
        self._buttons(False)
        self.protocol("WM_DELETE_WINDOW", self.close)

    # ── Préparation ───────────────────────────────────────────────────────
    def pick(self):
        p = filedialog.askdirectory(parent=self, title="Dossier à traiter",
                                    initialdir=self.app.cfg.get("last_dir") or None)
        if not p:
            return
        self.folder_lbl.configure(text=str(Path(p)), fg=T.TEXT)
        self.items = B.candidates(Path(p))
        self.tree.delete(*self.tree.get_children())
        for i, it in enumerate(self.items):
            self.tree.insert("", "end", iid=str(i), values=(it.status, "", it.path.name), tags=(it.status,))
        if not self.items:
            self.status.configure(text="Aucune source dans ce dossier.")
            return
        self.prepare_all()

    def _row(self, i):
        it = self.items[i]
        s = it.session
        typ = f"{s.profile.icon} {s.profile.label} › {s.profile.subcategories.get(s.sub_id, '')}" if s and s.profile else ""
        self.tree.item(str(i), values=(it.status, typ, it.name), tags=(it.status,))

    def prepare_all(self):
        try:
            api = self.app.c411()
        except Exception as e:
            messagebox.showerror("Mode lot", str(e), parent=self)
            return
        self.cancel = threading.Event()
        self._buttons(True)
        cfg, cancel = self.app.cfg, self.cancel

        def work():
            for i, it in enumerate(self.items):
                if cancel.is_set():
                    break
                UI.call(self.status.configure, {"text": f"Préparation {i + 1}/{len(self.items)} : {it.path.name}"})
                try:
                    B.prepare(it, cfg, api, self.app.client,
                              lambda m, n=it.path.name: UI.call(self.status.configure, {"text": f"{n} : {m}"}))
                except Exception as e:
                    it.status = B.ERROR
                    it.messages.append(("error", str(e)))
                UI.call(self._row, i)

        def done(_=None):
            self._buttons(False)
            n = sum(1 for it in self.items if it.status == B.READY)
            self.status.configure(text=f"{n} prêt(s) sur {len(self.items)}. Double-clic : ouvrir dans l'assistant.")
        run_bg(work, done, lambda e: done())

    # ── Envoi ─────────────────────────────────────────────────────────────
    def send(self):
        ready = [i for i, it in enumerate(self.items) if it.status == B.READY]
        if not ready:
            messagebox.showinfo("Mode lot", "Aucun élément « Prêt ».", parent=self)
            return
        if not self.app.cfg.get("tracker_url"):
            messagebox.showerror("Mode lot", "URL d'annonce manquante (Paramètres).", parent=self)
            return
        api = self.app.c411()
        try:
            free = B.MAX_DRAFTS - len(api.drafts())
        except Exception:
            free = B.MAX_DRAFTS
        if free <= 0:
            messagebox.showerror("Mode lot", "Tu as déjà 15 brouillons sur C411 (maximum). Publie ou supprime-en.",
                                 parent=self)
            return
        ready = ready[:free]
        client = CL.make(self.app.cfg) if self.app.cfg.get("client_auto") else None
        if not messagebox.askyesno("Mode lot", f"Créer les torrents et envoyer {len(ready)} brouillon(s) sur C411 ?"
                                   + (f"\n\nLes torrents seront aussi ajoutés à {client.name}." if client else "")
                                   + ("\n\nLimite de 15 brouillons : les suivants restent « Prêt »." if free < len(
                                       [it for it in self.items if it.status == B.READY]) else ""), parent=self):
            return
        self.cancel = threading.Event()
        self._buttons(True)
        cfg, cancel = self.app.cfg, self.cancel

        def work():
            from ..config import add_history
            for n, i in enumerate(ready, 1):
                if cancel.is_set():
                    break
                it = self.items[i]
                try:
                    B.send(it, cfg, api, client,
                           lambda m, nm=it.name: UI.call(self.status.configure, {"text": f"{n}/{len(ready)} {nm} : {m}"}),
                           cancel)
                    if it.status == B.SENT:
                        add_history({"name": it.name, "type": it.session.profile.label, "action": "Brouillon (lot)",
                                     "url": it.url, "torrent": str(it.session.torrent), "infohash": it.session.infohash})
                except Exception as e:
                    it.status = B.ERROR
                    it.messages.append(("error", str(e)))
                UI.call(self._row, i)

        def done(_=None):
            self._buttons(False)
            sent = sum(1 for it in self.items if it.status == B.SENT)
            self.status.configure(text=f"{sent} brouillon(s) envoyé(s). Relis-les et publie-les depuis C411.")
        run_bg(work, done, lambda e: done())

    # ── Divers ────────────────────────────────────────────────────────────
    def _selected(self):
        sel = self.tree.selection()
        return self.items[int(sel[0])] if sel else None

    def show_messages(self):
        it = self._selected()
        if not it:
            return
        empty = {B.READY: ("ok", "Rien à signaler : prêt à être envoyé en brouillon."),
                 B.PENDING: ("info", "Pas encore analysé.")}.get(it.status, ("info", "Aucun détail."))
        msgs = it.messages or [empty]
        self.msgs.show(msgs[:8], wrap=980)
        if it.url:
            self.msgs.show(msgs[:7] + [("ok", f"Brouillon : {it.url}")], wrap=980)

    def open_in_wizard(self):
        it = self._selected()
        if not it or not it.session or self.cancel is not None:
            return
        if it.status == B.SENT:
            webbrowser.open(it.url)
            return
        self.app.load_session(it.session)
        self.close()

    def _buttons(self, running):
        if running:
            self.stop_btn.pack(side="right", padx=(0, 8))
        else:
            self.stop_btn.pack_forget()
            self.cancel = None
        self.send_btn.set_enabled(not running)
        self.open_btn.set_enabled(not running)

    def stop(self):
        if self.cancel:
            self.cancel.set()
            self.status.configure(text="Arrêt après l'élément en cours…")

    def close(self):
        if self.cancel is not None and not messagebox.askyesno("Mode lot", "Un traitement est en cours. Fermer ?",
                                                               parent=self):
            return
        self.stop()
        self.destroy()
