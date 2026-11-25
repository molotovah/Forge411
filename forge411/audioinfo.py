"""Analyse de fichiers audio (tags et caractéristiques) avec mutagen."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .model import Source

try:
    import mutagen
    MUTAGEN_OK = True
except ImportError:
    mutagen = None
    MUTAGEN_OK = False

AUDIO_EXT = {".flac", ".mp3", ".m4a", ".m4b", ".aac", ".ogg", ".oga", ".opus", ".wav", ".aif",
             ".aiff", ".ape", ".wv", ".dsf", ".dff", ".wma", ".mpc"}
LOSSLESS = {"FLAC", "ALAC", "WAV", "AIFF", "APE", "WV", "DSD"}
IMAGE_EXT = {".jpg", ".jpeg", ".png"}


@dataclass
class Track:
    rel: str
    title: str = ""
    artist: str = ""
    album: str = ""
    albumartist: str = ""
    date: str = ""
    number: str = ""
    disc: str = ""
    genre: str = ""
    duration: float = 0.0
    bitrate: int = 0          # kb/s
    sample_rate: int = 0
    bits: int = 0
    channels: int = 0
    codec: str = ""
    vbr: bool = False
    size: int = 0
    tag_format: str = ""      # Vorbis, ID3v2, MP4…
    embedded_cover: bool = False


@dataclass
class AudioAnalysis:
    tracks: list = field(default_factory=list)
    has_cue: bool = False
    has_log: bool = False
    cover: str = ""           # fichier image trouvé à la racine
    cover_size: tuple = (0, 0)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def _common(self, attr):
        vals = [getattr(t, attr) for t in self.tracks if getattr(t, attr)]
        return max(set(vals), key=vals.count) if vals else ""

    @property
    def artist(self) -> str:
        return self._common("albumartist") or self._common("artist")

    @property
    def album(self) -> str:
        return self._common("album")

    @property
    def year(self) -> str:
        return str(self._common("date"))[:4]

    @property
    def genres(self) -> list:
        out = []
        for t in self.tracks:
            for g in t.genre.replace(";", "/").split("/"):
                g = g.strip()
                if g and g not in out:
                    out.append(g)
        return out[:6]

    @property
    def codecs(self) -> set:
        return {t.codec for t in self.tracks if t.codec}

    @property
    def codec(self) -> str:
        return self._common("codec")

    @property
    def lossless(self) -> bool:
        return self.codec in LOSSLESS

    @property
    def duration(self) -> float:
        return sum(t.duration for t in self.tracks)

    @property
    def bitrate(self) -> int:
        vals = [t.bitrate for t in self.tracks if t.bitrate]
        return int(sum(vals) / len(vals)) if vals else 0

    @property
    def sample_rate(self) -> int:
        return self._common("sample_rate") or 0

    @property
    def bits(self) -> int:
        return self._common("bits") or 0

    @property
    def vbr(self) -> bool:
        return any(t.vbr for t in self.tracks)

    @property
    def missing_tags(self) -> list:
        """Tags obligatoires (wiki C411) absents d'au moins une piste."""
        out = []
        for key, label in (("artist", "artiste"), ("album", "album"), ("title", "titre"),
                           ("number", "numéro de piste"), ("date", "année"), ("genre", "genre")):
            if any(not getattr(t, key) for t in self.tracks):
                out.append(label)
        return out

    @property
    def all_covers_embedded(self) -> bool:
        return bool(self.tracks) and all(t.embedded_cover for t in self.tracks)

    @property
    def channels(self) -> int:
        return self._common("channels") or 0


def _first(tags, key) -> str:
    if not tags:
        return ""
    v = tags.get(key)
    if isinstance(v, list):
        v = v[0] if v else ""
    return str(v).strip() if v else ""


def _codec(f, path: Path) -> str:
    name = type(f).__name__.upper()
    ext = path.suffix.lower()
    if "FLAC" in name:
        return "FLAC"
    if "MP3" in name or ext == ".mp3":
        return "MP3"
    if "MP4" in name or ext in (".m4a", ".m4b", ".aac"):
        c = str(getattr(f.info, "codec", "")).lower()
        return "ALAC" if "alac" in c else "AAC"
    if "OPUS" in name:
        return "OPUS"
    if "OGG" in name or "VORBIS" in name:
        return "OGG"
    if "WAVE" in name:
        return "WAV"
    if "AIFF" in name:
        return "AIFF"
    if "MONKEY" in name:
        return "APE"
    if "WAVPACK" in name:
        return "WV"
    if "DSF" in name or "DSDIFF" in name:
        return "DSD"
    if "ASF" in name:
        return "WMA"
    if "MUSEPACK" in name:
        return "MPC"
    return ext.lstrip(".").upper()


def read_track(path: Path, rel: str) -> Track:
    t = Track(rel=rel, size=path.stat().st_size, codec=path.suffix.lstrip(".").upper())
    if not MUTAGEN_OK:
        return t
    try:
        f = mutagen.File(str(path), easy=True)
    except Exception:
        f = None
    if f is None:
        return t
    info = f.info
    t.codec = _codec(f, path)
    t.duration = float(getattr(info, "length", 0) or 0)
    br = getattr(info, "bitrate", 0) or 0
    t.bitrate = int(br / 1000) if br > 10000 else int(br)
    t.sample_rate = int(getattr(info, "sample_rate", 0) or 0)
    t.bits = int(getattr(info, "bits_per_sample", 0) or 0)
    t.channels = int(getattr(info, "channels", 0) or 0)
    mode = getattr(info, "bitrate_mode", None)
    t.vbr = mode is not None and "VBR" in str(mode).upper()
    tags = f.tags
    t.title = _first(tags, "title")
    t.artist = _first(tags, "artist")
    t.album = _first(tags, "album")
    t.albumartist = _first(tags, "albumartist")
    t.date = _first(tags, "date") or _first(tags, "year")
    t.number = _first(tags, "tracknumber").split("/")[0]
    t.disc = _first(tags, "discnumber").split("/")[0]
    t.genre = _first(tags, "genre")
    try:
        raw = mutagen.File(str(path))
        name = type(raw).__name__.upper()
        rt = raw.tags if raw is not None else None
        if "FLAC" in name:
            t.tag_format, t.embedded_cover = "Vorbis", bool(getattr(raw, "pictures", []))
        elif "MP3" in name:
            t.tag_format = "ID3v2" if rt is not None else ""
            t.embedded_cover = rt is not None and any(k.startswith("APIC") for k in rt.keys())
        elif "MP4" in name:
            t.tag_format, t.embedded_cover = "MP4", rt is not None and "covr" in rt
        elif rt is not None:
            t.tag_format = "Vorbis" if "OGG" in name or "OPUS" in name else name.title()
            t.embedded_cover = "metadata_block_picture" in rt or "covr" in rt
    except Exception:
        pass
    return t


def analyze(src: Source, progress: Optional[Callable[[str], None]] = None) -> AudioAnalysis:
    a = AudioAnalysis()
    audio = src.by_ext(*AUDIO_EXT)
    if not audio:
        a.errors.append("Aucun fichier audio trouvé.")
        return a
    for i, f in enumerate(audio):
        if progress and i % 5 == 0:
            progress(f"Lecture des tags {i + 1}/{len(audio)} : {f.name}")
        a.tracks.append(read_track(f, src.rel(f)))
    root = src.path if src.is_dir else src.path.parent
    a.has_cue = bool(src.by_ext(".cue"))
    a.has_log = bool(src.by_ext(".log"))
    for name in ("cover.jpg", "cover.png", "folder.jpg", "front.jpg"):
        if src.is_dir and (root / name).exists():
            a.cover = name
            try:
                from PIL import Image
                with Image.open(root / name) as im:
                    a.cover_size = im.size
            except Exception:
                pass
            break
    if not MUTAGEN_OK:
        a.warnings.append("mutagen indisponible : les tags audio ne sont pas lus.")
    return a
