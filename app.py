import os
import csv
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
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
import platform
import tempfile

# Import pillow-heif for HEIC support
try:
    import pillow_heif
    # Register the HEIF opener with PIL
    pillow_heif.register_heif_opener()
    HEIF_SUPPORT = True
except ImportError:
    HEIF_SUPPORT = False

# Import the utility functions for logging and CSV path handling
from utils import setup_logger, get_csv_path

# Setup logger
logger = setup_logger()

app = Flask(__name__)

# Create directory structure if it doesn't exist
app.config['CSV_FOLDER'] = os.path.join('data', 'csv')
app.config['LOG_FOLDER'] = os.path.join('data', 'log')
app.config['PHOTOS_FOLDER'] = os.path.join('data', 'photos')
app.config['TEMP_FOLDER'] = tempfile.gettempdir()

# Ensure the directories exist
os.makedirs(app.config['CSV_FOLDER'], exist_ok=True)
os.makedirs(app.config['LOG_FOLDER'], exist_ok=True)
os.makedirs(app.config['PHOTOS_FOLDER'], exist_ok=True)

app.config['ALLOWED_EXTENSIONS'] = {'jpg', 'jpeg', 'png', 'csv', 'heic', 'heif', 'mp4', 'mov', 'avi', 'mkv'}
app.secret_key = 'your-secret-key-here'  # Needed for flash messages

# Log application initialization
logger.info("Initializing Picture GPS Reviewer application")
logger.info(f"CSV folder: {app.config['CSV_FOLDER']}")
logger.info(f"Log folder: {app.config['LOG_FOLDER']}")
logger.info(f"Photos folder: {app.config['PHOTOS_FOLDER']}")
logger.info(f"CSV folder exists: {os.path.exists(app.config['CSV_FOLDER'])}")
logger.info(f"CSV folder writable: {os.access(app.config['CSV_FOLDER'], os.W_OK)}")
logger.info(f"Log folder exists: {os.path.exists(app.config['LOG_FOLDER'])}")
logger.info(f"Log folder writable: {os.access(app.config['LOG_FOLDER'], os.W_OK)}")
logger.info(f"Photos folder exists: {os.path.exists(app.config['PHOTOS_FOLDER'])}")
logger.info(f"Photos folder writable: {os.access(app.config['PHOTOS_FOLDER'], os.W_OK)}")
logger.info(f"HEIC/HEIF support: {HEIF_SUPPORT}")

# Handle Windows long path issue
if platform.system() == 'Windows':
    try:
        # Enable long path support on Windows
        import ctypes
        from ctypes import wintypes
        
        # Define the function to enable long paths
        try:
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.SetFileAttributesW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD)
            kernel32.SetFileAttributesW.restype = wintypes.BOOL
            
            # Enable long path support (needs Windows 10+)
            FILE_ATTRIBUTE_NORMAL = 0x80
            test_path = "\\\\?\\" + os.getcwd()
            result = kernel32.SetFileAttributesW(test_path, FILE_ATTRIBUTE_NORMAL)
            
            if result:
                logger.info("Windows long path support enabled")
                def fix_long_path(path):
                    # If path is too long, prefix with \\?\
                    if len(path) >= 260 and not path.startswith('\\\\?\\'):
                        return '\\\\?\\' + os.path.abspath(path)
                    return path
            else:
                logger.warning("Could not enable Windows long path support")
                def fix_long_path(path):
                    return path
        except Exception as e:
            logger.warning(f"Windows long path API not available: {e}")
            def fix_long_path(path):
                return path
    except Exception as e:
        logger.warning(f"Could not import Windows-specific modules: {e}")
        def fix_long_path(path):
            return path
else:
    # For non-Windows systems, no change needed
    def fix_long_path(path):
        return path

def validate_coordinates(lat, lon):
    """Validate latitude and longitude values"""
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        logger.error(f"Invalid coordinates: lat={lat}, lon={lon}")
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
        logger.error(f"Failed to convert ratio {ratio} to decimal: {e}")
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
        logger.info(f"Geocoding address: {address}")
        location = geolocator.geocode(address)
        if location:
            logger.info(f"Found location: {location.latitude}, {location.longitude}")
            return {'latitude': location.latitude, 'longitude': location.longitude}
        logger.warning(f"No location found for address: {address}")
        return None
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        logger.error(f"Geocoding error for address {address}: {e}")
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
        logger.error(f"Error converting DMS to decimal: {e}")
        return None

def get_exif_data(image_path):
    """Extract EXIF data from an image file."""
    try:
        logger.debug(f"Extracting EXIF data from: {image_path}")
        image = Image.open(image_path)
        exif_data = image._getexif()
        
        if exif_data is None:
            logger.debug(f"No EXIF data found in {image_path}")
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
            logger.debug(f"No GPS information found in {image_path}")
            return None
        
        logger.debug(f"Successfully extracted EXIF data from {image_path}")
        return exif_info
    except Exception as e:
        logger.error(f"Error extracting EXIF data from {image_path}: {e}")
        return None

def _clean_exif_dict(exif_dict):
    """Clean problematic tags from EXIF dictionary"""
    if "Exif" in exif_dict and 41729 in exif_dict["Exif"]:
        logger.debug("Removing problematic EXIF tag 41729")
        del exif_dict["Exif"][41729]
    return exif_dict

def update_image_gps(file_path, lat, lon):
    """Update GPS metadata for media files (images, HEIC, videos)."""
    try:
        # Fix long path issue on Windows
        file_path = fix_long_path(file_path)
        
        # Check if file exists before processing
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False
        
        # Get media type
        media_type = get_media_type(file_path)
        file_lower = file_path.lower()
        
        logger.info(f"Processing {media_type} file: {file_path}")
        
        # Handle HEIC files specifically with pillow-heif
        if media_type == 'heic' and HEIF_SUPPORT:
            try:
                # Open HEIC with pillow-heif
                img = Image.open(file_path)
                exif_data = img.getexif()
                
                # Get GPS IFD or create a new one
                gps_ifd = exif_data.get_ifd(0x8825) or {}
                
                # Update GPS data
                gps_ifd[1] = 'N' if lat >= 0 else 'S'  # GPSLatitudeRef
                gps_ifd[2] = decimal_to_dms(abs(lat))  # GPSLatitude
                gps_ifd[3] = 'E' if lon >= 0 else 'W'  # GPSLongitudeRef
                gps_ifd[4] = decimal_to_dms(abs(lon))  # GPSLongitude
                gps_ifd[0] = (2, 3, 0, 0)  # GPSVersionID
                
                # Set the GPS IFD back to the EXIF data
                exif_data.set_ifd(0x8825, gps_ifd)
                
                # Create a temporary JPEG copy with the updated EXIF
                temp_file = file_path + '.temp'
                img.save(temp_file, exif=exif_data.tobytes())
                
                # Replace the original file with the temporary one
                shutil.move(temp_file, file_path)
                
                logger.info(f"Successfully updated GPS for HEIC file {file_path}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to update HEIC file {file_path}: {str(e)}")
                return False
        
        # Handle video files
        elif media_type == 'video':
            try:
                # Use FFmpeg to add GPS metadata to video
                # Note: FFmpeg can modify some video metadata, but GPS data might not be preserved by all players
                # This is a best-effort approach
                
                # Format GPS coordinates for FFmpeg
                lat_ref = 'N' if lat >= 0 else 'S'
                lon_ref = 'E' if lon >= 0 else 'W'
                
                # Create temporary file
                temp_file = file_path + '.temp.mp4'
                
                # FFmpeg command to copy the video with new metadata
                ffmpeg_command = [
                    'ffmpeg', '-y', '-i', file_path,
                    '-metadata', f'location={lat_ref}{abs(lat)}{lon_ref}{abs(lon)}',
                    '-codec', 'copy',
                    temp_file
                ]
                
                # Run the command
                result = subprocess.run(
                    ffmpeg_command, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    text=True
                )
                
                if result.returncode != 0:
                    logger.error(f"FFmpeg error: {result.stderr}")
                    return False
                
                # Replace the original file
                shutil.move(temp_file, file_path)
                
                logger.info(f"Successfully updated GPS for video {file_path}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to update video {file_path}: {str(e)}")
                return False
        
        # Handle standard image files
        else:  # media_type == 'image'
            try:
                try:
                    exif_dict = piexif.load(file_path)
                except Exception as e:
                    logger.info(f"Creating new EXIF data: {str(e)}")
                    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
                
                # Clean problematic tags
                exif_dict = _clean_exif_dict(exif_dict)
                
                # Create GPS metadata
                gps_ifd = {
                    piexif.GPSIFD.GPSLatitudeRef: 'N' if lat >= 0 else 'S',
                    piexif.GPSIFD.GPSLatitude: decimal_to_dms(abs(lat)),
                    piexif.GPSIFD.GPSLongitudeRef: 'E' if lon >= 0 else 'W',
                    piexif.GPSIFD.GPSLongitude: decimal_to_dms(abs(lon)),
                    # Add GPSVersionID if not present
                    piexif.GPSIFD.GPSVersionID: exif_dict.get("GPS", {}).get(piexif.GPSIFD.GPSVersionID, (2, 3, 0, 0))
                }
                
                exif_dict["GPS"] = gps_ifd
                
                # Save with new EXIF
                piexif.insert(piexif.dump(exif_dict), file_path)
                logger.info(f"Successfully updated GPS for image {file_path}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to update image {file_path}: {str(e)}")
                return False
            
    except Exception as e:
        logger.error(f"Failed to update {file_path}: {str(e)}")
        return False

# ==============================================
# Directory Scanning Functions
# ==============================================

def scan_directory_for_media(directory):
    """Scan directory for media files (images, HEIC, and videos) and collect their metadata"""
    media_files = []
    logger.debug(f"Scanning directory: {directory}")
    
    # Define supported extensions
    image_extensions = ('.jpg', '.jpeg', '.png', '.tiff')
    heic_extensions = ('.heic', '.heif')
    video_extensions = ('.mp4', '.mov', '.avi', '.mkv')
    
    all_supported_extensions = image_extensions
    if HEIF_SUPPORT:
        all_supported_extensions += heic_extensions
    all_supported_extensions += video_extensions
    
    for root, _, files in os.walk(directory):
        for file in files:
            file_lower = file.lower()
            if file_lower.endswith(all_supported_extensions):
                file_path = os.path.join(root, file)
                
                # Fix long paths on Windows
                file_path = fix_long_path(file_path)
                
                # Skip unsupported HEIC files if pillow-heif is not available
                if not HEIF_SUPPORT and file_lower.endswith(heic_extensions):
                    logger.warning(f"Skipping HEIC/HEIF file {file_path} - pillow-heif not available")
                    continue
                
                try:
                    dt = get_media_datetime(file_path)
                    gps = get_media_gps(file_path)
                    media_type = get_media_type(file_path)
                    
                    logger.debug(f"File: {file_path}\n  Type: {media_type}\n  Datetime: {dt}\n  GPS: {gps}")
                    
                    media_files.append({
                        'path': file_path,
                        'datetime': dt,
                        'gps': gps,
                        'media_type': media_type
                    })
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {str(e)}")
    
    logger.debug(f"Total media files found: {len(media_files)}")
    return media_files

def find_closest_gps(media_files, target_file, time_window_hours=1):
    """Find closest GPS coordinates within a time window"""
    target_dt = target_file['datetime']
    if not target_dt:
        logger.debug(f"Target file {target_file['path']} has no datetime, skipping proxy search.")
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
                    logger.debug(f"Potential proxy: {media['path']} | GPS: {closest_gps} | Time diff: {time_diff/60:.1f} min")
    if closest_gps:
        logger.debug(f"Closest GPS for {target_file['path']}: {closest_gps} (diff {min_time_diff/60:.1f} min)")
    else:
        logger.debug(f"No proxy GPS found for {target_file['path']}")
    return closest_gps

def scan_directory_with_closest(directory, time_frame=1):
    """Scan directory and find closest GPS for files without GPS"""
    media_files = scan_directory_for_media(directory)
    gps_files = [m for m in media_files if m['gps'] is not None and m['gps'] != (0.0, 0.0)]
    logger.debug(f"Reference files with valid GPS: {len(gps_files)}")

    for media in media_files:
        if (media['gps'] is None or media['gps'] == (0.0, 0.0)) and media['datetime'] is not None:
            logger.debug(f"Looking for proxy GPS for: {media['path']}")
            proxy_gps = find_closest_gps(gps_files, media, time_frame)
            if proxy_gps and proxy_gps != (0.0, 0.0):
                logger.debug(f"Assigned proxy GPS {proxy_gps} to {media['path']}")
                media['gps'] = proxy_gps
            else:
                logger.debug(f"No proxy GPS assigned to {media['path']}")
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
            logger.debug(f"Entry for review: {entry}")
            entries.append(entry)
        elif orig_gps and orig_gps != (0.0, 0.0):
            # Already has GPS, will be included if not hide_with_gps
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
            entry['__include_if_not_hide_gps'] = True
            entries.append(entry)
    logger.debug(f"Total entries for review: {len(entries)}")
    return entries

def scan_directory_for_jpgs_without_gps_entries(root_dir):
    """Scan directory for media files (images, HEIC, videos) without GPS data"""
    entries = []
    
    # Define supported extensions
    image_extensions = ('.jpg', '.jpeg', '.png', '.tiff')
    heic_extensions = ('.heic', '.heif')
    video_extensions = ('.mp4', '.mov', '.avi', '.mkv')
    
    all_supported_extensions = image_extensions
    if HEIF_SUPPORT:
        all_supported_extensions += heic_extensions
    all_supported_extensions += video_extensions
    
    for root, _, files in os.walk(root_dir):
        for file in files:
            file_lower = file.lower()
            if file_lower.endswith(all_supported_extensions):
                file_path = os.path.join(root, file)
                
                # Fix long paths on Windows
                file_path = fix_long_path(file_path)
                
                # Skip unsupported HEIC files if pillow-heif is not available
                if not HEIF_SUPPORT and file_lower.endswith(heic_extensions):
                    logger.warning(f"Skipping HEIC/HEIF file {file_path} - pillow-heif not available")
                    continue
                
                try:
                    # Get media info
                    dt = get_media_datetime(file_path)
                    gps = get_media_gps(file_path)
                    media_type = get_media_type(file_path)
                    
                    # Add entries without GPS
                    if gps is None or gps == (0.0, 0.0):
                        entries.append({
                            'path': file_path,
                            'datetime': dt.isoformat() if dt else '',
                            'latitude': '',
                            'longitude': '',
                            'gps_source': 'scan',
                            'media_type': media_type
                        })
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {str(e)}")
                    entries.append({
                        'path': file_path,
                        'datetime': '',
                        'latitude': '',
                        'longitude': '',
                        'gps_source': 'scan',
                        'media_type': 'unknown',
                        'error': str(e)
                    })
    
    logger.info(f"Found {len(entries)} media files without GPS data in {root_dir}")
    return entries

# ==============================================
# GPS and EXIF Related Functions
# ==============================================

def get_media_datetime(file_path):
    """Extract datetime from media file (image, HEIC, or video)."""
    # Fix long path issue on Windows
    file_path = fix_long_path(file_path)
    
    # Check if file exists
    if not os.path.exists(file_path):
        logger.error(f"File not found when getting datetime: {file_path}")
        return None
    
    file_lower = file_path.lower()
        
    # Handle HEIC files specifically with pillow-heif if available
    if file_lower.endswith(('.heic', '.heif')) and HEIF_SUPPORT:
        try:
            # pillow-heif allows opening HEIC files directly via PIL
            img = Image.open(file_path)
            exif_data = img.getexif()
            
            # Get DateTimeOriginal (tag 36867)
            if 36867 in exif_data:
                dt_str = exif_data[36867]
                return datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S').replace(tzinfo=pytz.UTC)
                
            logger.debug(f"No DateTimeOriginal found in HEIC/HEIF file: {file_path}")
            return None
        except Exception as e:
            logger.error(f"Error processing HEIC/HEIF file {file_path}: {str(e)}")
    
    # For regular images
    try:
        if file_lower.endswith(('.jpg', '.jpeg', '.png', '.tiff')):
            with open(file_path, 'rb') as f:
                tags = exifread.process_file(f, details=False)
                if 'EXIF DateTimeOriginal' in tags:
                    dt_str = str(tags['EXIF DateTimeOriginal'])
                    return datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S').replace(tzinfo=pytz.UTC)
                else:
                    logger.debug(f"No DateTimeOriginal found in {file_path}")
    except Exception as e:
        logger.error(f"Error extracting datetime from image {file_path}: {str(e)}")
    
    # For videos
    try:
        if file_lower.endswith(('.mp4', '.mov', '.avi', '.mkv')):
            # Use FFmpeg to extract metadata, including creation time
            ffmpeg_command = [
                'ffmpeg', '-i', file_path, '-f', 'ffmetadata', '-']
            result = subprocess.run(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            metadata = result.stdout
            stderr = result.stderr

            # Look for creation_time in the metadata output
            creation_time = None
            for line in metadata.splitlines():
                if 'creation_time' in line.lower():
                    creation_time = line.split('=')[1].strip()
                    break
                    
            # If not found in stdout, check stderr (ffmpeg often outputs metadata there)
            if not creation_time:
                for line in stderr.splitlines():
                    if 'creation_time' in line.lower():
                        parts = line.split('creation_time')
                        if len(parts) > 1:
                            # Fix: More carefully extract the timestamp
                            time_part = parts[1].strip()
                            if time_part.startswith(':'):
                                time_part = time_part[1:].strip()
                            creation_time = time_part.split(',')[0].strip()
                            break

            if creation_time:
                # Handle multiple date formats
                import re
                
                # Method 1: ISO 8601 format with microseconds and Z timezone
                # Example: 2025-06-12T08:42:06.000000Z
                try:
                    pattern = r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.(\d+)Z$'
                    match = re.match(pattern, creation_time)
                    if match:
                        base_time = match.group(1)  # YYYY-MM-DDThh:mm:ss
                        dt = datetime.strptime(base_time, '%Y-%m-%dT%H:%M:%S')
                        dt = dt.replace(tzinfo=datetime.timezone.utc)
                        return dt
                except Exception:
                    pass

                # Method 2: Use regex to extract just the basic date and time components with T
                try:
                    pattern = r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})'
                    match = re.match(pattern, creation_time)
                    if match:
                        # Found YYYY-MM-DDThh:mm:ss format
                        base_time = match.group(1)
                        dt = datetime.strptime(base_time, '%Y-%m-%dT%H:%M:%S')
                        dt = dt.replace(tzinfo=datetime.timezone.utc)
                        return dt
                except Exception:
                    pass
                
                # Method 3: Try standard date format without 'T'
                try:
                    pattern = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'
                    match = re.match(pattern, creation_time)
                    if match:
                        time_str = match.group(1)
                        dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                        dt = dt.replace(tzinfo=datetime.timezone.utc)
                        return dt
                except Exception:
                    pass
                
                # Method 4: Try directly removing Z and microseconds
                if 'Z' in creation_time:
                    try:
                        # Replace Z with UTC marker
                        simple_time = creation_time.replace('Z', '+00:00')
                        
                        # Remove microseconds if present
                        if '.' in simple_time:
                            simple_time = simple_time.split('.')[0] + '+00:00'
                        
                        dt = datetime.fromisoformat(simple_time)
                        return dt
                    except Exception:
                        pass
                
                # Method 5: Try direct parsing
                try:
                    dt = datetime.fromisoformat(creation_time)
                    return dt
                except Exception:
                    pass
                
                # Last effort - log the failure and return None
                logger.error(f"Could not parse creation_time: {creation_time}")
                return None
            else:
                logger.debug(f"No creation_time found in video metadata for {file_path}")
    except Exception as e:
        logger.error(f"Error extracting datetime from video {file_path}: {str(e)}")

    logger.debug(f"Could not extract datetime from {file_path}")
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
                logger.error(f"Error with file {file_path}: {result.stderr}")
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
                        logger.warning(f"Invalid GPS coordinates skipped: {lat}, {lon}")
                        return None
                else:
                    logger.warning(f"Could not parse GPS coordinates: {loc}")
                    return None

        # Default behavior for other files
        else:
            # For image files (e.g., .jpg, .png), continue using EXIF
            with open(file_path, 'rb') as f:
                tags = exifread.process_file(f, details=False)
                
                # Check if GPS coordinates exist
                if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
                    lat = tags['GPS GPSLatitude']
                    lon = tags['GPS GPSLongitude']
                    
                    # Convert to decimal degrees
                    lat = float(lat.values[0]) + float(lat.values[1])/60 + float(lat.values[2])/3600
                    lon = float(lon.values[0]) + float(lon.values[1])/60 + float(lon.values[2])/3600

                    # Handle GPS reference directions if available
                    if 'GPS GPSLatitudeRef' in tags and 'GPS GPSLongitudeRef' in tags:
                        lat_ref = tags['GPS GPSLatitudeRef']
                        lon_ref = tags['GPS GPSLongitudeRef']
                        
                        if str(lat_ref) == 'S':
                            lat = -lat
                        if str(lon_ref) == 'W':
                            lon = -lon
                    else:
                        # If ref tags are missing, infer them from coordinate values
                        # For images with missing ref tags but valid coordinates
                        logger.info(f"Missing GPS ref tags in {file_path}, inferring from coordinate signs")
                        
                        # In the Northern and Eastern hemispheres, coordinates are typically positive
                        # In the Southern and Western hemispheres, coordinates are typically negative
                        # We can't infer accurately without the ref tags, but we'll return the coordinates as-is
                        # Most software uses positive values for N/E and negative for S/W
                        
                    if is_valid_gps((lat, lon)):
                        return (lat, lon)
                    else:
                        logger.warning(f"Invalid GPS coordinates skipped: {lat}, {lon}")
                        return None

    except Exception as e:
        logger.error(f"Error extracting GPS: {e}")
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
        logger.debug(f"Extracting EXIF data from: {image_path}")
        image = Image.open(image_path)
        exif_data = image._getexif()
        
        if exif_data is None:
            logger.debug(f"No EXIF data found in {image_path}")
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
            logger.debug(f"No GPS information found in {image_path}")
            return None
        
        logger.debug(f"Successfully extracted EXIF data from {image_path}")
        return exif_info
    except Exception as e:
        logger.error(f"Error extracting EXIF data from {image_path}: {e}")
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
        # Make sure csv_path is normalized to use CSV_FOLDER
        if not os.path.isabs(csv_path) and not csv_path.startswith(app.config['CSV_FOLDER']):
            csv_path = os.path.join(app.config['CSV_FOLDER'], os.path.basename(csv_path))
        
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
                        logger.warning(f"Image not found at path: {path}")
                        entry['latitude'] = lat
                        entry['longitude'] = lon
                else:
                    # Fallback: use CSV values
                    entry['latitude'] = lat
                    entry['longitude'] = lon
                entries.append(entry)
        logger.info(f"Loaded {len(entries)} entries from CSV")
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
            logger.error(f"Invalid coordinates: {e}")
            return False
        entry = self.get_current_entry()
        if not entry:
            return False
        file_path = entry['path']
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False
        try:
            backup_path = file_path + '.bak'
            if not os.path.exists(backup_path):
                shutil.copy2(file_path, backup_path)
                logger.debug(f"Created backup of {file_path} to {backup_path}")
            if update_image_gps(file_path, lat, lon):
                entry['latitude'] = lat
                entry['longitude'] = lon
                entry['gps_source'] = 'manual'
                self.changes_made += 1
                logger.info(f"GPS coordinates updated for {file_path}")
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"Error updating GPS: {e}")
            return False

    def save_all(self):
        # Only save CSV if csv_path is set (CSV workflow)
        logger.info("Starting bulk save operation...")
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
                # Make sure csv_path points to CSV_FOLDER
                if not os.path.isabs(self.csv_path) and not self.csv_path.startswith(app.config['CSV_FOLDER']):
                    self.csv_path = os.path.join(app.config['CSV_FOLDER'], os.path.basename(self.csv_path))
                
                backup_path = self.csv_path + '.bak'
                if not os.path.exists(backup_path):
                    shutil.copy2(self.csv_path, backup_path)
                    logger.debug(f"Created backup of CSV file: {backup_path}")
            
            for entry in self.entries:
                try:
                    file_path = entry['path']
                    if entry['latitude'] and entry['longitude']:
                        img_backup = file_path + '.bak'
                        if not os.path.exists(img_backup):
                            shutil.copy2(file_path, img_backup)
                            logger.debug(f"Created backup of image: {img_backup}")
                        lat = float(entry['latitude'])
                        lon = float(entry['longitude'])
                        if update_image_gps(file_path, lat, lon):
                            results['success'] += 1
                        else:
                            results['failed'] += 1
                            results['failed_paths'].append(entry['path'])
                            logger.warning(f"Failed to update GPS for: {file_path}")
                    else:
                        results['success'] += 1
                except Exception as e:
                    logger.error(f"Error processing {entry['path']}: {str(e)}")
                    results['failed'] += 1
                    results['failed_paths'].append(entry['path'])
            
            if self.csv_path:
                with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                    fieldnames = ['path', 'datetime', 'latitude', 'longitude', 'gps_source']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for entry in self.entries:
                        writer.writerow({
                            'path': entry['path'],
                            'datetime': entry['datetime'],
                            'latitude': entry.get('latitude', ''),
                            'longitude': entry.get('longitude', ''),
                            'gps_source': entry.get('gps_source', '')
                        })
                logger.info(f"Updated CSV file: {self.csv_path}")
            
            logger.info(f"Bulk save completed. Success: {results['success']}, Failed: {results['failed']}")
            return results
        except Exception as e:
            logger.error(f"Critical error during bulk save: {str(e)}", exc_info=True)
            if self.csv_path and os.path.exists(self.csv_path + '.bak'):
                shutil.copy2(self.csv_path + '.bak', self.csv_path)
                logger.info(f"Restored CSV backup due to error")
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
    logger.debug(f"Index route called, method: {request.method}")
    
    # Show the index page with options for directories or CSV
    if request.method == 'GET':
        return render_template('index.html')
    
    if request.method == 'POST':
        logger.debug("POST request received")
        logger.debug(f"Form data: {request.form}")
        logger.debug(f"Files: {request.files}")
        if 'csv_file' not in request.files:
            logger.warning("No CSV file selected")
            flash('No CSV file selected')
            return redirect(url_for('directory_list'))
        csv_file = request.files['csv_file']
        if csv_file.filename == '':
            logger.warning("Empty CSV filename")
            flash('No selected CSV file')
            return redirect(url_for('directory_list'))
        if csv_file and allowed_file(csv_file.filename):
            filename = secure_filename(csv_file.filename)
            csv_path = os.path.join(app.config['CSV_FOLDER'], filename)
            try:
                csv_file.save(csv_path)
                logger.info(f"CSV saved to: {csv_path}")
                reviewer = Reviewer.from_csv(csv_path)
                if not reviewer.entries:
                    logger.warning(f"CSV file is empty or invalid: {csv_path}")
                    flash('CSV file is empty or invalid')
                    return redirect(url_for('directory_list'))
                # Set session variables for tracking source type
                session['source_type'] = 'csv'
                session['find_closest'] = False
                session['has_proxy_gps'] = any(entry.get('gps_source') == 'proxy' for entry in reviewer.entries)
                logger.info(f"Starting review with {len(reviewer.entries)} entries")
                return redirect(url_for('review'))
            except Exception as e:
                logger.error(f"Error processing CSV file: {e}", exc_info=True)
                flash('Error processing CSV file')
                return redirect(url_for('directory_list'))
    return redirect(url_for('directory_list'))

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
    
    # Prepare file path - using full path
    file_path = entry['path']
    file_path = fix_long_path(file_path)
    
    if not os.path.exists(file_path):
        flash(f'File not found: {file_path}', 'danger')
        return redirect(url_for('index'))
    
    # Determine media type (image, HEIC, or video)
    if 'media_type' not in entry:
        entry['media_type'] = get_media_type(file_path)
    
    media_type = entry['media_type']
    thumbnail_path = None
    
    # For video files, generate a thumbnail
    if media_type == 'video':
        thumbnail_path = get_video_thumbnail(file_path)
        if not thumbnail_path:
            logger.error(f"Failed to generate thumbnail for video: {file_path}")
            # We'll still show the video with a default thumbnail or player
    
    # Extract EXIF info (different approach based on media type)
    exif_info = {}
    date_taken = "Unknown"
    
    if media_type == 'image':
        # Standard image handling
        exif_info = get_exif_data(file_path) or {}
        date_taken = exif_info.get('DateTimeOriginal', 'Unknown')
    elif media_type == 'heic' and HEIF_SUPPORT:
        # HEIC handling using pillow-heif
        try:
            img = Image.open(file_path)
            exif_data = img.getexif()
            # Extract basic EXIF info
            for tag_id in exif_data:
                tag_name = TAGS.get(tag_id, tag_id)
                exif_info[tag_name] = exif_data[tag_id]
            # Get date taken
            if 36867 in exif_data:  # DateTimeOriginal tag
                date_taken = exif_data[36867]
        except Exception as e:
            logger.error(f"Error extracting HEIC EXIF data: {e}")
    elif media_type == 'video':
        # Extract video metadata using ffmpeg
        try:
            ffmpeg_command = [
                'ffmpeg', '-i', file_path, '-f', 'ffmetadata', '-']
            result = subprocess.run(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            metadata = result.stdout
            stderr = result.stderr
            
            # Parse metadata
            for line in metadata.splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    exif_info[key.strip()] = value.strip()
            
            # Get creation time from metadata
            if 'creation_time' in exif_info:
                try:
                    creation_time = exif_info['creation_time']
                    # Handle ISO format (2023-05-30T12:34:56.000000Z)
                    if 'Z' in creation_time:
                        # Handle ISO format with Z (UTC timezone marker)
                        clean_time = creation_time.replace('Z', '+00:00')
                        # Format microseconds if needed
                        if '.' in clean_time:
                            parts = clean_time.split('.')
                            if len(parts) == 2:
                                base_time = parts[0]
                                micro_part = parts[1]
                                # If microseconds part is too long, truncate it
                                tz_split = micro_part.split('+')
                                if len(tz_split[0]) > 6:
                                    micro_part = tz_split[0][:6]
                                    if len(tz_split) > 1:
                                        micro_part += '+' + tz_split[1]
                                    clean_time = base_time + '.' + micro_part
                        date_taken = clean_time
                    else:
                        date_taken = creation_time
                except Exception as e:
                    logger.error(f"Error formatting creation_time '{creation_time}': {str(e)}")
                    date_taken = "Unknown (format error)"
            else:
                # Check stderr for creation time (ffmpeg often outputs metadata there)
                for line in stderr.splitlines():
                    if 'creation_time' in line.lower():
                        parts = line.split('creation_time')
                        if len(parts) > 1:
                            date_taken = parts[1].strip(':').strip().split(',')[0].strip()
                            break
        except Exception as e:
            logger.error(f"Error extracting video metadata: {e}")
    
    # Prepare GPS data for display
    gps_info = exif_info.get('GPSInfo', {})
    
    # Check if gps_info is a dictionary (it might be an int or another type in some cases)
    if not isinstance(gps_info, dict):
        logger.warning(f"GPS info is not a dictionary but {type(gps_info).__name__}: {gps_info}")
        gps_info = {}
        
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
    
    # Prepare GPS points for heatmap (list of [lat, lon])
    gps_points = []
    for e in reviewer.entries:
        try:
            lat = float(e.get('latitude', ''))
            lon = float(e.get('longitude', ''))
            if lat != 0.0 or lon != 0.0:
                gps_points.append([lat, lon])
        except Exception:
            continue
            
    # Get source type and proxy GPS status from session or determine from entries
    source_type = session.get('source_type', 'unknown')
    use_proxy = session.get('find_closest', False)
    has_proxy_gps = any(e.get('gps_source') == 'proxy' for e in reviewer.entries)
    
    # Create a file URL for direct access
    file_url = f"file:///{file_path.replace(os.sep, '/')}"
    
    return render_template('review.html',
                         image_url=os.path.basename(file_path),
                         file_url=file_url,
                         entry=entry,
                         media_type=media_type,
                         thumbnail_path=thumbnail_path,
                         current_index=reviewer.current_index + 1,
                         total_entries=len(reviewer.entries),
                         changes_made=reviewer.changes_made,
                         date_taken=date_taken,
                         latitude=latitude,
                         longitude=longitude,
                         file_location=os.path.abspath(file_path),
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
        logger.warning("Save attempt without initialized reviewer")
        return jsonify({'status': 'error', 'message': 'No reviewer initialized'})

    try:
        results = reviewer.save_all()
        changes_made = results['success']  # Assuming 'success' represents the number of changes made
        current_index = results['current_index']  # The index of the current image being saved
        total_entries = results['total_entries']  # The total number of images to save

        logger.info(f"Saved {results['success']} / {results['total']} entries.")
        return jsonify({
            'status': 'success',
            'message': f"Saved {results['success']} of {results['total']} entries.",
            'changes_made': changes_made,
            'current_index': current_index,
            'total_entries': total_entries,
            'details': results
        })
    except Exception as e:
        logger.error(f"Save failed: {e}", exc_info=True)
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

@app.route('/directories')
def directory_list():
    """Display available directories in data/photos"""
    photos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'photos')
    
    if not os.path.exists(photos_dir):
        logger.warning(f"Photos directory not found: {photos_dir}")
        flash("Photos directory not found.", "warning")
        return redirect(url_for('index'))
    
    try:
        # Get all directories within data/photos
        directories = []
        for item in os.listdir(photos_dir):
            item_path = os.path.join(photos_dir, item)
            if os.path.isdir(item_path):
                # Count image files
                file_count = 0
                for root, _, files in os.walk(item_path):
                    file_count += sum(1 for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.heic')))
                
                directories.append({
                    'name': item,
                    'path': os.path.abspath(item_path),
                    'file_count': file_count
                })
        
        logger.info(f"Found {len(directories)} directories in photos folder")
        return render_template('directory_list.html', directories=directories)
    except Exception as e:
        logger.error(f"Error listing photo directories: {e}", exc_info=True)
        flash(f"Error listing directories: {str(e)}", "error")
        return redirect(url_for('index'))

@app.route('/browse/<path:subpath>')
def browse_subdirectory(subpath):
    """Browse subdirectory structure in data/photos"""
    photos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'photos')
    
    # Handle empty subpath as root directory
    if not subpath:
        browse_path = photos_dir
    else:
        # Build the full path by joining photos_dir with subpath
        browse_path = os.path.join(photos_dir, subpath)
    
    # Validate the path exists and is within photos_dir for security
    if not os.path.exists(browse_path) or not os.path.isdir(browse_path):
        logger.warning(f"Directory not found or not a directory: {browse_path}")
        flash("Selected directory not found.", "error")
        return redirect(url_for('directory_list'))
    
    if not os.path.abspath(browse_path).startswith(os.path.abspath(photos_dir)):
        logger.warning(f"Attempted to access directory outside data/photos: {browse_path}")
        flash("For security reasons, only directories within data/photos can be processed.", "error")
        return redirect(url_for('directory_list'))
    
    try:
        # Get all subdirectories and image files in the current path
        subdirectories = []
        images = []
        
        for item in os.listdir(browse_path):
            item_path = os.path.join(browse_path, item)
            rel_path = os.path.relpath(item_path, photos_dir)
            
            if os.path.isdir(item_path):
                # Count images in the subdirectory
                image_count = 0
                for root, _, files in os.walk(item_path):
                    image_count += sum(1 for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.heic')))
                
                subdirectories.append({
                    'name': item,
                    'path': item_path,
                    'rel_path': rel_path,
                    'image_count': image_count
                })
            elif os.path.isfile(item_path):
                # Define supported extensions
                image_extensions = ('.jpg', '.jpeg', '.png', '.tiff')
                heic_extensions = ('.heic', '.heif')
                video_extensions = ('.mp4', '.mov', '.avi', '.mkv')
                
                file_lower = item.lower()
                
                # Check if it's a supported media file
                if (file_lower.endswith(image_extensions) or 
                    (file_lower.endswith(heic_extensions) and HEIF_SUPPORT) or 
                    file_lower.endswith(video_extensions)):
                    
                    # Get media info
                    gps = get_media_gps(item_path)
                    dt = get_media_datetime(item_path)
                    media_type = get_media_type(item_path)
                    
                    # Skip unsupported HEIC files if pillow-heif is not available
                    if file_lower.endswith(heic_extensions) and not HEIF_SUPPORT:
                        logger.warning(f"Skipping HEIC/HEIF file {item_path} - pillow-heif not available")
                        continue
                    
                    images.append({
                        'name': item,
                        'path': item_path,
                        'rel_path': rel_path,
                        'has_gps': gps is not None and gps != (0.0, 0.0),
                        'datetime': dt.isoformat() if dt else 'Unknown',
                        'media_type': media_type
                    })
        
        # Sort subdirectories and images by name
        subdirectories.sort(key=lambda x: x['name'].lower())
        images.sort(key=lambda x: x['name'].lower())
        
        # Get parent directory for breadcrumb navigation
        parent_path = os.path.dirname(browse_path)
        
        # Handle parent path correctly for both root and subdirectories
        if os.path.normpath(parent_path) == os.path.normpath(photos_dir):
            # Parent is the root photos directory
            parent_rel_path = ''
        elif parent_path.startswith(photos_dir):
            # Parent is a subdirectory
            parent_rel_path = os.path.relpath(parent_path, photos_dir)
        else:
            # Parent is outside the photos directory (shouldn't happen with validation)
            parent_rel_path = None
        
        # Create breadcrumbs for navigation
        breadcrumbs = []
        current_path = ''
        path_parts = subpath.split(os.sep)
        
        # Add root level
        breadcrumbs.append({
            'name': 'Root',
            'rel_path': ''
        })
        
        # Add intermediate paths
        for i, part in enumerate(path_parts[:-1]):
            current_path = os.path.join(current_path, part)
            breadcrumbs.append({
                'name': part,
                'rel_path': current_path
            })
        
        # Add current directory
        if path_parts:
            current_path = subpath
            breadcrumbs.append({
                'name': path_parts[-1],
                'rel_path': current_path,
                'is_current': True
            })
        
        return render_template(
            'directory_browser.html',
            current_path=browse_path,
            rel_path=subpath,
            subdirectories=subdirectories,
            images=images,
            breadcrumbs=breadcrumbs,
            parent_rel_path=parent_rel_path
        )
        
    except Exception as e:
        logger.error(f"Error browsing directory {browse_path}: {e}", exc_info=True)
        flash(f"Error browsing directory: {str(e)}", "error")
        return redirect(url_for('directory_list'))

@app.route('/scan/')
@app.route('/scan')
@app.route('/scan/<path:directory_path>')
def scan_photo_directory(directory_path=''):
    """Scan a specific directory from data/photos"""
    global reviewer
    
    photos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'photos')
    
    # Handle both absolute and relative paths
    if not directory_path:
        # Empty path means root directory
        scan_path = photos_dir
    elif os.path.isabs(directory_path):
        scan_path = directory_path
    else:
        scan_path = os.path.join(photos_dir, directory_path)
    
    # Validate directory exists and is within data/photos
    if not os.path.exists(scan_path) or not os.path.isdir(scan_path):
        logger.warning(f"Directory not found or not a directory: {scan_path}")
        flash("Selected directory not found.", "error")
        return redirect(url_for('directory_list'))
    
    if not os.path.abspath(scan_path).startswith(os.path.abspath(photos_dir)):
        logger.warning(f"Attempted to access directory outside data/photos: {scan_path}")
        flash("For security reasons, only directories within data/photos can be processed.", "error")
        return redirect(url_for('directory_list'))
    
    # Get URL parameters for options
    find_closest = request.args.get('find_closest', 'false').lower() == 'true'
    time_frame = int(request.args.get('time_frame', '1'))
    hide_with_gps = request.args.get('hide_with_gps', 'false').lower() == 'true'  # Default to false
    
    try:
        logger.info(f"Scanning directory: {scan_path}")
        
        if find_closest:
            entries = scan_directory_with_closest(scan_path, time_frame)
            if hide_with_gps:
                # Only show images without original GPS (only proxy GPS)
                entries = [e for e in entries if e.get('gps_source') == 'proxy']
            else:
                # Show all images (with or without GPS)
                for e in entries:
                    if '__include_if_not_hide_gps' in e:
                        del e['__include_if_not_hide_gps']
        else:
            media_files = scan_directory_for_media(scan_path)
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
            if hide_with_gps:
                # Only show images without GPS
                entries = [e for e in entries if not e['latitude'] or not e['longitude']]
                
        if not entries:
            logger.warning(f"No images found for review in {scan_path}")
            flash("No images found for review in the selected directory.", "warning")
            return redirect(url_for('directory_list'))
            
        reviewer = Reviewer.from_entries(entries)
        # Set session variables for tracking source type
        session['source_type'] = 'directory'
        session['find_closest'] = find_closest
        session['has_proxy_gps'] = any(entry.get('gps_source') == 'proxy' for entry in reviewer.entries)
        
        logger.info(f"Starting review with {len(entries)} entries")
        return redirect(url_for('review'))
        
    except Exception as e:
        logger.error(f"Error scanning directory {scan_path}: {e}", exc_info=True)
        flash(f"Error scanning directory: {str(e)}", "error")
        return redirect(url_for('directory_list'))

@app.route('/scan_directory', methods=['POST'])
def scan_directory():
    global reviewer
    data = request.get_json()
    file_list = data.get('file_list')
    directory = data.get('directory')
    find_closest = data.get('find_closest', False)
    time_frame = data.get('time_frame', 1)
    hide_with_gps = data.get('hide_with_gps', False)  # Default to false (show all images by default)
    
    # Validate that the directory is within data/photos for security
    photos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'photos')
    
    # Check if directory is in data/photos
    if directory and not directory.startswith(photos_dir):
        logger.warning(f"Attempted to access directory outside data/photos: {directory}")
        return jsonify({
            'status': 'error',
            'message': 'For security reasons, only directories within data/photos can be processed.'
        }), 400

    # If file_list is provided (from folder picker), use it. Otherwise, fall back to directory scan.
    if file_list and isinstance(file_list, list) and len(file_list) > 0:
        # file_list contains relative paths (webkitRelativePath), but we need absolute paths
        # Assume all files are under the same root (the first path's root)
        # Try to reconstruct the root directory from the first file
        first_path = file_list[0]
        # Remove the relative part to get the root directory
        # e.g. Edenred-100.jpg or subfolder/IMG_001.jpg
        # The user selects a folder, so the files are relative to that folder
        # Use the directory as the root directory
        root_dir = directory
        abs_file_paths = [os.path.join(root_dir, rel_path) for rel_path in file_list]
        logger.debug(f"Received file_list with {len(abs_file_paths)} files. Root dir: {root_dir}")

        # Only process files that exist
        abs_file_paths = [f for f in abs_file_paths if os.path.exists(f)]
        if not abs_file_paths:
            logger.warning("No valid files found in the selected directory")
            return jsonify({'status': 'error', 'message': 'No valid files found in the selected directory.'}), 200

        # Build media_files list as in scan_directory_for_media
        media_files = []
        for file_path in abs_file_paths:
            if file_path.lower().endswith(('.jpg', '.jpeg')):
                dt = get_media_datetime(file_path)
                gps = get_media_gps(file_path)
                logger.debug(f"File: {file_path}\n  Datetime: {dt}\n  GPS: {gps}")
                media_files.append({
                    'path': file_path,
                    'datetime': dt,
                    'gps': gps
                })

        if find_closest:
            # Use the same logic as scan_directory_with_closest, but only for the selected files
            gps_files = [m for m in media_files if m['gps'] is not None and m['gps'] != (0.0, 0.0)]
            logger.debug(f"Reference files with valid GPS: {len(gps_files)}")
            for media in media_files:
                if (media['gps'] is None or media['gps'] == (0.0, 0.0)) and media['datetime'] is not None:
                    logger.debug(f"Looking for proxy GPS for: {media['path']}")
                    proxy_gps = find_closest_gps(gps_files, media, time_frame)
                    if proxy_gps and proxy_gps != (0.0, 0.0):
                        logger.debug(f"Assigned proxy GPS {proxy_gps} to {media['path']}")
                        media['gps'] = proxy_gps
                    else:
                        logger.debug(f"No proxy GPS assigned to {media['path']}")
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
                logger.debug(f"Entry for review: {entry}")
                entries.append(entry)
            elif orig_gps and orig_gps != (0.0, 0.0):
                # Already has GPS
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
                entry['__include_if_not_hide_gps'] = True
                entries.append(entry)

        if hide_with_gps:
            # Only keep entries without original GPS
            entries = [e for e in entries if e.get('gps_source') != 'original']
        else:
            # Remove marker key
            for e in entries:
                if '__include_if_not_hide_gps' in e:
                    del e['__include_if_not_hide_gps']

        if not entries:
            logger.warning("No images found for review after filtering")
            return jsonify({'status': 'error', 'message': 'No images found for review.'}), 200
        reviewer = Reviewer.from_entries(entries)
        logger.info(f"Starting review with {len(entries)} entries")
        return jsonify({'status': 'success', 'redirect': url_for('review')}), 200

    # Fallback: legacy directory scan
    if not directory or not os.path.isdir(directory):
        return jsonify({'status': 'error', 'message': 'Invalid or missing directory'}), 400
    try:
        if find_closest:
            entries = scan_directory_with_closest(directory, time_frame)
            if hide_with_gps:
                entries = [e for e in entries if e.get('gps_source') == 'proxy']
            else:
                for e in entries:
                    if '__include_if_not_hide_gps' in e:
                        del e['__include_if_not_hide_gps']
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
            if hide_with_gps:
                entries = [e for e in entries if not e['latitude'] or not e['longitude']]
        if not entries:
            return jsonify({'status': 'error', 'message': 'No images found for review.'}), 200
        reviewer = Reviewer.from_entries(entries)
        return jsonify({'status': 'success', 'redirect': url_for('review')}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Add route to get available photo directories from data/photos
@app.route('/get_photo_directories')
def get_photo_directories():
    photos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'photos')
    
    if not os.path.exists(photos_dir):
        logger.warning(f"Photos directory not found: {photos_dir}")
        return jsonify({'directories': []})
    
    try:
        # Get all directories within data/photos
        directories = []
        for item in os.listdir(photos_dir):
            item_path = os.path.join(photos_dir, item)
            if os.path.isdir(item_path):
                abs_path = os.path.abspath(item_path)
                rel_path = os.path.relpath(item_path, os.path.dirname(os.path.abspath(__file__)))
                directories.append({
                    'name': item,
                    'path': abs_path,
                    'rel_path': rel_path
                })
        
        logger.info(f"Found {len(directories)} directories in photos folder")
        return jsonify({'directories': directories})
    except Exception as e:
        logger.error(f"Error listing photo directories: {e}", exc_info=True)
        return jsonify({'directories': [], 'error': str(e)})

@app.route('/image/<path:filepath>')
def serve_image(filepath):
    """Serve an image or thumbnail directly from its filepath"""
    # Security check: ensure path doesn't go outside data directory unless it's a temp thumbnail
    photos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'photos')
    temp_dir = app.config['TEMP_FOLDER']
    
    try:
        # Handle both absolute paths and relative paths
        if os.path.isabs(filepath):
            full_path = filepath
        else:
            full_path = os.path.normpath(os.path.join(photos_dir, filepath))
        
        # Fix long paths on Windows
        full_path = fix_long_path(full_path)
        
        # Allow temp directory for thumbnails of videos
        is_in_temp = os.path.abspath(full_path).startswith(os.path.abspath(temp_dir))
        is_in_photos = os.path.abspath(full_path).startswith(os.path.abspath(photos_dir))
        
        if not (is_in_photos or is_in_temp):
            logger.warning(f"Attempted to access file outside allowed directories: {full_path}")
            return "Access denied", 403
            
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            logger.warning(f"Requested file not found: {full_path}")
            return "File not found", 404
            
        # For thumbnails in temp directory
        if is_in_temp and "thumb_" in os.path.basename(full_path):
            directory = os.path.dirname(full_path)
            filename = os.path.basename(full_path)
            return send_from_directory(directory, filename)
            
        # For HEIC files, convert to JPEG on-the-fly if supported
        if full_path.lower().endswith(('.heic', '.heif')) and HEIF_SUPPORT:
            try:
                # Create a temporary JPEG version
                temp_jpeg = os.path.join(
                    app.config['TEMP_FOLDER'], 
                    f"convert_{os.path.basename(full_path)}_{hash(full_path)}.jpg"
                )
                
                # Check if already converted
                if not os.path.exists(temp_jpeg):
                    # Convert HEIC to JPEG
                    img = Image.open(full_path)
                    img.save(temp_jpeg, format='JPEG', quality=90)
                
                return send_from_directory(os.path.dirname(temp_jpeg), os.path.basename(temp_jpeg))
            except Exception as e:
                logger.error(f"Error converting HEIC file {full_path}: {e}")
        
        # For regular files in photos directory
        directory = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        
        return send_from_directory(directory, filename)
    except Exception as e:
        logger.error(f"Error serving image {filepath}: {e}")
        return "Error serving image", 500

@app.route('/csv_list')
def csv_list():
    """Display available CSV files in data/csv"""
    csv_dir = app.config['CSV_FOLDER']
    
    if not os.path.exists(csv_dir):
        logger.warning(f"CSV directory not found: {csv_dir}")
        flash("CSV directory not found.", "warning")
        return redirect(url_for('index'))
    
    try:
        # Get all CSV files within data/csv
        csv_files = []
        for item in os.listdir(csv_dir):
            item_path = os.path.join(csv_dir, item)
            if os.path.isfile(item_path) and item.lower().endswith('.csv'):
                # Get file stats
                stats = os.stat(item_path)
                modified_time = datetime.fromtimestamp(stats.st_mtime)
                
                # Get row count (excluding header)
                row_count = 0
                try:
                    with open(item_path, 'r', encoding='utf-8') as f:
                        row_count = sum(1 for _ in csv.reader(f)) - 1  # Subtract header
                except Exception as e:
                    logger.warning(f"Could not read row count for {item_path}: {e}")
                
                csv_files.append({
                    'name': item,
                    'path': os.path.abspath(item_path),
                    'size': stats.st_size,
                    'modified': modified_time,
                    'row_count': max(0, row_count)  # Ensure we don't show negative counts
                })
        
        # Sort by modified date (newest first)
        csv_files.sort(key=lambda x: x['modified'], reverse=True)
        
        logger.info(f"Found {len(csv_files)} CSV files in CSV folder")
        return render_template('csv_list.html', csv_files=csv_files)
    except Exception as e:
        logger.error(f"Error listing CSV files: {e}", exc_info=True)
        flash(f"Error listing CSV files: {str(e)}", "error")
        return redirect(url_for('index'))

@app.route('/load_csv/<csv_filename>')
def load_csv(csv_filename):
    """Load a specific CSV file from data/csv"""
    global reviewer
    
    csv_dir = app.config['CSV_FOLDER']
    csv_path = os.path.join(csv_dir, csv_filename)
    
    # Validate file exists and is within data/csv
    if not os.path.exists(csv_path) or not os.path.isfile(csv_path):
        logger.warning(f"CSV file not found: {csv_path}")
        flash("Selected CSV file not found.", "error")
        return redirect(url_for('csv_list'))
    
    if not csv_path.startswith(csv_dir):
        logger.warning(f"Attempted to access CSV file outside data/csv: {csv_path}")
        flash("For security reasons, only CSV files within data/csv can be processed.", "error")
        return redirect(url_for('csv_list'))
    
    try:
        logger.info(f"Loading CSV file: {csv_path}")
        reviewer = Reviewer.from_csv(csv_path)
        
        if not reviewer.entries:
            logger.warning(f"CSV file is empty or invalid: {csv_path}")
            flash('CSV file is empty or invalid', 'warning')
            return redirect(url_for('csv_list'))
        
        # Set session variables for tracking source type
        session['source_type'] = 'csv'
        session['find_closest'] = False
        session['has_proxy_gps'] = any(entry.get('gps_source') == 'proxy' for entry in reviewer.entries)
        
        logger.info(f"Starting review with {len(reviewer.entries)} entries from CSV")
        flash(f"Loaded {len(reviewer.entries)} entries from CSV", "success")
        return redirect(url_for('review'))
        
    except Exception as e:
        logger.error(f"Error loading CSV file {csv_path}: {e}", exc_info=True)
        flash(f"Error loading CSV file: {str(e)}", "error")
        return redirect(url_for('csv_list'))

@app.route('/browse/')
@app.route('/browse')
def browse_root():
    """Browse the root directory of data/photos"""
    # Redirect to the browse_subdirectory function with an empty subpath
    return browse_subdirectory('')

def get_video_thumbnail(video_path):
    """Generate a thumbnail for a video file using ffmpeg."""
    try:
        # Fix long path issue on Windows
        video_path = fix_long_path(video_path)
        
        # Check if file exists
        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return None
            
        # Create a unique temporary file for the thumbnail
        thumb_file = os.path.join(
            app.config['TEMP_FOLDER'], 
            f"thumb_{os.path.basename(video_path)}_{hash(video_path)}.jpg"
        )
        
        # Use FFmpeg to extract a frame at 1 second
        ffmpeg_command = [
            'ffmpeg', '-y', '-i', video_path, 
            '-ss', '00:00:01.000', '-vframes', '1',
            '-vf', 'scale=640:-1',
            thumb_file
        ]
        
        # Run the command
        result = subprocess.run(
            ffmpeg_command, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"Error generating thumbnail for {video_path}: {result.stderr}")
            # Try at 0 seconds if 1 second fails
            ffmpeg_command[4] = '00:00:00.000'
            result = subprocess.run(
                ffmpeg_command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            if result.returncode != 0:
                logger.error(f"Failed again to generate thumbnail: {result.stderr}")
                return None
        
        # Check if thumbnail was created
        if os.path.exists(thumb_file):
            logger.debug(f"Generated thumbnail for {video_path} at {thumb_file}")
            return thumb_file
        else:
            logger.error(f"Thumbnail file not created: {thumb_file}")
            return None
            
    except Exception as e:
        logger.error(f"Error creating video thumbnail: {str(e)}")
        return None

def is_media_file(file_path):
    """Check if the file is a supported media file (image, HEIC, or video)."""
    file_lower = file_path.lower()
    image_extensions = ('.jpg', '.jpeg', '.png', '.tiff')
    heic_extensions = ('.heic', '.heif')
    video_extensions = ('.mp4', '.mov', '.avi', '.mkv')
    
    # Check if it's a standard image format
    if file_lower.endswith(image_extensions):
        return 'image'
    # Check if it's a HEIC/HEIF file
    elif file_lower.endswith(heic_extensions) and HEIF_SUPPORT:
        return 'heic'
    # Check if it's a video file
    elif file_lower.endswith(video_extensions):
        return 'video'
    else:
        return None

def get_media_type(file_path):
    """Determine the type of media file."""
    media_type = is_media_file(file_path)
    if media_type:
        logger.debug(f"Media type for {file_path}: {media_type}")
    else:
        logger.debug(f"Not a supported media file: {file_path}")
    return media_type

if __name__ == "__main__":
    try:
        # Start the Flask application
        logger.info("Starting Flask application on http://0.0.0.0:5000")
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"Error starting the application: {str(e)}")
        import traceback
        traceback.print_exc()