import os
import subprocess
import json
from PIL import Image, ImageFile
import exifread
from datetime import datetime, timedelta
import pytz
import csv
import argparse
import piexif

# Allow loading of truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = True


def get_media_datetime(file_path):
    """Extract datetime from media file."""
    try:
        with open(file_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            if 'EXIF DateTimeOriginal' in tags:
                dt_str = str(tags['EXIF DateTimeOriginal'])
                return datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S').replace(tzinfo=pytz.UTC)
    except Exception:
        pass

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
            if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
                lat = convert_to_decimal(tags['GPS GPSLatitude'], tags['GPS GPSLatitudeRef'])
                lon = convert_to_decimal(tags['GPS GPSLongitude'], tags['GPS GPSLongitudeRef'])

                if lat == 0.0 and lon == 0.0:
                    return None
                return lat, lon
    except Exception as e:
        print(f"Error extracting GPS from {file_path}: {e}")
    return None


def convert_to_decimal(coord, ref):
    """Convert EXIF GPS coordinates to decimal degrees."""
    degrees = float(coord.values[0])
    minutes = float(coord.values[1]) / 60
    seconds = float(coord.values[2]) / 3600
    decimal = degrees + minutes + seconds
    if str(ref) in ['S', 'W']:
        decimal = -decimal
    return decimal


def get_video_metadata(file_path):
    """Use ffprobe to extract metadata from video."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', file_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return json.loads(result.stdout)
    except Exception:
        return None


def scan_directory_for_media(directory, process_videos=False):
    """Scan directory for media files and identify those needing GPS updates."""
    media_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            if is_valid_media(file_path, process_videos):
                try:
                    gps_data = get_media_gps(file_path)
                    timestamp = get_media_datetime(file_path)
                    media_files.append({
                        'file_path': file_path,
                        'timestamp': timestamp,
                        'gps': gps_data
                    })
                except Exception as e:
                    print(f"Error processing file {file_path}: {e}")
            else:
                print(f"Skipping unsupported file: {file_path}")
    return media_files


def is_valid_media(file_path, process_videos=False):
    """Check if the file is a valid media file."""
    valid_image_extensions = ('.jpg', '.jpeg', '.png')
    valid_video_extensions = ('.mov', '.mp4') if process_videos else ()
    return file_path.lower().endswith(valid_image_extensions + valid_video_extensions)


def find_closest_gps(media_files, target_file, time_window_hours=1):
    """Find closest media file with GPS within a time window."""
    target_dt = target_file['timestamp']
    if not target_dt:
        return None

    time_window = timedelta(hours=time_window_hours)
    closest_gps = None
    min_time_diff = None

    for media in media_files:
        if media['gps'] and media['timestamp']:
            time_diff = abs((target_dt - media['timestamp']).total_seconds())
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
        if media['gps'] is None and media['timestamp'] is not None:
            media['gps'] = find_closest_gps(gps_files, media)

    return media_files


def save_results(media_files, output_file):
    """Save only files needing GPS updates to a CSV file."""
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['file_path', 'timestamp', 'latitude', 'longitude']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for media in media_files:
            if media['gps'] is None:
                writer.writerow({
                    'file_path': media['file_path'],
                    'timestamp': media['timestamp'],
                    'latitude': '',
                    'longitude': ''
                })


def update_image_gps(image_path, lat, lon):
    """Update GPS metadata for images using piexif."""
    try:
        exif_dict = piexif.load(image_path)
        gps_ifd = {
            piexif.GPSIFD.GPSLatitudeRef: 'N' if lat >= 0 else 'S',
            piexif.GPSIFD.GPSLatitude: decimal_to_dms(abs(lat)),
            piexif.GPSIFD.GPSLongitudeRef: 'E' if lon >= 0 else 'W',
            piexif.GPSIFD.GPSLongitude: decimal_to_dms(abs(lon)),
        }
        exif_dict["GPS"] = gps_ifd
        piexif.insert(piexif.dump(exif_dict), image_path)
        print(f"Successfully updated GPS for image: {image_path}")
        return True
    except Exception as e:
        print(f"Failed to update image GPS: {e}")
        return False


def update_video_gps(video_path, lat, lon):
    """Update GPS metadata for videos using FFmpeg."""
    temp_path = video_path.replace(".mp4", ".temp.mp4")
    try:
        cmd = [
            'ffmpeg', '-i', video_path,
            '-metadata', f'location={lat},{lon}',
            '-metadata', f'location-eng={lat},{lon}',
            '-c', 'copy', temp_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            return False

        os.replace(temp_path, video_path)
        print(f"Successfully updated GPS for video: {video_path}")
        return True
    except Exception as e:
        print(f"Failed to update video GPS: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False


def decimal_to_dms(decimal):
    """Convert decimal degrees to EXIF-friendly degrees, minutes, seconds format."""
    degrees = int(decimal)
    remainder = abs(decimal - degrees) * 60
    minutes = int(remainder)
    seconds = (remainder - minutes) * 60
    return ((degrees, 1), (minutes, 1), (int(seconds * 1000), 1000))


def main():
    parser = argparse.ArgumentParser(description="Media GPS Tool - Extract or Update GPS coordinates in media files")
    subparsers = parser.add_subparsers(dest='command', required=True)

    extract_parser = subparsers.add_parser('extract', help='Extract GPS coordinates from media files')
    extract_parser.add_argument("directory", help="Directory to scan for media files")
    extract_parser.add_argument("--output", required=True, help="Output CSV file to save results")
    extract_parser.add_argument("--process-videos", action="store_true", help="Include video files in processing")

    update_parser = subparsers.add_parser('update', help='Update GPS coordinates in media files from CSV')
    update_parser.add_argument("directory", help="Directory containing media files")
    update_parser.add_argument("csv_file", help="CSV file with filenames and GPS coordinates")
    update_parser.add_argument("--process-videos", action="store_true", help="Include video files in processing")

    args = parser.parse_args()

    if args.command == 'extract':
        media_files = process_directory(args.directory, process_videos=args.process_videos)
        save_results(media_files, args.output)
        print(f"Results saved to {args.output}")

    elif args.command == 'update':
        update_gps_from_csv(args.csv_file, args.directory, process_videos=args.process_videos)


if __name__ == "__main__":
    main()