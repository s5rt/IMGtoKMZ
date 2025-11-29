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
def make_kml(placemarks, doc_name, include_tour):
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    hdr = f'<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">\n  <Document>\n    <name>{escape(doc_name)}</name>\n    <open>1</open>\n'
    body = ""
    for p in placemarks:
        name = escape(p['kname'])
        img_src = p.get('kimg',"files/"+os.path.basename(p['srcpath']))
        coords = f"{p['lon']},{p['lat']}"
        if p.get('alt') is not None:
            coords += f",{p['alt']}"
        placemark = f'\n    <Placemark>\n      <name>{name}</name>\n      <description><![CDATA[<img src="{img_src}" width="400"/>]]></description>\n      <Point><coordinates>{coords}</coordinates></Point>\n    </Placemark>\n'
        body += placemark
    tour = ""
    if include_tour:
        playlist = ""
        for p in sorted(placemarks, key=lambda x: x.get('dt') or datetime.utcfromtimestamp(0)):
            lat = p['lat']; lon = p['lon']; alt = p.get('alt') or 0
            duration = 3
            lookat = f"<LookAt><longitude>{lon}</longitude><latitude>{lat}</latitude><altitude>{alt}</altitude><heading>0</heading><tilt>45</tilt><range>200</range><altitudeMode>relativeToGround</altitudeMode></LookAt>"
            playlist += f'      <gx:FlyTo>\n        <gx:duration>{duration}</gx:duration>\n        {lookat}\n      </gx:FlyTo>\n'
        tour = f'\n    <gx:Tour>\n      <name>Photo Tour</name>\n      <gx:Playlist>\n{playlist}      </gx:Playlist>\n    </gx:Tour>\n'
    footer = "\n  </Document>\n</kml>\n"
    return hdr + body + tour + footer
def main():
    args = sys.argv
    if len(args) < 2:
        print("Usage: python3 create.py /path/to/images [output_name.kmz] [--tour]")
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
            skipped.append(candidate if candidate and os.path.exists(candidate) else src)
            continue
        try:
            lat = float(gpslat)
            lon = float(gpslon)
        except Exception:
            skipped.append(candidate if candidate and os.path.exists(candidate) else src)
            continue
        alt = item.get("GPSAltitude")
        alt_val = float(alt) if (alt is not None) else None
        dt = parse_dt(item.get("DateTimeOriginal"), candidate)
        items.append({"srcpath": src, "lon": lon, "lat": lat, "alt": alt_val, "dt": dt, "candidate": candidate})
    if not items and not skipped:
        print("No images found.")
        sys.exit(1)
    items.sort(key=lambda x: (x['dt'] is None, x['dt'] or datetime.utcfromtimestamp(0)))
    for idx, it in enumerate(items, start=1):
        it['kname'] = f"p{idx}"
    kml_items = list(reversed(items))
    tmp = tempfile.mkdtemp(prefix="kmz_")
    try:
        files_dir = os.path.join(tmp, "files")
        os.makedirs(files_dir, exist_ok=True)
        for p in items:
            candidate = p['candidate']
            dst = os.path.join(files_dir, os.path.basename(candidate))
            if not os.path.exists(candidate):
                print("Warning: could not find file to copy:", candidate)
                continue
            shutil.copy2(candidate, dst)
            p['kimg'] = "files/" + os.path.basename(candidate)
        kml_text = make_kml(kml_items, os.path.splitext(os.path.basename(out_kmz))[0], include_tour)
        kml_path = os.path.join(tmp, "doc.kml")
        with open(kml_path, "w", encoding="utf-8") as f:
            f.write(kml_text)
        out_dir = os.path.dirname(out_kmz) or "."
        os.makedirs(out_dir, exist_ok=True)
        no_gps_dir = os.path.join(out_dir, "no_gps")
        if skipped:
            os.makedirs(no_gps_dir, exist_ok=True)
            for s in skipped:
                try:
                    if os.path.exists(s):
                        shutil.copy2(s, os.path.join(no_gps_dir, os.path.basename(s)))
                except Exception:
                    pass
        with zipfile.ZipFile(out_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
            kmz.write(kml_path, arcname="doc.kml")
            for root, _, files in os.walk(files_dir):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, tmp)
                    kmz.write(full, arcname=rel)
        csv_path = os.path.join(out_dir, os.path.splitext(os.path.basename(out_kmz))[0] + "_report.csv")
        geojson_path = os.path.join(out_dir, os.path.splitext(os.path.basename(out_kmz))[0] + "_report.geojson")
        rows = []
        for p in items:
            rows.append((p['kname'], p['candidate'], p['lat'], p['lon'], p['dt'].isoformat() if p['dt'] else "", "OK"))
        for s in skipped:
            rows.append(("", s, "", "", "", "NO_GPS"))
        with open(csv_path, "w", newline="", encoding="utf-8") as cf:
            w = csv.writer(cf)
            w.writerow(("kname","source_path","lat","lon","datetime","status"))
            for r in rows:
                w.writerow(r)
        features = []
        for r in rows:
            kname, srcpath, lat, lon, dtstr, status = r
            props = {"kname": kname, "source_path": srcpath, "datetime": dtstr, "status": status}
            if lat != "" and lon != "":
                try:
                    latf = float(lat); lonf = float(lon)
                    geom = {"type":"Point","coordinates":[lonf, latf]}
                except Exception:
                    geom = None
            else:
                geom = None
            feat = {"type":"Feature","properties":props,"geometry":geom}
            features.append(feat)
        fc = {"type":"FeatureCollection","features":features}
        with open(geojson_path, "w", encoding="utf-8") as gf:
            json.dump(fc, gf, ensure_ascii=False, indent=2)
        print("KMZ created:", out_kmz)
        print("CSV report:", csv_path)
        print("GeoJSON report:", geojson_path)
        if skipped:
            print("Copied", len(skipped), "files without GPS to", no_gps_dir)
    finally:
        shutil.rmtree(tmp)
if __name__ == "__main__":
    main()