"""Fenêtre « Mon profil C411 » : niveau, classe, volumes, ratio, Zen et état de téléchargement."""

import time
import tkinter as tk
import webbrowser

from .. import profile as P
from ..api import BASE
from ..config import KEY_LINKS
from . import theme as T
from .dialogs import Dialog
from .widgets import Btn, Card, Meter, ScrollFrame, Tooltip, autowrap, badge, fit_font, label, run_bg

PROFILE_URL = f"{BASE}/user/profile"
MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre")


def fmt_date(d) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}" if d else ""


class ProfileDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "Mon profil C411", 860, 820)
        self.app = app
        self.sf = ScrollFrame(self)
        self.sf.pack(fill="both", expand=True, padx=20, pady=(20, 0))
        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=20, pady=14)
        self.stamp = label(bar, "", fg=T.FAINT, font=T.F_SMALL)
        self.stamp.pack(side="left")
        Btn(bar, "Fermer", self.destroy, kind="ghost").pack(side="right")
        self.refresh_btn = Btn(bar, "Actualiser", lambda: self.load(force=True))
        self.refresh_btn.pack(side="right", padx=(0, 8))
        Tooltip(self.refresh_btn, "C411 rafraîchit le profil au plus toutes les 30 secondes.")
        self.load()

    # ── Chargement ────────────────────────────────────────────────────────
    def load(self, force: bool = False):
        cached = self.app.profile_cache
        if cached and not force:
            self._show(*cached)
            return
        if cached and time.time() - cached[1] < P.MIN_REFRESH:
            wait = int(P.MIN_REFRESH - (time.time() - cached[1])) + 1
            self.stamp.configure(text=f"Déjà à jour : C411 recalcule le profil toutes les {P.MIN_REFRESH} s "
                                      f"(réessaie dans {wait} s).", fg=T.WARNING)
            return
        if cached:                       # garde l'affichage, signale seulement le chargement
            self.stamp.configure(text="Actualisation…", fg=T.MUTED)
        else:
            self._message("Chargement du profil…")
        self.refresh_btn.set_enabled(False)
        self.refresh_btn.set_text("Actualisation…")
        before = cached[0] if cached else None

        def ok(prof):
            self.app.set_profile(prof)
            if self.winfo_exists():
                self._show(*self.app.profile_cache)
                if before is not None and _same(before, prof):
                    self.stamp.configure(text=self.stamp.cget("text") + " · aucune variation depuis la dernière lecture")

        def err(e):
            if self.winfo_exists():
                self.refresh_btn.set_enabled(True)
                self.refresh_btn.set_text("Actualiser")
                self._error(str(e))
        run_bg(lambda: P.parse(self.app.c411().profile(), BASE), ok, err)

    def _clear(self):
        for w in self.sf.inner.winfo_children():
            w.destroy()

    def _message(self, text):
        self._clear()
        label(self.sf.inner, text, fg=T.MUTED).pack(fill="x", pady=20)

    def _error(self, text):
        self._clear()
        card = self._card()
        label(card, "Profil indisponible", font=T.F_H2).pack(fill="x")
        autowrap(label(card, text, fg=T.ERROR)).pack(fill="x", pady=(6, 10))
        autowrap(label(card, "Sur C411 : Profil › Intégrations › Créer une clé, coche « Profil (lecture) » en plus de "
                             "tes droits actuels (brouillons, upload).", fg=T.MUTED, font=T.F_SMALL)).pack(fill="x")
        row = tk.Frame(card, bg=T.SURFACE)
        row.pack(fill="x", pady=(12, 0))
        Btn(row, "Créer une clé API  ↗", lambda: webbrowser.open(KEY_LINKS["c411_api_key"][1]), kind="primary").pack(side="left")
        Btn(row, "Paramètres", self._settings).pack(side="left", padx=(8, 0))
        self.stamp.configure(text="")

    def _settings(self):
        self.destroy()
        self.app.open_settings()

    # ── Affichage ─────────────────────────────────────────────────────────
    def _card(self, title: str = "", right: str = ""):
        c = Card(self.sf.inner, padding=18)
        c.pack(fill="x", pady=(0, 12), padx=(0, 12))
        if title:
            head = tk.Frame(c.body, bg=T.SURFACE)
            head.pack(fill="x", pady=(0, 12))
            label(head, title, font=T.F_H2).pack(side="left")
            if right:
                label(head, right, fg=T.MUTED, font=T.F_SMALL).pack(side="right")
        return c.body

    def _show(self, p: P.Profile, at: float):
        self._clear()
        self.refresh_btn.set_enabled(True)
        self.refresh_btn.set_text("Actualiser")
        self.stamp.configure(text="Mis à jour à " + time.strftime("%H:%M:%S", time.localtime(at)), fg=T.FAINT)
        self._header(p)
        self._tiles(p)
        self._trend(p, at)
        self._status(p)
        if p.class_name:
            self._class(p)
        self.after(150, self._fit)            # encadrés arrondis ajustés : toute la page visible sans défiler

    def _fit(self):
        if self.winfo_exists():
            bar = self.refresh_btn.master
            self.fit_height(self.sf.inner, T.px(self, 20) + bar.winfo_reqheight() + T.px(self, 28) + T.px(self, 4))

    def _header(self, p):
        body = self._card()
        top = tk.Frame(body, bg=T.SURFACE)
        top.pack(fill="x")
        av = tk.Canvas(top, width=64, height=64, bg=T.SURFACE, highlightthickness=0)
        av.pack(side="left", padx=(0, 16))
        av.create_oval(2, 2, 62, 62, fill=T.ACCENT_SOFT, outline=T.ACCENT, width=2)
        av.create_text(32, 32, text=(p.username[:1] or "?").upper(), fill=T.ACCENT, font=("Segoe UI Semibold", 22))
        info = tk.Frame(top, bg=T.SURFACE)
        info.pack(side="left", fill="x", expand=True)
        label(info, p.username, font=T.F_TITLE, fg=T.HIGHLIGHT).pack(fill="x")
        tags = tk.Frame(info, bg=T.SURFACE)
        tags.pack(fill="x", pady=(4, 0))
        badge(tags, f"Niveau {p.level}", "accent").pack(side="left", padx=(0, 6))
        if p.class_name:
            badge(tags, p.class_name, "muted").pack(side="left", padx=(0, 6))
        if p.grade:
            badge(tags, p.grade, "warning").pack(side="left", padx=(0, 6))
        if p.team_name:
            t = badge(tags, f"Team {p.team_tag or p.team_name}", "success")
            t.pack(side="left", padx=(0, 6))
            Tooltip(t, f"{p.team_name}, {p.team_role}. Tag à utiliser dans le nom de tes releases d'équipe.")
        since = fmt_date(p.member_since)
        if since:
            label(info, f"Membre depuis le {since} · {p.days} jour{'s' if p.days > 1 else ''}", fg=T.MUTED,
                  font=T.F_SMALL).pack(fill="x", pady=(6, 0))
        lnk = label(top, "Voir sur C411  ↗", fg=T.ACCENT, font=T.F_SMALL_B, cursor="hand2")
        lnk.pack(side="right", anchor="n")
        lnk.bind("<Button-1>", lambda e: webbrowser.open(PROFILE_URL))

        lv = tk.Frame(body, bg=T.SURFACE)
        lv.pack(fill="x", pady=(18, 0))
        row = tk.Frame(lv, bg=T.SURFACE)
        row.pack(fill="x")
        label(row, f"Progression vers le niveau {p.level + 1}", fg=T.MUTED, font=T.F_SMALL_B).pack(side="left")
        label(row, f"{P.fmt_int(p.xp_into)} / {P.fmt_int(p.xp_into + p.xp_next)} XP", fg=T.TEXT,
              font=T.F_SMALL_B).pack(side="right")
        Meter(lv, p.level_progress, T.ACCENT, height=8).pack(fill="x", pady=(6, 4))
        label(lv, f"{P.fmt_int(p.xp)} XP au total · encore {P.fmt_int(p.xp_next)} XP", fg=T.FAINT,
              font=T.F_SMALL).pack(fill="x")

    def _tile(self, parent, col, title, value, color, sub, tip=""):
        f = tk.Frame(parent, bg=T.SURFACE)
        f.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 14, 0))
        if col:
            tk.Frame(parent, bg=T.BORDER, width=1).grid(row=0, column=col, sticky="nsw")
        inner = tk.Frame(f, bg=T.SURFACE)
        inner.pack(fill="both", padx=(14 if col else 0, 0))
        label(inner, title, fg=T.MUTED, font=T.F_SMALL).pack(fill="x")
        fit_font(label(inner, value, fg=color), "Segoe UI Semibold", 20).pack(fill="x", pady=(2, 0))
        autowrap(label(inner, sub, fg=T.FAINT, font=T.F_SMALL)).pack(fill="x")
        if tip:
            Tooltip(f, tip)
            for w in inner.winfo_children():
                Tooltip(w, tip)

    def _tiles(self, p):
        body = self._card("Volumes et Zen")
        grid = tk.Frame(body, bg=T.SURFACE)
        grid.pack(fill="x")
        for c in range(4):
            grid.columnconfigure(c, weight=1, uniform="tiles")
        r = p.ratio
        rc = T.MUTED if r is None else T.SUCCESS if r >= 1 else T.WARNING if r >= 0.5 else T.ERROR
        self._tile(grid, 0, "Ratio", P.fmt_ratio(r), rc, "envoyé ÷ reçu, crédits inclus")
        self._tile(grid, 1, "Envoyé", P.fmt_bytes(p.up_total), T.UPLOADED,
                   f"dont {P.fmt_bytes(p.up_credit)} de crédit" if p.up_credit else "mesuré par le tracker",
                   f"Mesuré : {P.fmt_bytes(p.up_actual)} · crédit acheté ou offert : {P.fmt_bytes(p.up_credit)}")
        self._tile(grid, 2, "Reçu", P.fmt_bytes(p.down_total), T.DOWNLOADED,
                   f"crédit déduit : {P.fmt_bytes(p.down_credit)}" if p.down_credit else "mesuré par le tracker",
                   f"Mesuré : {P.fmt_bytes(p.down_actual)} · crédit déduit : {P.fmt_bytes(p.down_credit)}")
        self._tile(grid, 3, "Zen", P.fmt_int(p.zen), T.ACCENT,
                   f"{P.fmt_int(p.zen_earned)} gagnés · {P.fmt_int(p.zen_spent)} dépensés")

    def _trend(self, p, at):
        from ..config import PROFILE_HISTORY_PATH
        t = P.trend(p, P.load_history(PROFILE_HISTORY_PATH), at)
        if t is None:
            body = self._card("Évolution")
            autowrap(label(body, "Forge411 garde un relevé de ton profil à chaque ouverture (au plus un par heure). "
                                 "Reviens plus tard pour voir ta progression.", fg=T.MUTED, font=T.F_SMALL)).pack(fill="x")
            return
        since = time.strftime("%d/%m à %H:%M", time.localtime(t.since))
        body = self._card("Évolution", f"depuis le {since}")
        grid = tk.Frame(body, bg=T.SURFACE)
        grid.pack(fill="x")
        for c in range(4):
            grid.columnconfigure(c, weight=1, uniform="trend")
        ratio_now = P.fmt_ratio(p.ratio)
        ratio_sub = f"avant : {P.fmt_ratio(t.ratio_before)}" if t.ratio_before is not None or p.ratio is not None else ""
        self._tile(grid, 0, "Ratio", ratio_now, T.TEXT, ratio_sub)
        self._tile(grid, 1, "Envoyé", P.fmt_delta_bytes(t.up), T.UPLOADED, f"reçu : {P.fmt_delta_bytes(t.down)}")
        self._tile(grid, 2, "Zen", ("+" if t.zen >= 0 else "−") + P.fmt_int(abs(t.zen)), T.ACCENT,
                   f"{t.quests:+d} quête(s)" if t.quests else "aucune quête terminée")
        if t.days_to_next is not None:
            eta = "< 1 jour" if t.days_to_next < 1 else f"≈ {t.days_to_next:.0f} jour{'s' if t.days_to_next >= 2 else ''}"
            sub = f"{P.fmt_int(int(t.xp_per_day))} XP par jour"
        else:
            eta, sub = "-", "pas d'XP gagnée sur la période"
        self._tile(grid, 3, f"Niveau {p.level + 1}", eta, T.SECONDARY, sub)

    def _status(self, p):
        body = self._card("État du compte")
        rows = []
        if p.can_download:
            rows.append(("ok", "Téléchargement autorisé"))
        else:
            rows.append(("error", "Téléchargement bloqué" + (f" : {p.blocked_reason}" if p.blocked_reason else "")))
        if p.freeleech:
            rows.append(("ok", "Freeleech actif" + (f" ({', '.join(p.freeleech_sources)})" if p.freeleech_sources else "")))
        else:
            rows.append(("muted", "Pas de freeleech en cours"))
        rows.append(("ok" if p.silverleech else "muted", "Silverleech actif" if p.silverleech else "Pas de silverleech"))
        for b in p.leech_bonuses:
            rows.append(("ok", f"Bonus : {b}"))
        icons = {"ok": ("✓", T.SUCCESS, T.TEXT), "error": ("✕", T.ERROR, T.TEXT), "muted": ("–", T.FAINT, T.MUTED)}
        grid = tk.Frame(body, bg=T.SURFACE)
        grid.pack(fill="x")
        grid.columnconfigure((0, 1), weight=1, uniform="st")
        for i, (tone, text) in enumerate(rows):
            icon, ic, fg = icons[tone]
            cell = tk.Frame(grid, bg=T.SURFACE)
            cell.grid(row=i // 2, column=i % 2, sticky="w", pady=3)
            tk.Label(cell, text=icon, fg=ic, bg=T.SURFACE, font=T.F_UI_B, width=2).pack(side="left")
            label(cell, text, fg=fg).pack(side="left")

    def _class(self, p):
        stars = "★" * p.stars + "☆" * max(0, len(p.voies) - p.stars)
        body = self._card(f"Classe : {p.class_name}", f"{p.grade}  ·  {stars}" if p.grade else stars)
        info = f"{p.quests_done} quête{'s' if p.quests_done > 1 else ''} terminée{'s' if p.quests_done > 1 else ''} sur {p.quests_total}"
        if p.tree_bonus:
            info += f" · bonus de l'arbre +{p.tree_bonus:.2f} %".replace(".", ",")
        label(body, info, fg=T.MUTED, font=T.F_SMALL).pack(fill="x", pady=(0, 12))
        grid = tk.Frame(body, bg=T.SURFACE)
        grid.pack(fill="x")
        grid.columnconfigure((0, 1), weight=1, uniform="voies")
        colors = {"seed": T.SUCCESS, "upload": T.ACCENT, "specialization": T.SECONDARY, "competitivity": T.INFO}
        for i, v in enumerate(p.voies):
            cell = tk.Frame(grid, bg=T.SURFACE)
            cell.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 18 if i % 2 == 0 else 0), pady=(0, 12))
            head = tk.Frame(cell, bg=T.SURFACE)
            head.pack(fill="x")
            label(head, ("★ " if v.star else "") + f"Voie {v.label}", fg=T.WARNING if v.star else T.TEXT,
                  font=T.F_SMALL_B).pack(side="left")
            label(head, f"{v.done} / {v.total}" if v.total else "aucune quête", fg=T.MUTED, font=T.F_SMALL).pack(side="right")
            Meter(cell, v.done / v.total if v.total else 0, colors.get(v.key, T.ACCENT), height=6).pack(fill="x", pady=(5, 0))


def _same(a, b) -> bool:
    """Mêmes chiffres principaux (C411 n'a rien recalculé entre les deux lectures)."""
    keys = ("ratio", "up_total", "down_actual", "level", "xp", "zen")
    return all(getattr(a, k, None) == getattr(b, k, None) for k in keys)
