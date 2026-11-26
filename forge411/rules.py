"""
Règles de présentation vérifiées par C411 (et par le robot de la Team Pending).

- Hébergeurs d'images : liste blanche du site (les autres images sont remplacées
  par un simple lien et ne comptent pas).
- Captures d'écran : nombre minimal « hors images bannières » selon la catégorie
  (XXX : 3, 4 pour un pack, sur postimg.cc ou zupimages.net ; jeux : 3 ;
  applications : 2), d'après la checklist d'upload et le guide Description & NFO.
"""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from .model import Check

# Liste blanche C411 (éditeur de présentation du site, novembre 2026)
IMAGE_HOSTING = set(
    "i.ibb.co ibb.co i.imgur.com imgur.com i.postimg.cc postimg.cc files.catbox.moe images2.imgbox.com imgbox.com "
    "i.goopics.net goopics.net zupimages.net www.zupimages.net img0.pixhost.to img1.pixhost.to img2.pixhost.to "
    "img3.pixhost.to t0.pixhost.to t1.pixhost.to t2.pixhost.to t3.pixhost.to cdn-images.imagevenue.com "
    "image.noelshack.com images.unsplash.com prnt.sc image.prntscr.com casimages.com cdn.imgpile.com "
    "upload.wikimedia.org imgbb.com img.onlyimage.org onlyimage.org hamsterimg.net".split())
# Images de fiches (affiches, jaquettes, bannières) : affichées, mais ce ne sont pas des captures
META_HOSTS = set(
    "image.tmdb.org media.themoviedb.org www.themoviedb.org artworks.thetvdb.com cdn.theporndb.net media.rawg.io "
    "cdn.akamai.steamstatic.com shared.akamai.steamstatic.com shared.fastly.steamstatic.com "
    "cdn.cloudflare.steamstatic.com steamcdn-a.akamaihd.net image.api.playstation.com images.gog.com "
    "cdn.dekudeals.com image.jeuxvideo.com images.igdb.com howlongtobeat.com assetsio.gnwcdn.com s.pacn.ws "
    "images.pushsquare.com i.scdn.co mosaic.scdn.co f4.bcbits.com covers.mp3million.com i.discogs.com "
    "coverartarchive.org archive.org e-cdns-images.dzcdn.net cdn-images.dzcdn.net static.qobuz.com "
    "imagescdn.juno.co.uk resources.tidal.com is1-ssl.mzstatic.com is2-ssl.mzstatic.com is3-ssl.mzstatic.com "
    "is4-ssl.mzstatic.com is5-ssl.mzstatic.com lastfm.freetls.fastly.net cdn1.booknode.com books.google.com "
    "books.google.fr media.electre-ng.com media.hachette.fr products-images.di-static.com "
    "images-na.ssl-images-amazon.com images-eu.ssl-images-amazon.com m.media-amazon.com covers.openlibrary.org "
    "static.fnac-static.com cdn.myanimelist.net www.manga-news.com mangadex.org uploads.mangadex.org s4.anilist.co "
    "media.kitsu.io images.allocine.fr acsta.net images.justwatch.com www.imdb.com ia.media-imdb.com "
    "flxt.tmsimg.com media.senscritique.com assets.mubicdn.net flagcdn.com flagpedia.net".split())
ALLOWED_HOSTS = IMAGE_HOSTING | META_HOSTS
# XXX : hébergeurs demandés par la Team Pending pour les captures
XXX_SHOT_HOSTS = {"i.postimg.cc", "postimg.cc", "zupimages.net", "www.zupimages.net"}

IMG_RE = re.compile(r"\[img(?:=[^\]]*)?\]\s*(https?://[^\s\[\]]+?)\s*\[/img\]", re.I)


@dataclass
class ShotRule:
    minimum: int = 0
    hosts: Optional[set] = None          # hébergeurs admis pour les captures (None : liste blanche)
    hosts_label: str = ""
    recommended: int = 0                 # conseillé sans être exigé


def host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def allowed(url: str) -> bool:
    return host(url) in ALLOWED_HOSTS


def images(bbcode: str) -> list:
    return IMG_RE.findall(bbcode or "")


def screenshots(bbcode: str, banner: str = "", hosts: Optional[set] = None) -> list:
    """Captures de la description : images d'hébergeurs (pas des fiches), sans la bannière."""
    out = []
    for url in images(bbcode):
        h = host(url)
        if url == banner or h in META_HOSTS or h not in IMAGE_HOSTING:
            continue
        if hosts is not None and h not in hosts:
            continue
        if url not in out:
            out.append(url)
    return out


def shots_missing(bbcode: str, rule: ShotRule, banner: str = "") -> tuple:
    """(captures présentes, captures attendues, exigées par C411) quand il en manque, sinon None : exigées sous le
    minimum de la catégorie, ou conseillées et absentes. Sert à l'encart « Ajouter des captures »."""
    if rule.minimum:
        n = len(screenshots(bbcode, banner, rule.hosts))
        return (n, rule.minimum, True) if n < rule.minimum else None
    if rule.recommended and not screenshots(bbcode, banner):
        return (0, rule.recommended, False)
    return None


def check_description(bbcode: str, rule: ShotRule, banner: str = "") -> Check:
    """Images non affichées et nombre de captures exigé par la catégorie."""
    c = Check()
    bad = sorted({host(u) or u for u in images(bbcode) if not allowed(u)})
    if bad:
        c.errors.append("Images refusées par C411 (remplacées par un lien) : " + ", ".join(bad) +
                        ". Héberge-les sur un hébergeur autorisé (lien direct).")
    if rule.minimum:
        n = len(screenshots(bbcode, banner, rule.hosts))
        if n < rule.minimum:
            where = f" sur {rule.hosts_label}" if rule.hosts_label else ""
            c.errors.append(f"Captures d'écran : {n} sur {rule.minimum} minimum (hors bannière){where}. "
                            "Utilise « Ajouter des captures ».")
        if rule.hosts is not None:
            other = [u for u in screenshots(bbcode, banner) if host(u) not in rule.hosts]
            if other:
                c.warnings.append(f"{len(other)} capture(s) hors de {rule.hosts_label} : la Team Pending ne les "
                                  "compte pas.")
    elif rule.recommended and not screenshots(bbcode, banner):
        c.infos.append(f"Captures d'écran recommandées ({rule.recommended} ou plus).")
    return c
