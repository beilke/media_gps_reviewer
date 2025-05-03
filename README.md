# GPS Metadata Reviewer Application

## Overview  
This Flask-based web application provides an interface for reviewing and updating GPS metadata in image files.  

## Features  

- **EXIF Data Extraction** - Reads GPS metadata from JPEG/PNG images  
- **GPS Coordinate Validation** - Ensures entered coordinates are valid  
- **Geocoding Support** - Converts addresses to GPS coordinates using Nominatim  
- **Bulk Processing** - Handles multiple images efficiently  
- **Automatic Backups** - Creates `.bak` files before modifications  
- **Responsive Interface** - Web-based review system  

## Requirements  

```plaintext
Python 3.7+
Flask
Pillow (PIL)
piexif
geopy
werkzeug

Installation
Clone the repository:

bash
git clone https://github.com/yourusername/gps-reviewer.git
cd gps-reviewer
Install dependencies:

bash
pip install -r requirements.txt
Set up uploads folder:

bash
mkdir -p static/uploads
Usage
Starting the Application
bash
python app.py
Access at: http://localhost:5000

Workflow
Homepage

Upload CSV file with image paths

Specify media folder location

Review Interface

View images with current GPS data

Navigate with Previous/Next buttons

Update coordinates manually or via geocoding

Saving Changes

Save individual updates

Or bulk save all modifications

CSV Format
Required columns:

Column	Description	Example
path	Relative image path	photos/img1.jpg
datetime	Capture timestamp (optional)	2023-01-01 12:00
Configuration
Edit in app.py:

python
app.config['UPLOAD_FOLDER'] = 'static/uploads'  # File storage
app.config['ALLOWED_EXTENSIONS'] = {'jpg', 'jpeg', 'png', 'csv'}  # Supported files
app.secret_key = 'your-secret-key-here'  # For session security
API Endpoints
Endpoint	Method	Description
/	GET	Main application interface
/review	GET	Image review dashboard
/save_all	POST	Bulk save all GPS updates
/geocode	POST	Convert address → coordinates (JSON)
Troubleshooting
Common Issues:

Upload folder not writable

bash
chmod 755 static/uploads
No EXIF data found
Verify images contain metadata with:

bash
exiftool sample.jpg
Geocoding failures
Check Nominatim service status

License
MIT License - See LICENSE file

Contributing
Fork the repository

Create a feature branch

Submit a pull request

Note: Screenshot image should be placed in static/ folder


Key formatting elements preserved:
- Consistent 2-space indentation for code blocks
- Proper table formatting with alignment
- Horizontal rules (`---`) for section separation
- Backtick-enclosed code snippets
- Ordered/unordered list spacing
- Header hierarchy with `#`, `##`, `###`

The markdown will render correctly on:
- GitHub/GitLab/Bitbucket
- VS Code markdown preview
- Most documentation systems
