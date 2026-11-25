# Changelog

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ; versions : [SemVer](https://semver.org/lang/fr/).

## [2.1.2] - 2026-11-25

### Corrigé
- Mise à jour : l'ancienne fenêtre ne se fermait pas après « Installer et redémarrer ». Forge411.exe restait verrouillé : la nouvelle version démarrait depuis le fichier temporaire, sans remplacer l'exécutable. Elle se ferme désormais. Si une ancienne version (2.1.1 ou avant) reste bloquée, elle est arrêtée au bout de 15 secondes, l'upload en cours étant déjà sauvegardé.
- Mise à jour : la progression est visible du début à la fin. La fenêtre suit trois étapes : téléchargement (pourcentage, débit, temps restant), vérification par l'antivirus Windows, installation. Une fenêtre « Mise à jour de Forge411 » reste ensuite affichée jusqu'à l'ouverture de la nouvelle version, qui passe au premier plan.
- Si le remplacement échoue malgré tout, la fenêtre d'installation l'explique et propose « Réessayer ».

## [2.1.1] - 2026-11-25

### Ajouté
- Mises à jour : les nouveautés de toutes les versions depuis la tienne (tirées du CHANGELOG) s'affichent avant le téléchargement.
- Une nouvelle version disponible est signalée par une pastille sur l'icône ⟳ et un badge cliquable en haut à droite. Vérification au démarrage puis toutes les 6 heures, sans fenêtre qui s'ouvre d'elle-même.

### Modifié
- Thème sombre par défaut. Le thème choisi dans les Paramètres est conservé d'un lancement à l'autre.
- Notes des releases GitHub reprises du CHANGELOG.

### Corrigé
- Captures XXX : la fenêtre des liens affiche le minimum exigé (3, ou 4 pour un pack) au lieu du nombre de captures extraites.

## [2.1.0] - 2026-11-25

### Ajouté
- **Corriger une validation** : après « Modification demandée », colle le message de la Team Pending. Forge411 rouvre l'upload (même .torrent, seed inchangé) et affiche chaque point sur l'étape concernée. Il prépare ensuite le titre, la description et le NFO à coller dans « Modifier », avant « Soumettre pour re-examen ». Un bouton **Corriger** est aussi présent dans l'Historique.
- Contrôle des images de la présentation : hébergeurs de la liste blanche C411 et nombre minimal de captures hors bannière (XXX : 3, 4 pour un pack, sur postimg.cc ou zupimages.net ; jeux : 3 ; applications : 2). L'étape Présentation reste bloquée tant que le compte n'y est pas.
- Captures XXX : extraction avec ffmpeg, puis dépôt sur postimg.cc et collage des liens directs (dialogue guidé).
- Captures à partir d'images du disque pour les contenus sans vidéo (jeux, applications…).
- Client torrent : bouton **Détecter**, aide d'activation de l'interface web, champs adaptés au client, option « client sur un autre appareil », bouton **Proposer** pour la correspondance des dossiers et aperçu du chemin transmis au client.

### Modifié
- Paramètres repensés : navigation par sections (Compte C411, Bases en ligne, Uploads, Client torrent, Captures, Général), pastilles d'état, lignes compactes libellé / champ, bouton Afficher pour les clés, tests intégrés, Ctrl+S.
- Nommage XXX Films / VR conforme aux retours de la Team Pending : `[Studio][CATÉGORIE].Titre.Date.Acteur.Langue.Résolution.Source.Audio.Codec-TEAM`. La source suit la résolution, la date suit le titre, et la catégorie non hétéro passe en tête, entre crochets. Ces règles sont aussi vérifiées sur un nom saisi à la main.
- Image ThePornDB prise sur cdn.theporndb.net : thumb.theporndb.net n'est pas affiché par C411.
- Publication impossible sans seed : seed vérifié dans le client configuré, sinon case à cocher obligatoire.
- Déplacement vers le dossier de seed : copie native Windows (CopyFileEx), nettement plus rapide vers un partage réseau, avec débit et temps restant.

### Corrigé
- Mise à jour intégrée : plus de script batch. La nouvelle version attend la fermeture de l'ancienne, se copie à sa place et redémarre. L'analyse de Microsoft Defender sur le fichier téléchargé est attendue, et rien ne se lance plus depuis le fil de l'interface (fenêtre figée, Forge411.exe disparu).

## [2.0.3] - 2026-11-25

### Corrigé
- qBittorrent : ajout refusé en HTTP 415 quand la session avait expiré (le .torrent était renvoyé vide après reconnexion).
- qBittorrent 5 : un torrent déjà présent (HTTP 409) n'est plus affiché comme une erreur.

## [2.0.2] - 2026-11-25

### Corrigé
- qBittorrent 5 : la connexion était refusée à tort (réponse 204 sans « Ok. »).

## [2.0.1] - 2026-11-25

### Ajouté
- Client torrent distant (Docker, NAS) : correspondance des dossiers entre Forge411 et le client (ex. `\\192.168.1.251\Torrents` → `/downloads`), pour que le client retrouve les données à seeder.

## [2.0.0] - 2026-11-25

Première version publique.

### Assistant d'upload
- Six étapes guidées : Source, Identification, Nom et informations, NFO, Présentation, Publication ; visite guidée, aide au survol, reprise d'un upload interrompu.
- Toutes les catégories C411 (hors Nulled) : Films & Vidéos, Audio, Ebook, Jeux Vidéo, Applications, Émulation, GPS, Impression 3D et XXX (Films, VR, Hentai, Images, Ebooks, Jeux).
- Détection du type de contenu et de la sous-catégorie ; analyse MediaInfo, tags audio, métadonnées EPUB/PDF/CBZ, type de release des jeux et applications.
- Fiches en ligne : TMDB, MusicBrainz, Open Library / Google Books, RAWG, ThePornDB (`tpdbData` joint à l'upload) ; saisie manuelle possible.
- Noms conformes au wiki d'upload de C411, vérifiés en direct : sources et marqueurs HDLight / 4KLight, débits minimums, règle anti-detag, formats et interdits de chaque catégorie ; tag d'équipe configurable.
- NFO et présentation BBCode générés ; options C411 préremplies depuis l'API ; captures d'écran extraites avec ffmpeg (installable en un clic) et hébergées sur pixhost ou catbox.

### Publication
- Torrent privé avec `source = C411` et taille de pièce du guide d'upload.
- Client torrent (qBittorrent, Transmission, Deluge) : ajout du torrent et suivi jusqu'au seed avant la publication.
- « Déjà sur C411 » : doublons et estimation du slot occupé, justification hors slot (`slotJustification`).
- Brouillon ou publication directe ; mode lot pour un dossier entier ; liste des brouillons C411 (15 au maximum).

### Compte et application
- Mon profil : niveau, classe, voies, ratio, volumes, Zen, équipe, freeleech et évolution depuis le dernier relevé.
- Apparence aux couleurs de C411 : modes Système, Sombre et Clair.
- Mises à jour intégrées depuis les releases GitHub (téléchargement vérifié par SHA-256, redémarrage automatique).
- Fenêtre À propos : auteur, licence GNU GPL version 3, services utilisés.
- Exécutable Windows autonome, script d'installation depuis les sources, compilation automatique des releases.
