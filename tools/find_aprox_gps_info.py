import os
import subprocess
import json
import sys
from PIL import Image, UnidentifiedImageError
import exifread
from datetime import datetime, timedelta
import pytz
import csv
import platform
from log_utils import setup_logger

# Set up logger
logger = setup_logger('find_aprox_gps_info')

# Handle Windows long path issue
if platform.system() == 'Windows':
    try:
        # Enable long path support on Windows
        import ctypes
        from ctypes import wintypes
        ntdll = ctypes.WinDLL('ntdll')
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        
        # Define the function to enable long paths
        try:
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
        except Exception:
            logger.warning("Windows long path API not available")
            def fix_long_path(path):
                return path
    except Exception:
        logger.warning("Could not import Windows-specific modules")
        def fix_long_path(path):
            return path
else:
    # For non-Windows systems, no change needed
    def fix_long_path(path):
        return path

# Import pillow-heif for HEIC support
try:
    import pillow_heif
    # Register the HEIF opener with PIL
    pillow_heif.register_heif_opener()
    HEIF_SUPPORT = True
    logger.info("pillow-heif successfully loaded. HEIC/HEIF files will be supported.")
except ImportError:
    HEIF_SUPPORT = False
    logger.warning("pillow-heif not available. HEIC/HEIF files may not be properly processed.")

def get_media_datetime(file_path):
    """Extract datetime from media file."""
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
            metadata = get_video_metadata(file_path)
            if metadata:
                tags = metadata.get('format', {}).get('tags', {})
                creation_time = tags.get('creation_time')
                if creation_time:
                    return datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                else:
                    logger.debug(f"No creation_time found in video metadata for {file_path}")
    except Exception as e:
        logger.error(f"Error extracting datetime from video {file_path}: {str(e)}")

    logger.debug(f"Could not extract datetime from {file_path}")
    return None

def is_valid_gps(gps_coord):
    """Check if GPS coordinates are valid and not (0,0)."""
    if not gps_coord:
        return False
    lat, lon = gps_coord
    return (-90 <= lat <= 90) and (-180 <= lon <= 180) and (lat, lon) != (0.0, 0.0)

def get_media_gps(file_path):
    """Extract GPS coordinates from media file if available."""
    try:
        # Fix long path issue on Windows
        file_path = fix_long_path(file_path)
        
        # Check if file exists before processing
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None
        
        file_lower = file_path.lower()
        
        # Handle HEIC files specifically with pillow-heif if available
        if file_lower.endswith(('.heic', '.heif')) and HEIF_SUPPORT:
            try:
                # pillow-heif allows opening HEIC files directly via PIL
                img = Image.open(file_path)
                exif_data = img.getexif()
                
                # EXIF tags for GPS information
                gps_info = img.getexif().get_ifd(0x8825)
                if gps_info:
                    # Convert GPS coordinates to decimal degrees
                    lat_ref = gps_info.get(1, 'N')  # 1 is GPSLatitudeRef
                    lat = gps_info.get(2)           # 2 is GPSLatitude
                    lon_ref = gps_info.get(3, 'E')  # 3 is GPSLongitudeRef
                    lon = gps_info.get(4)           # 4 is GPSLongitude
                    
                    if lat and lon:
                        # Convert degrees, minutes, seconds to decimal
                        lat_d, lat_m, lat_s = lat
                        lat_decimal = float(lat_d) + float(lat_m)/60 + float(lat_s)/3600
                        if lat_ref == 'S':
                            lat_decimal = -lat_decimal
                            
                        lon_d, lon_m, lon_s = lon
                        lon_decimal = float(lon_d) + float(lon_m)/60 + float(lon_s)/3600
                        if lon_ref == 'W':
                            lon_decimal = -lon_decimal
                            
                        if is_valid_gps((lat_decimal, lon_decimal)):
                            return (lat_decimal, lon_decimal)
                            
                logger.debug(f"No GPS data found in HEIC/HEIF file: {file_path}")
                return None
            except Exception as e:
                logger.error(f"Error processing GPS from HEIC/HEIF file {file_path}: {str(e)}")
                return None
            
        # Check if it's a video file (MOV, MP4, etc.)
        if file_lower.endswith(('.mov', '.mp4', '.avi', '.mkv')): 
            # Handle path with spaces or special characters
            if ' ' in file_path or any(c in file_path for c in '()[]&$;,'):
                logger.debug(f"Path contains spaces or special characters: {file_path}")
            
            # Use FFmpeg to extract metadata, including GPS coordinates
            try:
                # Just pass the path directly - subprocess handles escaping
                ffmpeg_command = [
                    'ffmpeg', '-i', file_path, '-f', 'ffmetadata', '-']
                result = subprocess.run(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                metadata = result.stdout

                # Check for errors
                if result.stderr and "error" in result.stderr.lower():
                    logger.error(f"Error with file {file_path}: {result.stderr}")
                    return None
            except Exception as e:
                logger.error(f"FFmpeg execution error for {file_path}: {str(e)}")
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
                        # If ref tags are missing, infer them from coordinate signs
                        logger.info(f"Missing GPS ref tags in {file_path}, inferring from coordinate signs")
                        # We'll just use the coordinates as they are, assuming positive is N/E

                    if is_valid_gps((lat, lon)):
                        return (lat, lon)
                    else:
                        logger.warning(f"Invalid GPS coordinates skipped: {lat}, {lon}")
                        return None

    except Exception as e:
        logger.error(f"Error extracting GPS: {e}")
    return None

def get_video_metadata(file_path):
    """Use ffprobe to extract metadata from video."""
    try:
        # Fix long path issue on Windows
        file_path = fix_long_path(file_path)
        
        # Check if file exists before processing
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None
        
        # Handle path for subprocess
        if ' ' in file_path or any(c in file_path for c in '()[]&$;,'):
            # Don't quote the path in the list - subprocess will handle it properly
            logger.debug(f"Path contains spaces or special characters: {file_path}")
        
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', file_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if result.stderr:
            logger.error(f"ffprobe error for {file_path}: {result.stderr}")
        
        if not result.stdout:
            logger.error(f"No output from ffprobe for {file_path}")
            return None
            
        return json.loads(result.stdout)
    except Exception as e:
        logger.error(f"Error in get_video_metadata for {file_path}: {str(e)}")
        return None

def scan_directory_for_media(directory):
    """Scan a directory and return all media files with their datetime and GPS info."""
    media_files = []
    
    # Fix long path issue on Windows
    directory = fix_long_path(directory)
    
    # Verify directory exists
    if not os.path.exists(directory):
        logger.error(f"Directory does not exist: {directory}")
        return media_files
        
    # Define supported extensions
    image_extensions = ('.jpg', '.jpeg', '.png', '.tiff')
    heic_extensions = ('.heic', '.heif')
    video_extensions = ('.mp4', '.mov', '.avi', '.mkv')
    
    all_supported_extensions = image_extensions + video_extensions
    if HEIF_SUPPORT:
        all_supported_extensions += heic_extensions
    
    logger.info(f"Scanning directory: {directory}")
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            
            # Fix long paths
            file_path = fix_long_path(file_path)
            file_lower = file_path.lower()
            
            # Skip unsupported HEIC files if pillow-heif is not available
            if not HEIF_SUPPORT and file_lower.endswith(heic_extensions):
                logger.warning(f"Skipping HEIC/HEIF file {file_path} - pillow-heif not available")
                continue
                
            # Check file extension
            if file_lower.endswith(all_supported_extensions):
                try:
                    logger.debug(f"Processing: {file_path}")
                    dt = get_media_datetime(file_path)
                    gps = get_media_gps(file_path)
                    media_files.append({
                        'path': file_path,
                        'datetime': dt,
                        'gps': gps  # Will be None if no valid GPS found
                    })
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {str(e)}")
            else:
                logger.debug(f"Skipping (unrecognized extension): {file_path}")
    
    logger.info(f"Found {len(media_files)} media files in {directory}")
    return media_files

def find_closest_gps(media_files, target_file, time_window_hours=1):
    """Find closest media file with valid GPS within a time window."""
    try:
        target_dt = target_file['datetime']
        if not target_dt:
            logger.debug(f"No datetime for target file: {target_file['path']}")
            return None
            
        time_window = timedelta(hours=time_window_hours)
        closest_gps = None
        min_time_diff = None
        source_path = None
        
        for media in media_files:
            # Skip files that don't exist anymore
            if not os.path.exists(media['path']):
                continue
                
            # Skip comparing to self
            if media['path'] == target_file['path']:
                continue
                
            # Look for valid GPS data with datetime
            if is_valid_gps(media['gps']) and media['datetime']:
                try:
                    time_diff = abs((target_dt - media['datetime']).total_seconds())
                    if time_diff <= time_window.total_seconds():
                        if min_time_diff is None or time_diff < min_time_diff:
                            min_time_diff = time_diff
                            closest_gps = media['gps']
                            source_path = media['path']
                except Exception as e:
                    logger.error(f"Error calculating time difference: {str(e)}")
        
        # Log the result
        if closest_gps:
            logger.info(f"Found GPS match for {target_file['path']}: using {source_path} with GPS {closest_gps} (time diff: {min_time_diff/60:.1f} minutes)")
        else:
            logger.debug(f"No GPS match found for {target_file['path']} within {time_window_hours} hour window")
            
        return closest_gps
    except Exception as e:
        logger.error(f"Error finding closest GPS for {target_file.get('path', 'unknown')}: {str(e)}")
        return None

def process_directory(directory, time_window_hours=1):
    """Process media files and assign GPS coordinates."""
    # Verify directory exists and is accessible
    if not os.path.exists(directory):
        logger.error(f"Directory does not exist: {directory}")
        return []
        
    if not os.access(directory, os.R_OK):
        logger.error(f"Directory is not readable: {directory}")
        return []
    
    # Scan for media files
    media_files = scan_directory_for_media(directory)
    logger.info(f"Found {len(media_files)} media files to process")
    
    # Process files without GPS data
    files_processed = 0
    for media in media_files:
        try:
            # Skip files that don't exist anymore
            if not os.path.exists(media['path']):
                logger.warning(f"File no longer exists, skipping: {media['path']}")
                continue
                
            if not is_valid_gps(media['gps']) and media['datetime'] is not None:
                media['gps'] = find_closest_gps(media_files, media, time_window_hours)
                if is_valid_gps(media['gps']):
                    files_processed += 1
        except Exception as e:
            logger.error(f"Error processing {media['path']}: {str(e)}")
    
    logger.info(f"Added proxy GPS data to {files_processed} files")
    return media_files

def save_results(media_files, output_file):
    """Save processed results to CSV."""
    try:
        # Ensure output goes to the data/csv directory
        csv_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'csv')
        os.makedirs(csv_dir, exist_ok=True)
        
        # If output_file is not an absolute path, place it in the CSV directory
        if not os.path.isabs(output_file):
            output_file = os.path.join(csv_dir, output_file)
        
        logger.info(f"Saving results to {output_file}")
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['path', 'datetime', 'latitude', 'longitude', 'gps_source']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for media in media_files:
                try:
                    # Skip files that don't exist anymore
                    if not os.path.exists(media['path']):
                        logger.warning(f"File no longer exists, skipping CSV entry: {media['path']}")
                        continue
                        
                    original_gps = get_media_gps(media['path'])
                    gps_source = 'original' if media['gps'] == original_gps else 'proxy'
                    
                    writer.writerow({
                        'path': media['path'],
                        'datetime': media['datetime'].isoformat() if media['datetime'] else '',
                        'latitude': media['gps'][0] if is_valid_gps(media['gps']) else '',
                        'longitude': media['gps'][1] if is_valid_gps(media['gps']) else '',
                        'gps_source': gps_source if is_valid_gps(media['gps']) else 'none'
                    })
                except Exception as e:
                    logger.error(f"Error writing CSV row for {media['path']}: {str(e)}")
        
        logger.info(f"Successfully saved {len(media_files)} entries to {output_file}")
    except Exception as e:
        logger.error(f"Error saving results to CSV: {str(e)}")
        raise

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Process media files and assign GPS coordinates.")
    parser.add_argument("directory", help="Directory to scan for media files.")
    parser.add_argument("--output", help="Output CSV file to save results.", required=True)
    parser.add_argument("--time-window", type=float, default=1.0,
                       help="Time window in hours to search for GPS matches (default: 1 hour)")
    args = parser.parse_args()

    try:
        # Check if directory exists
        if not os.path.exists(args.directory):
            logger.error(f"Directory does not exist: {args.directory}")
            sys.exit(1)
            
        # Check if directory is readable
        if not os.access(args.directory, os.R_OK):
            logger.error(f"Directory is not readable: {args.directory}")
            sys.exit(1)
            
        logger.info(f"Starting find_aprox_gps_info with directory: {args.directory}, time window: {args.time_window} hours")
        logger.info(f"Scanning {args.directory} for media files...")
        
        # Process directory
        media_files = process_directory(args.directory, args.time_window)
        
        # If no media files found, log and exit
        if not media_files:
            logger.warning(f"No media files found in {args.directory}")
            sys.exit(0)
        
        # Count files with GPS
        files_with_gps = sum(1 for m in media_files if is_valid_gps(m['gps']))
        
        # Only count original GPS if the files still exist
        files_with_original_gps = sum(1 for m in media_files 
                                     if os.path.exists(m['path']) and 
                                     m['gps'] == get_media_gps(m['path']) and 
                                     is_valid_gps(m['gps']))
                                     
        files_with_proxy_gps = files_with_gps - files_with_original_gps
        
        logger.info(f"Processed {len(media_files)} media files:")
        logger.info(f"- {files_with_gps} files with valid GPS coordinates")
        logger.info(f"  - {files_with_original_gps} with original GPS")
        logger.info(f"  - {files_with_proxy_gps} with proxy GPS")
        logger.info(f"- {len(media_files) - files_with_gps} files without GPS coordinates")
        
        # Save results
        save_results(media_files, args.output)
        logger.info(f"Results saved to {args.output}")
    except Exception as e:
        logger.exception(f"Error during processing: {str(e)}")
        print(f"\nError: {str(e)}")
        print("\nTroubleshooting suggestions:")
        print(" - Check if the path contains spaces or special characters")
        print(" - For Windows long path issues, try using the fix_file_paths.py tool")
        print(" - For video files, verify they can be read with:")
        print(f"   python tools/fix_file_paths.py \"{args.directory}\" --check-video")
        print(" - If running in Docker, convert the path with:")
        print(f"   python tools/fix_file_paths.py \"{args.directory}\"")
        print(" - Check the log file for detailed error messages")
        sys.exit(1)