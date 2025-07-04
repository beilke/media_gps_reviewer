import os
import argparse
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from PIL import Image, ImageFile
import piexif
import subprocess
import sys
from log_utils import setup_logger

# Set up logger
logger = setup_logger('update_media_gps')

# Allow loading of truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = True

def get_gps_coordinates(place_name):
    """Convert place name to GPS coordinates using Nominatim."""
    geolocator = Nominatim(user_agent="media_geo_updater")
    try:
        location = geolocator.geocode(place_name)
        if location:
            logger.info(f"Found coordinates for '{place_name}': {location.latitude}, {location.longitude}")
            return (location.latitude, location.longitude)
        logger.error(f"Could not find coordinates for '{place_name}'")
        return None
    except (GeocoderTimedOut, GeocoderUnavailable) as e:
        logger.error(f"Geocoding error: {e}")
        return None

def decimal_to_dms(decimal):
    """Convert decimal degrees to EXIF-friendly degrees, minutes, seconds format."""
    degrees = int(decimal)
    remainder = abs(decimal - degrees) * 60
    minutes = int(remainder)
    seconds = (remainder - minutes) * 60
    return ((degrees, 1), (minutes, 1), (int(seconds * 1000), 1000))

def update_image_gps(image_path, lat, lon):
    """Update GPS metadata for images using piexif."""
    try:
        logger.info(f"Processing image: {image_path}")
        
        # Load existing EXIF or create new
        try:
            exif_dict = piexif.load(image_path)
        except Exception as e:
            logger.debug(f"Creating new EXIF data: {str(e)}")
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
        
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
        logger.info(f"Successfully updated GPS for image")
        return True
    except Exception as e:
        logger.error(f"Failed to update image: {str(e)}")
        return False

def update_video_gps(video_path, lat, lon):
    """Update GPS metadata for videos using FFmpeg."""
    #temp_path = video_path + ".temp"
    temp_path = video_path.replace(".mp4", ".temp.mp4")
    
    try:
        logger.info(f"Processing video: {video_path}")
        
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
            logger.error(f"FFmpeg error: {result.stderr}")
            return False
            
        # Replace original file
        os.replace(temp_path, video_path)
        logger.info("Successfully updated GPS for video")
        return True
        
    except Exception as e:
        logger.error(f"Video processing failed: {str(e)}")
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
        logger.warning(f"Invalid media file: {str(e)}")
        return False

def process_directory(directory, place_name):
    """Process all media files in directory."""
    logger.info(f"Starting processing for: {directory}")
    coordinates = get_gps_coordinates(place_name)
    if not coordinates:
        logger.error(f"Could not get coordinates for {place_name}. Aborting processing.")
        return

    lat, lon = coordinates
    media_extensions = ('.jpg', '.jpeg', '.png', '.heic', '.mp4', '.mov')
    processed = 0
    skipped = 0

    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(media_extensions):
                file_path = os.path.join(root, file)
                
                if not is_valid_media(file_path):
                    logger.warning(f"Skipping invalid file: {file_path}")
                    skipped += 1
                    continue
                
                try:
                    success = False
                    if file.lower().endswith(('.mp4', '.mov')):
                        success = update_video_gps(file_path, lat, lon)
                    else:
                        success = update_image_gps(file_path, lat, lon)
                    
                    if success:
                        processed += 1
                    else:
                        skipped += 1
                except Exception as e:
                    logger.exception(f"Error processing {file_path}")
                    skipped += 1

    logger.info(f"Processing complete for {directory}!")
    logger.info(f"Successfully processed: {processed} files")
    logger.info(f"Skipped: {skipped} files")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Update media files with GPS coordinates",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("directory", help="Directory containing media files")
    parser.add_argument("place", help="Place name (e.g., 'Paris, France')")
    
    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        logger.error(f"Directory not found - {args.directory}")
        sys.exit(1)

    logger.info(f"{'='*50}")
    logger.info(f"Media GPS Updater Tool")
    logger.info(f"Directory: {args.directory}")
    logger.info(f"Location: {args.place}")
    logger.info(f"{'='*50}")
    
    process_directory(args.directory, args.place)