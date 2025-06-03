// scripts.js - Unified JavaScript for the GPS Reviewer application
// Combines functionality from index.js, review.js, and review-page.js

// =====================================
// Shared utility functions
// =====================================

// Bootstrap tooltips initialization
function enableBootstrapTooltips() {
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Controls visibility of the Save All button based on source type and GPS status
function updateSaveAllButtonVisibility() {
    const saveAllBtn = document.getElementById('saveAllBtn');
    if (!saveAllBtn) return;
    
    const isCsvUpload = window.IS_CSV_UPLOAD === true;
    const isProxyGpsScan = window.IS_PROXY_GPS_SCAN === true;
    const hasProxyGps = window.HAS_PROXY_GPS === true;
    
    // Show the button if:
    // 1. Source is CSV upload, OR
    // 2. Source is directory scan with "Find closest GPS" option selected
    // 3. AND in both cases, only if there are proxy GPS values assigned
    const shouldShow = (isCsvUpload || isProxyGpsScan) && hasProxyGps;
    
    // Set display style based on visibility condition
    saveAllBtn.style.display = shouldShow ? 'inline-block' : 'none';
    
    console.log(`Save All button visibility: ${shouldShow ? 'visible' : 'hidden'}`);
    console.log(`- CSV Upload: ${isCsvUpload}`);
    console.log(`- Proxy GPS Scan: ${isProxyGpsScan}`);
    console.log(`- Has Proxy GPS: ${hasProxyGps}`);
}

// =====================================
// Directory browser helper
// =====================================

function setupDirectoryBrowser() {
    const directoryHelper = document.getElementById('directoryHelper');
    const scanDirectoryInput = document.getElementById('scan_directory');
    const directoryBrowseBtn = document.getElementById('directoryBrowseBtn');
    
    if (!scanDirectoryInput) return;
    
    // Set up the directory browser dialog
    if (directoryBrowseBtn) {
        directoryBrowseBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Show directory selection popup
            const directoryModal = new bootstrap.Modal(document.getElementById('directorySelectorModal'));
            
            // If modal exists, show it
            if (directoryModal) {
                directoryModal.show();
            } else {
                // Fallback to file input if modal isn't available
                if (directoryHelper) directoryHelper.click();
            }
        });
    }
    
    // Set up the directory path examples to be clickable
    const dirExamples = document.querySelectorAll('.dir-example');
    dirExamples.forEach(example => {
        example.addEventListener('click', function(e) {
            e.preventDefault();
            scanDirectoryInput.value = this.dataset.path || this.textContent;
            
            // Close the modal if it exists
            const directoryModal = bootstrap.Modal.getInstance(document.getElementById('directorySelectorModal'));
            if (directoryModal) directoryModal.hide();
            
            // Show success feedback
            scanDirectoryInput.classList.add('is-valid');
            setTimeout(() => scanDirectoryInput.classList.remove('is-valid'), 2000);
        });
    });
    
    // Handle manual path confirmation
    const confirmPathBtn = document.getElementById('confirmPathBtn');
    if (confirmPathBtn) {
        confirmPathBtn.addEventListener('click', function() {
            const directoryModal = bootstrap.Modal.getInstance(document.getElementById('directorySelectorModal'));
            if (directoryModal) directoryModal.hide();
            
            // Show success feedback
            scanDirectoryInput.classList.add('is-valid');
            setTimeout(() => scanDirectoryInput.classList.remove('is-valid'), 2000);
        });
    }
    
    // Also handle the legacy file selector if it exists
    if (directoryHelper) {
        directoryHelper.addEventListener('change', function(e) {
            if (this.files && this.files.length > 0) {
                try {
                    // Get the path of the first file
                    const filePath = this.files[0].path || this.files[0].webkitRelativePath;
                    
                    if (filePath) {
                        // Extract the directory path by removing the filename
                        let directoryPath;
                        
                        if (this.files[0].path) {
                            // For browsers that support the path property (Chrome)
                            directoryPath = filePath.substring(0, filePath.lastIndexOf('\\'));
                            
                            // Handle forward slashes for Unix-like systems
                            if (directoryPath === filePath) {
                                directoryPath = filePath.substring(0, filePath.lastIndexOf('/'));
                            }
                        } else {
                            // For browsers using webkitRelativePath (Firefox, Safari)
                            const pathParts = filePath.split('/');
                            pathParts.pop(); // Remove the filename
                            directoryPath = pathParts.join('/');
                        }
                        
                        // Update the directory input
                        scanDirectoryInput.value = directoryPath;
                        
                        // Add visual feedback
                        scanDirectoryInput.classList.add('is-valid');
                        setTimeout(() => scanDirectoryInput.classList.remove('is-valid'), 2000);
                    }
                } catch (err) {
                    console.error('Error extracting directory path:', err);
                    scanDirectoryInput.classList.add('is-invalid');
                    setTimeout(() => scanDirectoryInput.classList.remove('is-invalid'), 2000);
                }
            }
        });
    }
}

// =====================================
// Heatmap Modal functionality
// =====================================

function setupHeatmapModal(gpsPoints) {
    // Set up the focus management for accessibility (ARIA) fix
    const heatmapModalEl = document.getElementById('heatmapModal');
    const showHeatmapBtn = document.getElementById('showHeatmapBtn');
    
    if (!heatmapModalEl || !showHeatmapBtn) return;
    
    // Fix for aria-hidden error when modal is closed - add this outside any other functions
    heatmapModalEl.addEventListener('hide.bs.modal', function() {
        setTimeout(() => {
            // Move focus to the button that opened the modal
            showHeatmapBtn.focus();
        }, 10);
    });
    
    showHeatmapBtn.addEventListener('click', function() {
        var heatmapModal = new bootstrap.Modal(heatmapModalEl);
        heatmapModal.show();
        const mapDiv = document.getElementById('heatmapMap');
        mapDiv.innerHTML = `<div class="modern-loader"><div class="loader-spinner"></div><div class="loader-text">Generating heatmap visualization...</div></div>`;
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
                gpsPoints.forEach(pt => {
                    latSum += pt[0];
                    lonSum += pt[1];
                });
                center = [latSum / gpsPoints.length, lonSum / gpsPoints.length];
            }
            var heatmapMap = L.map('heatmapMap', { preferCanvas: true }).setView(center, gpsPoints.length > 0 ? 8 : 2);
            L.tileLayer('https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors'
            }).addTo(heatmapMap);
            if (gpsPoints.length > 0) {
                // Add heat layer
                L.heatLayer(gpsPoints, {
                    radius: 25,
                    blur: 15,
                    maxZoom: 10,
                    max: 1.0,
                    gradient: {0.4: 'blue', 0.65: 'lime', 1: 'red'}
                }).addTo(heatmapMap);
                
                // Add markers
                gpsPoints.forEach((pt, i) => {
                    if (i < 100) { // Limit to 100 markers for performance
                        L.circleMarker([pt[0], pt[1]], {
                            radius: 4,
                            color: '#ff4400',
                            weight: 1,
                            opacity: 0.8,
                            fillOpacity: 0.8
                        }).addTo(heatmapMap);
                    }
                });
            } else {
                // Show message if no points
                const noDataDiv = document.createElement('div');
                noDataDiv.className = 'alert alert-info';
                noDataDiv.style.position = 'absolute';
                noDataDiv.style.zIndex = '1000';
                noDataDiv.style.top = '10px';
                noDataDiv.style.left = '50%';
                noDataDiv.style.transform = 'translateX(-50%)';
                noDataDiv.style.padding = '10px 20px';
                noDataDiv.innerHTML = '<i class="bi bi-exclamation-circle"></i> No GPS data available for heatmap';
                document.getElementById('heatmapMap').appendChild(noDataDiv);
            }
            heatmapMap.zoomControl.setPosition('topright');
            L.control.scale({ position: 'bottomleft', metric: true, imperial: false, maxWidth: 200 }).addTo(heatmapMap);
            if (L.control.fullscreen) {
                L.control.fullscreen({ position: 'topright' }).addTo(heatmapMap);
            }
            heatmapMap.on('load', function() {
                mapDiv.querySelector('.modern-loader')?.remove();
            });
            document.getElementById('heatmapModal').addEventListener('hidden.bs.modal', function() {
                heatmapMap.remove();
                window.heatmapInitialized = false;
            });
        }
        
        if (!heatmapModalShown) {
            heatmapModalEl.addEventListener('shown.bs.modal', onHeatmapModalShown, {once: true});
        }
    });
}

// =====================================
// Review page functionality
// =====================================

function initReviewPage() {
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

    // Call the function to update Save All button visibility
    updateSaveAllButtonVisibility();

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
    
    // Define searchAddress function to fix reference error
    function searchAddress() {
        const address = document.getElementById('addressSearch').value.trim();
        if (!address) return;

        const resultsDiv = document.getElementById('searchResults');
        resultsDiv.innerHTML = '<div class="text-center"><i class="bi bi-arrow-repeat bi-spin"></i> Searching...</div>';

        fetch('/geocode', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ address: address })
        })
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(data => {
            if (data.error) {
                resultsDiv.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
            } else {
                // Display results
                resultsDiv.innerHTML = '';
                if (data.results && data.results.length > 0) {
                    data.results.forEach(result => {
                        const div = document.createElement('div');
                        div.className = 'alert alert-light alert-dismissible p-2 mb-2';
                        div.innerHTML = `
                            <button type="button" class="btn-close float-end" data-bs-dismiss="alert" aria-label="Close"></button>
                            <strong>${result.display_name}</strong><br>
                            <small>Lat: ${result.lat}, Lon: ${result.lon}</small>
                            <button class="btn btn-sm btn-primary mt-1" onclick="window.useThisLocation(${result.lat}, ${result.lon}, '${result.display_name.replace("'", "\\'")}')">
                                <i class="bi bi-check-lg"></i> Use
                            </button>
                        `;
                        resultsDiv.appendChild(div);
                    });
                } else {
                    resultsDiv.innerHTML = '<div class="alert alert-info">No results found</div>';
                }
            }
        })
        .catch(error => {
            resultsDiv.innerHTML = `<div class="alert alert-danger">Search failed: ${error.message}</div>`;
        });
    }

    // Address search functionality
    document.getElementById('searchAddressBtn')?.addEventListener('click', searchAddress);
    document.getElementById('addressSearch')?.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            searchAddress();
        }
    });
    document.getElementById('addressSearch')?.addEventListener('input', function() {
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
    document.getElementById('gpsForm')?.addEventListener('submit', function(e) {
        const action = document.activeElement.value;
        if (action === 'save') {
            e.preventDefault();
            handleSaveAll();
        }
    });
    document.getElementById('saveAllBtn')?.addEventListener('click', handleSaveAll);

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
}

// =====================================
// Index page functionality
// =====================================

function initIndexPage() {
    const modeScan = document.getElementById("modeScan");
    const modeCSV = document.getElementById("modeCSV");
    const scanGroup = document.getElementById("scanGroup");
    const csvGroup = document.getElementById("csvGroup");
    const scanDirectoryInput = document.getElementById("scan_directory");
    const csvFileInput = document.getElementById("csv_file");
    const findClosestGPS = document.getElementById("findClosestGPS");
    const timeFrameGroup = document.getElementById("timeFrameGroup");
    const timeFrameHours = document.getElementById("timeFrameHours");
    const unifiedForm = document.getElementById("unifiedForm");
    const scanResult = document.getElementById("scanResult");

    // Set up directory browser
    setupDirectoryBrowser();

    // Early return if these elements don't exist (we're not on the index page)
    if (!modeScan || !modeCSV) return;
    
    // Sync the instructions tabs with the input mode selection
    const scanTab = document.getElementById('scan-tab');
    const csvTab = document.getElementById('csv-tab');
    
    if (scanTab && csvTab) {
        modeScan.addEventListener('change', function() {
            if (this.checked) {
                new bootstrap.Tab(scanTab).show();
            }
        });
        
        modeCSV.addEventListener('change', function() {
            if (this.checked) {
                new bootstrap.Tab(csvTab).show();
            }
        });
        
        scanTab.addEventListener('click', function() {
            modeScan.checked = true;
            updateMode();
        });
        
        csvTab.addEventListener('click', function() {
            modeCSV.checked = true;
            updateMode();
        });
    }

    function updateMode() {
        if (modeScan.checked) {
            scanGroup.classList.remove("opacity-50", "pointer-events-none");
            scanDirectoryInput.disabled = false;
            document.getElementById("showWithGPS").disabled = false;
            findClosestGPS.disabled = false;
            timeFrameHours.disabled = !findClosestGPS.checked;
            csvGroup.classList.add("opacity-50", "pointer-events-none");
            csvFileInput.disabled = true;
        } else {
            scanGroup.classList.add("opacity-50", "pointer-events-none");
            scanDirectoryInput.disabled = true;
            document.getElementById("showWithGPS").disabled = true;
            findClosestGPS.disabled = true;
            timeFrameHours.disabled = true;
            csvGroup.classList.remove("opacity-50", "pointer-events-none");
            csvFileInput.disabled = false;
        }
    }

    modeScan.addEventListener("change", updateMode);
    modeCSV.addEventListener("change", updateMode);
    updateMode();

    if (findClosestGPS) {
        findClosestGPS.addEventListener("change", function () {
            timeFrameGroup.style.display = this.checked ? "" : "none";
            if (modeScan.checked) {
                timeFrameHours.disabled = !this.checked;
            }
        });
    }

    if (unifiedForm) {
        unifiedForm.addEventListener("submit", function (e) {
            e.preventDefault();
            scanResult.innerHTML = "";
            if (modeScan.checked) {
                // Scan Directory mode
                const directory = scanDirectoryInput.value.trim();
                if (!directory) {
                    alert("Please enter a directory path to scan.");
                    return;
                }
                const findClosest = findClosestGPS.checked;
                const timeFrame = findClosest ? parseInt(timeFrameHours.value, 10) : null;
                const showWithGPS = document.getElementById("showWithGPS").checked;
                scanResult.innerHTML =
                    '<div class="text-center"><div class="spinner-border" role="status"></div> Scanning...</div>';
                fetch("/scan_directory", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        directory: directory,
                        find_closest: findClosest,
                        time_frame: timeFrame,
                        show_with_gps: showWithGPS
                    }),
                })
                    .then((res) => res.json())
                    .then((data) => {
                        if (data.status === "success" && data.redirect) {
                            window.location.href = data.redirect;
                        } else if (data.status === "error") {
                            scanResult.innerHTML = `<div class='alert alert-danger'>${
                                data.message || "Scan failed."
                            }</div>`;
                        }
                    })
                    .catch((err) => {
                        scanResult.innerHTML = `<div class='alert alert-danger'>Error: ${err.message}</div>`;
                    });
            } else {
                // CSV Upload mode
                if (!csvFileInput.files.length) {
                    alert("Please select a CSV file to upload.");
                    return;
                }
                unifiedForm.submit();
            }
        });
    }
}

// =====================================
// Document ready handler that initializes appropriate functionality
// =====================================

document.addEventListener("DOMContentLoaded", function () {
    // Initialize page-specific functionality based on page elements
    
    // Check if we're on the index page
    if (document.getElementById("unifiedForm")) {
        initIndexPage();
    }
    
    // Check if we're on the review page
    if (document.getElementById("map") && document.getElementById("gpsForm")) {
        initReviewPage();
        
        // Initialize heatmap if GPS points are available
        if (window.GPS_POINTS) {
            setupHeatmapModal(window.GPS_POINTS);
        }
        
        // Enable tooltips (for proxy GPS indicators)
        enableBootstrapTooltips();
    }
});
