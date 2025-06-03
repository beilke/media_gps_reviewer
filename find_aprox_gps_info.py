import os
import subprocess
import json
from PIL import Image, UnidentifiedImageError
import exifread
from datetime import datetime, timedelta
import pytz
import csv

def get_media_datetime(file_path):
    """Extract datetime from media file."""
    try:
        # For images
        with open(file_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            if 'EXIF DateTimeOriginal' in tags:
                dt_str = str(tags['EXIF DateTimeOriginal'])
                return datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S').replace(tzinfo=pytz.UTC)
    except Exception:
        pass

    # For videos
    metadata = get_video_metadata(file_path)
    if metadata:
        try:
            tags = metadata.get('format', {}).get('tags', {})
            creation_time = tags.get('creation_time')
            if creation_time:
                return datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
        except Exception:
            pass

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

def get_video_metadata(file_path):
    """Use ffprobe to extract metadata from video."""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', file_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return json.loads(result.stdout)
    except Exception:
        return None

def scan_directory_for_media(directory):
    """Scan a directory and return all media files with their datetime and GPS info."""
    media_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.tiff', '.mp4', '.mov', '.avi', '.mkv')):
                print(f"Processing: {file_path}")
                dt = get_media_datetime(file_path)
                gps = get_media_gps(file_path)
                media_files.append({
                    'path': file_path,
                    'datetime': dt,
                    'gps': gps  # Will be None if no valid GPS found
                })
            else:
                print(f"Skipping (unrecognized): {file_path}")
    return media_files

def find_closest_gps(media_files, target_file, time_window_hours=1):
    """Find closest media file with valid GPS within a time window."""
    target_dt = target_file['datetime']
    if not target_dt:
        return None
        
    time_window = timedelta(hours=time_window_hours)
    closest_gps = None
    min_time_diff = None
    
    for media in media_files:
        if is_valid_gps(media['gps']) and media['datetime']:
            time_diff = abs((target_dt - media['datetime']).total_seconds())
            if time_diff <= time_window.total_seconds():
                if min_time_diff is None or time_diff < min_time_diff:
                    min_time_diff = time_diff
                    closest_gps = media['gps']
                    print(f"Found potential GPS match: {media['path']} with GPS {closest_gps} (time diff: {time_diff/60:.1f} minutes)")
    
    return closest_gps

def process_directory(directory, time_window_hours=1):
    """Process media files and assign GPS coordinates."""
    media_files = scan_directory_for_media(directory)
    
    for media in media_files:
        if not is_valid_gps(media['gps']) and media['datetime'] is not None:
            media['gps'] = find_closest_gps(media_files, media, time_window_hours)
    
    return media_files

def save_results(media_files, output_file):
    """Save processed results to CSV."""
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['path', 'datetime', 'latitude', 'longitude', 'gps_source']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for media in media_files:
            original_gps = get_media_gps(media['path'])
            gps_source = 'original' if media['gps'] == original_gps else 'proxy'
            writer.writerow({
                'path': media['path'],
                'datetime': media['datetime'].isoformat() if media['datetime'] else '',
                'latitude': media['gps'][0] if is_valid_gps(media['gps']) else '',
                'longitude': media['gps'][1] if is_valid_gps(media['gps']) else '',
                'gps_source': gps_source if is_valid_gps(media['gps']) else 'none'
            })

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Process media files and assign GPS coordinates.")
    parser.add_argument("directory", help="Directory to scan for media files.")
    parser.add_argument("--output", help="Output CSV file to save results.", required=True)
    parser.add_argument("--time-window", type=float, default=1.0,
                       help="Time window in hours to search for GPS matches (default: 1 hour)")
    args = parser.parse_args()

    print(f"Scanning {args.directory} for media files...")
    media_files = process_directory(args.directory, args.time_window)
    
    files_with_gps = sum(1 for m in media_files if is_valid_gps(m['gps']))
    files_with_original_gps = sum(1 for m in media_files if m['gps'] == get_media_gps(m['path']) and is_valid_gps(m['gps']))
    files_with_proxy_gps = files_with_gps - files_with_original_gps
    
    print(f"\nProcessed {len(media_files)} media files:")
    print(f"- {files_with_gps} files with valid GPS coordinates")
    print(f"  - {files_with_original_gps} with original GPS")
    print(f"  - {files_with_proxy_gps} with proxy GPS")
    print(f"- {len(media_files) - files_with_gps} files without GPS coordinates")
    
    save_results(media_files, args.output)
    print(f"\nResults saved to {args.output}")