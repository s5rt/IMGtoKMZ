# Photo → KMZ Converter
```Left with some images at your gallery from the fieldwork which are not in your tracking application? Use this tool to land those images in the specific location – compare with the tagged points & tadaah! Complete your fieldwork with ease.```

- Converts a folder of photos (JPEG / PNG / HEIC) that contain GPS EXIF into a single KMZ file with one placemark per photo.
- Also copies files into useful folders and writes a CSV report for QA.
---
## What this script does
- Scans an input directory (recursively) for image files.
- **Accepts**: `.jpg`, `.jpeg`, `.png`, `.heic` (case-insensitive).
- **Converts HEIC → JPEG** using macOS `sips`, then copies EXIF metadata back to the JPEG using `exiftool`. Originals are not modified.
- Extracts GPS EXIF (`GPSLatitude`, `GPSLongitude`, optionally `GPSAltitude`) and `DateTimeOriginal` using `exiftool`.
- Creates a KMZ containing `doc.kml` and an internal `files/` folder with the images used.
- Copies:
  - images that **have** GPS into `files_geo/` (next to the output KMZ),
  - images that **do not** have GPS into `files_nongeo/`,
  - any **non-image or unsupported files** into `files_nonimg/`.
- Writes a CSV report: `<output_basename>_report.csv` with columns:
  - `slno` — sequence number (starts at 1; geotagged images first in chronological order),
  - `filename` — basename of the source file (HEICs are converted to JPEG first; CSV shows the converted filename),
  - `datetime` — DateTimeOriginal (ISO string when available; otherwise empty),
  - `lat` — latitude (decimal) or empty,
  - `long` — longitude (decimal) or empty,
  - `status` — `OK` / `NO_GPS` / `NON_IMAGE`.

---

## Requirements
- **macOS** (the script uses `sips` to convert HEIC → JPEG). On other platforms you can modify the conversion step (e.g., use `magick` / `ffmpeg`).
- `exiftool` must be installed and on `PATH`. Install with Homebrew:
    ```bash
  brew install exiftool
    ```
- Python 3.8+ (uses standard library only).
---
# Usage
```
# Basic
python3 create.py /path/to/photos/ kmz/photo-marks.kmz

# If output path omitted, creates `images.kmz` in current directory:
python3 create.py /path/to/photos/

# Example
python3 create.py ~/Pictures/my_batch/ kmz/photo-marks.kmz
```
After running you'll see:
- kmz/photo-marks.kmz
- kmz/photo-marks_report.csv
- files_geo/ (copied geotagged images)
- files_nongeo/ (copied non-geotagged images)
- files_nonimg/ (copied non-image / unsupported files)
> Open the resulting .kmz in Google Earth or Google Earth Pro.

# Notes & behavior details
- HEIC conversion: The script converts .heic files to JPEG into a temporary heicfix_ directory, copying the original EXIF tags to the converted file using exiftool -tagsFromFile. The converted JPEGs are the ones embedded in the KMZ and copied into the files_geo/ or files_nongeo/ folders.
- Original files: Originals are not modified.
- Supported files only: The script explicitly ignores files that do not have the allowed extensions and copies them to files_nonimg/.
- Ordering & naming:
  - Photos are sorted oldest → newest based on DateTimeOriginal (falls back to file modification time).
  - Each used photo is named p1, p2, ... in the KML. The KML placemarks are written reversed so newer placemarks appear above older ones in the Google Earth layer list
- Icon: Uses the donut icon http://maps.google.com/mapfiles/kml/shapes/donut.png for placemarks. If you prefer embedding the icon into the KMZ, edit the script to copy the icon into the KMZ and reference it as files/icon.png.

# CSV format example
| slno | filename | datetime | lat | long | status |
| -- | -- | -- | -- | -- | -- |
| 1|IMG_001.jpg|2023-05-01T12:34:56|12.345678|77.123456|OK |
| 2|IMG_002.jpg|2023-05-02T09:10:11|12.355678|77.133456|OK |
| 3|IMG_003.jpg|| | |NO_GPS |
| 4|video.mov|| | |NON_IMAGE |

# Troubleshooting
- If exiftool is not found: install via Homebrew and ensure brew's bin is in your PATH.
- If HEIC conversion fails: confirm sips works on your mac (sips -s format jpeg file.heic --out out.jpg) and that the HEIC file is not corrupted.
- If many images are missing GPS: check a sample image with:
    ```
  exiftool -gps* -DateTimeOriginal -G1 -s sample.jpg
    ```
- Very large KMZ: embedding many full-resolution images will produce a big KMZ. Consider generating thumbnails (script can be modified to create thumbnails instead of embedding originals).
# License & attribution
Use this script freely. Attribution appreciated but not required.

# Example quick checklist
- Install exiftool: ```brew install exiftool```
- Put all images in ```/path/to/photos/```
- Run: ```python3 create.py /path/to/photos/ kmz/photo-marks.kmz```
- Open ```kmz/photo-marks.kmz``` in ```Google Earth``` and inspect ```kmz/photo-marks_report.csv``` for QA.