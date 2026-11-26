# Installation

## Windows (recommandé)

1. Télécharge **`Forge411.exe`** depuis la [dernière version](https://github.com/molotovah/Forge411/releases/latest).
2. Double-clique dessus. Rien d'autre à installer : MediaInfo et les dépendances sont incluses.

> [!NOTE]
> Au premier lancement, Windows peut afficher « Windows a protégé votre ordinateur » : l'exécutable n'est pas signé.
> Clique sur **Informations complémentaires**, puis **Exécuter quand même**.

Forge411 se met ensuite à jour tout seul : voir [Mises à jour](<Mises-à-jour>).

## Depuis le code source (Windows, Linux, macOS)

Il faut [Python 3.10 ou plus récent](https://www.python.org/downloads/).

- **Windows** : télécharge le code, puis double-clique sur `install.bat`. Il prépare tout et crée un raccourci sur le Bureau.
- **Linux / macOS** :

  ```bash
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
  .venv/bin/python Forge411.pyw
  ```

  Sous Linux, installe aussi `libmediainfo` et `python3-tk` avec le gestionnaire de paquets de ta distribution.

Étape suivante : [Premier lancement](Premier-lancement).
