# python3 create.py ./photos/ kmz/my_photos.kmz
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape
def run_exiftool_json(image_dir):
    cmd = [
        "exiftool", "-json", "-n",
        "-FileName", "-SourceFile",
        "-GPSLatitude", "-GPSLongitude", "-GPSAltitude",
        "-DateTimeOriginal",
        "-r", image_dir
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"exiftool failed: {proc.stderr.strip()}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError("Failed to parse exiftool JSON output") from e
    return data
def make_kml(placemarks):
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    header = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Photos {escape(now)}</name>
    <open>1</open>
'''
    style = '''
    <Style id="photoThumb">
      <BalloonStyle>
        <text><![CDATA[
          <b>$[name]</b><br/>
          <table><tr><td>
            <img src="$[image_link]" width="400"/><br/>
          </td></tr>
          <tr><td>$[description]</td></tr></table>
        ]]></text>
      </BalloonStyle>
    </Style>
'''
    body = ""
    for p in placemarks:
        name = escape(p['name'])
        desc = escape(p.get('description',''))
        img_src = "files/" + os.path.basename(p['srcpath'])
        ed = ""
        if p.get('datetime'):
            ed += f"<ExtendedData><Data name='DateTimeOriginal'><value>{escape(p['datetime'])}</value></Data></ExtendedData>"
        coords = f"{p['lon']},{p['lat']}"
        if p.get('alt') is not None:
            coords += f",{p['alt']}"
        placemark = f'''
    <Placemark>
      <name>{name}</name>
      <description><![CDATA[<img src="{img_src}" width="400"/><br/>{desc}]]></description>
      <styleUrl>#photoThumb</styleUrl>
      {ed}
      <Point><coordinates>{coords}</coordinates></Point>
    </Placemark>
'''
        body += placemark
    footer = """
  </Document>
</kml>
"""
    return header + style + body + footer
def main():
    if len(sys.argv) < 2:
        print("Usage: python3 create_kmz.py /path/to/images [output_name.kmz]")
        sys.exit(1)
    image_dir = sys.argv[1]
    if not os.path.isdir(image_dir):
        print("Error: image directory not found:", image_dir)
        sys.exit(1)
    out_kmz = sys.argv[2] if len(sys.argv) >= 3 else "images.kmz"
    print("Reading EXIF (this may take a moment)...")
    data = run_exiftool_json(image_dir)
    placemarks = []
    skipped = []
    for item in data:
        src = item.get("SourceFile") or item.get("FileName")
        if not src:
            continue
        gpslat = item.get("GPSLatitude")
        gpslon = item.get("GPSLongitude")
        if gpslat is None or gpslon is None:
            skipped.append(src)
            continue
        try:
            lat = float(gpslat)
            lon = float(gpslon)
        except Exception:
            skipped.append(src)
            continue
        alt = item.get("GPSAltitude")
        alt_val = float(alt) if (alt is not None) else None
        dt = item.get("DateTimeOriginal")
        placemarks.append({
            "name": os.path.basename(src),
            "srcpath": src,
            "lon": lon,
            "lat": lat,
            "alt": alt_val,
            "datetime": dt,
            "description": f"Source file: {os.path.basename(src)}"
        })
    if not placemarks:
        print("No geotagged images found in the folder.")
        if skipped:
            print(f"{len(skipped)} images without GPS (examples):\n  " + "\n  ".join(skipped[:5]))
        sys.exit(1)
    print(f"Found {len(placemarks)} geotagged images, {len(skipped)} without GPS (skipped).")
    print("Creating KML...")
    kml_text = make_kml(placemarks)
    tmp = tempfile.mkdtemp(prefix="kmz_")
    try:
        files_dir = os.path.join(tmp, "files")
        os.makedirs(files_dir, exist_ok=True)
        for p in placemarks:
            src = p['srcpath']
            dst = os.path.join(files_dir, os.path.basename(src))
            if not os.path.isabs(src):
                candidate = os.path.join(image_dir, src)
            else:
                candidate = src
            if not os.path.exists(candidate):
                candidate = os.path.join(image_dir, os.path.basename(src))
            if not os.path.exists(candidate):
                print("Warning: could not find file to copy:", src)
                continue
            shutil.copy2(candidate, dst)
        kml_path = os.path.join(tmp, "doc.kml")
        with open(kml_path, "w", encoding="utf-8") as f:
            f.write(kml_text)
        print("Writing KMZ to", out_kmz)
        with zipfile.ZipFile(out_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
            kmz.write(kml_path, arcname="doc.kml")
            for root, _, files in os.walk(files_dir):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, tmp)  # so it becomes files/filename
                    kmz.write(full, arcname=rel)
        print("KMZ created:", out_kmz)
        if skipped:
            print(f"Skipped {len(skipped)} files (no GPS).")
            if len(skipped) <= 10:
                for s in skipped:
                    print("  ", s)
            else:
                print("  Example skipped:", skipped[0])
    finally:
        shutil.rmtree(tmp)
if __name__ == "__main__":
    main()