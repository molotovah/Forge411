"""
Analyse vidéo avec MediaInfo.

Produit les tags C411 déduits des pistes réelles : langue, résolution,
codec audio, codec vidéo, HDR.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .model import Source
from .scanner import parse_release_name, ParsedRelease

try:
    from pymediainfo import MediaInfo
    MEDIAINFO_OK = MediaInfo.can_parse()
except Exception:  # bibliothèque absente ou libmediainfo introuvable
    MediaInfo = None
    MEDIAINFO_OK = False

VIDEO_EXT = {".mkv", ".mp4", ".m4v", ".avi", ".ts", ".m2ts"}
FORBIDDEN_EXT = {".wmv", ".mov", ".flv", ".swf", ".rm", ".rar", ".zip", ".7z"}

SE_RE = re.compile(r"\bS(\d{1,2})[ ._-]?E(\d{1,3})\b", re.I)
S_RE = re.compile(r"\bS(\d{1,2})\b", re.I)


# ═══════════════════════════════════════════════════════════════════════════
# Structures
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class AudioTrack:
    format: str = ""
    features: str = ""
    commercial: str = ""
    channels: int = 0
    language: str = ""
    title: str = ""
    bitrate: int = 0


@dataclass
class SubTrack:
    format: str = ""
    language: str = ""
    title: str = ""
    forced: bool = False


@dataclass
class VideoTrack:
    format: str = ""
    library: str = ""
    width: int = 0
    height: int = 0
    bitrate: int = 0
    hdr: str = ""
    fps: str = ""
    bit_depth: str = ""


@dataclass
class MediaFile:
    path: Path
    size: int = 0
    container: str = ""
    duration_ms: int = 0
    video: Optional[VideoTrack] = None
    audios: list = field(default_factory=list)
    subs: list = field(default_factory=list)
    text: str = ""          # sortie MediaInfo complète (pour le NFO)


@dataclass
class VideoAnalysis:
    videos: list = field(default_factory=list)      # MediaFile des vidéos
    kind: str = "movie"                             # movie | episode | season | pack
    seasons: list = field(default_factory=list)     # [2] ou [1, 2, 3]
    episode: Optional[int] = None
    parsed: Optional[ParsedRelease] = None
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def main(self) -> Optional[MediaFile]:
        return self.videos[0] if self.videos else None

    @property
    def duration_ms(self) -> int:
        return sum(v.duration_ms for v in self.videos)

    @property
    def is_tv(self) -> bool:
        return self.kind in ("episode", "season", "pack")


# ═══════════════════════════════════════════════════════════════════════════
# Lecture MediaInfo
# ═══════════════════════════════════════════════════════════════════════════

def _int(v) -> int:
    try:
        return int(float(str(v).split("/")[0].strip()))
    except (TypeError, ValueError):
        return 0


def _str(v) -> str:
    return str(v).strip() if v not in (None, "") else ""


def read_media(path: Path, with_text: bool = True) -> MediaFile:
    mf = MediaFile(path=path, size=path.stat().st_size)
    if not MEDIAINFO_OK:
        return mf
    mi = MediaInfo.parse(str(path))
    full = False
    if with_text and mi.video_tracks and not _int(mi.video_tracks[0].bit_rate):
        # MKV sans statistiques : analyse complète du fichier pour obtenir le débit vidéo (exigé par C411)
        mi, full = MediaInfo.parse(str(path), parse_speed=1.0), True
    if mi.general_tracks:
        g = mi.general_tracks[0]
        mf.container = _str(g.format)
        mf.duration_ms = _int(g.duration)
    for t in mi.video_tracks[:1]:
        mf.video = VideoTrack(
            format=_str(t.format),
            library=_str(t.encoded_library_name or t.writing_library),
            width=_int(t.width), height=_int(t.height),
            bitrate=_int(t.bit_rate),
            hdr=" / ".join(x for x in (_str(t.hdr_format),
                                       _str(t.hdr_format_compatibility)) if x),
            fps=_str(t.frame_rate), bit_depth=_str(t.bit_depth),
        )
    for t in mi.audio_tracks:
        mf.audios.append(AudioTrack(
            format=_str(t.format), features=_str(t.format_additionalfeatures),
            commercial=_str(t.commercial_name), channels=_int(t.channel_s),
            language=_str(t.language).lower(), title=_str(t.title),
            bitrate=_int(t.bit_rate),
        ))
    for t in mi.text_tracks:
        mf.subs.append(SubTrack(
            format=_str(t.format), language=_str(t.language).lower(),
            title=_str(t.title), forced=_str(t.forced).lower() == "yes",
        ))
    if with_text:
        text = MediaInfo.parse(str(path), output="", full=False, **({"parse_speed": 1.0} if full else {}))
        # Ne pas exposer le chemin local dans le NFO
        mf.text = re.sub(r"(?m)^(Complete name\s*:\s*).*$",
                         lambda m: m.group(1) + path.name, text).strip()
    return mf


# ═══════════════════════════════════════════════════════════════════════════
# Analyse d'une source
# ═══════════════════════════════════════════════════════════════════════════

def normalize_name(name: str) -> str:
    """'Titre 2025 S02E01 VOSTFR 1080p x265 TEAM' → forme pointée."""
    n = re.sub(r"[\s_]+", ".", name.strip())
    n = re.sub(r"\.{2,}", ".", n)
    return n.strip(".")


def analyze(src: Source, progress: Optional[Callable[[str], None]] = None) -> VideoAnalysis:
    va = VideoAnalysis()
    video_paths = [f for f in src.files if f.suffix.lower() in VIDEO_EXT]
    bad = sorted({f.suffix.lower() for f in src.files if f.suffix.lower() in FORBIDDEN_EXT})
    if bad:
        va.errors.append("Formats refusés par C411 : " + ", ".join(bad))
    if not video_paths:
        va.errors.append("Aucune vidéo trouvée (mkv, mp4, avi, ts, m2ts).")
        return va
    for i, vp in enumerate(video_paths):
        if progress:
            progress(f"Analyse MediaInfo {i + 1}/{len(video_paths)} : {vp.name}"
                     + (" (calcul du débit vidéo, quelques secondes…)" if i == 0 else ""))
        va.videos.append(read_media(vp, with_text=(i == 0)))

    stem = src.stem
    va.parsed = parse_release_name(normalize_name(stem))
    eps = []
    for v in va.videos:
        m = SE_RE.search(normalize_name(v.path.stem).replace(".", " "))
        if m:
            eps.append((int(m.group(1)), int(m.group(2))))
    s_match = S_RE.search(normalize_name(stem).replace(".", " "))
    if len(va.videos) == 1 and eps:
        va.kind, va.seasons, va.episode = "episode", [eps[0][0]], eps[0][1]
    elif len(va.videos) > 1 and eps:
        va.seasons = sorted({s for s, _ in eps})
        va.kind = "season" if len(va.seasons) == 1 else "pack"
    elif len(va.videos) > 1:
        va.kind = "season" if s_match else "pack"
        if s_match:
            va.seasons = [int(s_match.group(1))]
    elif s_match:
        va.kind, va.seasons = "season", [int(s_match.group(1))]
    _check_consistency(va)
    return va


def _check_consistency(src: VideoAnalysis):
    if not MEDIAINFO_OK:
        src.warnings.append("MediaInfo indisponible : les tags ne peuvent pas être déduits des pistes.")
        return
    if len(src.videos) > 1:
        specs = {(resolution_tag(v), video_codec_tag(v, "")) for v in src.videos}
        if len(specs) > 1:
            src.warnings.append("Les vidéos du pack n'ont pas toutes les mêmes caractéristiques "
                                "(résolution / codec) : C411 l'exige.")
    for v in src.videos:
        for s in v.subs:
            t = s.title.lower()
            if s.language.startswith("fr") and ("auto" in t or "machine" in t or "google" in t):
                src.warnings.append("Sous-titres français en traduction automatique : "
                                    "interdits par C411 pour un VOSTFR.")
                return


# ═══════════════════════════════════════════════════════════════════════════
# Tags déduits des pistes
# ═══════════════════════════════════════════════════════════════════════════

def resolution_tag(mf: Optional[MediaFile]) -> str:
    if not mf or not mf.video:
        return ""
    w, h = mf.video.width, mf.video.height
    if w >= 3800 or h >= 1800:
        return "2160p"
    if w >= 1700 or h >= 900:
        return "1080p"
    if w >= 1200 or h >= 650:
        return "720p"
    return ""


def hdr_tag(mf: Optional[MediaFile]) -> str:
    if not mf or not mf.video or not mf.video.hdr:
        return ""
    h = mf.video.hdr
    dv = "Dolby Vision" in h
    if "HDR10+" in h or "2094" in h:
        hdr = "HDR10PLUS"
    elif "HDR10" in h or "2086" in h:
        hdr = "HDR10"
    elif "HLG" in h:
        hdr = "HLG"
    else:
        hdr = ""
    if dv and hdr:
        return f"DV.{hdr}"
    return "DV" if dv else hdr


def video_codec_tag(mf: Optional[MediaFile], source: str) -> str:
    if not mf or not mf.video:
        return ""
    lib = mf.video.library.lower()
    fmt = mf.video.format.upper()
    for enc in ("x264", "x265"):
        if enc in lib:
            return enc
    pure = source.upper() in ("REMUX", "BDMV", "ISO", "BLURAY.REMUX")
    if fmt == "AVC":
        return "AVC" if pure else "H264"
    if fmt == "HEVC":
        return "HEVC" if pure else "H265"
    if fmt == "AV1":
        return "AV1"
    if "XVID" in lib or fmt == "MPEG-4 VISUAL":
        return "XviD"
    if fmt == "MPEG VIDEO":
        return "MPEG2"
    return fmt


def _audio_codec(a: AudioTrack) -> str:
    f, feat, com = a.format.upper(), a.features.upper(), a.commercial.upper()
    if f.startswith("AAC"):
        return "AAC"
    if f == "E-AC-3":
        return "EAC3.ATMOS" if ("JOC" in feat or "ATMOS" in com) else "EAC3"
    if f == "AC-3":
        return "AC3"
    if f == "DTS":
        if "DTS:X" in com or "XLL X" in feat:
            return "DTSX"
        if "XLL" in feat or "MA" in com:
            return "DTS.HD.MA"
        return "DTS"
    if f.startswith("MLP"):
        return "TRUEHD.ATMOS" if ("16-CH" in feat or "ATMOS" in com) else "TRUEHD"
    if f == "PCM":
        return "LPCM"
    if f == "FLAC":
        return "FLAC"
    if f == "OPUS":
        return "OPUS"
    if f == "MPEG AUDIO":
        return "MP3"
    return f.replace("-", "")


_CHANNELS = {1: "1.0", 2: "2.0", 3: "2.1", 6: "5.1", 7: "6.1", 8: "7.1"}


def audio_tag(mf: Optional[MediaFile]) -> str:
    """Piste française avec le plus de canaux, sinon la piste la plus riche."""
    if not mf or not mf.audios:
        return ""
    fr = [a for a in mf.audios if a.language.startswith("fr")]
    best = max(fr or mf.audios, key=lambda a: a.channels)
    ch = _CHANNELS.get(best.channels, f"{best.channels}.0" if best.channels else "")
    codec = _audio_codec(best)
    return f"{codec}.{ch}" if ch else codec


def _fr_variant(a: AudioTrack) -> str:
    t = a.title.upper()
    if a.language in ("fr-ca",) or "VFQ" in t or "QUEB" in t or "CANAD" in t:
        return "VFQ"
    if a.language == "fr-be" or "VFB" in t or "BELG" in t:
        return "VFB"
    if "VFI" in t:
        return "VFI"
    return "VFF"


def language_tag(mf: Optional[MediaFile], original: Optional[ParsedRelease] = None) -> str:
    if not mf:
        return ""
    fr_subs = any(s.language.startswith("fr") and not s.forced for s in mf.subs)
    if not mf.audios:
        return "MUET.VOSTFR" if fr_subs else "MUET"
    fr = [a for a in mf.audios if a.language.startswith("fr")]
    others = [a for a in mf.audios if a.language and not a.language.startswith("fr")]
    orig = {l.upper() for l in (original.languages if original else [])}
    if fr:
        variants = {_fr_variant(a) for a in fr}
        if {"VFF", "VFQ"} <= variants:
            return "MULTI.VF2"
        main = "VFF" if "VFF" in variants else sorted(variants)[0]
        # Garder TRUEFRENCH / VOF / VFI du nom d'origine s'ils sont cohérents
        for keep in ("TRUEFRENCH", "VOF", "VFI"):
            if main == "VFF" and keep in orig:
                main = keep
        return f"MULTI.{main}" if others else main
    if fr_subs:
        for keep in ("FANSUB", "FASTSUB"):
            if keep in orig or keep in (original.raw_name.upper() if original else ""):
                return f"VOSTFR.{keep}"
        return "VOSTFR"
    return ""
