import os
import csv
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from PIL import Image
import piexif
import shutil
import exifread
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from PIL import JpegImagePlugin
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

import pytz
import subprocess

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'jpg', 'jpeg', 'png', 'csv'}
app.secret_key = 'your-secret-key-here'  # Needed for flash messages

# Debug setup
print("Initializing application...")
print(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
print(f"Upload folder exists: {os.path.exists(app.config['UPLOAD_FOLDER'])}")
print(f"Upload folder writable: {os.access(app.config['UPLOAD_FOLDER'], os.W_OK)}")

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

def _clean_exif_dict(exif_dict):
    """Clean problematic tags from EXIF dictionary"""
    if "Exif" in exif_dict and 41729 in exif_dict["Exif"]:
        del exif_dict["Exif"][41729]
    return exif_dict

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

# ==============================================
# Directory Scanning Functions
# ==============================================

def scan_directory_for_media(directory):
    """Scan directory for media files (JPEGs) and collect their metadata"""
    media_files = []
    print(f"[DEBUG] Scanning directory: {directory}")
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg')):
                file_path = os.path.join(root, file)
                dt = get_media_datetime(file_path)
                gps = get_media_gps(file_path)
                print(f"[DEBUG] File: {file_path}\n  Datetime: {dt}\n  GPS: {gps}")
                media_files.append({
                    'path': file_path,
                    'datetime': dt,
                    'gps': gps
                })
    print(f"[DEBUG] Total media files found: {len(media_files)}")
    return media_files

def find_closest_gps(media_files, target_file, time_window_hours=1):
    """Find closest GPS coordinates within a time window"""
    target_dt = target_file['datetime']
    if not target_dt:
        print(f"[DEBUG] Target file {target_file['path']} has no datetime, skipping proxy search.")
        return None
    time_window = timedelta(hours=time_window_hours)
    closest_gps = None
    min_time_diff = None
    for media in media_files:
        if media['gps'] and media['gps'] != (0.0, 0.0) and media['datetime']:
            time_diff = abs((target_dt - media['datetime']).total_seconds())
            if time_diff <= time_window.total_seconds():
                if min_time_diff is None or time_diff < min_time_diff:
                    min_time_diff = time_diff
                    closest_gps = media['gps']
                    print(f"[DEBUG] Potential proxy: {media['path']} | GPS: {closest_gps} | Time diff: {time_diff/60:.1f} min")
    if closest_gps:
        print(f"[DEBUG] Closest GPS for {target_file['path']}: {closest_gps} (diff {min_time_diff/60:.1f} min)")
    else:
        print(f"[DEBUG] No proxy GPS found for {target_file['path']}")
    return closest_gps

def scan_directory_with_closest(directory, time_frame=1):
    """Scan directory and find closest GPS for files without GPS"""
    media_files = scan_directory_for_media(directory)
    gps_files = [m for m in media_files if m['gps'] is not None and m['gps'] != (0.0, 0.0)]
    print(f"[DEBUG] Reference files with valid GPS: {len(gps_files)}")

    for media in media_files:
        if (media['gps'] is None or media['gps'] == (0.0, 0.0)) and media['datetime'] is not None:
            print(f"[DEBUG] Looking for proxy GPS for: {media['path']}")
            proxy_gps = find_closest_gps(gps_files, media, time_frame)
            if proxy_gps and proxy_gps != (0.0, 0.0):
                print(f"[DEBUG] Assigned proxy GPS {proxy_gps} to {media['path']}")
                media['gps'] = proxy_gps
            else:
                print(f"[DEBUG] No proxy GPS assigned to {media['path']}")
                media['gps'] = None

    entries = []
    for m in media_files:
        orig_gps = get_media_gps(m['path'])
        if (not orig_gps or orig_gps == (0.0, 0.0)) and m['gps'] and m['gps'] != (0.0, 0.0):
            lat = m['gps'][0]
            lon = m['gps'][1]
            gps_source = 'proxy'
            entry = {
                'path': m['path'],
                'datetime': m['datetime'].isoformat() if m['datetime'] else '',
                'latitude': lat,
                'longitude': lon,
                'gps_source': gps_source
            }
            print(f"[DEBUG] Entry for review: {entry}")
            entries.append(entry)
        elif orig_gps and orig_gps != (0.0, 0.0):
            # Already has GPS, will be included if show_with_gps is set (handled in scan_directory)
            lat = orig_gps[0]
            lon = orig_gps[1]
            gps_source = 'original'
            entry = {
                'path': m['path'],
                'datetime': m['datetime'].isoformat() if m['datetime'] else '',
                'latitude': lat,
                'longitude': lon,
                'gps_source': gps_source
            }
            entry['__include_if_show_with_gps'] = True
            entries.append(entry)
    print(f"[DEBUG] Total entries for review: {len(entries)}")
    return entries

def scan_directory_for_jpgs_without_gps_entries(root_dir):
    """Scan directory for JPEGs without GPS data"""
    import exifread
    import pytz
    from datetime import datetime
    entries = []
    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.tiff')):
                file_path = os.path.join(root, file)
                # --- get_media_datetime logic ---
                dt = None
                try:
                    with open(file_path, 'rb') as f:
                        tags = exifread.process_file(f, details=False)
                        if 'EXIF DateTimeOriginal' in tags:
                            dt_str = str(tags['EXIF DateTimeOriginal'])
                            try:
                                dt = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S').replace(tzinfo=pytz.UTC)
                            except Exception:
                                dt = None
                except Exception:
                    dt = None

                # --- get_media_gps logic ---
                gps = None
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
                            gps = (lat, lon)
                except Exception:
                    gps = None

                if gps is None or gps == (0.0, 0.0):
                    entries.append({
                        'path': file_path,
                        'datetime': dt.isoformat() if dt else '',
                        'latitude': '',
                        'longitude': '',
                        'gps_source': 'scan'
                    })
    return entries

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
    """Extract GPS coordinates from media file if available."""
    try:
        # Check if it's a video file (MOV, MP4, etc.)
        if file_path.lower().endswith(('.mov', '.mp4', '.avi', '.mkv')): 
            # Use FFmpeg to extract metadata, including GPS coordinates
            ffmpeg_command = [
                'ffmpeg', '-i', file_path, '-f', 'ffmetadata', '-']
            result = subprocess.run(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            metadata = result.stdout

            # Check for errors
            if "error" in result.stderr.lower():
                print(f"Error with file {file_path}: {result.stderr}")
                return None

            gps_data = None
            # Look for GPS info in the metadata output
            for line in metadata.splitlines():
                if 'location' in line.lower():  # Check for the location tag in the metadata
                    gps_data = line.split('=')[1].strip()
                    break

            if gps_data:
                # Parse the location string if found (e.g., +38.7695-009.1297)
                loc = gps_data.strip('/')
                if loc[0] not in ('+', '-'):
                    return None  # Invalid location format

                split_indexes = [i for i in range(1, len(loc)) if loc[i] in ('+', '-') and loc[i-1] not in ('E', 'W', 'N', 'S')]

                if len(split_indexes) == 1:
                    # Extract latitude and longitude from the two parts
                    lat = float(loc[:split_indexes[0]])
                    lon = float(loc[split_indexes[0]:])
                    if is_valid_gps((lat, lon)):
                        return (lat, lon)
                    else:
                        print(f"Warning: Invalid GPS coordinates skipped: {lat}, {lon}")
                        return None
                else:
                    print(f"Warning: Could not parse GPS coordinates: {loc}")
                    return None

        # Default behavior for other files
        else:
            # For image files (e.g., .jpg, .png), continue using EXIF
            with open(file_path, 'rb') as f:
                tags = exifread.process_file(f, details=False)
                if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
                    lat = tags['GPS GPSLatitude']
                    lon = tags['GPS GPSLongitude']
                    lat_ref = tags['GPS GPSLatitudeRef']
                    lon_ref = tags['GPS GPSLongitudeRef']

                    # Convert to decimal degrees
                    lat = float(lat.values[0]) + float(lat.values[1])/60 + float(lat.values[2])/3600
                    lon = float(lon.values[0]) + float(lon.values[1])/60 + float(lon.values[2])/3600

                    if str(lat_ref) == 'S':
                        lat = -lat
                    if str(lon_ref) == 'W':
                        lon = -lon

                    if is_valid_gps((lat, lon)):
                        return (lat, lon)
                    else:
                        print(f"Warning: Invalid GPS coordinates skipped: {lat}, {lon}")
                        return None

    except Exception as e:
        print(f"Error extracting GPS: {e}")
    return None

def is_valid_gps(gps_coord):
    """Check if GPS coordinates are valid and not (0,0)."""
    if not gps_coord:
        return False
    lat, lon = gps_coord
    return (-90 <= lat <= 90) and (-180 <= lon <= 180) and (lat, lon) != (0.0, 0.0)

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


# Unified Reviewer class for both CSV and directory scan workflows
class Reviewer:
    def __init__(self, entries, csv_path=None):
        self.entries = entries
        self.csv_path = csv_path  # Only set for CSV workflow
        self.current_index = 0
        self.changes_made = 0

    @classmethod
    def from_csv(cls, csv_path):
        entries = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                path = row.get('path', '')
                dt = row.get('datetime', '')
                lat = row.get('latitude', '')
                lon = row.get('longitude', '')
                gps_source = row.get('gps_source', '').lower() if row.get('gps_source') else ''

                entry = {
                    'path': path,
                    'datetime': dt,
                    'latitude': '',
                    'longitude': '',
                    'gps_source': gps_source or 'manual'
                }

                if gps_source == 'proxy':
                    # Use CSV values for proxy
                    entry['latitude'] = lat
                    entry['longitude'] = lon
                    entry['gps_source'] = 'proxy'
                elif gps_source == 'original' or gps_source == 'exif':
                    # Try to get from EXIF, fallback to CSV if not found
                    if os.path.exists(path):
                        exif_info = get_exif_data(path)
                        if exif_info and 'GPSInfo' in exif_info:
                            gps_info = exif_info['GPSInfo']
                            if 'GPSLatitude' in gps_info and 'GPSLongitude' in gps_info:
                                entry['latitude'] = str(gps_info['GPSLatitude'])
                                entry['longitude'] = str(gps_info['GPSLongitude'])
                                entry['gps_source'] = 'exif'
                            else:
                                entry['latitude'] = lat
                                entry['longitude'] = lon
                        else:
                            entry['latitude'] = lat
                            entry['longitude'] = lon
                    else:
                        print(f"Warning: Image not found at path: {path}")
                        entry['latitude'] = lat
                        entry['longitude'] = lon
                else:
                    # Fallback: use CSV values
                    entry['latitude'] = lat
                    entry['longitude'] = lon
                entries.append(entry)
        print(f"Loaded {len(entries)} entries from CSV")
        return cls(entries, csv_path=csv_path)

    @classmethod
    def from_entries(cls, entries):
        # Used for directory scan workflow
        return cls(entries)

    def get_current_entry(self):
        if 0 <= self.current_index < len(self.entries):
            return self.entries[self.current_index]
        return None

    def update_gps(self, lat, lon):
        try:
            lat = float(lat)
            lon = float(lon)
            validate_coordinates(lat, lon)
        except Exception as e:
            print(f"Invalid coordinates: {e}")
            return False
        entry = self.get_current_entry()
        if not entry:
            return False
        file_path = entry['path']
        if not os.path.exists(file_path):
            return False
        try:
            backup_path = file_path + '.bak'
            if not os.path.exists(backup_path):
                shutil.copy2(file_path, backup_path)
            if update_image_gps(file_path, lat, lon):
                entry['latitude'] = lat
                entry['longitude'] = lon
                entry['gps_source'] = 'manual'
                self.changes_made += 1
                return True
            else:
                return False
        except Exception as e:
            print(f"Error updating GPS: {e}")
            return False

    def save_all(self):
        # Only save CSV if csv_path is set (CSV workflow)
        print("Starting bulk save operation...")
        results = {
            'total': len(self.entries),
            'success': 0,
            'failed': 0,
            'failed_paths': [],
            'current_index': self.current_index,
            'total_entries': len(self.entries)
        }
        try:
            if self.csv_path:
                backup_path = self.csv_path + '.bak'
                if not os.path.exists(backup_path):
                    shutil.copy2(self.csv_path, backup_path)
            for entry in self.entries:
                try:
                    file_path = entry['path']
                    if entry['latitude'] and entry['longitude']:
                        img_backup = file_path + '.bak'
                        if not os.path.exists(img_backup):
                            shutil.copy2(file_path, img_backup)
                        lat = float(entry['latitude'])
                        lon = float(entry['longitude'])
                        if update_image_gps(file_path, lat, lon):
                            results['success'] += 1
                        else:
                            results['failed'] += 1
                            results['failed_paths'].append(entry['path'])
                    else:
                        results['success'] += 1
                except Exception as e:
                    print(f"Error processing {entry['path']}: {str(e)}")
                    results['failed'] += 1
                    results['failed_paths'].append(entry['path'])
            if self.csv_path:
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
            if self.csv_path and os.path.exists(self.csv_path + '.bak'):
                shutil.copy2(self.csv_path + '.bak', self.csv_path)
            results['success'] = 0
            results['failed'] = results['total']
            results['failed_paths'] = [e['path'] for e in self.entries]
            results['error'] = str(e)
            return results

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Global reviewer instance
reviewer = None

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
        if csv_file.filename == '':
            flash('No selected CSV file')
            return redirect(request.url)
        if csv_file and allowed_file(csv_file.filename):
            filename = secure_filename(csv_file.filename)
            csv_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                csv_file.save(csv_path)
                print(f"CSV saved to: {csv_path}")
                reviewer = Reviewer.from_csv(csv_path)
                if not reviewer.entries:
                    flash('CSV file is empty or invalid')
                    return redirect(request.url)
                # Set session variables for tracking source type
                session['source_type'] = 'csv'
                session['find_closest'] = False
                session['has_proxy_gps'] = any(entry.get('gps_source') == 'proxy' for entry in reviewer.entries)
                return redirect(url_for('review'))
            except Exception as e:
                print(f"Error saving file: {e}")
                flash('Error processing CSV file')
                return redirect(request.url)
    return render_template('index.html')

# In the review route, update the image path handling:
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
    
    # Prepare image path - using full path from CSV
    image_path = entry['path']
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
    
    # Prepare GPS data for display
    gps_info = exif_info.get('GPSInfo', {})
    latitude = gps_info.get('GPSLatitude', 'Unknown')
    longitude = gps_info.get('GPSLongitude', 'Unknown')
    
    # Convert to decimal if needed
    if isinstance(latitude, tuple):
        latitude = rational_to_decimal(latitude)
    if isinstance(longitude, tuple):
        longitude = rational_to_decimal(longitude)
    
    # Update exif_info with processed values
    exif_info['GPSLatitude'] = latitude
    exif_info['GPSLongitude'] = longitude
    
    # Get date taken or use unknown
    date_taken = exif_info.get('DateTimeOriginal', 'Unknown')
    
    # Prepare GPS points for heatmap (list of [lat, lon])
    gps_points = []
    for e in reviewer.entries:
        try:
            lat = float(e.get('latitude', ''))
            lon = float(e.get('longitude', ''))
            if lat != 0.0 or lon != 0.0:
                gps_points.append([lat, lon])
        except Exception:
            continue    # Get source type and proxy GPS status from session or determine from entries
    source_type = session.get('source_type', 'unknown')
    use_proxy = session.get('find_closest', False)
    has_proxy_gps = any(e.get('gps_source') == 'proxy' for e in reviewer.entries)
    
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
                         exif_info=exif_info,
                         all_entries=reviewer.entries,
                         gps_points=gps_points,
                         source_type=source_type,
                         use_proxy=use_proxy,
                         has_proxy_gps=has_proxy_gps)

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

@app.route('/scan_directory', methods=['POST'])
def scan_directory():
    global reviewer
    data = request.get_json()
    file_list = data.get('file_list')
    directory = data.get('directory')
    find_closest = data.get('find_closest', False)
    time_frame = data.get('time_frame', 1)
    show_with_gps = data.get('show_with_gps', False)

    # If file_list is provided (from folder picker), use it. Otherwise, fall back to directory scan.
    if file_list and isinstance(file_list, list) and len(file_list) > 0:
        # file_list contains relative paths (webkitRelativePath), but we need absolute paths
        # Assume all files are under the same root (the first path's root)
        # Try to reconstruct the root directory from the first file
        first_path = file_list[0]
        # Remove the relative part to get the root directory
        # e.g. Edenred-100.jpg or subfolder/IMG_001.jpg
        # The user selects a folder, so the files are relative to that folder
        # We'll ask the user to upload from a known location, or try to resolve to static/uploads
        # For now, try to join with UPLOAD_FOLDER
        root_dir = app.config['UPLOAD_FOLDER']
        abs_file_paths = [os.path.join(root_dir, rel_path) for rel_path in file_list]
        print(f"[DEBUG] Received file_list with {len(abs_file_paths)} files. Root dir: {root_dir}")

        # Only process files that exist
        abs_file_paths = [f for f in abs_file_paths if os.path.exists(f)]
        if not abs_file_paths:
            return jsonify({'status': 'error', 'message': 'No valid files found in the selected directory.'}), 200

        # Build media_files list as in scan_directory_for_media
        media_files = []
        for file_path in abs_file_paths:
            if file_path.lower().endswith(('.jpg', '.jpeg')):
                dt = get_media_datetime(file_path)
                gps = get_media_gps(file_path)
                print(f"[DEBUG] File: {file_path}\n  Datetime: {dt}\n  GPS: {gps}")
                media_files.append({
                    'path': file_path,
                    'datetime': dt,
                    'gps': gps
                })

        if find_closest:
            # Use the same logic as scan_directory_with_closest, but only for the selected files
            gps_files = [m for m in media_files if m['gps'] is not None and m['gps'] != (0.0, 0.0)]
            print(f"[DEBUG] Reference files with valid GPS: {len(gps_files)}")
            for media in media_files:
                if (media['gps'] is None or media['gps'] == (0.0, 0.0)) and media['datetime'] is not None:
                    print(f"[DEBUG] Looking for proxy GPS for: {media['path']}")
                    proxy_gps = find_closest_gps(gps_files, media, time_frame)
                    if proxy_gps and proxy_gps != (0.0, 0.0):
                        print(f"[DEBUG] Assigned proxy GPS {proxy_gps} to {media['path']}")
                        media['gps'] = proxy_gps
                    else:
                        print(f"[DEBUG] No proxy GPS assigned to {media['path']}")
                        media['gps'] = None

        entries = []
        for m in media_files:
            orig_gps = get_media_gps(m['path'])
            if (not orig_gps or orig_gps == (0.0, 0.0)) and m['gps'] and m['gps'] != (0.0, 0.0):
                lat = m['gps'][0]
                lon = m['gps'][1]
                gps_source = 'proxy' if find_closest else 'scan'
                entry = {
                    'path': m['path'],
                    'datetime': m['datetime'].isoformat() if m['datetime'] else '',
                    'latitude': lat,
                    'longitude': lon,
                    'gps_source': gps_source
                }
                print(f"[DEBUG] Entry for review: {entry}")
                entries.append(entry)
            elif orig_gps and orig_gps != (0.0, 0.0):
                # Already has GPS, will be included if show_with_gps is set
                lat = orig_gps[0]
                lon = orig_gps[1]
                gps_source = 'original'
                entry = {
                    'path': m['path'],
                    'datetime': m['datetime'].isoformat() if m['datetime'] else '',
                    'latitude': lat,
                    'longitude': lon,
                    'gps_source': gps_source
                }
                entry['__include_if_show_with_gps'] = True
                entries.append(entry)

        if not show_with_gps:
            # Only keep proxy/scan entries
            entries = [e for e in entries if e.get('gps_source') != 'original']
        else:
            # Remove marker key
            for e in entries:
                if '__include_if_show_with_gps' in e:
                    del e['__include_if_show_with_gps']

        if not entries:
            return jsonify({'status': 'error', 'message': 'No images found for review.'}), 200
        reviewer = Reviewer.from_entries(entries)
        return jsonify({'status': 'success', 'redirect': url_for('review')}), 200

    # Fallback: legacy directory scan
    if not directory or not os.path.isdir(directory):
        return jsonify({'status': 'error', 'message': 'Invalid or missing directory'}), 400
    try:
        if find_closest:
            entries = scan_directory_with_closest(directory, time_frame)
            if not show_with_gps:
                entries = [e for e in entries if e.get('gps_source') == 'proxy']
            else:
                for e in entries:
                    if '__include_if_show_with_gps' in e:
                        del e['__include_if_show_with_gps']
        else:
            media_files = scan_directory_for_media(directory)
            entries = []
            for m in media_files:
                gps = m['gps']
                dt = m['datetime']
                if gps and gps != (0.0, 0.0):
                    entry = {
                        'path': m['path'],
                        'datetime': dt.isoformat() if dt else '',
                        'latitude': gps[0],
                        'longitude': gps[1],
                        'gps_source': 'original'
                    }
                    entries.append(entry)
                else:
                    entry = {
                        'path': m['path'],
                        'datetime': dt.isoformat() if dt else '',
                        'latitude': '',
                        'longitude': '',
                        'gps_source': 'scan'
                    }
                    entries.append(entry)
            if not show_with_gps:
                entries = [e for e in entries if not e['latitude'] or not e['longitude']]
        if not entries:
            return jsonify({'status': 'error', 'message': 'No images found for review.'}), 200
        reviewer = Reviewer.from_entries(entries)
        return jsonify({'status': 'success', 'redirect': url_for('review')}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)