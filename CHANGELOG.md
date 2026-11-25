# Changelog

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ; versions : [SemVer](https://semver.org/lang/fr/).

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
