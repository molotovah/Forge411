"""Captures d'écran du README avec des données de démonstration (Windows).

    python tools/screenshots.py            → docs/screenshots/19-profil.png, 21-brouillons.png, 25-historique.png
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
SHOTS = {"profil": "19-profil.png", "brouillons": "21-brouillons.png", "historique": "25-historique.png"}


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


def demo_profile(now: float) -> P.Profile:
    p = P.Profile(username="membre", member_since=datetime(2025, 3, 14, tzinfo=timezone.utc), level=37, xp=18420,
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
    rows = [("2026-11-20 18:02", "Big.Buck.Bunny.2008.VOSTFR.1080p.WEBRip.HDLight.AAC.2.0.x264-DEMO", "Films & Vidéos",
             "Publication", ok),
            ("2026-11-21 09:15", "Nine.Inch.Nails.Ghosts.I.IV.2008.FLAC[16bit.44.1kHz]-NOTAG", "Audio", "Brouillon",
             tor / "absent-1.torrent"),
            ("2026-11-22 21:40", "Les.Miserables.Victor.Hugo.FR.[EPUB]-NOTAG", "Ebook", "Publication", ok),
            ("2026-11-23 11:05", "Les.Miserables.Victor.Hugo.FR.[EPUB]-NOTAG", "Ebook", "Correction", ok),
            ("2026-11-24 15:30", "0 A.D. V0.27.0 [WIN X64 FR PORTABLE] [DRM FREE]", "Jeux Vidéo", "Brouillon (lot)",
             tor / "absent-2.torrent"),
            ("2026-11-25 10:12", "VLC.media.player.v3.0.21 [WINx64 FR UNLOCKED]", "Applications", "Publication", ok)]
    C.HISTORY_PATH.write_text("".join(json.dumps(
        {"date": d, "name": n, "type": t, "action": a, "torrent": str(p), "url": "https://c411.org/torrents/demo",
         "infohash": "ab"}) + "\n" for d, n, t, a, p in rows), encoding="utf-8")


def shoot(kind: str):
    from PIL import ImageGrab
    from forge411.ui.widgets import UI
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
        root.profile_cache = (demo_profile(time.time()), time.time())
        d = ProfileDialog(root)
    elif kind == "brouillons":
        from forge411.ui.drafts_view import DraftsDialog
        d = DraftsDialog(root)
    else:
        demo_history()
        from forge411.ui.dialogs import HistoryDialog
        d = HistoryDialog(root)
        root.after(800, lambda: (d.tree.selection_set(d.tree.get_children()[2]), d.tree.focus_set()))
    d.deiconify()
    d.lift()
    d.attributes("-topmost", True)

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
