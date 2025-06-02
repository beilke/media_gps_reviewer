import os
import csv
import argparse
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from datetime import datetime

def get_exif_data(image_path):
    """Get EXIF data from image file"""
    try:
        with Image.open(image_path) as img:
            exif_data = img._getexif()
            if exif_data is not None:
                return {TAGS.get(tag, tag): value for tag, value in exif_data.items()}
    except (AttributeError, IOError, KeyError, IndexError):
        pass
    return None

def has_gps_data(exif_data):
    """Check if EXIF data contains GPS information"""
    if exif_data is None:
        return False
    return 'GPSInfo' in exif_data

def format_datetime(exif_data):
    """Format DateTime from EXIF data to ISO format"""
    if exif_data is None:
        return None
    
    # Try different EXIF datetime tags
    datetime_tags = ['DateTimeOriginal', 'DateTimeDigitized', 'DateTime']
    for tag in datetime_tags:
        if tag in exif_data:
            dt_str = exif_data[tag]
            try:
                # Typical format: "YYYY:MM:DD HH:MM:SS"
                dt = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
                return dt.isoformat() + '+00:00'  # Assuming UTC timezone
            except ValueError:
                pass
    return None

def scan_directory_for_jpgs_without_gps(root_dir, output_csv):
    """Scan directory for JPGs without GPS data and write to CSV"""
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['path', 'datetime'])  # Write header
        
        for root, _, files in os.walk(root_dir):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg')):
                    file_path = os.path.join(root, file)
                    exif_data = get_exif_data(file_path)
                    
                    if not has_gps_data(exif_data):
                        dt = format_datetime(exif_data)
                        writer.writerow([file_path, dt])

def main():
    parser = argparse.ArgumentParser(description='Find JPG files without GPS metadata')
    parser.add_argument('directory', help='Directory to scan for JPG files')
    parser.add_argument('output_csv', help='Output CSV filename')
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.directory):
        print(f"Error: Directory '{args.directory}' does not exist")
        return
    
    print(f"Scanning {args.directory} for JPGs without GPS data...")
    scan_directory_for_jpgs_without_gps(args.directory, args.output_csv)
    print(f"Results saved to {args.output_csv}")

if __name__ == '__main__':
    main()