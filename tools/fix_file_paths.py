#!/usr/bin/env python3
"""
Path Converter Tool for Picture GPS Reviewer

This tool helps convert local file paths to Docker-compatible paths for use with the
Picture GPS Reviewer application when running in Docker.

Usage:
    python fix_file_paths.py input_path [--output output_path]
    
Example:
    python fix_file_paths.py "Z:\docker\projects\gps_reviewer\data\photos\Teste1" --output "/app/data/photos/Teste1"
"""

import os
import sys
import argparse
import csv
import subprocess
from log_utils import setup_logger

# Set up logger
logger = setup_logger('fix_file_paths')

def convert_path_to_docker(input_path, base_path="Z:\\docker\\projects\\gps_reviewer"):
    """
    Convert Windows absolute path to Docker container path.
    
    Args:
        input_path: The Windows path to convert
        base_path: The base Windows path that maps to /app in Docker
        
    Returns:
        Docker-compatible path
    """
    # Normalize path separators
    input_path = input_path.replace('\\', '/')
    base_path = base_path.replace('\\', '/')
    
    # Handle spaces in paths
    quoted = False
    if input_path.startswith('"') and input_path.endswith('"'):
        input_path = input_path[1:-1]
        quoted = True
    
    # Remove drive letter if present
    if ':' in input_path:
        input_path = input_path.split(':', 1)[1]
        
    # If path starts with base_path, replace with /app
    base_path_no_drive = base_path.split(':', 1)[1] if ':' in base_path else base_path
    if base_path_no_drive in input_path:
        docker_path = input_path.replace(base_path_no_drive, '/app')
    else:
        # Check if it's a data subdirectory
        data_folders = ['/data/photos/', '/data/csv/', '/data/log/']
        docker_path = None
        
        for folder in data_folders:
            if folder in input_path:
                parts = input_path.split(folder, 1)  # Split only on first occurrence
                if len(parts) > 1:
                    docker_path = f"/app{folder}{parts[1]}"
                    break
                
        # If no matching data folder found, use the path as is
        if not docker_path:
            docker_path = input_path
    
    # Ensure path starts with /
    if not docker_path.startswith('/'):
        docker_path = f"/{docker_path}"
    
    # Special handling for spaces in paths when using in Docker command
    if ' ' in docker_path and quoted:
        return f'"{docker_path}"'
    
    return docker_path

def convert_csv_paths(csv_file, output_file=None):
    """
    Convert all file paths in a CSV file to Docker-compatible paths.
    
    Args:
        csv_file: Input CSV file with Windows paths
        output_file: Output CSV file with Docker paths. If None, overwrites input file.
    """
    if output_file is None:
        output_file = csv_file + '.docker.csv'
    
    try:
        rows = []
        with open(csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            for row in reader:
                if 'path' in row:
                    row['path'] = convert_path_to_docker(row['path'])
                rows.append(row)
                
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            
        logger.info(f"Converted {len(rows)} paths and saved to {output_file}")
        return True
    except Exception as e:
        logger.error(f"Error converting CSV paths: {str(e)}")
        return False

def convert_directory_path(directory_path):
    """
    Converts a directory path for use with find_aprox_gps_info.py in Docker.
    
    Args:
        directory_path: Windows directory path
        
    Returns:
        Docker-compatible path and command line
    """
    docker_path = convert_path_to_docker(directory_path)
    
    # Create command line suggestion
    cmd = f"python /app/tools/find_aprox_gps_info.py '{docker_path}' --output output.csv"
    
    return docker_path, cmd

def check_video_file(file_path):
    """
    Check if a video file can be processed by ffmpeg and report any issues.
    
    Args:
        file_path: Path to the video file
    
    Returns:
        Tuple (is_valid, message)
    """
    try:
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
            
        # Try running ffprobe on the file
        ffprobe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
                       '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        
        result = subprocess.run(ffprobe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if result.returncode != 0:
            return False, f"ffprobe error: {result.stderr.strip()}"
            
        # Try extracting metadata
        ffmetadata_cmd = ['ffmpeg', '-i', file_path, '-f', 'ffmetadata', '-']
        result = subprocess.run(ffmetadata_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if "error" in result.stderr.lower() and "no such file" in result.stderr.lower():
            return False, f"File access error: {result.stderr.strip()}"
            
        return True, f"Video file appears valid. Duration: {result.stdout.strip()} seconds"
    
    except Exception as e:
        return False, f"Error checking video file: {str(e)}"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert file paths for Docker environment")
    parser.add_argument("input_path", help="Windows path to convert or CSV file to process")
    parser.add_argument("--output", help="Output path for converted file (optional)")
    parser.add_argument("--check-video", action="store_true", help="Check if a video file is accessible by ffmpeg")
    parser.add_argument("--base-path", default="Z:\\docker\\projects\\gps_reviewer",
                        help="Base Windows path that maps to /app in Docker")
    args = parser.parse_args()
    
    # Check if we should check a video file
    if args.check_video:
        if not os.path.isfile(args.input_path):
            print(f"Error: {args.input_path} is not a file.")
            sys.exit(1)
            
        is_valid, message = check_video_file(args.input_path)
        if is_valid:
            print(f"✅ Success: {message}")
        else:
            print(f"❌ Error: {message}")
            
        # Also output the Docker path
        docker_path = convert_path_to_docker(args.input_path, args.base_path)
        print(f"\nWindows Path: {args.input_path}")
        print(f"Docker Path:  {docker_path}")
        print("\nTo check this video in Docker, use:")
        print(f"docker exec -it picture_gps_reviewer ffprobe -v error \"{docker_path}\"")
        
    # Check if input is a CSV file
    elif args.input_path.lower().endswith('.csv'):
        output_file = args.output if args.output else args.input_path + '.docker.csv'
        if convert_csv_paths(args.input_path, output_file):
            print(f"Successfully converted paths in CSV file: {output_file}")
        else:
            print("Failed to convert CSV file")
    else:
        # Convert a single path
        docker_path = convert_path_to_docker(args.input_path, args.base_path)
        print(f"Windows Path: {args.input_path}")
        print(f"Docker Path:  {docker_path}")
        
        # If it looks like a directory path, suggest a command
        if os.path.isdir(args.input_path):
            _, cmd = convert_directory_path(args.input_path)
            print("\nTo process this directory in Docker, use:")
            print(f"docker exec -it picture_gps_reviewer {cmd}")
        # If it looks like a video file, suggest checking it
        elif args.input_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
            print("\nTo check if this video can be processed, run:")
            print(f"python tools/fix_file_paths.py \"{args.input_path}\" --check-video")
