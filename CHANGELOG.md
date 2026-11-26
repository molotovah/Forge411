# Changelog

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ; versions : [SemVer](https://semver.org/lang/fr/).

## [2.5.1] - 2026-11-26

### Ajouté
- Nettoyage des uploads abandonnés : captures et NFO d'une release absente de l'historique (et de l'upload en cours ou à reprendre) supprimés après 7 jours.
- Brouillons publiés depuis le site : suivis pendant 30 jours ; une fois validés par C411, ils passent « Validé » dans l'historique, comptent pour le statut d'uploader certifié, et leurs captures et NFO sont nettoyés.

### Corrigé
- Pastilles des types de contenu : icônes alignées sur le texte (dessinées à part, en police emoji).
- Mon profil : les grandes valeurs des tuiles (« moins d'un jour »…) étaient rognées ; leur police se réduit maintenant pour tenir dans la tuile, et l'estimation du niveau suivant s'écrit « < 1 jour ».

## [2.5.0] - 2026-11-26

### Ajouté
- Changement de thème sans redémarrer : l'interface se reconstruit aussitôt, avec l'étape et l'upload en cours.
- Courbe de vitesse refaite façon tableau de bord : courbe lissée et anticrénelée, dégradé dessous, graduations rondes en Mo/s, temps écoulé, vitesse moyenne en pointillé et point sur la dernière mesure.
- Fin d'une copie ou d'un hachage : bilan dans les tuiles (vitesse moyenne, durée, vitesse maximale) au lieu de la dernière vitesse mesurée. Le bilan du déplacement vers le dossier de seed reste affiché.

### Modifié
- Mode clair refait : fonds gris-bleu très clairs et cartes blanches (inspiré de GitHub Primer), vert de C411 assombri ; tous les textes atteignent le contraste WCAG AA (4,5:1), vérifié par les tests pour les deux thèmes.
- Tuiles de statistiques dans le même ordre partout (hachage, copie, vérification) : avancement, vitesse, temps écoulé, temps restant.

### Corrigé
- Mon profil : la fenêtre s'ouvre à la taille de son contenu, sans défilement, dans la limite de l'écran (barre des tâches exclue).
- Visite guidée : la bulle était placée d'après une taille provisoire et pouvait sortir de la fenêtre.
- Pochettes d'album (MusicBrainz) affichées carrées au lieu d'être recadrées en affiche ; images de jeux (RAWG) en paysage dans la liste des résultats aussi.
- Courbe de vitesse masquée quand le hachage ou la copie est trop rapide pour être mesuré (cadre vide).
- Résultats de recherche TMDB : type affiché en français (Film, Série) au lieu de movie, tv.

### Documentation
- Toutes les captures du README et du wiki sont régénérées automatiquement à chaque version, avec des données de démonstration : étapes de l'assistant (film, album, livre, jeu), visite guidée, aide au survol, doublons et slots, mode lot, correction et mode clair.

## [2.4.0] - 2026-11-26

### Ajouté
- Courbe de vitesse sous les tuiles pendant le hachage du torrent et le déplacement vers le dossier de seed, avec la vitesse moyenne en pointillé et le maximum atteint. Coût mesuré : moins d'une milliseconde par mise à jour.
- Boutons vers les dossiers : « Ouvrir l'emplacement » de la source (étape Source), « Afficher le .torrent », « Afficher le NFO » et « Dossier des captures » (étape Publication), « Ouvrir » à côté des dossiers des Paramètres.
- Captures d'écran manquantes : encart bien visible au-dessus de la description, avec le nombre de captures présentes et exigées et un grand bouton « Ajouter des captures ». À l'étape Publication, un bouton ramène à l'étape Présentation quand elles manquent encore.

### Modifié
- Déplacement de la source vers le dossier de seed : mêmes tuiles que le hachage du torrent (vitesse, temps écoulé, temps restant, fichier en cours), progression sur le total réel du dossier, résumé à la fin (taille, durée, vitesse moyenne).

## [2.3.0] - 2026-11-26

### Ajouté
- Interface au style de C411 : boutons, encadrés, pastilles, bandeaux, notifications et bulle de la visite guidée aux coins arrondis (anticrénelés).
- Mise à jour disponible : bandeau bleu en haut de la fenêtre avec la principale nouveauté (Voir et installer, Plus tard, Ignorer cette version), notification en bas à droite et clignotement du bouton dans la barre des tâches quand Forge411 n'est pas au premier plan.
- README : guide pas à pas du client torrent pour trois cas (client sur ce PC, NAS ou Docker, seedbox dans le cloud) et tableau des messages d'erreur avec leur solution.

### Modifié
- Torrent ajouté au client : disposition d'origine des fichiers imposée (qBittorrent), démarrage forcé hors file d'attente et aucune limite de ratio ni de durée de seed, quels que soient les réglages du client.
- Création du torrent plus rapide : lecture du disque et calcul des empreintes en parallèle, sans copie des données.
- Étape Publication : les vérifications ne sont plus recalculées à chaque touche frappée dans la justification, et la liste n'est reconstruite que si elle change.
- Molette : un seul gestionnaire pour toute l'application. Chaque fenêtre ouverte en ajoutait un, jamais retiré, qui ralentissait le défilement au fil de la session.

### Corrigé
- Un torrent en file d'attente, en pause ou arrêté n'est plus compté « En seed » : il n'annonce rien au tracker. Forge411 le démarre, et l'indique s'il reste inactif.
- qBittorrent : avec le réglage « Créer un sous-dossier » ou « Ne pas créer de sous-dossier », la vérification cherchait les fichiers au mauvais endroit.
- Deluge : un torrent mis en file d'attente faisait attendre Forge411 jusqu'à 6 h.
- Torrent déjà présent dans le client mais incomplet (ajouté avant la fin d'un transfert vers une seedbox) : la vérification est relancée. Deluge et Transmission signalent aussi le doublon.
- La notification « Validé sur C411 » ne s'affichait pas quand elle indiquait que la place était libre pour un nouvel upload.

## [2.2.0] - 2026-11-26

### Ajouté
- Publication : pendant le hachage du torrent et la vérification des données par le client torrent, des tuiles affichent la vitesse (sur les dernières secondes), le temps écoulé, le temps restant et l'avancement (pièces hachées, part vérifiée). À la fin : durée totale et vitesse moyenne.
- Règle C411 des uploaders non certifiés (moins de 15 torrents validés) : un seul upload à la fois en attente de la Team Pending, modification demandée comprise. L'étape Publication signale l'upload déjà en attente et conseille le brouillon ; « Publier » demande alors confirmation. La notification de validation indique quand la place est libre. Statut déduit de l'historique, ou déclaré dans Paramètres › Uploads › Statut d'uploader.
- Historique : clic droit « Marquer comme refusé ou supprimé » sur un upload en attente (l'API ne distingue pas un torrent refusé d'un torrent en attente).

### Modifié
- Le NFO d'une release est supprimé du dossier de sortie quand C411 a validé le torrent, comme ses captures. Les NFO des sources ne sont jamais touchés.

## [2.1.8] - 2026-11-26

### Modifié
- Captures : le dossier local d'une release est supprimé quand C411 a validé le torrent, et non plus dès l'envoi. Tant qu'il est en attente, elles restent disponibles si la Team Pending demande une modification.

### Corrigé
- Menu latéral : la ligne cliquée (Historique, Mon profil…) restait surlignée après la fermeture de sa fenêtre.
- Bandeau de mise à jour : flèche affichée en carré (symbole absent de la police) remplacée.

## [2.1.7] - 2026-11-26

### Ajouté
- Suivi de la validation par la Team Pending : colonne « C411 » dans l'historique (Validé, En attente, À vérifier au-delà de 3 jours, Refusé quand C411 l'indique), filtre « En attente C411 » et heure de validation notée. Vérification au démarrage, à l'ouverture de l'historique puis toutes les 30 minutes, avec une notification dès qu'un upload est validé.

## [2.1.6] - 2026-11-26

### Ajouté
- Historique refait en tableau : tri par colonne, recherche, filtres (publiés, brouillons, corrections, torrent introuvable), sélection multiple, menu clic droit. « Retirer » enlève des lignes de l'historique et « Retirer les introuvables » enlève d'un coup les uploads dont le .torrent n'existe plus (rien n'est supprimé sur C411 ni sur le disque).
- Captures : le dossier local des captures d'une release est supprimé dès sa publication (images hébergées, liens dans la présentation). Au démarrage, Forge411 nettoie aussi celles des releases déjà publiées. Les captures d'un brouillon sont gardées.
- Garde-fous contre les régressions : test de bout en bout de chaque type de contenu, règles d'affichage vérifiées sur le code, hooks git (tests et ruff avant chaque commit), ruff dans la CI, outil de captures du README avec des données de démonstration.

### Corrigé
- Client torrent distant : un partage désigné par le nom de la machine (\\NAS\Torrents) et par son IP (\\192.168.1.251\Torrents) est reconnu comme le même dossier. Le chemin transmis au client et la vérification du dossier de seed ne se trompent plus.
- Reprise après fermeture : l'upload en cours était effacé au démarrage au lieu d'être proposé à la reprise.
- Mon profil : « Actualiser » montre l'actualisation en cours, l'heure de la lecture et l'absence de variation ; dans les 30 s, l'attente restante est indiquée. Icône illisible remplacée.
- Brouillons : bouton « Actualiser » lisible ; les noms longs passent à la ligne au lieu d'être coupés.
- Audio : la liste des pistes MusicBrainz n'est plus traduite (« One More Time » restait « Encore une fois »).
- Ebook : un ISBN erroné dans les métadonnées ne fait plus proposer un autre livre ; le titre et l'auteur passent devant.
- Genres : « Fiction » ne donne plus « Science-Fiction » ; genres RAWG traduits pour les jeux (Platformer → Plates-formes…).
- Jeux GOG : « Jeu.v1.0-GOG » et les installateurs setup_jeu_version.exe sont reconnus comme jeux, modèle GOG.
- Applications : « 7-Zip.24.08.x64 » donnait le titre « 7 » ; le titre saisi à l'étape Identification est repris dans le nom.
- XXX : pour « [Studio] AAAA-MM-JJ Titre », la date n'est plus recopiée dans le titre et ni le jour (« 15 ») ni le dernier mot ne sont pris pour une team.
- Déjà sur C411 : la même version publiée par une autre team est signalée comme doublon probable ; les résultats sans rapport (recherche texte) sont écartés.
- GPS : « NT.2025.10 » garde sa version complète. Impression 3D : « STL » et « Pack » ne sont plus répétés dans le nom.
- Audio : « Tags » affiche la parenthèse fermante de l'année.
- Tests : la vérification du débit vidéo ne dépendait pas des données analysées mais de la présence de MediaInfo ; la suite passe désormais aussi sous Linux.
- Publication : la case « Mon client torrent seed ce torrent » passe à la ligne au lieu d'être coupée.
- Interface : icône Émulation décalée, barres de défilement horizontales claires, survol resté actif dans le menu latéral après la fermeture d'une fenêtre, cases à cocher des Paramètres coupées, en-têtes du mode lot centrés.

## [2.1.5] - 2026-11-25

### Corrigé
- Captures : après « Déplacer dans le dossier de seed » (ou le renommage d'un dossier), ffmpeg lit la vidéo à son nouvel emplacement au lieu de l'ancien (« No such file or directory »).
- Paramètres : options rognées sous Windows avec un affichage à 125 % ou 150 % ; les dimensions suivent désormais l'échelle de l'écran.

## [2.1.4] - 2026-11-25

### Corrigé
- Traduction des résumés : les noms des interprètes et du studio ne sont plus traduits (Amber, Hannah Blue, Roxanne White…).

## [2.1.3] - 2026-11-25

### Ajouté
- Résumés des fiches (TMDB, ThePornDB, RAWG, livres…) traduits en français quand ils sont dans une autre langue : Google Traduction, gratuit et sans compte, avec une adresse de secours si la première est limitée. Désactivable dans Paramètres › Bases en ligne.
- XXX : catégorie non hétéro déduite de la fiche ThePornDB (tags Lesbian, Gay, Trans…, sinon genre des interprètes).

### Corrigé
- Corriger une validation : la correction avance seule. La fiche est choisie automatiquement, le nom est recalculé avec les règles actuelles, puis le NFO et la présentation sont régénérés. L'assistant s'arrête seulement à l'étape qui demande une action (par exemple les captures), puis vérifie le seed dans le client à la Publication.
- Corriger une validation : les éléments absents du nom du fichier seedé (catégorie, langue…) sont repris du titre publié.
- Captures XXX : fenêtre des liens postimg refaite. Trois étapes numérotées ont chacune leur bouton (ouvrir le dossier, ouvrir postimages.org), avec un exemple de lien dans la zone de collage et un compteur « 2 / 3 ». Les liens qui ne sont pas des liens directs sont signalés.

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
