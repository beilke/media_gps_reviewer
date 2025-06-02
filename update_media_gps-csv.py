import os
import subprocess
import json
from PIL import Image, UnidentifiedImageError, ImageFile
import exifread
from datetime import datetime, timedelta
import pytz
import csv
import argparse
import sys
import piexif
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

# Allow loading of truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = True

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

def get_media_gps(file_path):
    """Extract GPS coordinates from media file if available."""
    try:
        with open(file_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            
            # Check if all required GPS tags exist
            required_tags = [
                'GPS GPSLatitude',
                'GPS GPSLongitude',
                'GPS GPSLatitudeRef',
                'GPS GPSLongitudeRef'
            ]
            
            # If any required tag is missing, return None
            if not all(tag in tags for tag in required_tags):
                return None
                
            try:
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

                # Check for (0,0) coordinates and treat as invalid
                if abs(lat) < 0.0001 and abs(lon) < 0.0001:
                    return None

                return (lat, lon)
                
            except (AttributeError, IndexError, ValueError, TypeError) as e:
                print(f"Error parsing GPS data in {file_path}: {str(e)}")
                return None
                
    except Exception as e:
        # Only print errors that aren't about missing tags
        if not isinstance(e, KeyError) or 'GPS ' not in str(e):
            print(f"Error processing {file_path}: {str(e)}")
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

def get_video_gps(file_path):
    """Extract GPS coordinates from video metadata."""
    try:
        metadata = get_video_metadata(file_path)
        if metadata:
            # Check format tags first
            format_tags = metadata.get('format', {}).get('tags', {})
            location = format_tags.get('location')
            if location:
                # Parse location string (format may vary: "+38.0000-009.0000/" or "38.0000,-009.0000")
                if ',' in location:
                    lat, lon = map(float, location.split(','))
                else:
                    # Handle format like +38.0000-009.0000/
                    loc = location.strip('/')
                    # Find where the sign changes between lat and lon
                    sign_pos = max(loc.find('+', 1), loc.find('-', 1))
                    if sign_pos > 0:
                        lat = float(loc[:sign_pos])
                        lon = float(loc[sign_pos:])
                    else:
                        return None
                
                # Validate coordinates
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return (lat, lon)
            
            # Check stream metadata if not found in format tags
            for stream in metadata.get('streams', []):
                stream_tags = stream.get('tags', {})
                location = stream_tags.get('location')
                if location:
                    # Same parsing logic as above
                    if ',' in location:
                        lat, lon = map(float, location.split(','))
                    else:
                        loc = location.strip('/')
                        sign_pos = max(loc.find('+', 1), loc.find('-', 1))
                        if sign_pos > 0:
                            lat = float(loc[:sign_pos])
                            lon = float(loc[sign_pos:])
                        else:
                            continue
                    
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        return (lat, lon)
                    
    except Exception as e:
        print(f"Error extracting video GPS: {e}")
    return None

def scan_directory_for_media(directory, process_videos=False):
    """Scan a directory and return all media files with their datetime and GPS info."""
    media_files = []
    image_extensions = ('.jpg', '.jpeg', '.png', '.heic', '.tiff')
    video_extensions = ('.mov', '.mp4', '.avi', '.mkv')
    
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            lower_file = file.lower()
            
            if lower_file.endswith(image_extensions):
                print(f"Processing image: {file_path}")
                dt = get_media_datetime(file_path)
                gps = get_media_gps(file_path)
                
                media_files.append({
                    'path': file_path,
                    'datetime': dt,
                    'gps': gps
                })
            elif process_videos and lower_file.endswith(video_extensions):
                print(f"Processing video: {file_path}")
                dt = get_media_datetime(file_path)
                gps = get_video_gps(file_path)
                
                media_files.append({
                    'path': file_path,
                    'datetime': dt,
                    'gps': gps
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
        # Only consider files with valid GPS that's not None
        if media['gps'] is not None and media['datetime']:
            time_diff = abs((target_dt - media['datetime']).total_seconds())
            if time_diff <= time_window.total_seconds():
                if min_time_diff is None or time_diff < min_time_diff:
                    min_time_diff = time_diff
                    closest_gps = media['gps']
    
    return closest_gps

def process_directory(directory, process_videos=False):
    """Process media files and assign GPS coordinates."""
    media_files = scan_directory_for_media(directory, process_videos)
    gps_files = [m for m in media_files if m['gps'] is not None]
    
    for media in media_files:
        if media['gps'] is None and media['datetime'] is not None:
            media['gps'] = find_closest_gps(gps_files, media)
    
    return media_files

def save_results(media_files, output_file):
    """Save processed results to CSV, focusing on suggested changes for images without original GPS."""
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['path', 'datetime', 'latitude', 'longitude', 'gps_source']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for media in media_files:
            # Skip videos
            if media['path'].lower().endswith(('.mov', '.mp4', '.avi', '.mkv')):
                continue
                
            # Get original GPS (will be None if not present)
            original_gps = get_media_gps(media['path'])
            
            # Only include files that:
            # 1. Had no original GPS (original_gps is None)
            # 2. Now have proxy GPS (media['gps'] is not None)
            if original_gps is None and media['gps'] is not None:
                writer.writerow({
                    'path': media['path'],
                    'datetime': media['datetime'].isoformat() if media['datetime'] else '',
                    'latitude': media['gps'][0],
                    'longitude': media['gps'][1],
                    'gps_source': 'proxy'
                })

def decimal_to_dms(decimal):
    """Convert decimal degrees to EXIF-friendly degrees, minutes, seconds format."""
    degrees = int(decimal)
    remainder = abs(decimal - degrees) * 60
    minutes = int(remainder)
    seconds = (remainder - minutes) * 60
    return ((degrees, 1), (minutes, 1), (int(seconds * 1000), 1000))

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

def update_video_gps(video_path, lat, lon):
    """Update GPS metadata for videos using FFmpeg."""
    temp_path = video_path + ".temp"
    
    try:
        print(f"\nProcessing video: {video_path}")
        
        # FFmpeg command to add location metadata
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-metadata', f'location={lat},{lon}',
            '-metadata', f'location-eng={lat},{lon}',
            '-c', 'copy',  # Copy streams without re-encoding
            temp_path
        ]
        
        # Run FFmpeg (hide banner and only show errors)
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            return False
            
        # Replace original file
        os.replace(temp_path, video_path)
        print("Successfully updated GPS for video")
        return True
        
    except Exception as e:
        print(f"Video processing failed: {str(e)}")
        # Clean up temp file if it exists
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False

def is_valid_media(file_path):
    """Check if file is a valid media file."""
    try:
        if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.heic')):
            with Image.open(file_path) as img:
                img.verify()
            return True
        return True  # Assume video files are valid
    except Exception as e:
        print(f"Invalid media file: {str(e)}")
        return False

def find_file_path(csv_path, directory):
    """Try to find the file path from CSV entry."""
    # First try exact path
    file_path = csv_path if os.path.isabs(csv_path) else os.path.join(directory, csv_path)
    if os.path.exists(file_path):
        return file_path
    
    # Try by basename in directory
    filename = os.path.basename(csv_path)
    file_path = os.path.join(directory, filename)
    if os.path.exists(file_path):
        return file_path
    
    # Search recursively
    for root, _, files in os.walk(directory):
        if filename in files:
            return os.path.join(root, filename)
    
    return None

def update_gps_from_csv(csv_file, directory, process_videos=False):
    """Update GPS data for media files based on CSV coordinates."""
    print(f"\nStarting GPS update from CSV: {csv_file}")
    
    with open(csv_file, 'r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        
        processed = 0
        skipped = 0
        
        for row in csv_reader:
            try:
                csv_path = row['path']
                file_path = find_file_path(csv_path, directory)
                
                if not file_path or not os.path.exists(file_path):
                    print(f"File not found: {csv_path}")
                    skipped += 1
                    continue
                
                if not is_valid_media(file_path):
                    print(f"Skipping invalid media file: {file_path}")
                    skipped += 1
                    continue
                
                # Get file extension
                lower_path = file_path.lower()
                is_video = any(lower_path.endswith(ext) for ext in ('.mov', '.mp4', '.avi', '.mkv'))
                
                # Skip videos unless explicitly allowed
                if is_video and not process_videos:
                    print(f"Skipping video (use --all to process): {file_path}")
                    skipped += 1
                    continue
                
                # Get coordinates
                try:
                    lat = float(row.get('latitude') or row.get('lat'))
                    lon = float(row.get('longitude') or row.get('lon'))
                except (ValueError, TypeError):
                    print(f"Invalid coordinates for {file_path}")
                    skipped += 1
                    continue
                
                # Update GPS based on file type
                success = False
                if not is_video:
                    success = update_image_gps(file_path, lat, lon)
                elif process_videos:
                    success = update_video_gps(file_path, lat, lon)
                
                if success:
                    processed += 1
                    print(f"Successfully updated {file_path}")
                else:
                    skipped += 1
                    print(f"Failed to update {file_path}")
                    
            except Exception as e:
                print(f"Error processing {csv_path}: {str(e)}")
                skipped += 1

    print(f"\nGPS update complete from CSV!")
    print(f"Successfully processed: {processed} files")
    print(f"Skipped: {skipped} files")

def main():
    parser = argparse.ArgumentParser(
        description="Media GPS Tool - Extract or Update GPS coordinates in media files",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # Extract command
    extract_parser = subparsers.add_parser('extract', help='Extract GPS coordinates from media files')
    extract_parser.add_argument("directory", help="Directory to scan for media files")
    extract_parser.add_argument("--output", help="Output CSV file to save results", required=True)
    extract_parser.add_argument("--all", help="Process all media files including videos", action='store_true')
    
    # Update command
    update_parser = subparsers.add_parser('update', help='Update GPS coordinates in media files from CSV')
    update_parser.add_argument("directory", help="Directory containing media files")
    update_parser.add_argument("csv_file", help="CSV file with filenames and GPS coordinates (latitude, longitude)")
    update_parser.add_argument("--all", help="Process all media files including videos", action='store_true')
    
    args = parser.parse_args()

    if args.command == 'extract':
        print(f"Scanning {args.directory} for {'all media files' if args.all else 'image files'}...")
        media_files = process_directory(args.directory, process_videos=args.all)
        
        files_with_gps = sum(1 for m in media_files if m['gps'] is not None)
        
        # Count proxy GPS (assigned from nearby files)
        files_with_proxy_gps = 0
        for m in media_files:
            if m['gps'] is not None:
                if not m['path'].lower().endswith(('.jpg', '.jpeg', '.png', '.heic')):
                    files_with_proxy_gps += 1  # Videos always count as proxy
                elif m['gps'] != get_media_gps(m['path']):
                    files_with_proxy_gps += 1  # Images with different GPS than original
        
        print(f"\nProcessed {len(media_files)} media files:")
        print(f"- {files_with_gps} files with GPS coordinates ({files_with_proxy_gps} with proxy GPS)")
        print(f"- {len(media_files) - files_with_gps} files without GPS coordinates")
        
        save_results(media_files, args.output)
        print(f"\nResults saved to {args.output}")
    
    elif args.command == 'update':
        if not os.path.isdir(args.directory):
            print(f"Error: Directory not found - {args.directory}")
            sys.exit(1)

        if not os.path.isfile(args.csv_file):
            print(f"Error: CSV file not found - {args.csv_file}")
            sys.exit(1)

        print(f"\n{'='*50}")
        print(f"Media GPS Updater Tool")
        print(f"Directory: {args.directory}")
        print(f"CSV File: {args.csv_file}")
        print(f"Processing videos: {'Yes' if args.all else 'No'}")
        print(f"{'='*50}\n")
        
        update_gps_from_csv(args.csv_file, args.directory, process_videos=args.all)

if __name__ == "__main__":
    main()