"""README et wiki (docs/wiki) : liens internes, images et pages existants. Un lien cassé se voit ici, avant que
le workflow Wiki ne publie les pages."""

import re
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "docs" / "wiki"
RAW = "https://raw.githubusercontent.com/molotovah/Forge411/main/"
LINK = re.compile(r"\]\((<[^>]+>|[^)\s]+)\)")
SRC = re.compile(r'(?:src|srcset)="([^"]+)"')


def _targets(text):
    for m in LINK.finditer(text):
        yield m.group(1).strip("<>")


class DocsTests(unittest.TestCase):
    def test_readme_files_exist(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        missing = []
        for t in list(_targets(text)) + SRC.findall(text):
            if t.startswith(("http", "#", "../../")):
                continue
            if not (ROOT / unquote(t.split("#")[0])).exists():
                missing.append(t)
        self.assertEqual(missing, [])

    def test_readme_wiki_links_point_to_pages(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        pages = {p.stem for p in WIKI.glob("*.md")}
        bad = [t for t in _targets(text) if t.startswith("../../wiki/") and unquote(t[len("../../wiki/"):]) not in pages]
        self.assertEqual(bad, [])

    def test_wiki_links_and_images(self):
        pages = {p.stem for p in WIKI.glob("*.md")}
        self.assertIn("Home", pages)
        bad = []
        for page in sorted(WIKI.glob("*.md")):
            text = page.read_text(encoding="utf-8")
            for t in _targets(text):
                if t.startswith(RAW):
                    if not (ROOT / t[len(RAW):]).exists():
                        bad.append(f"{page.name} : {t}")
                elif not t.startswith(("http", "#", "mailto:")) and unquote(t.split("#")[0]) not in pages:
                    bad.append(f"{page.name} : {t}")
            for src in SRC.findall(text):
                if not src.startswith(RAW) or not (ROOT / src[len(RAW):]).exists():
                    bad.append(f"{page.name} : image {src}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
