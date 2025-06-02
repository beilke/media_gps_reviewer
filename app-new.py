import os
import csv
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from PIL import Image, JpegImagePlugin
from PIL.ExifTags import TAGS, GPSTAGS
import piexif
import shutil
import exifread
import pytz
from werkzeug.utils import secure_filename
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# Initialize Flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'jpg', 'jpeg', 'png', 'csv'}
app.secret_key = 'your-secret-key-here'  # Needed for flash messages

# Debug setup
print("Initializing application...")
print(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
print(f"Upload folder exists: {os.path.exists(app.config['UPLOAD_FOLDER'])}")
print(f"Upload folder writable: {os.access(app.config['UPLOAD_FOLDER'], os.W_OK)}")

# Global reviewer instance
reviewer = None

# ==============================================
# Utility Functions
# ==============================================

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def validate_coordinates(lat, lon):
    """Validate latitude and longitude values"""
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise ValueError(f"Invalid coordinates: lat={lat}, lon={lon}")
    return True

def rational_to_decimal(ratio):
    """Convert a rational (tuple or IFDRational) to a decimal number."""
    try:
        if hasattr(ratio, 'numerator') and hasattr(ratio, 'denominator'):
            return ratio.numerator / ratio.denominator
        elif isinstance(ratio, tuple) and len(ratio) == 2:
            return ratio[0] / ratio[1]
        return float(ratio)
    except Exception as e:
        print(f"Failed to convert ratio {ratio} to decimal: {e}")
        return None

def decimal_to_dms(decimal):
    """Convert decimal degrees to EXIF-friendly degrees, minutes, seconds format."""
    degrees = int(decimal)
    remainder = abs(decimal - degrees) * 60
    minutes = int(remainder)
    seconds = (remainder - minutes) * 60
    return ((degrees, 1), (minutes, 1), (int(seconds * 1000), 1000))

def dms_to_decimal(dms, ref):
    """Convert GPS coordinates in degrees/minutes/seconds to decimal format."""
    try:
        # Handle case where dms is already converted to decimal
        if isinstance(dms, (int, float)):
            return -dms if ref in ['S', 'W'] else dms
            
        # Original handling for DMS tuples
        degrees = dms[0] if isinstance(dms[0], (int, float)) else dms[0][0] / dms[0][1]
        minutes = dms[1] if isinstance(dms[1], (int, float)) else dms[1][0] / dms[1][1]
        seconds = dms[2] if isinstance(dms[2], (int, float)) else dms[2][0] / dms[2][1]
        
        decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
        if ref in ['S', 'W']:
            decimal = -decimal
        return decimal
    except Exception as e:
        print(f"Error converting DMS to decimal: {e}")
        return None

def _clean_exif_dict(exif_dict):
    """Clean problematic tags from EXIF dictionary"""
    if "Exif" in exif_dict and 41729 in exif_dict["Exif"]:
        del exif_dict["Exif"][41729]
    return exif_dict

# ==============================================
# GPS and EXIF Related Functions
# ==============================================

def get_media_datetime(file_path):
    """Get datetime from media file using EXIF"""
    try:
        with open(file_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            if 'EXIF DateTimeOriginal' in tags:
                dt_str = str(tags['EXIF DateTimeOriginal'])
                return datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S').replace(tzinfo=pytz.UTC)
    except Exception:
        pass
    return None

def get_media_gps(file_path):
    """Get GPS coordinates from media file using EXIF"""
    try:
        with open(file_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
                lat = tags['GPS GPSLatitude']
                lon = tags['GPS GPSLongitude']
                lat_ref = tags['GPS GPSLatitudeRef']
                lon_ref = tags['GPS GPSLongitudeRef']
                lat = float(lat.values[0]) + float(lat.values[1])/60 + float(lat.values[2])/3600
                lon = float(lon.values[0]) + float(lon.values[1])/60 + float(lon.values[2])/3600
                if str(lat_ref) == 'S':
                    lat = -lat
                if str(lon_ref) == 'W':
                    lon = -lon
                return (lat, lon)
    except Exception:
        pass
    return None

def get_exif_data(image_path):
    """Extract EXIF data from an image file."""
    try:
        image = Image.open(image_path)
        exif_data = image._getexif()
        
        if exif_data is None:
            return None
        
        exif_info = {}
        gps_data = {}
        
        for tag, value in exif_data.items():
            tag_name = TAGS.get(tag, tag)
            
            if tag_name == 'GPSInfo' and isinstance(value, dict):
                for gps_tag, gps_value in value.items():
                    gps_tag_name = GPSTAGS.get(gps_tag, gps_tag)
                    
                    # Handle IFDRational objects
                    if hasattr(gps_value, 'numerator') and hasattr(gps_value, 'denominator'):
                        gps_data[gps_tag_name] = rational_to_decimal(gps_value)
                    elif isinstance(gps_value, tuple):
                        # Handle tuples of IFDRational objects
                        gps_data[gps_tag_name] = tuple(
                            rational_to_decimal(v) if hasattr(v, 'numerator') else v
                            for v in gps_value
                        )
                    else:
                        gps_data[gps_tag_name] = gps_value
                
                # Convert to decimal using ref
                if 'GPSLatitude' in gps_data and 'GPSLatitudeRef' in gps_data:
                    gps_data['GPSLatitude'] = dms_to_decimal(
                        gps_data['GPSLatitude'], 
                        gps_data['GPSLatitudeRef']
                    )
                if 'GPSLongitude' in gps_data and 'GPSLongitudeRef' in gps_data:
                    gps_data['GPSLongitude'] = dms_to_decimal(
                        gps_data['GPSLongitude'], 
                        gps_data['GPSLongitudeRef']
                    )

                if gps_data:
                    exif_info['GPSInfo'] = gps_data
            else:
                exif_info[tag_name] = value
        
        if 'GPSInfo' not in exif_info or not exif_info['GPSInfo']:
            return None
        
        return exif_info
    except Exception as e:
        print(f"Error extracting EXIF data: {e}")
        return None

def update_image_gps(image_path, lat, lon):
    """Update GPS metadata for images using piexif."""
    try:
        print(f"\nProcessing image: {image_path}")
        
        try:
            exif_dict = piexif.load(image_path)
        except Exception as e:
            print(f"Creating new EXIF data: {str(e)}")
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
        
        # Clean problematic tags
        exif_dict = _clean_exif_dict(exif_dict)
        
        # Create GPS metadata
        gps_ifd = {
            piexif.GPSIFD.GPSLatitudeRef: 'N' if lat >= 0 else 'S',
            piexif.GPSIFD.GPSLatitude: decimal_to_dms(abs(lat)),
            piexif.GPSIFD.GPSLongitudeRef: 'E' if lon >= 0 else 'W',
            piexif.GPSIFD.GPSLongitude: decimal_to_dms(abs(lon)),
        }
        
        exif_dict["GPS"] = gps_ifd
        
        # Save with new EXIF
        piexif.insert(piexif.dump(exif_dict), image_path)
        print(f"Successfully updated GPS for image")
        return True
            
    except Exception as e:
        print(f"Failed to update image: {str(e)}")
        return False

def geocode_address(address):
    """Convert address to GPS coordinates using Nominatim"""
    geolocator = Nominatim(user_agent="gps_review_app")
    try:
        location = geolocator.geocode(address)
        if location:
            return {'latitude': location.latitude, 'longitude': location.longitude}
        return None
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        print(f"Geocoding error: {e}")
        return None

# ==============================================
# Directory Scanning Functions
# ==============================================

def scan_directory_for_media(directory):
    """Scan directory for media files (JPEGs) and collect their metadata"""
    media_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg')):
                file_path = os.path.join(root, file)
                dt = get_media_datetime(file_path)
                gps = get_media_gps(file_path)
                media_files.append({
                    'path': file_path,
                    'datetime': dt,
                    'gps': gps
                })
    return media_files

def find_closest_gps(media_files, target_file, time_window_hours=1):
    """Find closest GPS coordinates within a time window"""
    target_dt = target_file['datetime']
    if not target_dt:
        return None
    time_window = timedelta(hours=time_window_hours)
    closest_gps = None
    min_time_diff = None
    for media in media_files:
        if media['gps'] and media['datetime']:
            time_diff = abs((target_dt - media['datetime']).total_seconds())
            if time_diff <= time_window.total_seconds():
                if min_time_diff is None or time_diff < min_time_diff:
                    min_time_diff = time_diff
                    closest_gps = media['gps']
    return closest_gps

def scan_directory_with_closest(directory, time_frame=1):
    """Scan directory and find closest GPS for files without GPS"""
    media_files = scan_directory_for_media(directory)
    gps_files = [m for m in media_files if m['gps'] is not None]
    
    for media in media_files:
        if media['gps'] is None and media['datetime'] is not None:
            media['gps'] = find_closest_gps(gps_files, media, time_frame)

    entries = []
    for m in media_files:
        orig_gps = get_media_gps(m['path'])
        # Only include images that truly lack GPS (None or (0.0, 0.0))
        if not orig_gps or orig_gps == (0.0, 0.0):
            # If a proxy GPS was found, fill it; otherwise, leave blank
            lat = ''
            lon = ''
            gps_source = 'none'
            if m['gps'] and m['gps'] != (0.0, 0.0):
                lat = m['gps'][0]
                lon = m['gps'][1]
                gps_source = 'proxy'
            entry = {
                'path': os.path.relpath(m['path'], directory),
                'datetime': m['datetime'].isoformat() if m['datetime'] else '',
                'latitude': lat,
                'longitude': lon,
                'gps_source': gps_source
            }
            entries.append(entry)
    return entries

def scan_directory_for_jpgs_without_gps_entries(root_dir):
    """Scan directory for JPEGs without GPS data"""
    def get_exif_data(image_path):
        try:
            with Image.open(image_path) as img:
                exif_data = img._getexif()
                if exif_data is not None:
                    return {TAGS.get(tag, tag): value for tag, value in exif_data.items()}
        except (AttributeError, IOError, KeyError, IndexError):
            pass
        return None

    def has_gps_data(exif_data):
        if exif_data is None:
            return False
        return 'GPSInfo' in exif_data

    def format_datetime(exif_data):
        if exif_data is None:
            return None
        datetime_tags = ['DateTimeOriginal', 'DateTimeDigitized', 'DateTime']
        for tag in datetime_tags:
            if tag in exif_data:
                dt_str = exif_data[tag]
                try:
                    dt = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
                    return dt.isoformat() + '+00:00'
                except ValueError:
                    pass
        return None

    entries = []
    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg')):
                file_path = os.path.join(root, file)
                exif_data = get_exif_data(file_path)
                if not has_gps_data(exif_data):
                    dt = format_datetime(exif_data)
                    rel_path = os.path.relpath(file_path, root_dir)
                    entries.append({
                        'path': rel_path,
                        'datetime': dt or '',
                        'latitude': '',
                        'longitude': '',
                        'gps_source': 'scan'
                    })
    return entries

# ==============================================
# GPS Reviewer Class
# ==============================================

class GPSReviewer:
    def __init__(self, csv_path, media_folder):
        self.csv_path = csv_path
        self.media_folder = media_folder
        self.entries = []
        self.current_index = 0
        self.changes_made = 0
        self.load_data()

    def load_data(self):
        """Load data from CSV with path and datetime columns"""
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            self.entries = []
            for row in reader:
                # Create a standardized entry format
                entry = {
                    'path': row.get('path', ''),
                    'datetime': row.get('datetime', ''),
                    'latitude': '',  # Will be populated from EXIF or manually
                    'longitude': '', # Will be populated from EXIF or manually
                    'gps_source': 'manual'  # Default source
                }
                
                # Try to get GPS from image EXIF
                image_path = os.path.join(self.media_folder, entry['path'])
                if os.path.exists(image_path):
                    exif_info = get_exif_data(image_path)
                    if exif_info and 'GPSInfo' in exif_info:
                        gps_info = exif_info['GPSInfo']
                        if 'GPSLatitude' in gps_info and 'GPSLongitude' in gps_info:
                            entry['latitude'] = str(gps_info['GPSLatitude'])
                            entry['longitude'] = str(gps_info['GPSLongitude'])
                            entry['gps_source'] = 'exif'
                
                self.entries.append(entry)
            
            print(f"Loaded {len(self.entries)} entries from CSV")

    def save_all(self):
        """Save all changes to both CSV and image files"""
        print("Starting bulk save operation...")
        
        # Track success/failure
        results = {
            'total': len(self.entries),
            'success': 0,
            'failed': 0,
            'failed_paths': []
        }
        
        try:
            # Create backup of CSV
            backup_path = self.csv_path + '.bak'
            if not os.path.exists(backup_path):
                shutil.copy2(self.csv_path, backup_path)
            
            # Process each entry
            for i, entry in enumerate(self.entries):
                try:
                    file_path = os.path.join(self.media_folder, entry['path'])
                    
                    # Only update if coordinates exist
                    if entry['latitude'] and entry['longitude']:
                        # Create image backup
                        img_backup = file_path + '.bak'
                        if not os.path.exists(img_backup):
                            shutil.copy2(file_path, img_backup)
                        
                        # Update image GPS
                        lat = float(entry['latitude'])
                        lon = float(entry['longitude'])
                        if update_image_gps(file_path, lat, lon):
                            results['success'] += 1
                        else:
                            results['failed'] += 1
                            results['failed_paths'].append(entry['path'])
                    else:
                        results['success'] += 1  # No GPS to update
                        
                except Exception as e:
                    print(f"Error processing {entry['path']}: {str(e)}")
                    results['failed'] += 1
                    results['failed_paths'].append(entry['path'])
            
            # Save updated CSV (only path and datetime columns)
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['path', 'datetime']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for entry in self.entries:
                    writer.writerow({
                        'path': entry['path'],
                        'datetime': entry['datetime']
                    })
                
            print(f"Bulk save completed. Success: {results['success']}, Failed: {results['failed']}")
            return results
            
        except Exception as e:
            print(f"Critical error during bulk save: {str(e)}")
            # Restore from backup if available
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, self.csv_path)
            return {
                'success': 0,
                'failed': results['total'],
                'failed_paths': [e['path'] for e in self.entries],
                'error': str(e)
            }

    def get_current_entry(self):
        """Get current entry data"""
        if 0 <= self.current_index < len(self.entries):
            return self.entries[self.current_index]
        return None

    def update_gps(self, lat, lon):
        """Update GPS data for current image"""
        try:
            validate_coordinates(float(lat), float(lon))
        except ValueError as e:
            print(f"Invalid coordinates: {e}")
            return False
            
        entry = self.get_current_entry()
        if not entry:
            return False
        
        file_path = os.path.join(self.media_folder, entry['path'])
        if not os.path.exists(file_path):
            return False
        
        try:
            # Create backup
            backup_path = file_path + '.bak'
            if not os.path.exists(backup_path):
                shutil.copy2(file_path, backup_path)
            
            # Update GPS in image
            if update_image_gps(file_path, float(lat), float(lon)):
                entry['latitude'] = lat
                entry['longitude'] = lon
                entry['gps_source'] = 'manual'
                self.changes_made += 1
                return True
        except Exception as e:
            print(f"Error updating GPS: {e}")
            return False

# ==============================================
# Flask Routes
# ==============================================

@app.route('/', methods=['GET', 'POST'])
def index():
    global reviewer
    print(f"Index route called, method: {request.method}")
    
    if request.method == 'POST':
        print("POST request received")
        print(f"Form data: {request.form}")
        print(f"Files: {request.files}")
        
        if 'csv_file' not in request.files:
            flash('No CSV file selected')
            return redirect(request.url)
            
        csv_file = request.files['csv_file']
        media_folder = request.form.get('media_folder', '').strip()
        
        if not media_folder:
            flash('Media folder path is required')
            return redirect(request.url)
            
        if not os.path.exists(media_folder):
            flash('Media folder does not exist')
            return redirect(request.url)
            
        if csv_file.filename == '':
            flash('No selected CSV file')
            return redirect(request.url)
            
        if csv_file and allowed_file(csv_file.filename):
            filename = secure_filename(csv_file.filename)
            csv_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            try:
                csv_file.save(csv_path)
                print(f"CSV saved to: {csv_path}")
                reviewer = GPSReviewer(csv_path, media_folder)
                
                if not reviewer.entries:
                    flash('CSV file is empty or invalid')
                    return redirect(request.url)
                    
                return redirect(url_for('review'))
            except Exception as e:
                print(f"Error saving file: {e}")
                flash('Error processing CSV file')
                return redirect(request.url)
    
    return render_template('index.html')

@app.route('/review', methods=['GET', 'POST'])
def review():
    global reviewer

    if not reviewer or not reviewer.entries:
        flash('No entries found to review', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update':
            lat = request.form.get('latitude')
            lon = request.form.get('longitude')
            if lat and lon:
                try:
                    if reviewer.update_gps(lat, lon):
                        flash('GPS coordinates updated successfully!', 'success')
                        # Move to next entry after successful update
                        reviewer.current_index = min(reviewer.current_index + 1, len(reviewer.entries) - 1)
                    else:
                        flash('Failed to update GPS coordinates', 'danger')
                except ValueError as e:
                    flash(f'Invalid coordinates: {str(e)}', 'danger')
        
        elif action == 'next':
            reviewer.current_index = min(reviewer.current_index + 1, len(reviewer.entries) - 1)
        
        elif action == 'prev':
            reviewer.current_index = max(reviewer.current_index - 1, 0)
        
        elif action == 'save':
            try:
                results = reviewer.save_all()
                flash(f'Saved {results["success"]} of {results["total"]} files successfully!', 'success')
                if results['failed'] > 0:
                    flash(f'Failed to save {results["failed"]} files', 'warning')
            except Exception as e:
                flash(f'Error saving changes: {str(e)}', 'danger')
            
            return redirect(url_for('review'))
    
    # Get current entry
    entry = reviewer.get_current_entry()
    if not entry:
        flash('No entries available to review', 'danger')
        return redirect(url_for('index'))
    
    # Prepare image path
    image_path = os.path.join(reviewer.media_folder, entry['path'])
    if not os.path.exists(image_path):
        flash(f'Image not found: {image_path}', 'danger')
        return redirect(url_for('index'))
    
    # Copy image to static folder for web display
    static_image_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(entry['path']))
    if not os.path.exists(static_image_path):
        try:
            shutil.copy2(image_path, static_image_path)
        except Exception as e:
            flash(f'Error preparing image for display: {str(e)}', 'warning')
    
    # Extract EXIF info
    exif_info = get_exif_data(image_path) or {}

    # Prefer entry's latitude/longitude if present (proxy/manual), else use EXIF
    latitude = entry.get('latitude')
    longitude = entry.get('longitude')
    # If latitude/longitude are empty or None, try EXIF
    if not latitude or not longitude:
        gps_info = exif_info.get('GPSInfo', {})
        latitude = gps_info.get('GPSLatitude', '')
        longitude = gps_info.get('GPSLongitude', '')
        # Convert to decimal if needed
        if isinstance(latitude, tuple):
            latitude = rational_to_decimal(latitude)
        if isinstance(longitude, tuple):
            longitude = rational_to_decimal(longitude)
    # Otherwise, ensure they're strings for display
    else:
        latitude = str(latitude)
        longitude = str(longitude)

    # Update exif_info with processed values for display
    exif_info['GPSLatitude'] = latitude
    exif_info['GPSLongitude'] = longitude

    # Get date taken or use unknown
    date_taken = exif_info.get('DateTimeOriginal', 'Unknown')

    return render_template('review.html',
                         image_url=os.path.basename(static_image_path),
                         entry=entry,
                         current_index=reviewer.current_index + 1,
                         total_entries=len(reviewer.entries),
                         changes_made=reviewer.changes_made,
                         date_taken=date_taken,
                         latitude=latitude,
                         longitude=longitude,
                         file_location=os.path.abspath(image_path),
                         exif_info=exif_info)

@app.route('/scan_directory', methods=['POST'])
def scan_directory():
    global reviewer
    data = request.get_json()
    directory = data.get('directory')
    if not directory or not os.path.isdir(directory):
        return jsonify({'status': 'error', 'message': 'Invalid or missing directory'}), 400

    try:
        find_closest = data.get('find_closest', False)
        time_frame = data.get('time_frame', 1)
        if find_closest:
            entries = scan_directory_with_closest(directory, time_frame)
        else:
            entries = scan_directory_for_jpgs_without_gps_entries(directory)
        if not entries:
            return jsonify({'status': 'error', 'message': 'No images without GPS found.'}), 200
        
        # Create a dummy reviewer instance with these entries
        class DummyReviewer:
            def __init__(self, entries, media_folder):
                self.entries = entries
                self.media_folder = media_folder
                self.current_index = 0
                self.changes_made = 0

            def get_current_entry(self):
                if 0 <= self.current_index < len(self.entries):
                    return self.entries[self.current_index]
                return None

            def update_gps(self, lat, lon):
                try:
                    lat = float(lat)
                    lon = float(lon)
                    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                        return False
                except Exception:
                    return False
                entry = self.get_current_entry()
                if not entry:
                    return False
                entry['latitude'] = lat
                entry['longitude'] = lon
                entry['gps_source'] = 'manual'
                self.changes_made += 1
                return True

            def save_all(self):
                # For DummyReviewer, just return a summary (no file writes)
                return {
                    'success': self.changes_made,
                    'failed': 0,
                    'total': len(self.entries),
                    'failed_paths': [],
                    'current_index': self.current_index,
                    'total_entries': len(self.entries)
                }
                
        reviewer = DummyReviewer(entries, directory)
        return jsonify({'status': 'success', 'redirect': url_for('review')}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/save_all', methods=['POST'])
def save_all():
    global reviewer
    if not reviewer:
        return jsonify({'status': 'error', 'message': 'No reviewer initialized'})

    try:
        results = reviewer.save_all()
        changes_made = results['success']  # Assuming 'success' represents the number of changes made
        current_index = results['current_index']  # The index of the current image being saved
        total_entries = results['total_entries']  # The total number of images to save

        print(f"[DEBUG] Saved {results['success']} / {results['total']} entries.")
        return jsonify({
            'status': 'success',
            'message': f"Saved {results['success']} of {results['total']} entries.",
            'changes_made': changes_made,
            'current_index': current_index,
            'total_entries': total_entries,
            'details': results
        })
    except Exception as e:
        print(f"[ERROR] Save failed: {e}")
        return jsonify({
            'status': 'error',
            'message': f"Save failed: {str(e)}"
        })

@app.route('/geocode', methods=['POST'])
def geocode():
    address = request.json.get('address')
    if not address:
        return jsonify({'error': 'Address is required'}), 400
    
    result = geocode_address(address)
    if result:
        return jsonify(result)
    return jsonify({'error': 'Address not found'}), 404

@app.route('/download_csv/<filename>')
def download_csv(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# ==============================================
# Main Application
# ==============================================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)