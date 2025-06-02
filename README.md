# GPS Media Reviewer

A web application for reviewing and updating GPS metadata in your media files (images) using a CSV file and an interactive map interface.

---

## Features

- **Upload CSV**: Import a CSV file listing your media files and their metadata.
- **Media Folder Selection**: Specify the folder containing your images.
- **EXIF GPS Extraction**: Automatically reads GPS data from image EXIF metadata.
- **Proxy GPS Suggestions**: Supports reviewing proxy/suggested GPS coordinates for images without original GPS.
- **Interactive Map**: Review and update GPS coordinates visually using a map (Leaflet/OpenStreetMap).
- **Address Search**: Search for locations by address and update coordinates via geocoding.
- **Bulk Save**: Save all changes to both the images' EXIF metadata and the CSV file.
- **Progress Feedback**: See progress and results of bulk save operations.
- **Flash Messages**: Get feedback for actions and errors.
- **Backups**: Automatically creates backups of your original CSV and image files before making changes.
- **CSV Tools**: Includes scripts for finding images without GPS and for updating GPS in bulk from CSV.

---

## How It Works

1. **Upload a CSV file** containing at least a `path` column (relative path to each image) and optionally `datetime` and `gps_source` columns.
2. **Specify your media folder** (where the images are stored).
3. **Review each image**: See the image, its current GPS data, and update the location using the map or address search.
4. **Save changes**: Write updated GPS data back to the images and the CSV.

---

## CSV Format

The CSV should have at least the following columns:

- `path`: Relative path to the image file (from the specified media folder)
- `datetime`: (Optional) Date/time of the image
- `latitude`, `longitude`: (Optional) Coordinates to suggest or update
- `gps_source`: (Optional) Source of the GPS data (e.g., 'manual', 'proxy', etc.)

Example:

```csv
path,datetime,latitude,longitude,gps_source
IMG_001.jpg,2024-05-01T12:00:00+00:00,52.5200,13.4050,proxy
IMG_002.jpg,2024-05-01T12:05:00+00:00,,,manual
```

---

## Installation

1. **Clone the repository**
2. **Install dependencies** (see below)
3. **Run the app**

```bash
pip install -r requirements.txt
python app.py
```

The app will be available at [http://localhost:5000](http://localhost:5000)

---

## Requirements

- Python 3.7+
- Flask
- Werkzeug
- Pillow
- piexif
- geopy

Install all dependencies with:

```bash
pip install -r requirements.txt
```

---

## Usage

1. Open the app in your browser.
2. Upload your CSV and specify the media folder.
3. Review and update GPS data for each image using the map or address search.
4. Save all changes when done.

---

## Included Tools

- **find_no_gps_media.py**: Scan a directory for images without GPS metadata and export a CSV.
- **update_media_gps.py**: Bulk update GPS metadata for images/videos in a directory using a place name.
- **update_media_gps-csv.py**: Extract or update GPS metadata for media files based on a CSV.

---

## Notes

- The app creates backups of your original CSV and image files before making changes.
- Only images with supported formats (`jpg`, `jpeg`, `png`) are processed.
- The map uses OpenStreetMap and Leaflet for interactive location selection.
- Address search uses OpenStreetMap Nominatim geocoding.
- The web interface only shows entries with proxy GPS suggestions for review.

---

## License

MIT License
