import os
import sys
from PIL import Image, UnidentifiedImageError
import exifread
from log_utils import setup_logger

# Set up logger
logger = setup_logger('find_no_gps_media')

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
    logger.info(f"Scanning directory: {directory}")
    total_files = 0
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            #if file.lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.tiff', '.mp4', '.mov', '.avi', '.mkv')):
            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.tiff')):
                total_files += 1
                if not has_gps_info(file_path):
                    logger.debug(f"No GPS found in: {file_path}")
                    no_gps_files.append(file_path)
    
    logger.info(f"Processed {total_files} files, found {len(no_gps_files)} without GPS")
    return no_gps_files

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="List media files without GPS data.")
    parser.add_argument("directory", help="Directory to scan for media files.")
    parser.add_argument("--output", help="Output file to save results (optional).")
    args = parser.parse_args()

    try:
        logger.info(f"Starting find_no_gps_media with directory: {args.directory}")
        no_gps_files = scan_directory_for_no_gps(args.directory)

        if no_gps_files:
            logger.info(f"Found {len(no_gps_files)} files without GPS")
            
            if args.output:
                # Ensure output goes to the data/csv directory if it's not an absolute path
                csv_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'csv')
                os.makedirs(csv_dir, exist_ok=True)
                
                output_path = args.output
                if not os.path.isabs(output_path):
                    output_path = os.path.join(csv_dir, os.path.basename(output_path))
                
                with open(output_path, 'w') as f:
                    f.write("\n".join(no_gps_files))
                logger.info(f"Results saved to {output_path}")
                
                # Print first 10 files for user feedback
                for i, file in enumerate(no_gps_files[:10]):
                    logger.info(f"Example {i+1}: {file}")
                if len(no_gps_files) > 10:
                    logger.info(f"... and {len(no_gps_files) - 10} more files")
        else:
            logger.info("No media files without GPS found.")
    except Exception as e:
        logger.exception(f"Error during scan: {str(e)}")
        sys.exit(1)