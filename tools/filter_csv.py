import csv
import os
import sys
from log_utils import setup_logger

# Set up logger
logger = setup_logger('filter_csv')

def filter_csv(csv_file_path, gps_list_file_path, output_csv_path):
    # Normalize paths to use CSV_FOLDER
    csv_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'csv')
    os.makedirs(csv_dir, exist_ok=True)
    
    # Handle input CSV path
    if not os.path.isabs(csv_file_path):
        csv_file_path = os.path.join(csv_dir, os.path.basename(csv_file_path))
        
    # Handle output CSV path
    if not os.path.isabs(output_csv_path):
        output_csv_path = os.path.join(csv_dir, os.path.basename(output_csv_path))
    
    # Try multiple encodings for the GPS list file
    encodings_to_try = ['utf-8', 'latin1', 'cp1252']
    files_to_keep = set()
    
    for encoding in encodings_to_try:
        try:
            with open(gps_list_file_path, 'r', encoding=encoding) as f:
                lines = f.readlines()
                # Extract the file paths (skip the first two lines)
                for line in lines[2:]:  # Skip headers
                    line = line.strip()
                    if line:
                        files_to_keep.add(line.lower())
                break  # Successfully read the file
        except UnicodeDecodeError:
            continue
    
    if not files_to_keep:
        error_msg = f"Could not read {gps_list_file_path} with any of the tried encodings"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info(f"Found {len(files_to_keep)} files in GPS list")
    
    # Process CSV file with similar encoding handling
    rows_to_keep = []
    for encoding in encodings_to_try:
        try:
            with open(csv_file_path, 'r', newline='', encoding=encoding) as csvfile:
                reader = csv.DictReader(csvfile)
                fieldnames = reader.fieldnames
                
                for row in reader:
                    file_path = row['path'].lower()
                    # Check both conditions:
                    # 1. File is in the GPS list
                    # 2. Has either latitude or longitude data
                    if (file_path in files_to_keep and 
                        (row['latitude'].strip() or row['longitude'].strip())):
                        rows_to_keep.append(row)
                break  # Successfully read the file
        except UnicodeDecodeError:
            continue
    
    if not rows_to_keep:
        error_msg = f"Could not read {csv_file_path} with any of the tried encodings"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Write output (always using UTF-8)
    with open(output_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_to_keep)
    
    logger.info(f"Filtered CSV saved to {output_csv_path}")
    logger.info(f"Initial files in GPS list: {len(files_to_keep)}")
    logger.info(f"Files with GPS coordinates kept: {len(rows_to_keep)}")

if __name__ == '__main__':
    if len(sys.argv) != 4:
        logger.error("Invalid number of arguments")
        logger.error("Usage: python filter_csv.py input.csv files_without_gps.txt output.csv")
        sys.exit(1)
    
    try:
        logger.info(f"Starting filter_csv with input: {sys.argv[1]}, GPS list: {sys.argv[2]}, output: {sys.argv[3]}")
        filter_csv(sys.argv[1], sys.argv[2], sys.argv[3])
        logger.info("Filter process completed successfully")
    except Exception as e:
        logger.exception(f"Error during filtering: {str(e)}")
        sys.exit(1)