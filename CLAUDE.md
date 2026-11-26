# Forge411 : règles de travail

## Commits, releases
- Jamais de mention de Claude ou d'Anthropic (ni `Co-Authored-By`, ni « Generated with ») dans les commits, PR, tags ou notes de version. Auteur : molotovah. Le hook `.githooks/commit-msg` le refuse.
- Hooks du dépôt, une fois par clone : `git config core.hooksPath .githooks`. Le hook `pre-commit` lance tous les tests et `ruff check --select F`.
- Release : version dans `forge411/__init__.py` et `version_info.txt`, section dans `CHANGELOG.md` (elle devient la note de version), commit « Forge411 x.y.z », tag `vx.y.z`. Le workflow Release refuse de compiler si un test échoue.

## Bugs : ne jamais les revoir
- Tout bug corrigé arrive avec un test qui échoue sans la correction. Vérifier : remettre l'ancien fichier (`git stash push -- fichier`), constater l'échec, reprendre la correction.
- La suite doit passer partout (Linux et Windows). Une vérification ne dépend jamais de l'environnement (bibliothèque présente ou non) mais des données analysées.
- Nouveau type de contenu, nouveau format de nom ou nouvelle règle C411 : ajouter le cas dans `tests/test_e2e.py` (source de démo, réponses enregistrées, nom attendu exact).
- Défaut d'affichage : ajouter la règle correspondante dans `tests/test_ui_rules.py` quand elle se vérifie sur le code.

## Interface (Tk sous Windows)
- Texte des boutons : caractères présents dans Segoe UI (pas de ⟳), jamais d'emoji avec U+FE0F.
- Case à cocher au libellé long : `wrap_check`. Tableau : `style_tree`. Nom de release long dans un libellé : `wrap_name`.
- Dimensions fixes en pixels : `T.px(widget, n)` (affichage Windows à 125 %, 150 %).
- Tester sous Windows avec Python 3.13 (même Tk 8.6 que l'exe), pas 3.14.

## Documentation
- README = vitrine courte (accroche, aperçu, démarrage rapide, liens). Le guide détaillé va dans le wiki : `docs/wiki/*.md`, publié sur le wiki GitHub par le workflow « Wiki » à chaque push sur main (ne jamais éditer le wiki sur le site : écrasé).
- Wiki : images en URL absolue `https://raw.githubusercontent.com/molotovah/Forge411/main/docs/screenshots/…`, liens entre pages par nom de page (`[Texte](Nom-de-page)`, `<…>` si accents). `tests/test_docs.py` vérifie liens et images.

## Captures d'écran
- README : données de démonstration uniquement (profil « membre », chemins sous `C:\Users\Public\Forge411-demo`), jamais le compte, l'historique ni le nom d'utilisateur Windows réels.
- `python tools/screenshots.py` (Windows) régénère toutes les captures du README et du wiki : fenêtres (Profil, Brouillons, Historique, Paramètres, À propos…) et assistant piloté sur les sources de démonstration (`tools/demo_wizard.py`, réutilise `tests/test_e2e.py`) ; `python tools/screenshots.py nom` pour une seule. Comparer avec `git diff`.
- Captures régénérées en local : pour vérifier un affichage uniquement, ne pas les commiter (`git checkout docs/screenshots`) ; seules celles du workflow font foi.
- À chaque tag `v*`, le workflow « Captures du README » (`.github/workflows/screenshots.yml`) les régénère sur Windows et les commite sur main (github-actions[bot]) si elles changent : faire `git pull` après une release.
- Tests manuels sur la vraie app : sauvegarder `%APPDATA%\Forge411` avant, ne jamais publier ni envoyer de brouillon, supprimer ensuite les .torrent, NFO et captures créés.
