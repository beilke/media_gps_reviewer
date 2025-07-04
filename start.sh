#!/bin/bash

# Create data directories if they don't exist
echo "Creating data directories..."
mkdir -p data/csv data/log data/photos

# Set proper permissions for data directories
echo "Setting permissions..."
chmod -R 777 data

# Start the Picture GPS Reviewer application using Docker Compose
echo "Starting Picture GPS Reviewer..."
docker-compose up -d

# Check if the container started successfully
if [ $? -eq 0 ]; then
    echo "Picture GPS Reviewer is running!"
    echo "Access it at http://localhost:5000"
    echo ""
    echo "To stop the application, run: ./stop.sh or docker-compose down"
else
    echo "Failed to start Picture GPS Reviewer. Check the logs for more information."
fi
