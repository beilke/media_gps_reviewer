# GPS Media Reviewer

A web application for reviewing and updating GPS metadata in your media files (images) using a CSV file and an interactive map interface.

---

## Features

- **Two Input Modes**: 
  - **Directory Scan**: Scan a directory for images with or without GPS metadata
  - **CSV Upload**: Import a CSV file listing your media files and their metadata
- **EXIF GPS Extraction**: Automatically reads GPS data from image EXIF metadata
- **Proxy GPS Suggestions**: Automatically finds and suggests GPS coordinates from other images taken at similar times
- **Interactive Map**: Review and update GPS coordinates visually using a map (Leaflet/OpenStreetMap)
- **Heatmap Visualization**: View an interactive heatmap of all GPS coordinates in your dataset to identify location clusters and geographic distribution
- **Address Search**: Search for locations by address and update coordinates via geocoding
- **Bulk Save**: Save all changes to both the images' EXIF metadata and the CSV file
- **Smart "Save All" Button**: Only appears when proxy GPS values are assigned and need review
- **Progress Feedback**: See progress and results of bulk save operations
- **Flash Messages**: Get feedback for actions and errors
- **Backups**: Automatically creates backups of your original CSV and image files before making changes
- **CSV Tools**: Includes scripts for finding images without GPS and for updating GPS in bulk from CSV

---

## How It Works

### Directory Scan Workflow
1. **Select "Scan Directory" mode** on the homepage.
2. **Enter the full path to your images directory** or click the **Browse** button to:
   - Enter a path manually in the directory selector
   - Select from common directory locations
   - (Note: This is a path selector, not a file uploader - it helps specify where your images are located)
3. (Optional) Check "Also show images that already have GPS" to include all images.
4. (Optional) Check "Find closest GPS metadata" to assign proxy GPS coordinates from similar timestamped images.
5. **Review each image**: See the image, its metadata, and update the location using the map or address search.
6. **Save changes**: Update individual images as you go, or use the "Save All Changes" button (visible only when proxy GPS values are assigned).

### CSV Upload Workflow
1. **Select "Upload CSV" mode** and upload a CSV file containing at least a `path` column (full path to each image).
2. **Review each image**: See the image, its metadata, and confirm or update the suggested GPS using the map or address search.
3. **Save changes**: Update individual images as you go, or use the "Save All Changes" button to update all at once.

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

## Heatmap Visualization

The application includes a powerful GPS heatmap visualization feature that allows you to:

- **View the geographic distribution** of all your media files on an interactive map
- **Identify location clusters** where most of your photos were taken
- **Detect outliers** or isolated locations in your dataset
- **Visualize density patterns** to understand your photography habits

To use the heatmap feature:

1. After loading your data (via directory scan or CSV upload), click the "**Show Heatmap**" button in the top-right corner of the review page
2. The heatmap modal will display all your GPS coordinates as a heat layer on the map
3. Zoom in/out to explore different density levels and areas
4. Use the fullscreen option for a larger view

This feature is especially useful for:
- Travel photographers analyzing their coverage of a location
- Event photographers confirming spatial distribution of shots
- Location scouts reviewing potential photography sites
- Anyone wanting to visualize their photo collection's geographic spread

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
- The "Save All Changes" button is intelligently shown only when:
  - Using the CSV upload mode, OR
  - Using directory scan mode with "Find closest GPS" option enabled
  - AND in both cases, only when proxy GPS values are available for review
- The interface color-codes proxy GPS values with a yellow background to indicate they are suggestions.
- Proxy GPS coordinates are assigned from other images taken within the specified time window (defaults to 1 hour).
- The heatmap visualization uses Leaflet.heat plugin to display location density and is available on the review page.
- The heatmap includes all images with GPS coordinates, including those from EXIF metadata and those with assigned proxy values.

---

## License

MIT License
