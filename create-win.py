#!/usr/bin/env python3
# python create-win.py ./photos/ ./kml/photo-marks.kmz
import json, os, shutil, subprocess, sys, tempfile, zipfile, csv
from datetime import datetime
from xml.sax.saxutils import escape
def convert_heic_to_jpeg(src, workdir):
    base = os.path.basename(src)
    out_jpg = os.path.join(workdir, os.path.splitext(base)[0] + ".jpg")
    try:
        r = subprocess.run(["magick", src, out_jpg], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr or "magick failed")
    except Exception:
        r2 = subprocess.run(["ffmpeg", "-y", "-i", src, out_jpg], capture_output=True, text=True)
        if r2.returncode != 0:
            raise RuntimeError("HEIC -> JPEG conversion failed. Install ImageMagick (magick) or ffmpeg.")
    subprocess.run(["exiftool", "-overwrite_original", "-tagsFromFile", src, out_jpg], capture_output=True)
    return out_jpg
def normalize_image(src, workdir):
    ext = os.path.splitext(src.lower())[1]
    if ext in (".heic", ".heif"):
        return convert_heic_to_jpeg(src, workdir)
    return src
def run_exiftool_json(image_dir):
    cmd = ["exiftool", "-json", "-n", "-FileName", "-SourceFile",
           "-GPSLatitude", "-GPSLongitude", "-GPSAltitude",
           "-DateTimeOriginal", "-r", image_dir]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "exiftool failed")
    return json.loads(proc.stdout)
def parse_dt(dt_str, src):
    if not dt_str:
        try:
            return datetime.utcfromtimestamp(os.path.getmtime(src))
        except Exception:
            return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y:%m:%d"):
        try:
            return datetime.strptime(dt_str, fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None
def make_kml(placemarks, doc_name):
    icon_url = "http://maps.google.com/mapfiles/kml/shapes/donut.png"
    hdr = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
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
        coords = f"{p['lon']},{p['lat']}"
        if p.get('alt') is not None:
            coords += f",{p['alt']}"
        body += f'''
    <Placemark>
      <name>{escape(p['kname'])}</name>
      <styleUrl>#customIcon</styleUrl>
      <description><![CDATA[<img src="{p['kimg']}" width="400"/>]]></description>
      <Point><coordinates>{coords}</coordinates></Point>
    </Placemark>
'''
    return hdr + body + "\n  </Document>\n</kml>\n"
def main():
    args = sys.argv
    if len(args) < 2:
        print("Usage: python3 create_windows.py IMAGEDIR [OUTPUT.kmz]")
        sys.exit(1)
    image_dir = args[1]
    out_kmz = args[2] if len(args) > 2 else "images.kmz"
    if not os.path.isdir(image_dir):
        print("Error: directory not found:", image_dir)
        sys.exit(1)
    allowed_exts = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
    convert_dir = tempfile.mkdtemp(prefix="heicfix_")
    tmp = tempfile.mkdtemp(prefix="kmz_")
    try:
        raw_list = run_exiftool_json(image_dir)
        items = []
        nongeo = []
        nonfiles = []
        for item in raw_list:
            src = item.get("SourceFile") or item.get("FileName")
            if not src:
                continue
            candidate = src if os.path.isabs(src) else os.path.join(image_dir, src)
            if not os.path.exists(candidate):
                candidate = os.path.join(image_dir, os.path.basename(src))
            ext = os.path.splitext(candidate.lower())[1]
            if ext not in allowed_exts:
                nonfiles.append(candidate)
                continue
            try:
                norm = normalize_image(candidate, convert_dir)
            except Exception as e:
                print("Warning: conversion failed for", candidate, "->", e)
                nonfiles.append(candidate)
                continue
            gpslat = item.get("GPSLatitude"); gpslon = item.get("GPSLongitude")
            dt = parse_dt(item.get("DateTimeOriginal"), norm)
            if gpslat is None or gpslon is None:
                nongeo.append({"src": norm, "dt": dt})
                continue
            try:
                lat = float(gpslat); lon = float(gpslon)
            except Exception:
                nongeo.append({"src": norm, "dt": dt})
                continue
            alt = item.get("GPSAltitude"); alt_val = float(alt) if alt is not None else None
            items.append({"src": norm, "lon": lon, "lat": lat, "alt": alt_val, "dt": dt})
        items.sort(key=lambda x: (x['dt'] is None, x['dt'] or datetime.utcfromtimestamp(0)))
        for i, p in enumerate(items, start=1):
            p['kname'] = f"p{i}"
        kml_items = list(reversed(items))
        out_dir = os.path.dirname(out_kmz) or "."
        os.makedirs(out_dir, exist_ok=True)
        files_geo_dir = os.path.join(out_dir, "files_geo")
        files_nongeo_dir = os.path.join(out_dir, "files_nongeo")
        files_nonimg_dir = os.path.join(out_dir, "files_nonimg")
        os.makedirs(files_geo_dir, exist_ok=True)
        os.makedirs(files_nongeo_dir, exist_ok=True)
        os.makedirs(files_nonimg_dir, exist_ok=True)
        files_dir = os.path.join(tmp, "files")
        os.makedirs(files_dir, exist_ok=True)
        for p in items:
            dst = os.path.join(files_dir, os.path.basename(p['src']))
            shutil.copy2(p['src'], dst)
            p['kimg'] = "files/" + os.path.basename(p['src'])
            shutil.copy2(p['src'], os.path.join(files_geo_dir, os.path.basename(p['src'])))
        for ng in nongeo:
            srcpath = ng['src']
            try:
                shutil.copy2(srcpath, os.path.join(files_nongeo_dir, os.path.basename(srcpath)))
            except Exception:
                pass
        for nf in nonfiles:
            if os.path.exists(nf):
                try:
                    shutil.copy2(nf, os.path.join(files_nonimg_dir, os.path.basename(nf)))
                except Exception:
                    pass
        kml_text = make_kml(kml_items, os.path.splitext(os.path.basename(out_kmz))[0])
        kml_path = os.path.join(tmp, "doc.kml")
        with open(kml_path, "w", encoding="utf-8") as f:
            f.write(kml_text)
        with zipfile.ZipFile(out_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
            kmz.write(kml_path, arcname="doc.kml")
            for root, _, files in os.walk(files_dir):
                for fn in files:
                    full = os.path.join(root, fn)
                    kmz.write(full, arcname=os.path.relpath(full, tmp))
        csv_path = os.path.join(out_dir, os.path.splitext(os.path.basename(out_kmz))[0] + "_report.csv")
        rows = []
        sl = 1
        for p in items:
            dtstr = p['dt'].isoformat() if p['dt'] else ""
            rows.append((sl, os.path.basename(p['src']), dtstr, p['lat'], p['lon'], "OK"))
            sl += 1
        for ng in nongeo:
            dtstr = ng['dt'].isoformat() if ng['dt'] else ""
            rows.append((sl, os.path.basename(ng['src']), dtstr, "", "", "NO_GPS"))
            sl += 1
        for nf in nonfiles:
            rows.append((sl, os.path.basename(nf), "", "", "", "NON_IMAGE"))
            sl += 1
        with open(csv_path, "w", newline="", encoding="utf-8") as cf:
            w = csv.writer(cf)
            w.writerow(("slno", "filename", "datetime", "lat", "long", "status"))
            for r in rows:
                w.writerow(r)
        print("KMZ created:", out_kmz)
        print("CSV report:", csv_path)
        print("Files with geo (copied):", files_geo_dir)
        print("Files without geo (copied):", files_nongeo_dir)
        print("Non-image files (copied):", files_nonimg_dir)
    finally:
        try:
            shutil.rmtree(tmp)
        except Exception:
            pass
        try:
            shutil.rmtree(convert_dir)
        except Exception:
            pass
if __name__ == "__main__":
    main()