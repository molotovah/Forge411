"""Fenêtre « Brouillons C411 » : liste, ouverture sur le site, suppression (15 au maximum)."""

import tkinter as tk
import webbrowser
from tkinter import messagebox

from ..api import BASE
from ..batch import MAX_DRAFTS
from . import theme as T
from .dialogs import Dialog
from .widgets import Btn, Card, Meter, ScrollFrame, autowrap, label, run_bg

UPLOAD_URL = f"{BASE}/upload"


def _field(d: dict, *keys, default=""):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return default


class DraftsDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "Brouillons C411", 820, 620)
        self.app = app
        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=20, pady=(20, 8))
        self.count = label(head, "", font=T.F_H2)
        self.count.pack(side="left")
        Btn(head, "Ouvrir la page d'upload  ↗", lambda: webbrowser.open(UPLOAD_URL), small=True).pack(side="right")
        Btn(head, "⟳", self.load, small=True, kind="ghost").pack(side="right", padx=(0, 6))
        self.meter = Meter(self, 0, T.ACCENT, height=6, track=T.SURFACE2)
        self.meter.configure(bg=T.BG)
        self.meter.pack(fill="x", padx=20)
        autowrap(label(self, "Pour reprendre un brouillon : page d'upload de C411 › bouton « Brouillons ». "
                             "C411 en garde 15 au maximum par membre.", fg=T.MUTED, font=T.F_SMALL)).pack(
            fill="x", padx=20, pady=(6, 8))
        self.sf = ScrollFrame(self)
        self.sf.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        self.load()

    def load(self):
        for w in self.sf.inner.winfo_children():
            w.destroy()
        label(self.sf.inner, "Chargement…", fg=T.MUTED).pack(fill="x")
        try:
            api = self.app.c411()
        except Exception as e:
            self._show_error(str(e))
            return
        run_bg(api.drafts, self._show, lambda e: self._show_error(str(e)))

    def _show_error(self, text):
        if not self.winfo_exists():
            return
        for w in self.sf.inner.winfo_children():
            w.destroy()
        autowrap(label(self.sf.inner, text, fg=T.ERROR)).pack(fill="x")

    def _show(self, drafts):
        if not self.winfo_exists():
            return
        for w in self.sf.inner.winfo_children():
            w.destroy()
        n = len(drafts)
        self.count.configure(text=f"{n} brouillon{'s' if n > 1 else ''} sur {MAX_DRAFTS}")
        self.meter.set(n / MAX_DRAFTS)
        self.meter.color = T.WARNING if n >= MAX_DRAFTS - 2 else T.ACCENT
        self.meter._draw()
        if not drafts:
            label(self.sf.inner, "Aucun brouillon sur C411.", fg=T.MUTED).pack(fill="x", pady=10)
        cats = {}
        try:
            for c in self.app.c411().categories():
                for sc in c.get("subcategories", []):
                    cats[sc["id"]] = f"{c['name']} › {sc['name']}"
        except Exception:
            pass
        for d in drafts:
            card = Card(self.sf.inner, padding=12)
            card.pack(fill="x", pady=(0, 8), padx=(0, 12))
            top = tk.Frame(card.body, bg=T.SURFACE)
            top.pack(fill="x")
            title = _field(d, "name", "title", "torrentName", default="(sans titre)")
            autowrap(label(top, title, font=T.F_UI_B)).pack(side="left", fill="x", expand=True)
            Btn(top, "Supprimer", lambda dd=d: self.delete(dd), kind="danger", small=True).pack(side="right")
            sub = cats.get(_field(d, "subcategoryId", default=0), "")
            when = str(_field(d, "updatedAt", "createdAt"))[:16].replace("T", " ")
            label(card.body, " · ".join(x for x in (sub, when) if x), fg=T.MUTED, font=T.F_SMALL).pack(fill="x", pady=(4, 0))

    def delete(self, d):
        did = _field(d, "id", "_id")
        name = _field(d, "name", "title", default="ce brouillon")
        if not did or not messagebox.askyesno("Supprimer", f"Supprimer définitivement le brouillon C411 :\n\n{name} ?",
                                              parent=self):
            return
        api = self.app.c411()
        run_bg(lambda: api.delete_draft(did), lambda ok: self.load() if ok else self._show_error("Suppression refusée."),
               lambda e: self._show_error(str(e)))
