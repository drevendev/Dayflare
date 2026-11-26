"""Keep the dated 19-title CSV reproducible from its exact source capsule."""
import csv
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.m1_niche_signal_csv import export

ROOT = Path(__file__).resolve().parents[1]
RELATIVE = "downloads/dayflare-19-2026-11-23-weekly-signals.csv"
PIN = "7099eeb63b7db35411f349a332b852f1371b8d1b44f6f6e164fed903dea8a79d"


class DatedNicheCsvTests(unittest.TestCase):
    def test_download_matches_verified_export(self):
        raw = (ROOT / RELATIVE).read_bytes()
        self.assertEqual(len(raw), 10799)
        self.assertEqual(sha256(raw).hexdigest(), PIN)
        with TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "one.csv", Path(tmp) / "two.csv"
            self.assertEqual(export(first), raw)
            self.assertEqual(export(second), raw)
            self.assertEqual(first.read_bytes(), second.read_bytes())
        rows = list(csv.DictReader(raw.decode("utf-8").splitlines()))
        self.assertEqual(len(rows), 19)
        self.assertEqual(len(rows[0]), 25)
        self.assertEqual({row["observation_start"] for row in rows}, {"2026-10-20"})
        self.assertEqual({row["observation_end"] for row in rows}, {"2026-11-23"})
        self.assertEqual(len({row["project_page_id"] for row in rows}), 19)
        self.assertEqual(sum(int(row["opposite_nonzero_signs"]) for row in rows), 4)

    def test_readme_links_exact_dated_download(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("https://raw.githubusercontent.com/drevendev/Dayflare/master/" + RELATIVE, readme)
        self.assertIn(PIN, readme)
        self.assertIn("downloads/dayflare-19-2026-11-23.html", readme)
        self.assertIn("downloads/dayflare-30-2026-11-21.html", readme)


if __name__ == "__main__":
    unittest.main()
