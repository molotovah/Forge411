# Questions fréquentes

<details>
<summary><b>La recherche ne trouve rien.</b></summary>

Essaie le titre original, retire l'année, ou passe en saisie manuelle. MusicBrainz limite le nombre de requêtes : patiente quelques secondes si la recherche échoue.
</details>

<details>
<summary><b>Un champ obligatoire est en rouge à l'étape Présentation.</b></summary>

C411 attend une valeur que Forge411 n'a pas pu deviner : choisis-la dans la liste.
</details>

<details>
<summary><b>Le renommage échoue.</b></summary>

Ferme le programme qui utilise le fichier (lecteur vidéo, client torrent), puis clique à nouveau sur **Continuer**.
</details>

<details>
<summary><b>C411 refuse le torrent publié.</b></summary>

Ton client doit seeder le torrent avant la publication. Configure ton client pour que Forge411 le vérifie : voir [Client torrent et seed](Client-torrent-et-seed). En cas de doute, commence par un brouillon.
</details>

<details>
<summary><b>Le client torrent n'arrive pas à vérifier les données.</b></summary>

Le client cherche les fichiers ailleurs : voir le tableau [Si ça ne marche pas](Client-torrent-et-seed#si-ça-ne-marche-pas).
</details>

<details>
<summary><b>« Un upload attend déjà la Team Pending ».</b></summary>

Tant que tu n'es pas uploader certifié, C411 n'accepte qu'un upload à la fois en attente. Enregistre le nouveau en brouillon, et publie-le une fois l'autre validé : voir [Brouillons et historique](Brouillons-et-historique#un-seul-upload-en-attente-tant-que-tu-nes-pas-certifié).
</details>

<details>
<summary><b>Forge411 s'est fermé pendant un upload.</b></summary>

L'upload en cours est sauvegardé à chaque étape : au lancement suivant, Forge411 propose de le reprendre.
</details>

<details>
<summary><b>Où sont mes réglages et le journal ?</b></summary>

Dans `%APPDATA%\Forge411` sous Windows (`~/.config/Forge411` sous Linux) : `config.json`, `history.jsonl` et `forge411.log`.

> [!TIP]
> Joins `forge411.log` si tu [signales un problème](https://github.com/molotovah/Forge411/issues).
</details>
