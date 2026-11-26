# Mises à jour

Au démarrage puis toutes les 6 heures, Forge411 cherche une nouvelle version sur GitHub (désactivable dans **Paramètres › Général**).

Quand une version existe :

- un **bandeau bleu** s'affiche en haut de la fenêtre avec la principale nouveauté : **Voir et installer**, **Plus tard** (jusqu'au prochain lancement) ou **Ignorer cette version** ;
- une **notification** apparaît en bas à droite ;
- le bouton de Forge411 **clignote dans la barre des tâches** si la fenêtre n'est pas au premier plan ;
- une pastille reste sur l'icône ⟳, en bas du menu.

**Voir et installer** affiche les nouveautés de chaque version depuis la tienne, avant tout téléchargement. L'exécutable Windows télécharge ensuite la nouvelle version et vérifie son empreinte SHA-256. Il attend la fin de l'analyse de l'antivirus Windows, puis la nouvelle version remplace l'ancienne et redémarre.

Depuis le code source : `git pull`.

Toutes les nouveautés : [CHANGELOG](https://github.com/molotovah/Forge411/blob/main/CHANGELOG.md).
