# Picture GPS Reviewer

A web application for reviewing and updating GPS metadata in your media files (images) using a CSV file and an interactive map interface.

---

## Features

- **Two Input Modes**: 
  - **Directory Scan**: Scan a directory for media files (images, HEIC, videos) with or without GPS metadata
  - **CSV Upload**: Import a CSV file listing your media files and their metadata
- **Multi-Format Support**: 
  - **Images**: JPG, JPEG, PNG, TIFF
  - **HEIC/HEIF**: Apple's High Efficiency Image Format
  - **Videos**: MP4, MOV, AVI, MKV
- **EXIF GPS Extraction**: Automatically reads GPS data from media files' metadata
- **Proxy GPS Suggestions**: Automatically finds and suggests GPS coordinates from other media files taken at similar times
- **Interactive Map**: Review and update GPS coordinates visually using a map (Leaflet/OpenStreetMap)
- **Heatmap Visualization**: View an interactive heatmap of all GPS coordinates in your dataset to identify location clusters and geographic distribution
- **Address Search**: Search for locations by address and update coordinates via geocoding
- **Video Thumbnail Generation**: Automatically generates thumbnails for video files
- **HEIC Conversion**: On-the-fly HEIC to JPEG conversion for preview
- **Bulk Save**: Save all changes to both the media files' metadata and the CSV file
- **Smart "Save All" Button**: Only appears when proxy GPS values are assigned and need review
- **Progress Feedback**: See progress and results of bulk save operations
- **Flash Messages**: Get feedback for actions and errors
- **Backups**: Automatically creates backups of your original CSV and media files before making changes
- **CSV Tools**: Includes scripts for finding media files without GPS and for updating GPS in bulk from CSV
- **Windows Long Path Support**: Handles paths longer than 260 characters on Windows systems

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

## Docker Deployment

The application can be easily deployed using Docker, which ensures consistent behavior across different environments.

### Using Docker Compose (Recommended)

1. **Clone the repository**
2. **Build and start the containers** using the provided script:

```bash
./start.sh
```

Or manually with:

```bash
docker-compose up -d
```

This will:
- Build the Docker image for the application
- Start the container in detached mode
- Mount the data directories as volumes
- Expose the application on port 5000

3. **Access the application** at [http://localhost:5000](http://localhost:5000)

4. **Stop the containers** when done with the provided script:

```bash
./stop.sh
```

Or manually with:

```bash
docker-compose down
```

### Data Persistence

All your data is stored in the following directories, which are mounted as Docker volumes:

- `./data/csv`: CSV files containing image metadata
- `./data/log`: Log files for application activity
- `./data/photos`: Your photo directories

These directories are preserved between container restarts and even if you rebuild the container.

### Using Tools in Docker

To use the included tools like `find_aprox_gps_info.py` within the Docker container:

```bash
# Execute a command inside the running container
docker exec -it picture_gps_reviewer python /app/tools/find_aprox_gps_info.py '/app/data/photos/your-folder' --output output.csv
```

#### Path Conversion Tool

When working with Docker, Windows file paths need to be converted to Docker-compatible paths. Use the included path converter tool:

```bash
# Convert a Windows path to Docker path
python tools/fix_file_paths.py "Z:\docker\projects\gps_reviewer\data\photos\your-folder"

# Convert paths in a CSV file
python tools/fix_file_paths.py "Z:\docker\projects\gps_reviewer\data\csv\your-file.csv"

# Check if a video file can be processed by ffmpeg
python tools/fix_file_paths.py "Z:\docker\projects\gps_reviewer\data\photos\videos\your-video.mp4" --check-video
```

This tool will:
- Output the Docker-compatible path
- Suggest the appropriate command to run inside the container
- Check if video files are accessible by ffmpeg when using the --check-video option
- Help identify issues with file paths, spaces, or special characters

### Manual Docker Build

If you prefer not to use Docker Compose, you can build and run the container manually:

```bash
# Build the Docker image
docker build -t picture-gps-reviewer .

# Run the container
docker run -d -p 5000:5000 \
  -v "$(pwd)/data/csv:/app/data/csv" \
  -v "$(pwd)/data/log:/app/data/log" \
  -v "$(pwd)/data/photos:/app/data/photos" \
  --name picture_gps_reviewer \
  picture-gps-reviewer
```

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
- **Supported image formats**: 
  - Standard formats: `jpg`, `jpeg`, `png`, `tiff` 
  - Apple formats: `heic`, `heif` (requires pillow-heif)
- **Supported video formats**: `mp4`, `mov`, `avi`, `mkv` (requires ffmpeg)
- Video files show thumbnails in the review interface and provide a link to open the original video
- HEIC files are automatically converted to JPEG for preview
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
