# Développement

## Lancer depuis le code

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # Windows
.venv/Scripts/python Forge411.pyw
```

## Tests

```bash
python -m unittest -v
```

Les tests couvrent la création des torrents (vérifiée pièce par pièce), la détection du type de contenu, les tags vidéo déduits des pistes, la construction des noms de chaque catégorie, les tables de type de release (jeux, applications) et les options C411 automatiques. Toute correction de bug vient avec un test qui la reproduit.

`tools/make_demo.sh <dossier>` génère des fichiers de démonstration (œuvres libres) pour essayer chaque type de contenu ; il demande `ffmpeg`.

## Architecture

```
Forge411.pyw              point d'entrée
forge411/
├── model.py              Source, Match, Ident, Part, Detail, Check ; formatage
├── files.py              lecture de la source, renommage, déplacement, dossier de seed
├── torrent.py            création des .torrent (source C411, table des tailles de pièce)
├── api.py                client de l'API C411 (catégories, options, doublons, brouillons, upload)
├── render.py             briques du NFO et de la présentation BBCode
├── videoinfo.py          analyse MediaInfo et tags vidéo
├── audioinfo.py          analyse des tags audio (mutagen)
├── scanner.py            analyseur de noms de release vidéo (aussi en ligne de commande)
├── lookup/               bases en ligne : tmdb, musicbrainz, books (Open Library / Google Books), rawg
├── profiles/             un profil par catégorie C411
│   ├── base.py           interface Profile + règles communes
│   ├── video.py  music.py  ebook.py  software.py (jeux, applications)  misc.py (émulation, GPS, 3D)  xxx.py (adulte)
│   └── __init__.py       registre et détection
├── session.py            état de l'upload en cours
├── config.py             réglages, liens des clés, historique
├── updater.py            mises à jour : release GitHub, téléchargement vérifié, remplacement de l'exe
├── profile.py            profil C411 (GET /api/user/profile) : lecture, mise en forme, relevés et évolution
├── clients.py            clients torrent (qBittorrent, Transmission, Deluge) : ajout et suivi jusqu'au seed
├── catalog.py            doublons et estimation des slots C411 à partir du nom
├── screens.py            captures ffmpeg et envoi sur pixhost / catbox
├── ffmpeg_setup.py       installation de ffmpeg (build officiel vérifié) à la demande
├── batch.py              mode lot : préparation et envoi en brouillons sans interface
└── ui/                   interface Tkinter : thème, composants, étapes, fenêtres, visite guidée
```

L'assistant (`ui/steps.py`) est générique : chaque étape interroge le profil de la session.

| Méthode du profil | Rôle |
|---|---|
| `score(src)` | probabilité que la source soit de ce type (détection) |
| `analyze(src)` | lecture des fichiers |
| `summary`, `issues`, `guess_sub` | étape Source |
| `query`, `search` (+ attribut `provider`) | étape Identification |
| `parts`, `build`, `validate`, `details`, `rename_target` | étape Nom |
| `nfo`, `description` | NFO et présentation |
| `auto_options` | options C411 préremplies |

### Ajouter un type de contenu

1. Crée une classe dérivée de `Profile` dans `forge411/profiles/`.
2. Ajoute-la à `PROFILES` dans `forge411/profiles/__init__.py`.
3. Ajoute un cas de détection et un test de nom dans `tests/test_core.py`.

Les options C411 se lisent par libellé (`pick`, `pick_fuzzy`) : les identifiants viennent de l'API au moment de l'envoi.

## Règles d'interface

- Couleurs et polices : `forge411/ui/theme.py` uniquement. Deux palettes (`PALETTES`, relevées sur c411.org) : toute nouvelle couleur s'ajoute aux deux. Le mode est lu au chargement du module ; en changer demande un redémarrage.
- Aucun appel réseau ni accès disque long dans le thread Tk : `run_bg()` (`ui/widgets.py`).
- Les modules hors de `forge411/ui/` n'importent jamais Tkinter.
- Chaque champ a une aide au survol (`help=`) ; chaque clé un lien (`config.KEY_LINKS`).

## Compiler l'exécutable Windows

```bat
build.bat
```

Le script crée l'environnement, lance les tests puis PyInstaller (`forge411.spec`) : le résultat est `dist\Forge411.exe`. Vérification rapide des bibliothèques embarquées :

```bat
dist\Forge411.exe --selftest rapport.txt
```

## Publier une version

1. Mets à jour `__version__` (`forge411/__init__.py`), `version_info.txt` et `CHANGELOG.md`.
2. Pousse un tag : `git tag v2.0.0 && git push --tags`.

Le workflow GitHub `Release` lance les tests, compile `Forge411.exe` et l'attache à la release.
