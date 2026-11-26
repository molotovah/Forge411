"""
Règles d'interface vérifiées sur le code source (sans ouvrir de fenêtre) : chacune empêche le retour d'un
défaut d'affichage constaté sous Windows.
"""

import ast
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "forge411"
UI_FILES = sorted((PKG / "ui").glob("*.py")) + sorted((PKG / "profiles").glob("*.py"))

# Caractères non latins sûrs dans les polices de texte (Segoe UI) : au-delà, Windows prend une police de
# secours, mal alignée ou affichée en carré (« ⟳ Actualiser » des brouillons et du profil).
SAFE_SYMBOLS = set("…·«»’—–→←↗↑✓✕×•▾▴●›⚠")


def _calls(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if (isinstance(f, ast.Name) and f.id == name) or (isinstance(f, ast.Attribute) and f.attr == name):
                yield node


def _str_args(call):
    for a in list(call.args) + [k.value for k in call.keywords if k.arg == "text"]:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            yield a.value
        elif isinstance(a, ast.JoinedStr):
            yield "".join(v.value for v in a.values if isinstance(v, ast.Constant) and isinstance(v.value, str))


class UiRulesTests(unittest.TestCase):
    def test_no_emoji_variation_selector(self):
        """U+FE0F (🕹️) est dessiné comme un espace large par Tk : icône Émulation décalée."""
        bad = [f.name for f in UI_FILES if "️" in f.read_text(encoding="utf-8")]
        self.assertEqual(bad, [])

    def test_text_uses_safe_glyphs(self):
        """Textes des boutons et libellés (police Segoe UI) : pas de symbole absent de la police. Les icônes en
        police F_ICON (Segoe UI Symbol) ne sont pas concernées."""
        problems = []
        for f in sorted((PKG / "ui").glob("*.py")):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for name in ("Btn", "Label", "label", "configure", "set_text", "badge"):
                for call in _calls(tree, name):
                    font = next((k.value for k in call.keywords if k.arg == "font"), None)
                    if isinstance(font, ast.Attribute) and font.attr == "F_ICON":
                        continue
                    for text in _str_args(call):
                        odd = {c for c in text if ord(c) > 0x24F and c not in SAFE_SYMBOLS}
                        if odd:
                            problems.append(f"{f.name}:{call.lineno} {text!r} {sorted(odd)}")
        self.assertEqual(problems, [])

    def test_tables_use_shared_style(self):
        """Un ttk.Treeview sans style_tree garde la bordure claire et les en-têtes du thème par défaut."""
        bad = [f.name for f in sorted((PKG / "ui").glob("*.py"))
               if "ttk.Treeview(" in (t := f.read_text(encoding="utf-8")) and "style_tree(" not in t]
        self.assertEqual(bad, [])

    def test_long_checkbox_labels_wrap(self):
        """Le texte d'un ttk.Checkbutton ne passe pas à la ligne : coupé par la fenêtre au-delà d'une ligne."""
        problems = []
        for f in sorted((PKG / "ui").glob("*.py")):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for call in _calls(tree, "Checkbutton"):
                for text in _str_args(call):
                    if len(text) > 60:
                        problems.append(f"{f.name}:{call.lineno} ({len(text)} caractères)")
        self.assertEqual(problems, [])

    def test_fixed_pixel_sizes_follow_dpi(self):
        """Dimensions de la fenêtre Paramètres en pixels : mises à l'échelle (T.px), sinon rognées à 125 %."""
        src = (PKG / "ui" / "dialogs.py").read_text(encoding="utf-8")
        settings = src[src.index("class SettingsDialog"):src.index("class MultiSelectDialog")]
        for needle in ("T.px(self, 210)", "T.px(self, self.LABEL_W)", "T.px(self, 48 if"):
            self.assertIn(needle.split("(", 1)[0], settings)
            self.assertIn(needle, src)
        self.assertIn("T.px(self, width)", src)       # toutes les fenêtres : taille de départ mise à l'échelle

    def test_hover_reset_on_click(self):
        """Un survol actif au moment d'ouvrir une fenêtre modale restait affiché à sa fermeture."""
        widgets = (PKG / "ui" / "widgets.py").read_text(encoding="utf-8")
        app = (PKG / "ui" / "app.py").read_text(encoding="utf-8")
        self.assertIn("self.configure(bg=self._bg)", widgets[widgets.index("def _click"):])
        self.assertIn("hover(row.winfo_containing(x, y) in parts)", app)


if __name__ == "__main__":
    unittest.main()
