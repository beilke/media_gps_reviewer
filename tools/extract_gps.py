#!/usr/bin/env python3
"""
GPS Extraction Tool

This script extracts GPS coordinates from image files even if they have incomplete EXIF data.
It's useful for diagnosing issues with GPS metadata in images.

Usage:
  python extract_gps.py [image_path]

Example:
  python extract_gps.py ../data/photos/photogps/20240816_171517.jpg
"""

import sys
import os
import exifread
import json
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

def extract_gps_with_exifread(image_path):
    """Extract GPS data using exifread library."""
    try:
        with open(image_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            
            # Print all GPS tags for debugging
            gps_tags = {k: str(v) for k, v in tags.items() if k.startswith('GPS ')}
            logger.info(f"GPS tags found with exifread: {json.dumps(gps_tags, indent=2)}")
            
            if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
                lat = tags['GPS GPSLatitude']
                lon = tags['GPS GPSLongitude']
                
                # Convert to decimal degrees
                lat_dec = float(lat.values[0]) + float(lat.values[1])/60 + float(lat.values[2])/3600
                lon_dec = float(lon.values[0]) + float(lon.values[1])/60 + float(lon.values[2])/3600
                
                # Apply reference if available
                if 'GPS GPSLatitudeRef' in tags:
                    lat_ref = tags['GPS GPSLatitudeRef']
                    if str(lat_ref) == 'S':
                        lat_dec = -lat_dec
                if 'GPS GPSLongitudeRef' in tags:
                    lon_ref = tags['GPS GPSLongitudeRef']
                    if str(lon_ref) == 'W':
                        lon_dec = -lon_dec
                
                return lat_dec, lon_dec
            return None
    except Exception as e:
        logger.error(f"Error with exifread: {e}")
        return None

def extract_gps_with_pil(image_path):
    """Extract GPS data using PIL library."""
    try:
        image = Image.open(image_path)
        exif_data = image._getexif()
        
        if not exif_data:
            logger.info("No EXIF data found with PIL.")
            return None
        
        # Find GPS info
        gps_info = None
        for tag, value in exif_data.items():
            tag_name = TAGS.get(tag, tag)
            if tag_name == 'GPSInfo':
                gps_info = value
                break
        
        if not gps_info:
            logger.info("No GPS info found with PIL.")
            return None
        
        # Debug output
        gps_data = {}
        for gps_tag, gps_value in gps_info.items():
            gps_tag_name = GPSTAGS.get(gps_tag, gps_tag)
            gps_data[gps_tag_name] = str(gps_value)
        logger.info(f"GPS tags found with PIL: {json.dumps(gps_data, indent=2)}")
        
        # Extract lat/lon
        lat_data = gps_info.get(2)  # GPSLatitude
        lon_data = gps_info.get(4)  # GPSLongitude
        
        if not lat_data or not lon_data:
            logger.info("Missing lat/lon data in PIL GPS info.")
            return None
        
        # Convert to decimal
        lat_dec = rational_to_decimal(lat_data[0]) + rational_to_decimal(lat_data[1])/60 + rational_to_decimal(lat_data[2])/3600
        lon_dec = rational_to_decimal(lon_data[0]) + rational_to_decimal(lon_data[1])/60 + rational_to_decimal(lon_data[2])/3600
        
        # Apply reference if available
        lat_ref = gps_info.get(1)  # GPSLatitudeRef
        lon_ref = gps_info.get(3)  # GPSLongitudeRef
        
        if lat_ref and lat_ref == 'S':
            lat_dec = -lat_dec
        if lon_ref and lon_ref == 'W':
            lon_dec = -lon_dec
            
        return lat_dec, lon_dec
    except Exception as e:
        logger.error(f"Error with PIL: {e}")
        return None

def main(image_path):
    """Main function to extract and display GPS data."""
    if not os.path.exists(image_path):
        logger.error(f"Image file not found: {image_path}")
        return
    
    # Get filename for display
    filename = os.path.basename(image_path)
    logger.info(f"Extracting GPS data from: {filename}")
    
    # Try exifread method
    logger.info("\n--- Using exifread library ---")
    exifread_result = extract_gps_with_exifread(image_path)
    
    # Try PIL method
    logger.info("\n--- Using PIL library ---")
    pil_result = extract_gps_with_pil(image_path)
    
    # Display results
    logger.info("\n--- Results ---")
    if exifread_result:
        logger.info(f"exifread GPS coordinates: {exifread_result[0]}, {exifread_result[1]}")
    else:
        logger.info("exifread: No GPS coordinates found")
    
    if pil_result:
        logger.info(f"PIL GPS coordinates: {pil_result[0]}, {pil_result[1]}")
    else:
        logger.info("PIL: No GPS coordinates found")
    
    # Recommendation
    logger.info("\n--- Recommendation ---")
    if exifread_result:
        logger.info(f"Recommended coordinates: {exifread_result[0]}, {exifread_result[1]}")
    elif pil_result:
        logger.info(f"Recommended coordinates: {pil_result[0]}, {pil_result[1]}")
    else:
        logger.info("No GPS data could be extracted from this image.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <image_path>")
        sys.exit(1)
    
    main(sys.argv[1])
