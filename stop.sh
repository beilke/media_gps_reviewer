#!/bin/bash

# Stop the Picture GPS Reviewer application
echo "Stopping Picture GPS Reviewer..."
docker-compose down

# Check if the container stopped successfully
if [ $? -eq 0 ]; then
    echo "Picture GPS Reviewer stopped successfully."
else
    echo "Failed to stop Picture GPS Reviewer. Try running: docker-compose down"
fi
