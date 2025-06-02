import os
from PIL import Image, UnidentifiedImageError
import exifread

def has_gps_info(file_path):
    """Check if a file has GPS metadata."""
    try:
        # Handle images (JPEG, PNG, etc.)
        if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.tiff')):
            with open(file_path, 'rb') as f:
                tags = exifread.process_file(f, details=False)
                return 'GPS GPSLatitude' in tags
        # Handle videos (MP4, MOV, etc.)
        elif file_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
            with open(file_path, 'rb') as f:
                tags = exifread.process_file(f, details=False)
                return 'GPS GPSLatitude' in tags
    except (IOError, UnidentifiedImageError, AttributeError):
        return False
    return False

def scan_directory_for_no_gps(directory):
    """Scan a directory and return media files without GPS."""
    no_gps_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            #if file.lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.tiff', '.mp4', '.mov', '.avi', '.mkv')):
            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.tiff')):
                if not has_gps_info(file_path):
                    no_gps_files.append(file_path)
    return no_gps_files

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="List media files without GPS data.")
    parser.add_argument("directory", help="Directory to scan for media files.")
    parser.add_argument("--output", help="Output file to save results (optional).")
    args = parser.parse_args()

    print(f"Scanning {args.directory} for media files without GPS...")
    no_gps_files = scan_directory_for_no_gps(args.directory)

    if no_gps_files:
        print(f"\nFound {len(no_gps_files)} files without GPS:")
        for file in no_gps_files:
            print(file)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write("\n".join(no_gps_files))
            print(f"\nResults saved to {args.output}")
    else:
        print("No media files without GPS found.")