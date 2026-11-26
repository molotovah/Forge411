"""Palette (couleurs de C411, mode sombre / clair / système), polices et styles ttk.

Le mode est lu dans la configuration au chargement du module ; set_mode() le change en cours de route et
l'application reconstruit alors son interface (les composants lisent la palette à leur création).
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
    # Clair : neutres froids et cartes blanches (inspiré de GitHub Primer), vert de C411 assombri pour un contraste
    # d'au moins 4,5:1 sur blanc (texte et boutons). Contrastes vérifiés par tests/test_ui_rules.py.
    "light": dict(
        BG="#f6f8fa", SIDEBAR="#eef1f5", SURFACE="#ffffff", SURFACE2="#f3f5f8", HOVER="#e6ebf0",
        BORDER="#d8dee4", TEXT="#1f2328", HIGHLIGHT="#0d1117", MUTED="#57606a", FAINT="#636c76",
        ACCENT="#007a55", ACCENT_HOVER="#00664a", ACCENT_SOFT="#e3f4ec", ON_ACCENT="#ffffff",
        SUCCESS="#1a7f37", SUCCESS_SOFT="#dafbe1", SUCCESS_HOVER="#116329",
        WARNING="#9a6700", WARNING_SOFT="#fff8c5",
        ERROR="#cf222e", ERROR_SOFT="#ffebe9", ERROR_HOVER="#ffcecb",
        INFO="#0969da", SECONDARY="#8250df", UPLOADED="#1a7f37", DOWNLOADED="#bc4c00"),
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


def set_mode(mode: str) -> str:
    """Charge la palette du mode (« dark », « light » ou « system ») dans les constantes du module. Les composants
    lisent ces constantes à leur création : l'application reconstruit ensuite son interface (App.apply_theme)."""
    global MODE, IS_DARK
    MODE = resolve(mode)
    IS_DARK = MODE == "dark"
    globals().update(PALETTES[MODE])
    return MODE


BG = SIDEBAR = SURFACE = SURFACE2 = HOVER = BORDER = TEXT = HIGHLIGHT = MUTED = FAINT = ""
ACCENT = ACCENT_HOVER = ACCENT_SOFT = ON_ACCENT = SUCCESS = SUCCESS_SOFT = SUCCESS_HOVER = ""
WARNING = WARNING_SOFT = ERROR = ERROR_SOFT = ERROR_HOVER = INFO = SECONDARY = UPLOADED = DOWNLOADED = ""
MODE, IS_DARK = "dark", True
set_mode(_configured_mode())

F_UI = ("Segoe UI", 10)
F_UI_B = ("Segoe UI Semibold", 10)
F_SMALL = ("Segoe UI", 9)
F_SMALL_B = ("Segoe UI Semibold", 9)
F_TITLE = ("Segoe UI Semibold", 18)
F_H2 = ("Segoe UI Semibold", 12)
F_BIG = ("Segoe UI Semibold", 14)
F_MONO = ("Cascadia Mono", 10)
F_ICON = ("Segoe UI Symbol", 11)
F_EMOJI = ("Segoe UI Emoji", 9)        # icônes des pastilles (types de contenu)


def enable_dpi_awareness():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def px(widget, n: int) -> int:
    """Taille en pixels mise à l'échelle de l'affichage Windows (125 %, 150 %…) : les polices grossissent
    avec le DPI, les dimensions fixées en pixels doivent suivre sinon le contenu est rogné."""
    try:
        return round(n * widget.winfo_fpixels("1i") / 96)
    except tk.TclError:
        return n


def work_area(widget: tk.Misc) -> tuple:
    """Zone utilisable de l'écran principal (x, y, largeur, hauteur), barre des tâches Windows exclue."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            r = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):   # SPI_GETWORKAREA
                return r.left, r.top, r.right - r.left, r.bottom - r.top
        except Exception:
            pass
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight() - 40


def flash_taskbar(root: tk.Misc):
    """Fait clignoter le bouton de Forge411 dans la barre des tâches Windows jusqu'à ce que la fenêtre revienne
    au premier plan. Rien si elle y est déjà."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                        ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(root.winfo_id())
        if user32.GetForegroundWindow() == hwnd:
            return
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x2 | 0xC, 0, 0)   # FLASHW_TRAY | FLASHW_TIMERNOFG
        user32.FlashWindowEx(ctypes.byref(info))
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
    for orient in ("Vertical", "Horizontal"):     # l'horizontale (NFO, tableaux) restait claire sinon
        s.configure(f"{orient}.TScrollbar", background=SURFACE2, troughcolor=BG,
                    bordercolor=BG, arrowcolor=MUTED, lightcolor=SURFACE2, darkcolor=SURFACE2,
                    gripcount=0, arrowsize=12)
        s.map(f"{orient}.TScrollbar", background=[("active", HOVER)])
