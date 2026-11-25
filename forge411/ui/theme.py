"""Palette (couleurs de C411, mode sombre / clair / système), polices et styles ttk.

Le mode est lu dans la configuration au chargement du module : changer de mode
demande un redémarrage de l'application (les composants lisent la palette à leur création).
"""

import subprocess
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# Couleurs relevées sur c411.org (variables --ui-* du site, thèmes sombre et clair)
PALETTES = {
    "dark": dict(
        BG="#030e0b", SIDEBAR="#08140f", SURFACE="#0a1712", SURFACE2="#19231f", HOVER="#232d29",
        BORDER="#23372d", TEXT="#d5eadf", HIGHLIGHT="#f4fff8", MUTED="#9db9ac", FAINT="#7f9b8d",
        ACCENT="#00d492", ACCENT_HOVER="#5ee9b5", ACCENT_SOFT="#0a3326", ON_ACCENT="#03140e",
        SUCCESS="#00d492", SUCCESS_SOFT="#0a3326", SUCCESS_HOVER="#5ee9b5",
        WARNING="#ffb900", WARNING_SOFT="#332606",
        ERROR="#ff637e", ERROR_SOFT="#3a1520", ERROR_HOVER="#4d1b29",
        INFO="#51a2ff", SECONDARY="#a684ff", UPLOADED="#00d492", DOWNLOADED="#ee760b"),
    "light": dict(
        BG="#dad6ca", SIDEBAR="#e7e3d8", SURFACE="#eeebe4", SURFACE2="#e2ded3", HOVER="#d8d3c6",
        BORDER="#cfcabd", TEXT="#0f172b", HIGHLIGHT="#020618", MUTED="#45556c", FAINT="#6b7a8f",
        ACCENT="#007a55", ACCENT_HOVER="#005f42", ACCENT_SOFT="#cfe3d6", ON_ACCENT="#ffffff",
        SUCCESS="#007a55", SUCCESS_SOFT="#cfe3d6", SUCCESS_HOVER="#005f42",
        WARNING="#973c00", WARNING_SOFT="#f1dfc8",
        ERROR="#c70036", ERROR_SOFT="#f3d3d8", ERROR_HOVER="#ecc0c8",
        INFO="#1447e6", SECONDARY="#7008e7", UPLOADED="#007a55", DOWNLOADED="#b45309"),
}
MODES = {"dark": "Sombre", "light": "Clair", "system": "Système"}


def system_mode() -> str:
    """« dark » ou « light » selon le réglage du système (sombre par défaut)."""
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
                return "light" if winreg.QueryValueEx(k, "AppsUseLightTheme")[0] else "dark"
        if sys.platform == "darwin":
            out = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                                 capture_output=True, text=True, timeout=3).stdout
            return "dark" if "dark" in out.lower() else "light"
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                             capture_output=True, text=True, timeout=3).stdout
        return "light" if "light" in out or "default" in out else "dark"
    except Exception:
        return "dark"


def resolve(mode: str) -> str:
    return mode if mode in PALETTES else system_mode()


def _configured_mode() -> str:
    try:
        from ..config import Config
        return Config().get("theme") or "dark"
    except Exception:
        return "dark"


MODE = resolve(_configured_mode())
IS_DARK = MODE == "dark"
_P = PALETTES[MODE]
BG = _P["BG"]
SIDEBAR = _P["SIDEBAR"]
SURFACE = _P["SURFACE"]
SURFACE2 = _P["SURFACE2"]
HOVER = _P["HOVER"]
BORDER = _P["BORDER"]
TEXT = _P["TEXT"]
HIGHLIGHT = _P["HIGHLIGHT"]
MUTED = _P["MUTED"]
FAINT = _P["FAINT"]
ACCENT = _P["ACCENT"]
ACCENT_HOVER = _P["ACCENT_HOVER"]
ACCENT_SOFT = _P["ACCENT_SOFT"]
ON_ACCENT = _P["ON_ACCENT"]
SUCCESS = _P["SUCCESS"]
SUCCESS_SOFT = _P["SUCCESS_SOFT"]
SUCCESS_HOVER = _P["SUCCESS_HOVER"]
WARNING = _P["WARNING"]
WARNING_SOFT = _P["WARNING_SOFT"]
ERROR = _P["ERROR"]
ERROR_SOFT = _P["ERROR_SOFT"]
ERROR_HOVER = _P["ERROR_HOVER"]
INFO = _P["INFO"]
SECONDARY = _P["SECONDARY"]
UPLOADED = _P["UPLOADED"]
DOWNLOADED = _P["DOWNLOADED"]

F_UI = ("Segoe UI", 10)
F_UI_B = ("Segoe UI Semibold", 10)
F_SMALL = ("Segoe UI", 9)
F_SMALL_B = ("Segoe UI Semibold", 9)
F_TITLE = ("Segoe UI Semibold", 18)
F_H2 = ("Segoe UI Semibold", 12)
F_BIG = ("Segoe UI Semibold", 14)
F_MONO = ("Cascadia Mono", 10)
F_ICON = ("Segoe UI Symbol", 11)


def enable_dpi_awareness():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def dark_title_bar(root: tk.Tk):
    """Barre de titre Windows assortie au mode (sombre ou claire)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        val = ctypes.c_int(1 if IS_DARK else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (selon la version)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), 4) == 0:
                break
    except Exception:
        pass


def _mono_font() -> tuple:
    fams = set(tkfont.families())
    for f in ("Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono"):
        if f in fams:
            return (f, 10)
    return ("Courier", 10)


def apply(root: tk.Tk):
    global F_MONO
    F_MONO = _mono_font()
    root.configure(bg=BG)
    root.option_add("*Font", F_UI)
    root.option_add("*TCombobox*Listbox.background", SURFACE2)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ON_ACCENT)
    root.option_add("*TCombobox*Listbox.font", F_UI)
    root.option_add("*TCombobox*Listbox.borderWidth", 0)

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=TEXT, font=F_UI,
                bordercolor=BORDER, focuscolor=ACCENT, troughcolor=SURFACE)

    field = dict(fieldbackground=SURFACE2, background=SURFACE2, foreground=TEXT,
                 bordercolor=BORDER, lightcolor=SURFACE2, darkcolor=SURFACE2,
                 insertcolor=TEXT, padding=(8, 6), arrowcolor=MUTED)
    s.configure("TEntry", **field)
    s.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)])
    s.configure("TCombobox", **field)
    s.map("TCombobox",
          fieldbackground=[("readonly", SURFACE2), ("disabled", SURFACE)],
          foreground=[("disabled", FAINT), ("readonly", TEXT)],
          background=[("active", HOVER), ("readonly", SURFACE2)],
          bordercolor=[("focus", ACCENT)], arrowcolor=[("active", TEXT)],
          selectbackground=[("readonly", SURFACE2)], selectforeground=[("readonly", TEXT)])
    s.configure("TSpinbox", **field)

    for name, bg in (("TCheckbutton", BG), ("Card.TCheckbutton", SURFACE)):
        s.configure(name, background=bg, foreground=TEXT, indicatorbackground=SURFACE2,
                    indicatorforeground=ACCENT, indicatorcolor=SURFACE2, focuscolor=bg,
                    upperbordercolor=BORDER, lowerbordercolor=BORDER)
        s.map(name, background=[("active", bg)],
              indicatorcolor=[("selected", ACCENT), ("pressed", HOVER)])

    s.configure("Horizontal.TProgressbar", troughcolor=SURFACE2, background=ACCENT,
                bordercolor=SURFACE2, lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)
    s.configure("Vertical.TScrollbar", background=SURFACE2, troughcolor=BG,
                bordercolor=BG, arrowcolor=MUTED, lightcolor=SURFACE2, darkcolor=SURFACE2,
                gripcount=0, arrowsize=12)
    s.map("Vertical.TScrollbar", background=[("active", HOVER)])
