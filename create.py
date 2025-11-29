#!/usr/bin/env python3
# python3 create.py ./photos/ kmz/my_photos.kmz
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import csv
from datetime import datetime
from xml.sax.saxutils import escape
def run_exiftool_json(image_dir):
    cmd = ["exiftool", "-json", "-n", "-FileName", "-SourceFile", "-GPSLatitude", "-GPSLongitude", "-GPSAltitude", "-DateTimeOriginal", "-r", image_dir]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "exiftool failed")
    return json.loads(proc.stdout)
def parse_dt(dt_str, candidate_path):
    if not dt_str:
        try:
            return datetime.utcfromtimestamp(os.path.getmtime(candidate_path))
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
def make_kml(placemarks, doc_name, include_tour):
    icon_url = "http://maps.google.com/mapfiles/kml/shapes/donut.png"
    hdr = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"
     xmlns:gx="http://www.google.com/kml/ext/2.2">
  <Document>
    <name>{escape(doc_name)}</name>
    <open>1</open>
    <Style id="customIcon">
      <IconStyle>
        <Icon>
          <href>{icon_url}</href>
        </Icon>
        <scale>1.2</scale>
      </IconStyle>
    </Style>
'''
    body = ""
    for p in placemarks:
        name = escape(p['kname'])
        img_src = p['kimg']
        coords = f"{p['lon']},{p['lat']}"
        if p['alt'] is not None:
            coords += f",{p['alt']}"
        body += f'''
    <Placemark>
      <name>{name}</name>
      <styleUrl>#customIcon</styleUrl>
      <description><![CDATA[<img src="{img_src}" width="400"/>]]></description>
      <Point><coordinates>{coords}</coordinates></Point>
    </Placemark>
'''
    tour = ""
    if include_tour:
        playlist = ""
        seq = sorted(placemarks, key=lambda x: x['dt'] or datetime.utcfromtimestamp(0))
        for p in seq:
            lat = p['lat']; lon = p['lon']; alt = p['alt'] or 0
            playlist += f'''
      <gx:FlyTo>
        <gx:duration>3</gx:duration>
        <LookAt>
          <longitude>{lon}</longitude>
          <latitude>{lat}</latitude>
          <altitude>{alt}</altitude>
          <heading>0</heading>
          <tilt>45</tilt>
          <range>200</range>
          <altitudeMode>relativeToGround</altitudeMode>
        </LookAt>
      </gx:FlyTo>
'''
        tour = f'''
    <gx:Tour>
      <name>Photo Tour</name>
      <gx:Playlist>
{playlist}
      </gx:Playlist>
    </gx:Tour>
'''
    return hdr + body + tour + "\n  </Document>\n</kml>\n"
def main():
    args = sys.argv
    if len(args) < 2:
        print("Usage: python3 create.py /path/to/images [output.kmz] [--tour]")
        sys.exit(1)
    image_dir = args[1]
    out_kmz = args[2] if len(args) >= 3 and not args[2].startswith("--") else "images.kmz"
    include_tour = ("--tour" in args)
    if not os.path.isdir(image_dir):
        print("Error: image directory not found:", image_dir)
        sys.exit(1)
    data = run_exiftool_json(image_dir)
    items = []
    skipped = []
    for item in data:
        src = item.get("SourceFile") or item.get("FileName")
        if not src:
            continue
        if not os.path.isabs(src):
            candidate = os.path.join(image_dir, src)
        else:
            candidate = src
        if not os.path.exists(candidate):
            candidate = os.path.join(image_dir, os.path.basename(src))
        gpslat = item.get("GPSLatitude")
        gpslon = item.get("GPSLongitude")
        if gpslat is None or gpslon is None:
            skipped.append(candidate)
            continue
        try:
            lat = float(gpslat); lon = float(gpslon)
        except Exception:
            skipped.append(candidate)
            continue
        alt = item.get("GPSAltitude")
        alt_val = float(alt) if alt is not None else None
        dt = parse_dt(item.get("DateTimeOriginal"), candidate)
        items.append({
             "sr cpath":  src, "candidate": candidate,"lon": lon,"lat": lat,"alt": alt_val,"dt": dt
        })
    if not items and not skipped:
        print("No images found.")
        sys.exit(1)
    items.sort(key=lambda x: (x['dt'] is None,
                              x['dt'] or datetime.utcfromtimestamp(0)))
    for idx, it in enumerate(items, start=1):
        it['kname'] = f"p{idx}"
    kml_items = list(reversed(items))
    tmp = tempfile.mkdtemp(prefix="kmz_")
    try:
        files_dir = os.path.join(tmp, "files")
        os.makedirs(files_dir, exist_ok=True)
        for p in items:
            dst = os.path.join(files_dir, os.path.basename(p['candidate']))
            shutil.copy2(p['candidate'], dst)
            p['kimg'] = "files/" + os.path.basename(p['candidate'])
        kml_text = make_kml(kml_items,
                            os.path.splitext(os.path.basename(out_kmz))[0],
                            include_tour)
        kml_path = os.path.join(tmp, "doc.kml")
        with open(kml_path, "w", encoding="utf-8") as f:
            f.write(kml_text)
        out_dir = os.path.dirname(out_kmz) or "."
        os.makedirs(out_dir, exist_ok=True)
        no_gps_dir = os.path.join(out_dir, "no_gps")
        if skipped:
            os.makedirs(no_gps_dir, exist_ok=True)
            for s in skipped:
                if os.path.exists(s):
                    shutil.copy2(s, os.path.join(no_gps_dir, os.path.basename(s)))
        with zipfile.ZipFile(out_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
            kmz.write(kml_path, arcname="doc.kml")
            for root, _, files in os.walk(files_dir):
                for fn in files:
                    full = os.path.join(root, fn)
                    kmz.write(full, arcname=os.path.relpath(full, tmp))
        csv_path = os.path.join(out_dir,
                                os.path.splitext(os.path.basename(out_kmz))[0] + "_report.csv")
        rows = []
        for p in items:
            rows.append((p['kname'], p['candidate'], p['lat'],
                         p['lon'], p['dt'].isoformat() if p['dt'] else "", "OK"))
        for s in skipped:
            rows.append(("", s, "", "", "", "NO_GPS"))
        with open(csv_path, "w", newline="", encoding="utf-8") as cf:
            w = csv.writer(cf)
            w.writerow(("kname", "source_path", "lat", "lon", "datetime", "status"))
            for r in rows:
                w.writerow(r)
        print("KMZ created:", out_kmz)
        print("CSV report:", csv_path)
        if skipped:
            print("Copied", len(skipped), "non-GPS images to:", no_gps_dir)
    finally:
        shutil.rmtree(tmp)
if __name__ == "__main__":
    main()
