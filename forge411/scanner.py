"""
forge411/scanner.py
-----------------
Scan un dossier de fichiers vidéo et valide leur nommage
selon les règles C411 (catégorie Films & Vidéos).

Usage:
    python -m forge411.scanner /chemin/vers/dossier
    python -m forge411.scanner /chemin/vers/dossier -v
    python -m forge411.scanner /chemin/vers/dossier --export rapport.json
"""

import re
import sys
import json
import unicodedata
import argparse
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constantes de référence C411
# ---------------------------------------------------------------------------

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".mov", ".wmv",
                    ".iso", ".img", ".bdmv"}

VALID_RESOLUTIONS = {"480p", "576p", "720p", "1080p", "2160p", "4k", "7k",
                     "8k", "hd", "sd"}

VALID_SOURCES = {
    "bluray", "blu-ray", "bluray", "bdrip", "bdremux", "uhd",
    "web", "web-dl", "webdl", "webrip",
    "dvd", "dvdrip", "dvdscr",
    "hdtv", "pdtv", "tvrip",
    "hdlight", "4klight", "hdcam",
    "remux", "bdmv",
}

VALID_VIDEO_CODECS = {
    "x264", "x265", "h264", "h265", "hevc", "avc",
    "xvid", "divx", "mpeg2", "vp9", "av1",
}

VALID_AUDIO_CODECS = {
    "aac", "ac3", "eac3", "dts", "flac", "mp3",
    "truehd", "atmos", "dtshd", "dtshdma",
    "pcm", "opus",
}

VALID_LANGUAGES = {
    "vff", "vf", "vf2", "vfi", "vfq", "vof",
    "multi", "truefrench", "french",
    "vostfr", "vosta", "vost",
    "vo", "en", "multi",
    "fansub",
}

VALID_HDR_FLAGS = {
    "hdr10", "hdr10plus", "hdr10+", "dv", "dolbyvision",
    "hlg", "sdr",
}

VALID_SPECIAL_FLAGS = {
    "proper", "repack", "custom", "extended", "theatrical",
    "directors.cut", "unrated", "uncensored", "imax",
    "3d", "hsbs", "sbs",
    "collection", "integrale",
}

# Sous-types Films & Vidéos détectés par pattern
SUBTYPE_PATTERNS = {
    "serie_episode": re.compile(r'\.S\d{2}E\d{2}\.', re.IGNORECASE),
    "serie_saison":  re.compile(r'\.S\d{2}\.', re.IGNORECASE),
    "serie_multi":   re.compile(r'\.S\d{2}S\d{2}\.', re.IGNORECASE),
    "integrale":     re.compile(r'\.INTEGRALE\.', re.IGNORECASE),
    "collection":    re.compile(r'\.COLLECTION\.', re.IGNORECASE),
    "documentaire":  re.compile(r'\.DOC\.', re.IGNORECASE),
}

# ---------------------------------------------------------------------------
# Structures de données
# ---------------------------------------------------------------------------

@dataclass
class ParsedRelease:
    """Composants extraits du nom d'une release."""
    raw_name: str
    title: str = ""
    year: Optional[str] = None
    subtype: str = "film"          # film | serie_episode | serie_saison | ...
    season: Optional[str] = None
    episode: Optional[str] = None
    languages: list = field(default_factory=list)
    resolution: Optional[str] = None
    source: Optional[str] = None
    hdr_flags: list = field(default_factory=list)
    audio_codec: Optional[str] = None
    audio_channels: Optional[str] = None
    video_codec: Optional[str] = None
    team: Optional[str] = None
    special_flags: list = field(default_factory=list)


@dataclass
class ValidationResult:
    """Résultat de validation d'un fichier."""
    filepath: str
    filename: str
    is_valid: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    parsed: Optional[ParsedRelease] = None
    suggested_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Parseur de nom de release
# ---------------------------------------------------------------------------

def strip_accents(text: str) -> str:
    """Supprime les accents d'une chaîne."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )

def detect_subtype(name: str) -> str:
    for subtype, pattern in SUBTYPE_PATTERNS.items():
        if pattern.search(name):
            return subtype
    return "film"

def parse_release_name(name: str) -> ParsedRelease:
    """
    Tente d'extraire les composants d'un nom de release C411.
    Travaille sur le stem (nom sans extension).
    """
    parsed = ParsedRelease(raw_name=name)
    parsed.subtype = detect_subtype(name)

    # Normaliser les sources composées avec tiret avant le split par point
    # WEB-DL → WEBDL (temporaire pour le parse), on les remet après
    _normalized = name
    _hyphen_sources = {"WEB-DL": "WEBDL", "UHD-BluRay": "UHDBluRay", "Blu-Ray": "BluRay"}
    for orig, repl in _hyphen_sources.items():
        _normalized = re.sub(re.escape(orig), repl, _normalized, flags=re.IGNORECASE)

    parts = _normalized.split('.')

    # --- Tag TEAM (dernier segment après le dernier tiret) ---
    last_part = parts[-1] if parts else ""
    if '-' in last_part:
        idx = last_part.rfind('-')
        parsed.team = last_part[idx+1:]
        parts[-1] = last_part[:idx]
    elif name.count('-') > 0:
        # team peut être à la fin du nom complet
        last_dash = name.rfind('-')
        candidate = name[last_dash+1:].split('.')[0]
        if candidate and not any(c.isspace() for c in candidate):
            parsed.team = candidate

    parts_lower = [p.lower() for p in parts]  # parts est déjà nettoyé du tiret-team via rfind

    # --- Année (4 chiffres entre 1900-2099) ---
    year_re = re.compile(r'^(19|20)\d{2}$')
    year_indices = [i for i, p in enumerate(parts) if year_re.match(p)]
    if year_indices:
        parsed.year = parts[year_indices[0]]

    # --- Saison / Episode ---
    se_re = re.compile(r'^(S\d{2})(E\d{2})?$', re.IGNORECASE)
    for i, p in enumerate(parts):
        m = se_re.match(p)
        if m:
            parsed.season = m.group(1).upper()
            if m.group(2):
                parsed.episode = m.group(2).upper()
            break

    # --- Résolution ---
    res_re = re.compile(r'^(\d{3,4}p|4k|7k|8k)$', re.IGNORECASE)
    for p in parts:
        if res_re.match(p):
            parsed.resolution = p.lower()
            break

    # --- Langues ---
    for p in parts_lower:
        if p in VALID_LANGUAGES:
            parsed.languages.append(p.upper())

    # --- Source ---
    for p in parts_lower:
        if p in VALID_SOURCES:
            parsed.source = p
            break

    # --- HDR flags ---
    for p in parts_lower:
        if p in VALID_HDR_FLAGS:
            parsed.hdr_flags.append(p.upper())

    # --- Codec audio ---
    audio_channel_re = re.compile(r'^\d+\.\d+$')
    for i, p in enumerate(parts_lower):
        if p in VALID_AUDIO_CODECS:
            parsed.audio_codec = p.upper()
            # cherche les canaux juste après
            if i+1 < len(parts) and audio_channel_re.match(parts[i+1]):
                parsed.audio_channels = parts[i+1]
            break

    # --- Codec vidéo ---
    for p in parts_lower:
        if p in VALID_VIDEO_CODECS:
            parsed.video_codec = p.upper()
            break

    # --- Flags spéciaux ---
    for p in parts_lower:
        if p in VALID_SPECIAL_FLAGS:
            parsed.special_flags.append(p.upper())

    # --- Titre : tout ce qui précède l'année ou le premier tag technique ---
    technical_tokens = (
        VALID_LANGUAGES | VALID_RESOLUTIONS | VALID_SOURCES |
        VALID_VIDEO_CODECS | VALID_AUDIO_CODECS | VALID_HDR_FLAGS
    )
    title_parts = []
    for p in parts:
        pl = p.lower()
        if year_re.match(p):
            break
        if pl in technical_tokens:
            break
        if se_re.match(p):
            break
        title_parts.append(p)
    parsed.title = '.'.join(title_parts)

    return parsed


# ---------------------------------------------------------------------------
# Validateur
# ---------------------------------------------------------------------------

def validate_filename(filepath: str) -> ValidationResult:
    path = Path(filepath)
    stem = path.stem
    ext = path.suffix.lower()

    result = ValidationResult(
        filepath=str(filepath),
        filename=path.name,
        is_valid=True,
    )

    # ── 1. Extension reconnue ──────────────────────────────────────────────
    if ext not in VIDEO_EXTENSIONS:
        result.warnings.append(
            f"Extension '{ext}' inhabituelle pour une vidéo."
        )

    # ── 2. Pas d'espaces ──────────────────────────────────────────────────
    if ' ' in stem:
        result.errors.append(
            "ESPACES détectés : le séparateur doit être le POINT, pas l'espace."
        )
        result.is_valid = False

    # ── 3. Pas d'accents / caractères non-ASCII ───────────────────────────
    try:
        stem.encode('ascii')
    except UnicodeEncodeError:
        accented = [c for c in stem if ord(c) > 127]
        result.errors.append(
            f"Caractères non-ASCII détectés : {set(accented)}. "
            f"Suggestion : '{strip_accents(stem)}'"
        )
        result.is_valid = False

    # ── 4. Tirets dans le titre (hors tag team) ───────────────────────────
    # Le tiret est autorisé uniquement avant le tag TEAM (fin de nom)
    stem_without_team = stem
    if '-' in stem:
        last_dash = stem.rfind('-')
        stem_without_team = stem[:last_dash]
        if '-' in stem_without_team:
            result.warnings.append(
                "Tirets détectés dans le corps du nom (hors tag TEAM). "
                "Vérifiez que seul le tag final utilise '-'."
            )

    # ── 5. Parse et validation sémantique ─────────────────────────────────
    parsed = parse_release_name(stem)
    result.parsed = parsed

    # Titre présent
    if not parsed.title:
        result.errors.append("Titre introuvable dans le nom de la release.")
        result.is_valid = False

    # Année (obligatoire pour films)
    if parsed.subtype == "film" and not parsed.year:
        result.warnings.append(
            "Année non détectée. Elle est requise pour les films "
            "(format : Nom.AAAA.Langue...)"
        )

    # Langue
    if not parsed.languages:
        result.errors.append(
            "Langue non détectée (ex: VFF, MULTI, TRUEFRENCH, VOSTFR)."
        )
        result.is_valid = False

    # Résolution
    if not parsed.resolution:
        result.warnings.append(
            "Résolution non détectée (ex: 1080p, 2160p). "
            "Obligatoire si qualité ≥ 720p."
        )

    # Source
    if not parsed.source:
        result.warnings.append(
            "Source non détectée (ex: BluRay, WEB, WEBRip, DVDRip)."
        )

    # Codec vidéo
    if not parsed.video_codec:
        result.errors.append(
            "Codec vidéo non détecté (ex: x264, x265, H264, H265, HEVC, AVC)."
        )
        result.is_valid = False

    # Codec audio
    if not parsed.audio_codec:
        result.warnings.append(
            "Codec audio non détecté (ex: AAC, AC3, EAC3, DTS, TrueHD)."
        )

    # Tag TEAM
    if not parsed.team:
        result.warnings.append(
            "Tag TEAM absent. Si la team d'origine est inconnue, "
            "ajouter '-NOTAG' en fin de nom."
        )

    # ── 6. Vérification de l'ordre des tokens ─────────────────────────────
    # Template attendu (index = position attendue dans le nom) :
    # Titre > Année > (Saison/Episode) > Langue > Résolution > Source > HDR > CodecAudio > CodecVidéo > -TEAM
    _order_errors = _check_token_order(stem, parsed)
    for err in _order_errors:
        result.errors.append(err)
        result.is_valid = False

    # ── 7. Suggestion de nom normalisé ────────────────────────────────────
    result.suggested_name = _build_suggested_name(parsed, ext)

    return result


def _check_token_order(stem: str, p: ParsedRelease) -> list[str]:
    """
    Vérifie que les tokens respectent l'ordre du template C411 :
    Titre . Année . [SxxExx] . Langue . Résolution . Source . [HDR] . CodecAudio . CodecVidéo - TEAM

    Retourne une liste d'erreurs (vide = ordre correct).
    """
    errors = []
    parts_lower = [x.lower() for x in stem.split('.')]

    # ── Localiser la position de chaque token clé ──────────────────────────
    def idx_of(token: str) -> int:
        """Retourne l'index du token dans parts_lower, -1 si absent."""
        if not token:
            return -1
        tl = token.lower()
        for i, part in enumerate(parts_lower):
            # nettoyage défensif : retire un éventuel -suffix collé
            part_clean = part.split('-')[0]
            if part_clean == tl or part == tl:
                return i
        return -1

    def idx_of_any(tokens: list[str]) -> int:
        """Retourne l'index du PREMIER token trouvé dans la liste."""
        indices = [idx_of(t) for t in tokens if t]
        valid = [i for i in indices if i >= 0]
        return min(valid) if valid else -1

    pos_year    = idx_of(p.year)
    pos_lang    = idx_of_any(p.languages)
    pos_res     = idx_of(p.resolution)
    pos_source  = idx_of(p.source)
    pos_hdr     = idx_of_any(p.hdr_flags)
    pos_audio   = idx_of(p.audio_codec)
    pos_video   = idx_of(p.video_codec)

    # ── Séquence des éléments présents avec leur position et label ─────────
    # On ne vérifie que les éléments effectivement détectés (pos >= 0)
    # Ordre attendu : année < langue < résolution < source < hdr < audio < vidéo
    sequence = [
        (pos_year,   "Année",        p.year),
        (pos_lang,   "Langue",       '.'.join(p.languages) if p.languages else None),
        (pos_res,    "Résolution",   p.resolution),
        (pos_source, "Source",       p.source),
        (pos_hdr,    "HDR",          '.'.join(p.hdr_flags) if p.hdr_flags else None),
        (pos_audio,  "CodecAudio",   p.audio_codec),
        (pos_video,  "CodecVidéo",   p.video_codec),
    ]

    # Ne garder que les éléments présents
    present = [(pos, label, val) for pos, label, val in sequence
               if pos >= 0 and val]

    # Vérifier chaque paire consécutive
    for i in range(len(present) - 1):
        pos_a, label_a, val_a = present[i]
        pos_b, label_b, val_b = present[i + 1]
        if pos_a > pos_b:
            errors.append(
                f"Ordre incorrect : '{val_b}' ({label_b}) apparaît AVANT '{val_a}' ({label_a}). "
                f"Template attendu : …{label_a}.{label_b}…"
            )

    return errors


def _build_suggested_name(p: ParsedRelease, ext: str) -> str:
    """Reconstruit un nom normalisé à partir des composants parsés."""
    parts = []

    if p.title:
        parts.append(strip_accents(p.title).replace(' ', '.'))
    if p.year:
        parts.append(p.year)
    if p.season:
        if p.episode:
            parts.append(f"{p.season}{p.episode}")
        else:
            parts.append(p.season)
    if p.languages:
        parts.append('.'.join(p.languages))
    if p.resolution:
        parts.append(p.resolution)
    if p.source:
        parts.append(p.source.upper())
    for hdr in p.hdr_flags:
        parts.append(hdr)
    if p.audio_codec:
        token = p.audio_codec
        if p.audio_channels:
            token += f".{p.audio_channels}"
        parts.append(token)
    if p.video_codec:
        parts.append(p.video_codec)

    name = '.'.join(parts)

    team = p.team if p.team else "NOTAG"
    return f"{name}-{team}{ext}"


# ---------------------------------------------------------------------------
# Scanner de dossier
# ---------------------------------------------------------------------------

def scan_directory(root: str, recursive: bool = True) -> list[ValidationResult]:
    results = []
    root_path = Path(root)

    if not root_path.exists():
        print(f"[ERREUR] Chemin introuvable : {root}", file=sys.stderr)
        return results

    glob = root_path.rglob('*') if recursive else root_path.glob('*')

    for entry in sorted(glob):
        if entry.is_file() and entry.suffix.lower() in VIDEO_EXTENSIONS:
            result = validate_filename(str(entry))
            results.append(result)

    return results


# ---------------------------------------------------------------------------
# Affichage rapport
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"

def _color(text, color):
    return f"{color}{text}{RESET}" if sys.stdout.isatty() else text

def print_report(results: list[ValidationResult], verbose: bool = False):
    total = len(results)
    valid = sum(1 for r in results if r.is_valid)
    invalid = total - valid

    print(f"\n{_color('═'*60, BOLD)}")
    print(f"{_color('  RAPPORT DE VALIDATION C411', BOLD)}")
    print(f"{_color('═'*60, BOLD)}")
    print(f"  Fichiers scannés : {total}")
    print(f"  {_color(f'Valides   : {valid}', GREEN)}")
    print(f"  {_color(f'Invalides : {invalid}', RED if invalid else GREEN)}")
    print()

    for r in results:
        icon = _color("✓", GREEN) if r.is_valid else _color("✗", RED)
        print(f"{icon}  {_color(r.filename, BOLD)}")

        if r.errors:
            for e in r.errors:
                print(f"     {_color('⚠ ERREUR', RED)}  : {e}")
        if r.warnings:
            for w in r.warnings:
                print(f"     {_color('⚡ AVERT.', YELLOW)} : {w}")

        if verbose and r.parsed:
            p = r.parsed
            print(f"     {_color('→ Titre', CYAN)}     : {p.title or '?'}")
            print(f"     {_color('→ Année', CYAN)}     : {p.year or '?'}")
            print(f"     {_color('→ Langues', CYAN)}   : {', '.join(p.languages) or '?'}")
            print(f"     {_color('→ Résol.', CYAN)}    : {p.resolution or '?'}")
            print(f"     {_color('→ Source', CYAN)}    : {p.source or '?'}")
            print(f"     {_color('→ Audio', CYAN)}     : {p.audio_codec or '?'} {p.audio_channels or ''}")
            print(f"     {_color('→ Vidéo', CYAN)}     : {p.video_codec or '?'}")
            print(f"     {_color('→ Team', CYAN)}      : {p.team or '?'}")

        if not r.is_valid and r.suggested_name:
            print(f"     {_color('→ Suggestion', CYAN)}: {r.suggested_name}")

        print()

    print(_color('═'*60, BOLD))


def export_json(results: list[ValidationResult], output_path: str):
    data = []
    for r in results:
        d = {
            "filepath": r.filepath,
            "filename": r.filename,
            "is_valid": r.is_valid,
            "errors": r.errors,
            "warnings": r.warnings,
            "suggested_name": r.suggested_name,
        }
        if r.parsed:
            d["parsed"] = asdict(r.parsed)
        data.append(d)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Rapport JSON exporté : {output_path}")


# ---------------------------------------------------------------------------
# Point d'entrée CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scanner et validateur de nommage C411 (Films & Vidéos)"
    )
    parser.add_argument("path", help="Dossier ou fichier à scanner")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Affiche les composants parsés")
    parser.add_argument("--no-recursive", action="store_true",
                        help="Ne pas scanner les sous-dossiers")
    parser.add_argument("--export", metavar="FILE",
                        help="Exporte le rapport en JSON")
    args = parser.parse_args()

    target = Path(args.path)

    if target.is_file():
        results = [validate_filename(str(target))]
    elif target.is_dir():
        recursive = not args.no_recursive
        results = scan_directory(str(target), recursive=recursive)
        if not results:
            print("Aucun fichier vidéo trouvé dans le dossier spécifié.")
            sys.exit(0)
    else:
        print(f"[ERREUR] '{args.path}' n'est ni un fichier ni un dossier valide.",
              file=sys.stderr)
        sys.exit(1)

    print_report(results, verbose=args.verbose)

    if args.export:
        export_json(results, args.export)

    # Code de sortie : 0 si tout valide, 1 sinon
    sys.exit(0 if all(r.is_valid for r in results) else 1)


if __name__ == "__main__":
    main()
