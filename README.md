# GPS Media Reviewer

A web application for reviewing and updating GPS metadata in your media files (images) using a CSV file and an interactive map interface.

## Features

- **Upload CSV**: Import a CSV file listing your media files and their metadata.
- **Media Folder Selection**: Specify the folder containing your images.
- **EXIF GPS Extraction**: Automatically reads GPS data from image EXIF metadata.
- **Interactive Map**: Review and update GPS coordinates visually using a map (Leaflet/OpenStreetMap).
- **Address Search**: Search for locations by address and update coordinates via geocoding.
- **Bulk Save**: Save all changes to both the images' EXIF metadata and the CSV file.
- **Progress Feedback**: See progress and results of bulk save operations.

## How It Works

1. **Upload a CSV file** containing at least a `path` column (relative path to each image) and optionally `datetime` and `gps_source` columns.
2. **Specify your media folder** (where the images are stored).
3. **Review each image**: See the image, its current GPS data, and update the location using the map or address search.
4. **Save changes**: Write updated GPS data back to the images and the CSV.

## CSV Format

The CSV should have at least the following columns:

- `path`: Relative path to the image file (from the specified media folder)
- `datetime`: (Optional) Date/time of the image
- `gps_source`: (Optional) Source of the GPS data (e.g., 'manual', 'proxy', etc.)

Example:

```csv
path,datetime,gps_source
IMG_001.jpg,2024-05-01 12:00:00,proxy
IMG_002.jpg,2024-05-01 12:05:00,manual
```

## Installation

1. **Clone the repository**
2. **Install dependencies** (see below)
3. **Run the app**

```bash
pip install -r requirements.txt
python app.py
```

The app will be available at http://localhost:5000

## Requirements

- Python 3.7+
- Flask
- Pillow
- piexif
- geopy

Install all dependencies with:

```bash
pip install -r requirements.txt
```

## Usage

1. Open the app in your browser.
2. Upload your CSV and specify the media folder.
3. Review and update GPS data for each image.
4. Save all changes when done.

## Notes

- The app creates backups of your original CSV and image files before making changes.
- Only images with supported formats (`jpg`, `jpeg`, `png`) are processed.
- The map uses OpenStreetMap and Leaflet for interactive location selection.
- Address search uses OpenStreetMap Nominatim geocoding.

## License

MIT License
