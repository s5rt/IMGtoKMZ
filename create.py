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
        raise RuntimeError(proc.stderr.strip() or "exiftool failed")
    try:
        return json.loads(proc.stdout)
    except Exception as e:
        raise RuntimeError("Failed to parse exiftool JSON output") from e
def parse_dt(dt_str, candidate_path):
    if not dt_str:
        try:
            ts = os.path.getmtime(candidate_path)
            return datetime.utcfromtimestamp(ts)
        except Exception:
            return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y:%m:%d"):
        try:
            return datetime.strptime(dt_str, fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None
def make_kml(placemarks):
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    header = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>locn</name>
    <open>1</open>
'''
    body = ""
    for p in placemarks:
        name = escape(p['kname'])
        img_src = "files/" + os.path.basename(p['srcpath'])
        coords = f"{p['lon']},{p['lat']}"
        if p.get('alt') is not None:
            coords += f",{p['alt']}"
        placemark = f'''
    <Placemark>
      <name>{name}</name>
      <description><![CDATA[<img src="{img_src}" width="400"/>]]></description>
      <Point><coordinates>{coords}</coordinates></Point>
    </Placemark>
'''
        body += placemark
    footer = """
  </Document>
</kml>
"""
    return header + body + footer
def main():
    if len(sys.argv) < 2:
        print("Usage: python3 create.py /path/to/images [output_name.kmz]")
        sys.exit(1)
    image_dir = sys.argv[1]
    if not os.path.isdir(image_dir):
        print("Error: image directory not found:", image_dir)
        sys.exit(1)
    out_kmz = sys.argv[2] if len(sys.argv) >= 3 else "images.kmz"
    data = run_exiftool_json(image_dir)
    items = []
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
        if not os.path.isabs(src):
            candidate = os.path.join(image_dir, src)
        else:
            candidate = src
        if not os.path.exists(candidate):
            candidate = os.path.join(image_dir, os.path.basename(src))
        dt = parse_dt(item.get("DateTimeOriginal"), candidate)
        items.append({
            "srcpath": src,
            "lon": lon,
            "lat": lat,
            "alt": alt_val,
            "dt": dt,
            "candidate": candidate,
            "description": f"Source file: {os.path.basename(src)}"
        })
    if not items:
        print("No geotagged images found.")
        if skipped:
            print(f"{len(skipped)} files without GPS.")
        sys.exit(1)
    items.sort(key=lambda x: (x['dt'] is None, x['dt'] or datetime.utcfromtimestamp(0)))
    for idx, it in enumerate(items, start=1):
        it['kname'] = f"p{idx}"
    kml_text = make_kml(list(reversed(items)))
    tmp = tempfile.mkdtemp(prefix="kmz_")
    try:
        files_dir = os.path.join(tmp, "files")
        os.makedirs(files_dir, exist_ok=True)
        for p in items:
            src = p['srcpath']
            dst = os.path.join(files_dir, os.path.basename(src))
            candidate = p['candidate']
            if not os.path.exists(candidate):
                print("Warning: could not find file to copy:", src)
                continue
            shutil.copy2(candidate, dst)
        kml_path = os.path.join(tmp, "doc.kml")
        with open(kml_path, "w", encoding="utf-8") as f:
            f.write(kml_text)
        with zipfile.ZipFile(out_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
            kmz.write(kml_path, arcname="doc.kml")
            for root, _, files in os.walk(files_dir):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, tmp)
                    kmz.write(full, arcname=rel)
        print("KMZ created:", out_kmz)
        if skipped:
            print(f"Skipped {len(skipped)} files (no GPS).")
    finally:
        shutil.rmtree(tmp)
if __name__ == "__main__":
    main()