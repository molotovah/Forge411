"""Captures d'écran du README avec des données de démonstration (Windows).

    python tools/screenshots.py            → docs/screenshots/ : Profil, Brouillons, Historique, notification de
                                             validation, Paramètres (compte, client torrent), À propos
    python tools/screenshots.py historique → une seule fenêtre
    python tools/screenshots.py profil-clair → la même en thème clair (README : <picture> clair / sombre)

Aucune donnée personnelle : profil « membre », brouillons et historique fictifs, chemins sous
C:\\Users\\Public\\Forge411-demo, configuration et historique dans un dossier temporaire. Comparer les
nouvelles images aux précédentes (git diff) montre tout changement d'affichage d'une version à l'autre.
"""

import json
import os
import shutil
import sys
import tempfile
import time
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LIGHT = "-clair"
DEMO = Path(r"C:\Users\Public\Forge411-demo")
if len(sys.argv) == 2:
    # Configuration temporaire, écrite avant tout import de forge411 (le thème est lu à l'import de l'interface) :
    # aucune configuration réelle n'est lue ni modifiée. Clés factices pour que l'assistant ne demande rien.
    _cfg = Path(tempfile.mkdtemp()) / "Forge411"
    _cfg.mkdir()
    (_cfg / "config.json").write_text(json.dumps({
        "theme": "light" if sys.argv[1].endswith(LIGHT) else "dark", "theme_chosen": True,
        "c411_api_key": "demo-0000-0000-0000", "tracker_url": "https://c411.org/announce/demo-passkey-0000",
        "tmdb_api_key": "demo-tmdb", "rawg_api_key": "demo-rawg", "tpdb_api_key": "demo-tpdb",
        "output_dir": str(DEMO / "sortie"), "tour_done": True, "check_updates": False, "team_tag_auto": False,
        "translate_overview": False}), encoding="utf-8")
    os.environ["APPDATA"] = str(_cfg.parent)

from forge411 import config as C, profile as P  # noqa: E402
from forge411.ui import theme as T  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
# Heure figée : sans elle, chaque capture changerait d'une exécution à l'autre (« Mis à jour à 17:34 »,
# ancienneté du compte, date du dernier upload) et le workflow commiterait des images identiques à l'œil.
NOW = time.mktime((2026, 11, 26, 18, 0, 0, 0, 0, -1))

SHOTS = {"profil": "19-profil.png", "brouillons": "21-brouillons.png", "historique": "25-historique.png",
         "validation": "26-validation.png", "parametres": "10-parametres.png",
         "parametres-client": "18-parametres-client.png", "a-propos": "23-a-propos.png"}
# Assistant (fenêtre principale) : capture → (fichier, source de démonstration, étape, particularité)
BBB = "Big.Buck.Bunny.2008.MULTi.1080p.BluRay.x264-NOTAG.mkv"
WIZARD = {
    "visite-guidee": ("02-visite-guidee.png", None, 0, "tour"),
    "source": ("03-source.png", BBB, 0, ""),
    "identification": ("04-identification.png", BBB, 1, ""),
    "identification-clair": ("04-identification-clair.png", BBB, 1, ""),      # image principale du README
    "nom": ("05-nom.png", BBB, 2, ""),
    "aide-au-survol": ("06-aide-au-survol.png", BBB, 2, "tooltip"),
    "nfo": ("07-nfo.png", BBB, 3, ""),
    "presentation": ("08-presentation.png", BBB, 4, ""),
    "publication": ("09-publication.png", BBB, 5, "seeded"),
    "musique-identification": ("12-musique-identification.png", "Daft Punk - Discovery (2001) [FLAC]", 1, ""),
    "ebook-identification": ("13-ebook-identification.png",
                             "Alexandre.Dumas-Le.Comte.de.Monte-Cristo.FRENCH.EPUB-NOTAG.epub", 1, ""),
    "jeu-source": ("14-jeu-source.png", "Celeste.v1.4.0.0-GOG", 0, ""),
    "jeu-identification": ("15-jeu-identification.png", "Celeste.v1.4.0.0-GOG", 1, ""),
    "jeu-nom": ("16-jeu-nom.png", "Celeste.v1.4.0.0-GOG", 2, ""),
    "deja-sur-c411": ("17-deja-sur-c411.png", BBB, 5, "catalog"),
    "mode-clair": ("20-mode-clair.png", BBB, 0, ""),
    "mode-lot": ("22-mode-lot.png", None, 0, "batch"),
    "correction": ("24-correction.png", BBB, 5, "correction"),
}
SHOTS.update({k: v[0] for k, v in WIZARD.items()})
# Variantes claires des captures du README (balise <picture> : suit le thème GitHub du visiteur)
SHOTS.update({k + LIGHT: SHOTS[k].replace(".png", LIGHT + ".png")
              for k in ("profil", "brouillons", "historique", "parametres-client")})

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


def shoot(name: str):
    if name in WIZARD:
        return shoot_wizard(name)
    kind = name.removesuffix(LIGHT)
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
            OUT / SHOTS[name])
        root.destroy()
        print("->", OUT / SHOTS[name])          # ASCII : la console Windows (cp1252) refuse « → »
    root.after(2500, grab)
    root.mainloop()


# ── Assistant ─────────────────────────────────────────────────────────────

# Message de la Team Pending (capture « Corriger une validation »)
FIX_MESSAGE = ("Merci pour l'upload, mais voici des points à corriger avant validation : 1. Nommage > Films - La Source "
               "doit être placée après la résolution dans le titre. 2. Disponibilite du torrent - Il n'y a aucun Seed "
               "sur le torrent, attention ! 3. Description - Ajoute au moins une capture d'écran.")


def shoot_wizard(name: str):
    """Fenêtre principale de Forge411 pilotée sur une source de démonstration, puis capturée à l'étape voulue."""
    from unittest import mock
    from PIL import ImageGrab
    from tools import demo_wizard as W
    from forge411.ui import app as A
    from forge411.ui.widgets import UI, Tooltip
    file, source, step, extra = WIZARD[name]
    time.time = lambda: NOW
    src_root = W.sources(DEMO)
    shutil.rmtree(DEMO / "sortie", ignore_errors=True)
    api = W.DemoC411()
    for p in W.patches() + [mock.patch.object(A.App, "c411", lambda self: api),
                            mock.patch.object(A.App, "fetch_profile", lambda self, *a, **k: None)]:
        p.start()
    clients = W.client_for(None)
    A.App.client = lambda self, provider: clients(provider)
    app = A.App()
    app.geometry("1280x800+20+20")
    app.attributes("-topmost", True)
    app.set_profile(demo_profile(NOW))
    errors = []
    app.report_callback_exception = lambda *a: errors.append(a)

    def finish(target=None):
        target = target or app
        target.update()
        x, y = target.winfo_rootx(), target.winfo_rooty()
        ImageGrab.grab(bbox=(x, y, x + target.winfo_width(), y + target.winfo_height()), all_screens=True).save(OUT / file)
        print("->", OUT / file, flush=True)
        if errors:
            import traceback
            for e in errors:
                traceback.print_exception(*e)
        os._exit(1 if errors else 0)

    def settle(then, quiet=0, waited=0):
        """Attend la fin des traitements en arrière-plan (analyse, recherche, hachage) et des images."""
        if waited > 240:                      # 60 s
            print("Délai dépassé : étape", app.current, flush=True)
            os._exit(2)
        idle = not app._busy and UI._q.empty()
        quiet = quiet + 1 if idle else 0
        if quiet >= 4:
            app.after(800, then)
        else:
            app.after(250, lambda: settle(then, quiet, waited + 1))

    def advance():
        if app.current >= step:
            return settle(special)
        if not app.steps[app.current].ready():
            print("Étape incomplète :", app.current, flush=True)
            os._exit(3)
        app.next()
        settle(advance)

    def special():
        pub = app.steps[-1]
        if extra in ("seeded", "catalog", "correction"):
            pub.seed_confirm.set(True)
            pub.render_checks()
        if extra == "catalog":
            card = pub.cat_box.master.master
            pub.sf.canvas.yview_moveto(max(0.0, card.winfo_y() / max(pub.sf.inner.winfo_height(), 1) - 0.25))
        elif extra == "correction":
            from forge411 import correction as FIX
            s = app.session
            s.correction = {"infohash": s.infohash, "url": FIX.torrent_page(s.infohash), "message": FIX_MESSAGE,
                            "points": FIX.parse(FIX_MESSAGE), "published": s.name}
            app.show(app.current)
        elif extra == "tooltip":
            st = app.steps[app.current]
            icon = next((w for w in _walk(st) if isinstance(w, tk.Label) and w.cget("text") == "?"
                         and any(isinstance(c, tk.Label) and c.cget("text") == "Source"
                                 for c in w.master.winfo_children())), None)
            if icon is not None:
                icon.event_generate("<Enter>")
        app.after(900, finish)

    def start():
        Tooltip.hide_all()
        if extra == "tour":
            app.start_tour()
            return app.after(1200, finish)
        if extra == "batch":
            from forge411.ui import batch_view as BV
            from forge411 import batch as B
            with mock.patch.object(BV.filedialog, "askdirectory", lambda **k: str(src_root)):
                d = BV.BatchDialog(app)
                d.deiconify()
                d.attributes("-topmost", True)
                d.pick()

            def prepared(waited=0):            # préparation du lot dans son propre fil : attendre chaque ligne
                if any(it.status == B.PENDING for it in d.items) and waited < 240:
                    return app.after(250, lambda: prepared(waited + 1))
                d.tree.selection_set(d.tree.get_children()[0])
                settle(lambda: finish(d))
            return prepared()
        app.steps[0].analyze(src_root / source)
        settle(advance)
    app.after(1500, start)
    app.mainloop()


def _walk(w):
    for c in w.winfo_children():
        yield c
        yield from _walk(c)


if __name__ == "__main__":
    if sys.platform != "win32":
        sys.exit("Captures prévues pour Windows (rendu des polices Segoe UI).")
    kinds = sys.argv[1:] or list(SHOTS)
    if len(kinds) == 1:
        T.enable_dpi_awareness()
        shoot(kinds[0])
    else:                                    # un processus par fenêtre : Tk n'aime pas deux racines successives
        import subprocess
        for k in kinds:                      # délai maximal : une capture bloquée échoue au lieu de tout figer
            subprocess.run([sys.executable, __file__, k], check=True, timeout=180)
