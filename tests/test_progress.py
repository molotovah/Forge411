"""Suivi du hachage et de la vérification (étape 6) : vitesse, temps écoulé, temps restant."""

import unittest

from forge411.progress import RateMeter, fmt_eta, fmt_rate

M = 1024 * 1024


class RateMeterTests(unittest.TestCase):
    def test_steady_speed_and_eta(self):
        m = RateMeter(1000 * M, start=0.0)
        r = None
        for t in range(1, 5):
            r = m.update(t * 100 * M, now=float(t))
        self.assertAlmostEqual(r.speed, 100 * M)
        self.assertAlmostEqual(r.eta, 6.0)
        self.assertAlmostEqual(r.elapsed, 4.0)
        self.assertAlmostEqual(r.fraction, 0.4)

    def test_speed_follows_recent_window(self):
        """Le disque ralentit : la vitesse affichée suit les dernières secondes, pas la moyenne."""
        m = RateMeter(10000 * M, window=5.0, start=0.0)
        done = 0
        for t in range(1, 11):
            done += 200 * M
            m.update(done, now=float(t))
        for t in range(11, 21):
            done += 50 * M
            r = m.update(done, now=float(t))
        self.assertAlmostEqual(r.speed, 50 * M)
        self.assertAlmostEqual(r.average, done / 20)

    def test_unknown_until_measurable(self):
        m = RateMeter(100 * M, start=0.0)
        r = m.update(M, now=0.1)
        self.assertEqual(r.speed, 0.0)
        self.assertIsNone(r.eta)
        self.assertEqual(fmt_eta(r.eta), "…")
        self.assertEqual(fmt_rate(r.speed), "…")

    def test_finished_eta_zero(self):
        r = RateMeter(10 * M, start=0.0).update(10 * M, now=2.0)
        self.assertEqual(r.eta, 0.0)
        self.assertEqual(fmt_eta(r.eta), "0:00")

    def test_client_started_before_tracking(self):
        """Le client avait déjà vérifié 60 % : la moyenne ne compte que ce qui a été relu depuis."""
        m = RateMeter(100 * M, done=60 * M, start=0.0)
        r = m.update(80 * M, now=2.0)
        self.assertAlmostEqual(r.average, 10 * M)
        self.assertAlmostEqual(r.speed, 10 * M)
        self.assertAlmostEqual(r.eta, 2.0)

    def test_recheck_restarts_measure(self):
        """Le client relance la vérification (progression qui redescend) : pas de vitesse négative."""
        m = RateMeter(100 * M, start=0.0)
        m.update(50 * M, now=5.0)
        r = m.update(5 * M, now=6.0)
        self.assertGreaterEqual(r.speed, 0.0)
        self.assertEqual(r.elapsed, 0.0)
        r = m.update(15 * M, now=8.0)
        self.assertAlmostEqual(r.speed, 5 * M)

    def test_peak_kept_for_final_summary(self):
        """Fin de copie : la vitesse maximale reste connue (bilan), même si la dernière mesure est plus basse."""
        m = RateMeter(1000 * M, window=2.0, start=0.0)
        done = 0
        for t, step in enumerate([100, 100, 300, 300, 50, 50, 50, 50], 1):
            done += step * M
            r = m.update(done, now=float(t))
        self.assertAlmostEqual(r.peak, 300 * M)
        self.assertLess(r.speed, r.peak)

    def test_formats(self):
        self.assertEqual(fmt_rate(150 * M), "150.0 Mo/s")
        self.assertEqual(fmt_eta(3725), "1:02:05")
        self.assertEqual(fmt_eta(65), "1:05")


if __name__ == "__main__":
    unittest.main()
