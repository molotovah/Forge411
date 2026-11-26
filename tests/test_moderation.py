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

    def test_to_check_skips_drafts_validated_and_duplicates(self):
        entries = [entry(ih="aa"), entry(action="Correction", ih="aa", date="2026-11-26 11:00"),
                   entry(ih="bb", c411_status="approved"), entry(action="Brouillon", ih="cc"),
                   entry(ih="dd")]
        self.assertEqual(M.to_check(entries), ["aa", "dd"])


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


if __name__ == "__main__":
    unittest.main()
