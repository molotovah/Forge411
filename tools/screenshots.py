"""Captures d'écran du README avec des données de démonstration (Windows).

    python tools/screenshots.py            → docs/screenshots/ : Profil, Brouillons, Historique, notification de
                                             validation, Paramètres (compte, client torrent), À propos
    python tools/screenshots.py historique → une seule fenêtre

Aucune donnée personnelle : profil « membre », brouillons et historique fictifs, chemins sous
C:\\Users\\Public\\Forge411-demo, configuration et historique dans un dossier temporaire. Comparer les
nouvelles images aux précédentes (git diff) montre tout changement d'affichage d'une version à l'autre.
"""

import json
import sys
import tempfile
import time
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from forge411 import config as C, profile as P  # noqa: E402
from forge411.ui import theme as T  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
DEMO = Path(r"C:\Users\Public\Forge411-demo")
# Heure figée : sans elle, chaque capture changerait d'une exécution à l'autre (« Mis à jour à 17:34 »,
# ancienneté du compte, date du dernier upload) et le workflow commiterait des images identiques à l'œil.
NOW = time.mktime((2026, 11, 26, 18, 0, 0, 0, 0, -1))

SHOTS = {"profil": "19-profil.png", "brouillons": "21-brouillons.png", "historique": "25-historique.png",
         "validation": "26-validation.png", "parametres": "10-parametres.png",
         "parametres-client": "18-parametres-client.png", "a-propos": "23-a-propos.png"}

# Paramètres de démonstration : clés factices (masquées à l'écran), client qBittorrent sur un NAS
DEMO_SETTINGS = {"c411_api_key": "demo-0000-0000-0000", "tracker_url": "https://c411.org/announce/demo-passkey-0000",
                 "tmdb_api_key": "demo-tmdb", "rawg_api_key": "demo-rawg", "tpdb_api_key": "demo-tpdb",
                 "client_kind": "qbittorrent", "client_url": "http://192.168.1.10:8080", "client_user": "admin",
                 "client_password": "demo", "client_label": "C411", "client_path_local": "\\\\NAS\\Torrents",
                 "client_path_remote": "/downloads"}


class DemoApi:
    def drafts(self):
        return [{"id": 1, "name": "Big.Buck.Bunny.2008.VOSTFR.1080p.WEBRip.HDLight.AAC.2.0.x264-DEMO",
                 "subcategoryId": 6, "updatedAt": "2026-11-24T18:02:00"},
                {"id": 2, "name": "Les.Miserables.Victor.Hugo.FR.[EPUB]-NOTAG", "subcategoryId": 30,
                 "updatedAt": "2026-11-23T09:15:00"},
                {"id": 3, "name": "Nine.Inch.Nails.Ghosts.I.IV.2008.FLAC[16bit.44.1kHz]-NOTAG", "subcategoryId": 20,
                 "updatedAt": "2026-11-22T21:40:00"}]

    def categories(self):
        return [{"name": "Films & Vidéos", "subcategories": [{"id": 6, "name": "Animation"}]},
                {"name": "Ebook", "subcategories": [{"id": 30, "name": "Livres"}]},
                {"name": "Audio", "subcategories": [{"id": 20, "name": "Musique"}]}]


class DemoProfile(P.Profile):
    @property
    def days(self) -> int:
        return (datetime.fromtimestamp(NOW, timezone.utc) - self.member_since).days


def demo_profile(now: float) -> P.Profile:
    p = DemoProfile(username="membre", member_since=datetime(2025, 3, 14, tzinfo=timezone.utc), level=37, xp=18420,
                  xp_into=310, xp_next=239, class_name="Team Resident Mainstream", grade="Argent II", team_tag="EXT",
                  team_name="Team EXT", zen=1840, zen_earned=12650, zen_spent=10810, up_actual=5_500_000_000_000,
                  up_credit=100 * 1024 ** 3, up_total=5_607_000_000_000, down_actual=3_350_000_000_000,
                  down_credit=50 * 1024 ** 3, down_total=3_241_000_000_000, quests_done=12, quests_total=20,
                  freeleech=True, freeleech_sources=["Événement du site"])
    C.PROFILE_HISTORY_PATH.write_text(json.dumps(
        {"at": int(now - 3 * 86400), "level": 37, "xp": 18100, "up": p.up_total - 105_000_000_000,
         "down": p.down_total, "zen": 1500, "earned": 12310, "quests": 10}) + "\n", encoding="utf-8")
    return p


def demo_history():
    tor = DEMO / "torrents"
    tor.mkdir(parents=True, exist_ok=True)
    ok = tor / "Les.Miserables.Victor.Hugo.FR.[EPUB]-NOTAG.torrent"
    ok.write_bytes(b"d")
    ok_c411 = {"c411_status": "approved", "c411_validated": "2026-11-21 09:40"}
    rows = [("2026-11-20 18:02", "Big.Buck.Bunny.2008.VOSTFR.1080p.WEBRip.HDLight.AAC.2.0.x264-DEMO", "Films & Vidéos",
             "Publication", ok, "b1", ok_c411),
            ("2026-11-21 09:15", "Nine.Inch.Nails.Ghosts.I.IV.2008.FLAC[16bit.44.1kHz]-NOTAG", "Audio", "Brouillon",
             tor / "absent-1.torrent", "", {}),
            ("2026-11-22 21:40", "Les.Miserables.Victor.Hugo.FR.[EPUB]-NOTAG", "Ebook", "Publication", ok, "c2", {}),
            ("2026-11-22 23:10", "Les.Miserables.Victor.Hugo.FR.[EPUB]-NOTAG", "Ebook", "Correction", ok, "c2", {}),
            ("2026-11-24 15:30", "0 A.D. V0.27.0 [WIN X64 FR PORTABLE] [DRM FREE]", "Jeux Vidéo", "Brouillon (lot)",
             tor / "absent-2.torrent", "", {}),
            (time.strftime("%Y-%m-%d %H:%M", time.localtime(NOW)), "VLC.media.player.v3.0.21 [WINx64 FR UNLOCKED]", "Applications",
             "Publication", ok, "d3", {})]
    C.HISTORY_PATH.write_text("".join(json.dumps(
        {"date": d, "name": n, "type": t, "action": a, "torrent": str(p),
         "url": f"https://c411.org/torrents/{ih}" if ih else "https://c411.org/upload", "infohash": ih, **extra})
        + "\n" for d, n, t, a, p, ih, extra in rows), encoding="utf-8")


def shoot(kind: str):
    from PIL import ImageGrab
    from forge411.ui.widgets import UI
    time.time = lambda: NOW                   # statuts « En attente » / « À vérifier », délais du profil
    tmp = Path(tempfile.mkdtemp())
    C.HISTORY_PATH = tmp / "history.jsonl"
    C.PROFILE_HISTORY_PATH = tmp / "profile-history.jsonl"
    root = tk.Tk()
    root.geometry("1400x900+40+40")
    T.apply(root)
    UI.install(root)
    root.cfg = C.Config(tmp / "config.json")
    root.cfg.update({"output_dir": str(tmp)})
    root.c411 = DemoApi
    root.set_profile = lambda p: None
    root.open_correction = lambda e: None
    if kind == "profil":
        from forge411.ui.profile_view import ProfileDialog
        root.profile_cache = (demo_profile(NOW), NOW)
        d = ProfileDialog(root)
    elif kind == "brouillons":
        from forge411.ui.drafts_view import DraftsDialog
        d = DraftsDialog(root)
    elif kind in ("parametres", "parametres-client"):
        from forge411.ui.dialogs import SettingsDialog
        root.cfg.update(DEMO_SETTINGS)
        d = SettingsDialog(root, root.cfg, first_run=kind == "parametres")
        if kind == "parametres-client":
            d.select("client")
            d.client_msg.configure(text="✓  qBittorrent v5.1.2 connecté", fg=T.SUCCESS)   # sans client réel
    elif kind == "a-propos":
        from forge411.ui.about_view import AboutDialog
        root._icon = tk.PhotoImage(file=str(ROOT / "forge411" / "assets" / "forge411.png"))   # logo, comme l'app
        d = AboutDialog(root)
    elif kind == "validation":                 # notification « Validé sur C411 » (coin de la fenêtre principale)
        from forge411.ui.app import App
        root.geometry("760x300+40+40")
        root.configure(bg=T.BG)
        root.open_history = lambda: None
        App._toast(root, "Validé sur C411", "Big.Buck.Bunny.2008.VOSTFR.1080p.WEBRip.HDLight.AAC.2.0.x264-DEMO")
        d = root
    else:
        demo_history()
        from forge411.ui.dialogs import HistoryDialog
        d = HistoryDialog(root)
        root.after(800, lambda: (d.tree.selection_set(d.tree.get_children()[2]), d.tree.focus_set()))
    d.deiconify()
    d.lift()
    d.attributes("-topmost", True)
    if d is root:
        root.title("Forge411")

    def grab():
        d.update()
        x, y = d.winfo_rootx(), d.winfo_rooty()
        ImageGrab.grab(bbox=(x, y, x + d.winfo_width(), y + d.winfo_height()), all_screens=True).save(
            OUT / SHOTS[kind])
        root.destroy()
        print("->", OUT / SHOTS[kind])          # ASCII : la console Windows (cp1252) refuse « → »
    root.after(2500, grab)
    root.mainloop()


if __name__ == "__main__":
    if sys.platform != "win32":
        sys.exit("Captures prévues pour Windows (rendu des polices Segoe UI).")
    kinds = sys.argv[1:] or list(SHOTS)
    if len(kinds) == 1:
        T.enable_dpi_awareness()
        shoot(kinds[0])
    else:                                    # un processus par fenêtre : Tk n'aime pas deux racines successives
        import subprocess
        for k in kinds:
            subprocess.run([sys.executable, __file__, k], check=True)
