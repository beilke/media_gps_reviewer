// review.js - Shared/reusable JS for review.html (and optionally index.html)

// Heatmap modal logic
function setupHeatmapModal(gpsPoints) {
    document.getElementById('showHeatmapBtn').addEventListener('click', function() {
        var heatmapModal = new bootstrap.Modal(document.getElementById('heatmapModal'));
        heatmapModal.show();
        const mapDiv = document.getElementById('heatmapMap');
        mapDiv.innerHTML = `<div class="modern-loader"><div class="loader-spinner"></div><div class="loader-text">Generating heatmap visualization...</div></div>`;
        let modal = document.getElementById('heatmapModal');
        let heatmapModalShown = false;
        function onHeatmapModalShown() {
            if (window.heatmapInitialized) return;
            window.heatmapInitialized = true;
            heatmapModalShown = true;
            // Filter out invalid points
            gpsPoints = gpsPoints.filter(pt => pt && pt.length === 2 && !isNaN(pt[0]) && !isNaN(pt[1]));
            let center = [0, 0];
            if (gpsPoints.length > 0) {
                let latSum = 0, lonSum = 0;
                gpsPoints.forEach(pt => { latSum += pt[0]; lonSum += pt[1]; });
                center = [latSum / gpsPoints.length, lonSum / gpsPoints.length];
            }
            var heatmapMap = L.map('heatmapMap', { preferCanvas: true }).setView(center, gpsPoints.length > 0 ? 8 : 2);
            L.tileLayer('https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors'
            }).addTo(heatmapMap);
            if (gpsPoints.length > 0) {
                var heat = L.heatLayer(gpsPoints, {
                    radius: 25,
                    blur: 20,
                    maxZoom: 15,
                    minOpacity: 0.4,
                    gradient: {
                        0.1: '#2c7bb6',
                        0.3: '#00a6ca',
                        0.5: '#00ccbc',
                        0.7: '#90eb9d',
                        0.9: '#ffff8c',
                        1.0: '#fdcd60'
                    },
                    max: 0.5
                }).addTo(heatmapMap);
            } else {
                heatmapMap.setView([0,0], 2);
                console.warn("No valid GPS points available for heatmap");
            }
            heatmapMap.zoomControl.setPosition('topright');
            L.control.scale({ position: 'bottomleft', metric: true, imperial: false, maxWidth: 200 }).addTo(heatmapMap);
            if (L.control.fullscreen) {
                L.control.fullscreen({
                    position: 'topright',
                    title: 'View Fullscreen',
                    titleCancel: 'Exit Fullscreen',
                    content: '<i class="bi bi-arrows-fullscreen"></i>',
                    forceSeparateButton: true
                }).addTo(heatmapMap);
            }
            heatmapMap.on('load', function() {
                const mapElement = document.getElementById('heatmapMap');
                mapElement.style.opacity = '0';
                mapElement.style.transition = 'opacity 0.5s ease';
                setTimeout(() => { mapElement.style.opacity = '1'; }, 100);
            });
            document.getElementById('heatmapModal').addEventListener('hidden.bs.modal', function() {
                if (heatmapMap) {
                    heatmapMap.remove();
                    window.heatmapInitialized = false;
                }
            });
        }
        if (!heatmapModalShown) {
            modal.addEventListener('shown.bs.modal', onHeatmapModalShown, {once: true});
        }
    });
}

// Bootstrap tooltips
function enableBootstrapTooltips() {
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// All review page logic

document.addEventListener('DOMContentLoaded', function() {
    // Map initialization
    const lat = parseFloat(window.REVIEW_ENTRY_LAT) || 0;
    const lng = parseFloat(window.REVIEW_ENTRY_LNG) || 0;
    const map = L.map('map').setView([lat, lng], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    // Add marker for current coordinates
    let currentMarker = null;
    if (lat !== 0 && lng !== 0) {
        currentMarker = L.marker([lat, lng]).addTo(map)
            .bindPopup('Current Location');
    }

    // Add geocoder control
    const geocoder = L.Control.geocoder({
        position: 'topright',
        placeholder: 'Search address...',
        errorMessage: 'Location not found',
        showResultIcons: true,
        defaultMarkGeocode: false
    }).addTo(map);

    // Handle geocoder results
    geocoder.on('markgeocode', function(e) {
        const result = e.geocode;
        const center = result.center;
        document.getElementById('latitude').value = center.lat.toFixed(6);
        document.getElementById('longitude').value = center.lng.toFixed(6);
        document.getElementById('addressSearch').value = result.name;
        map.setView(center, 16);
        if (currentMarker) map.removeLayer(currentMarker);
        currentMarker = L.marker(center).addTo(map)
            .bindPopup(result.name || 'Selected Location')
            .openPopup();
    });

    // Update form fields when clicking on the map
    map.on('click', function(e) {
        document.getElementById('latitude').value = e.latlng.lat.toFixed(6);
        document.getElementById('longitude').value = e.latlng.lng.toFixed(6);
        if (currentMarker) map.removeLayer(currentMarker);
        currentMarker = L.marker(e.latlng).addTo(map)
            .bindPopup('Selected Location')
            .openPopup();
    });

    // Address search functionality
    document.getElementById('searchAddressBtn').addEventListener('click', searchAddress);
    document.getElementById('addressSearch').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            searchAddress();
        }
    });
    document.getElementById('addressSearch').addEventListener('input', function() {
        const query = this.value.trim();
        if (query.length > 2) {
            fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(data => {
                    const resultsDiv = document.getElementById('searchResults');
                    resultsDiv.innerHTML = '';
                    if (data.length === 0) {
                        resultsDiv.innerHTML = '<div class="alert alert-info">No results found</div>';
                        return;
                    }
                    data.slice(0, 5).forEach(item => {
                        const div = document.createElement('div');
                        div.className = 'alert alert-light alert-dismissible p-2 mb-2';
                        div.innerHTML = `
                            <button type="button" class="btn-close float-end" data-bs-dismiss="alert" aria-label="Close"></button>
                            <strong>${item.display_name}</strong><br>
                            <small>Lat: ${item.lat}, Lon: ${item.lon}</small>
                            <button class="btn btn-sm btn-primary mt-1" onclick="window.useThisLocation(${item.lat}, ${item.lon}, '${item.display_name.replace("'", "\\'")}')">
                                <i class="bi bi-check-lg"></i> Use
                            </button>
                        `;
                        resultsDiv.appendChild(div);
                    });
                })
                .catch(error => {
                    console.error('Autocomplete error:', error);
                });
        }
    });

    window.useThisLocation = function(lat, lng, displayName = '') {
        document.getElementById('latitude').value = lat;
        document.getElementById('longitude').value = lng;
        if (displayName) {
            document.getElementById('addressSearch').value = displayName;
        }
        document.getElementById('searchResults').innerHTML = '';
        map.setView([lat, lng], 16);
        if (currentMarker) map.removeLayer(currentMarker);
        currentMarker = L.marker([lat, lng]).addTo(map)
            .bindPopup(displayName || 'Selected Location')
            .openPopup();
    };

    // Handle form submission
    document.getElementById('gpsForm').addEventListener('submit', function(e) {
        const action = document.activeElement.value;
        if (action === 'save') {
            e.preventDefault();
            handleSaveAll();
        }
    });
    document.getElementById('saveAllBtn').addEventListener('click', handleSaveAll);

    function handleSaveAll() {
        const saveModal = new bootstrap.Modal(document.getElementById('saveProgressModal'));
        saveModal.show();
        const saveProgressBar = document.getElementById('saveProgressBar');
        const saveStatusText = document.getElementById('saveStatusText');
        let progress = 0;
        const interval = setInterval(() => {
            if (progress >= 100) {
                clearInterval(interval);
                saveStatusText.innerText = 'Finalizing changes...';
            } else {
                progress += 10;
                saveProgressBar.style.width = `${progress}%`;
                saveStatusText.innerText = `Saving... ${progress}%`;
            }
        }, 300);
        fetch('/save_all', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
        })
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(data => {
            clearInterval(interval);
            if (data.status === 'success') {
                saveProgressBar.style.width = '100%';
                saveStatusText.innerHTML = `
                    <i class="bi bi-check-circle-fill text-success"></i> 
                    Saved ${data.changes_made} of ${data.total_entries} files
                `;
                document.getElementById('changesMadeCount').textContent = data.changes_made;
                setTimeout(() => saveModal.hide(), 1500);
            } else {
                saveProgressBar.classList.add('bg-danger');
                saveStatusText.innerHTML = `
                    <i class="bi bi-exclamation-triangle-fill text-danger"></i> 
                    Error: ${data.message || 'Unknown error occurred'}
                `;
            }
        })
        .catch(error => {
            clearInterval(interval);
            saveProgressBar.classList.add('bg-danger');
            saveStatusText.innerHTML = `
                <i class="bi bi-exclamation-triangle-fill text-danger"></i> 
                Request failed: ${error.message}
            `;
        });
    }
});
