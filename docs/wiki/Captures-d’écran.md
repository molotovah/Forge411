# Captures d'écran

C411 exige des captures d'écran pour certaines catégories, hors bannière :

| Catégorie | Minimum |
|---|---|
| XXX | 3 (4 pour un pack) |
| Jeux | 3 |
| Applications | 2 |

À l'étape **Présentation**, un encart orange au-dessus de la description indique quand il en manque, avec le bouton **Ajouter des captures**. À l'étape **Publication**, un bouton ramène à la Présentation si elles manquent encore.

## Vidéo

**Ajouter des captures** extrait des images avec ffmpeg, les envoie sur pixhost ou catbox (hébergeurs acceptés par C411) et ajoute les vignettes à la description. L'envoi demande toujours ta confirmation.

## Sans vidéo

Choisis des images sur le disque : elles sont hébergées et ajoutées de la même façon.

## Contenu adulte (XXX)

La Team Pending ne compte que **postimg.cc** et **zupimages.net**. Forge411 extrait les captures dans un dossier et ouvre postimages.org : tu y glisses les images, puis tu colles la liste des **liens directs**.

> [!WARNING]
> Les images hébergées ailleurs que sur la liste blanche de C411 sont signalées : elles ne s'afficheraient pas sur le site.

## Où sont les captures

Les captures extraites sont rangées dans le sous-dossier « captures » du dossier de sortie (bouton **Dossier des captures** à l'étape Publication).

Forge411 les supprime dès que C411 a validé le torrent, en même temps que le NFO de la release : les images sont hébergées et leurs liens figurent dans la présentation. Tant que le torrent est en attente, ou pour un brouillon, elles sont gardées : une modification demandée peut en réclamer de nouvelles. Les NFO des sources ne sont jamais touchés.

## ffmpeg

Sans ffmpeg sur le PC, Forge411 propose de l'installer en un clic (**Paramètres › Captures d'écran**, ou au premier clic sur **Ajouter des captures**) : version stable officielle (FFmpeg-Builds, LGPL) téléchargée depuis GitHub, vérifiée par SHA-256, environ 75 Mo. Un ffmpeg déjà présent (PATH, winget) est utilisé en priorité.
