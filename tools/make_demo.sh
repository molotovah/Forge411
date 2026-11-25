#!/bin/sh
# Génère un jeu de fichiers de démonstration (œuvres libres) pour tester Forge411 et faire les captures.
# Usage : tools/make_demo.sh <dossier>   (nécessite ffmpeg et python3)
set -e
D="${1:?dossier de sortie}"
mkdir -p "$D"

# Film : Big Buck Bunny (CC-BY), mire 1080p 20 s, audio anglais, sous-titres français
V="$D/Big Buck Bunny 2008 1080p WEBRip x264 AAC-DEMO.mkv"
printf '1\n00:00:01,000 --> 00:00:05,000\nUn lapin se réveille.\n' > "$D/fr.srt"
ffmpeg -loglevel error -y -f lavfi -i testsrc2=size=1920x1080:rate=24 -f lavfi -i sine=frequency=440:sample_rate=48000 \
  -i "$D/fr.srt" -t 20 -map 0:v -map 1:a -map 2:s -c:v libx264 -preset veryfast -crf 28 -c:a aac -ac 2 -b:a 128k \
  -c:s srt -metadata:s:a:0 language=eng -metadata:s:s:0 language=fre -metadata:s:s:0 title=Français "$V"
rm "$D/fr.srt"

# Album : Nine Inch Nails – Ghosts I-IV (CC BY-NC-SA), 4 pistes FLAC 16 bits taguées + pochette
A="$D/Nine Inch Nails - Ghosts I-IV (2008) [FLAC]"
mkdir -p "$A"
i=1
for t in "1 Ghosts I" "2 Ghosts I" "3 Ghosts I" "4 Ghosts I"; do
  ffmpeg -loglevel error -y -f lavfi -i "sine=frequency=$((200 + i * 60)):sample_rate=44100" -t 15 -ac 2 -sample_fmt s16 \
    -metadata artist="Nine Inch Nails" -metadata album="Ghosts I–IV" -metadata date=2008 -metadata genre="Ambient" \
    -metadata title="$t" -metadata track="$i/4" "$A/0$i - $t.flac"
  i=$((i + 1))
done
ffmpeg -loglevel error -y -f lavfi -i "gradients=size=600x600:speed=0" -frames:v 1 "$A/cover.jpg"

# Livre : Les Misérables (domaine public), EPUB minimal avec métadonnées
python3 - "$D" <<'PY'
import sys, zipfile
d = sys.argv[1]
opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:identifier id="id">urn:isbn:9782253096337</dc:identifier>
  <dc:title>Les Misérables</dc:title><dc:creator>Victor Hugo</dc:creator>
  <dc:language>fr</dc:language><dc:publisher>Domaine public</dc:publisher><dc:date>1862</dc:date>
 </metadata>
 <manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest>
 <spine><itemref idref="c1"/></spine>
</package>"""
with zipfile.ZipFile(f"{d}/Victor Hugo - Les Miserables.epub", "w") as z:
    z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
    z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    z.writestr("OEBPS/content.opf", opf)
    z.writestr("OEBPS/c1.xhtml", "<html><body><p>Tome premier – Fantine.</p></body></html>")
PY

# Jeu : 0 A.D. (libre), version portable
G="$D/0 A.D. v0.27.0 Portable"
mkdir -p "$G/binaries/system" "$G/binaries/data/mods/public"
head -c 300000 /dev/urandom > "$G/binaries/system/pyrogenesis.exe"
head -c 2000000 /dev/urandom > "$G/binaries/data/mods/public/public.pak"

# Application : VLC (libre), installateur Windows
P="$D/VLC media player 3.0.21 Windows"
mkdir -p "$P"
head -c 500000 /dev/urandom > "$P/vlc-3.0.21-win64-setup.exe"
echo "Démo générée dans $D"
