"""Suivi de la validation des uploads par la Team Pending (statut C411 dans l'historique)."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from forge411 import config as C, moderation as M
from forge411.api import C411, C411Error

NOW = time.mktime(time.strptime("2026-11-26 12:00", "%Y-%m-%d %H:%M"))


def entry(action="Publication", ih="aa", date="2026-11-26 10:00", **kw):
    return {"date": date, "name": f"Release.{ih}-T", "type": "Film", "action": action, "infohash": ih,
            "url": f"https://c411.org/torrents/{ih}", **kw}


class Resp:
    def __init__(self, code, body=None):
        self.status_code, self._body = code, body
        self.headers = {"content-type": "application/json"}

    def json(self):
        if self._body is None:
            raise ValueError
        return self._body


class ApiStatusTests(unittest.TestCase):
    def test_404_means_not_visible_yet(self):
        api = C411("cle")
        with mock.patch.object(api, "_req", return_value=Resp(404, {"message": "Torrent not found"})) as req:
            self.assertIsNone(api.torrent_status("ABCDEF"))
        req.assert_called_once_with("GET", "/api/torrents/abcdef")

    def test_200_returns_public_record(self):
        api = C411("cle")
        with mock.patch.object(api, "_req", return_value=Resp(200, {"data": {"status": "approved", "name": "X"}})):
            self.assertEqual(api.torrent_status("ab")["status"], "approved")

    def test_errors_are_raised(self):
        api = C411("cle")
        for code in (401, 500):
            with mock.patch.object(api, "_req", return_value=Resp(code, {})):
                with self.assertRaises(C411Error):
                    api.torrent_status("ab")


class LabelTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(M.label(entry(action="Brouillon"), NOW), "—")
        self.assertEqual(M.label(entry(), NOW), "En attente")
        self.assertEqual(M.label(entry(date="2026-11-20 10:00"), NOW), "À vérifier")       # plus de 3 jours
        self.assertEqual(M.label(entry(c411_status="approved"), NOW), "Validé")
        self.assertEqual(M.label(entry(c411_status="rejected"), NOW), "Refusé")

    def test_same_torrent_same_status_counted_from_last_submission(self):
        pub = entry(ih="c2", date="2026-11-20 10:00")
        fix = entry(action="Correction", ih="c2", date="2026-11-25 10:00")   # correction : l'attente repart
        self.assertEqual(M.labels([pub, fix], NOW), ["En attente", "En attente"])
        self.assertEqual(M.labels([pub], NOW), ["À vérifier"])

    def test_to_check_skips_old_drafts_validated_and_duplicates(self):
        entries = [entry(ih="aa"), entry(action="Correction", ih="aa", date="2026-11-26 11:00"),
                   entry(ih="bb", c411_status="approved"), entry(action="Brouillon", ih="cc"),
                   entry(action="Brouillon", ih="ee", date="2026-09-01 10:00"), entry(ih="dd")]
        # brouillon récent suivi (publié peut-être depuis le site), brouillon de plus de 30 jours ignoré
        self.assertEqual(M.to_check(entries, NOW), ["aa", "cc", "dd"])

    def test_draft_published_from_site_counts_once_validated(self):
        """Brouillon publié depuis la page d'upload du site : même info-hash, validé comme un upload."""
        draft = entry(action="Brouillon", ih="cc", c411_status="approved")
        self.assertEqual(M.label(draft, NOW), "Validé")
        self.assertEqual(M.label(entry(action="Brouillon", ih="cc"), NOW), "—")
        self.assertEqual(M.approved_count([draft]), 1)


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = C.HISTORY_PATH
        C.HISTORY_PATH = Path(self.tmp.name) / "history.jsonl"
        self.entries = [entry(ih="aa"), entry(action="Correction", ih="aa", date="2026-11-26 11:00"), entry(ih="bb"),
                        entry(ih="cc")]
        C.HISTORY_PATH.write_text("".join(json.dumps(e) + "\n" for e in self.entries), encoding="utf-8")

    def tearDown(self):
        C.HISTORY_PATH = self.old
        self.tmp.cleanup()

    def test_validated_torrent_is_recorded_on_every_entry(self):
        class Api:
            def torrent_status(self, ih):
                if ih == "cc":
                    raise C411Error("réseau")                 # n'empêche pas de vérifier les autres
                return {"status": "approved"} if ih == "aa" else None
        newly = M.check(Api(), self.entries, now=NOW)
        self.assertEqual(newly, ["Release.aa-T"])
        hist = C.read_history()
        aa = [h for h in hist if h["infohash"] == "aa"]
        self.assertEqual(len(aa), 2)
        self.assertTrue(all(h["c411_status"] == "approved" and h["c411_validated"] == "2026-11-26 12:00" for h in aa))
        bb = next(h for h in hist if h["infohash"] == "bb")
        self.assertNotIn("c411_status", bb)                   # toujours invisible : en attente
        self.assertEqual(bb["c411_checked"], "2026-11-26 12:00")
        self.assertEqual(sorted(M.to_check(hist)), ["bb", "cc"])   # « aa » n'est plus interrogé
        self.assertEqual(M.check(Api(), hist, now=NOW), [])   # pas de nouvelle notification

    def test_rejection_reason_is_kept(self):
        class Api:
            def torrent_status(self, ih):
                return {"status": "rejected", "rejectionReason": "Doublon"} if ih == "bb" else None
        self.assertEqual(M.check(Api(), self.entries, now=NOW), [])
        bb = next(h for h in C.read_history() if h["infohash"] == "bb")
        self.assertEqual((M.label(bb, NOW), bb["c411_reason"]), ("Refusé", "Doublon"))

    def test_history_rows_still_removable_after_update(self):
        C.update_history("bb", c411_checked="2026-11-26 12:00")
        bb = next(h for h in C.read_history() if h["infohash"] == "bb")
        self.assertEqual(C.remove_history([bb]), 1)


class PendingLimitTests(unittest.TestCase):
    """Règle C411 : non certifié (moins de 15 torrents validés), un seul upload à la fois en attente."""

    def test_one_waiting_blocks_until_certified(self):
        entries = [entry(ih="aa", c411_status="approved"), entry(ih="bb")]
        self.assertEqual(M.publish_blocker(entries), "Release.bb-T")
        self.assertEqual(M.publish_blocker(entries, declared_certified=True), "")

    def test_modification_requested_still_waiting(self):
        """Pas visible sur C411 depuis des jours (modification demandée) : toujours en attente."""
        entries = [entry(ih="bb", date="2026-11-01 10:00")]
        self.assertEqual(M.label(entries[0], NOW), "À vérifier")
        self.assertEqual(M.waiting(entries), [("bb", "Release.bb-T")])

    def test_closed_and_drafts_do_not_block(self):
        entries = [entry(ih="aa", c411_status="approved"), entry(ih="bb", c411_status="rejected"),
                   entry(action="Brouillon", ih="cc")]
        self.assertEqual(M.waiting(entries), [])
        self.assertEqual(M.publish_blocker(entries), "")

    def test_correction_of_waiting_torrent_not_blocked_by_itself(self):
        entries = [entry(ih="bb"), entry(action="Correction", ih="bb", date="2026-11-26 11:00")]
        self.assertEqual(M.waiting(entries), [("bb", "Release.bb-T")])
        self.assertEqual(M.publish_blocker(entries, exclude="BB"), "")

    def test_certified_after_15_validated(self):
        ok = [entry(ih=f"{i:02x}", c411_status="approved") for i in range(M.CERTIFIED_AT - 1)]
        waiting = [entry(ih="ff")]
        self.assertFalse(M.is_certified(ok))
        self.assertTrue(M.publish_blocker(ok + waiting))
        ok.append(entry(ih="fe", c411_status="approved"))
        ok.append(entry(action="Correction", ih="fe", c411_status="approved"))     # même torrent : compté une fois
        self.assertEqual(M.approved_count(ok), M.CERTIFIED_AT)
        self.assertEqual(M.publish_blocker(ok + waiting), "")


class CaptureCleanupTests(unittest.TestCase):
    def test_only_validated_torrents_lose_their_captures(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            cfg = C.Config(out / "config.json")
            cfg.update({"output_dir": str(out)})
            root = cfg.captures_dir
            for n in ("Release.aa-T", "Release.aa.v2-T", "Release.bb-T", "Brouillon-T"):
                (root / n).mkdir(parents=True)
                (root / n / "capture-01.png").write_bytes(b"png")
            entries = [entry(ih="aa", c411_status="approved", shots_dir=str(root / "Release.aa-T")),
                       entry(action="Correction", ih="aa", name="Release.aa.v2-T"),     # nom corrigé, même torrent
                       entry(ih="bb"),                                                  # en attente : gardées
                       entry(action="Brouillon", ih="", name="Brouillon-T")]
            C.remove_captures(cfg, *M.validated_capture_dirs(root, entries))
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["Brouillon-T", "Release.bb-T"])

    def test_only_validated_torrents_lose_their_nfo(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            cfg = C.Config(out / "config.json")
            cfg.update({"output_dir": str(out)})
            root = cfg.nfo_dir
            root.mkdir(parents=True, exist_ok=True)
            for n in ("Release.aa-T", "Release.aa.v2-T", "Release.bb-T", "Brouillon-T", "Ancien-T"):
                (root / f"{n}.nfo").write_text("nfo")
            src = out / "source"
            src.mkdir()
            (src / "Release.cc-T.nfo").write_text("nfo de la source")
            entries = [entry(ih="aa", c411_status="approved", nfo=str(root / "Release.aa-T.nfo")),
                       entry(action="Correction", ih="aa", name="Release.aa.v2-T"),     # nom corrigé, même torrent
                       entry(ih="dd", c411_status="approved", name="Ancien-T"),         # sans chemin noté
                       entry(ih="cc", c411_status="approved", nfo=str(src / "Release.cc-T.nfo")),
                       entry(ih="bb"),                                                  # en attente : gardé
                       entry(action="Brouillon", ih="", name="Brouillon-T")]
            n = C.remove_nfos(cfg, *M.validated_nfo_files(root, entries))
            self.assertEqual(n, 3)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["Brouillon-T.nfo", "Release.bb-T.nfo"])
            self.assertTrue((src / "Release.cc-T.nfo").exists())        # hors du dossier des NFO : jamais touché


class OrphanCleanupTests(unittest.TestCase):
    """Upload abandonné avant l'envoi : captures et NFO sans entrée dans l'historique, supprimés après 7 jours."""

    def test_orphans_old_and_unknown_only(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            old = time.time() - 10 * 86400
            for n in ("Abandon-T", "Release.aa-T", "EnCours-T", "Recent-T"):
                (root / n).mkdir()
            for n in ("Abandon-T", "Release.aa-T", "EnCours-T"):
                os.utime(root / n, (old, old))
            (root / "Abandon-T.nfo").write_text("x")
            (root / "Release.aa-T.nfo").write_text("x")
            for n in ("Abandon-T.nfo", "Release.aa-T.nfo"):
                os.utime(root / n, (old, old))
            entries = [entry(ih="aa")]                               # « Release.aa-T » : dans l'historique
            self.assertEqual([p.name for p in M.orphans(root, entries, keep=["EnCours-T"])], ["Abandon-T"])
            self.assertEqual([p.name for p in M.orphans(root, entries, suffix=".nfo")], ["Abandon-T.nfo"])

if __name__ == "__main__":
    unittest.main()
