import csv

def filter_csv(csv_file_path, gps_list_file_path, output_csv_path):
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
        raise ValueError(f"Could not read {gps_list_file_path} with any of the tried encodings")
    
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
        raise ValueError(f"Could not read {csv_file_path} with any of the tried encodings")
    
    # Write output (always using UTF-8)
    with open(output_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_to_keep)
    
    print(f"Filtered CSV saved to {output_csv_path}")
    print(f"Initial files in GPS list: {len(files_to_keep)}")
    print(f"Files with GPS coordinates kept: {len(rows_to_keep)}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 4:
        print("Usage: python filter_csv.py input.csv files_without_gps.txt output.csv")
        sys.exit(1)
    
    try:
        filter_csv(sys.argv[1], sys.argv[2], sys.argv[3])
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)