/**
 * Leaflet GIS Tactical Map Engine
 * Visualizes 50 Camera Registry Nodes, FOV Coverage Cones, and Animated Trajectory Routes.
 */

window.allCameras = [];
window.gisMap = null;
window.trajectoryMap = null;
let cameraMarkers = {};
let fovConesLayer = null;

document.addEventListener("DOMContentLoaded", () => {
    initGISMap();
    loadCameras();
    initFilterListeners();
});

function initGISMap() {
    // Centered on Gujarat (Gandhinagar / Ahmedabad region)
    window.gisMap = L.map("leaflet-map", {
        center: [23.0225, 72.5714],
        zoom: 11,
        zoomControl: true
    });

    // 100% Free Open-Source OpenStreetMap Layer (Zero Watermarks, No API Key Required)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors | Red EYE GIS',
        maxZoom: 19
    }).addTo(window.gisMap);

    fovConesLayer = L.layerGroup().addTo(window.gisMap);
}

async function loadCameras() {
    try {
        const res = await fetch("/api/cameras");
        const data = await res.json();
        window.allCameras = data.cameras;
        
        populateDepartmentFilter(window.allCameras);
        populateQuickSelect(window.allCameras);
        renderCameraMarkers(window.allCameras);
        renderCameraList(window.allCameras);
    } catch (e) {
        console.error("Error loading cameras:", e);
    }
}

function populateQuickSelect(cameras) {
    const selectQuick = document.getElementById("select-cam-quick");
    if (!selectQuick || !cameras || !cameras.length) return;
    const currentVal = selectQuick.value || window.currentCamId || "CAM-001";
    selectQuick.innerHTML = "";
    cameras.forEach(cam => {
        const opt = document.createElement("option");
        opt.value = cam.camera_id;
        opt.textContent = `${cam.camera_id} • ${cam.name} (${cam.city})`;
        if (cam.camera_id === currentVal) {
            opt.selected = true;
        }
        selectQuick.appendChild(opt);
    });
}

function populateDepartmentFilter(cameras) {
    const deptSelect = document.getElementById("filter-dept");
    const depts = [...new Set(cameras.map(c => c.department))].sort();
    
    depts.forEach(d => {
        const opt = document.createElement("option");
        opt.value = d;
        opt.textContent = d;
        deptSelect.appendChild(opt);
    });
}

function renderCameraMarkers(cameras) {
    // Clear existing
    Object.values(cameraMarkers).forEach(m => window.gisMap.removeLayer(m));
    cameraMarkers = {};
    fovConesLayer.clearLayers();

    const showCones = document.getElementById("chk-cones").checked;

    cameras.forEach(cam => {
        const isOnline = cam.status === "ACTIVE";
        const markerColor = isOnline ? "#00d2ff" : "#ff1744";

        // Custom Tactical Pin Icon
        const iconHtml = `
            <div style="
                width: 22px; height: 22px;
                background: ${isOnline ? 'rgba(0, 210, 255, 0.2)' : 'rgba(255, 23, 68, 0.2)'};
                border: 2px solid ${markerColor};
                border-radius: 50%;
                display: flex; align-items: center; justify-content: center;
                color: ${markerColor}; font-size: 10px; font-weight: bold;
                box-shadow: 0 0 10px ${markerColor};
            ">
                <i class="fa-solid fa-video" style="font-size: 9px;"></i>
            </div>
        `;

        const customIcon = L.divIcon({
            html: iconHtml,
            className: "tactical-cam-pin",
            iconSize: [22, 22],
            iconAnchor: [11, 11]
        });

        const marker = L.marker([cam.latitude, cam.longitude], { icon: customIcon })
            .bindPopup(`
                <div style="font-family: sans-serif; font-size: 12px; color: #111;">
                    <strong style="color: #0288d1; font-size: 13px;">${cam.camera_id}</strong>: ${cam.name}<br>
                    <strong>Dept:</strong> ${cam.department}<br>
                    <strong>District:</strong> ${cam.city} (${cam.district})<br>
                    <strong>Resolution:</strong> ${cam.resolution} @ ${cam.fps} FPS<br>
                    <strong>VMS Adapter:</strong> ${cam.vms_adapter.toUpperCase()}<br>
                    <strong>Status:</strong> <span style="color:${isOnline ? 'green' : 'red'}; font-weight:bold;">${cam.status}</span><br>
                    <div style="margin-top: 8px;">
                        <button onclick="viewCameraStream('${cam.camera_id}')" style="
                            background: #0288d1; color: #fff; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px;
                        ">Live Stream</button>
                        <button onclick="openEditLocationModal('${cam.camera_id}', ${cam.latitude}, ${cam.longitude})" style="
                            background: #2e7d32; color: #fff; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; margin-left: 5px;
                        "><i class="fa-solid fa-map-pin"></i> Edit Location</button>
                    </div>
                </div>
            `);

        marker.addTo(window.gisMap);
        cameraMarkers[cam.camera_id] = marker;

        // Draw FOV Coverage Cone
        if (showCones && isOnline) {
            drawFovCone(cam.latitude, cam.longitude, cam.heading_angle, cam.fov_angle, cam.coverage_radius);
        }
    });

    document.getElementById("filtered-cam-count").textContent = cameras.length;
}

function drawFovCone(lat, lng, heading, fov, radiusMeters) {
    const numPoints = 16;
    const startAngle = heading - (fov / 2);
    const endAngle = heading + (fov / 2);
    const step = (endAngle - startAngle) / numPoints;

    const points = [[lat, lng]];

    for (let a = startAngle; a <= endAngle; a += step) {
        const rad = (a * Math.PI) / 180.0;
        // Earth radius ~6378137m
        const dLat = (radiusMeters * Math.cos(rad)) / 111320.0;
        const dLng = (radiusMeters * Math.sin(rad)) / (111320.0 * Math.cos((lat * Math.PI) / 180.0));
        points.push([lat + dLat, lng + dLng]);
    }
    points.push([lat, lng]);

    const polygon = L.polygon(points, {
        color: "#00d2ff",
        weight: 1,
        fillColor: "#00d2ff",
        fillOpacity: 0.12
    });

    fovConesLayer.addLayer(polygon);
}

function renderCameraList(cameras) {
    const listEl = document.getElementById("camera-list-items");
    listEl.innerHTML = "";

    cameras.forEach(cam => {
        const isActive = (cam.operational_status === "ACTIVE" || cam.status === "ACTIVE");
        const statusText = isActive ? "ACTIVE" : "DEACTIVE";
        const statusColor = isActive ? "#00e676" : "#ff1744";

        const card = document.createElement("div");
        card.className = `cam-item-card ${isActive ? '' : 'offline'}`;
        card.innerHTML = `
            <div class="cam-item-header">
                <span class="cam-item-id">${cam.camera_id}</span>
                <span class="cam-item-status status-${isActive ? 'active' : 'offline'}">${statusText}</span>
            </div>
            <div class="cam-item-name">${cam.name}</div>
            <div class="cam-item-meta">${cam.department} &bull; ${cam.city}</div>
        `;
        card.addEventListener("click", () => {
            window.gisMap.setView([cam.latitude, cam.longitude], 15, { animate: true });
            if (cameraMarkers[cam.camera_id]) {
                cameraMarkers[cam.camera_id].openPopup();
            }
        });
        listEl.appendChild(card);
    });
}

function initFilterListeners() {
    const deptSelect = document.getElementById("filter-dept");
    const citySelect = document.getElementById("filter-city");
    const coneChk = document.getElementById("chk-cones");

    function applyFilters() {
        const dVal = deptSelect.value;
        const cVal = citySelect.value;

        const filtered = window.allCameras.filter(cam => {
            const matchDept = !dVal || cam.department === dVal;
            const matchCity = !cVal || cam.city === cVal;
            return matchDept && matchCity;
        });

        renderCameraMarkers(filtered);
        renderCameraList(filtered);
    }

    deptSelect.addEventListener("change", applyFilters);
    citySelect.addEventListener("change", applyFilters);
    coneChk.addEventListener("change", applyFilters);
}

// Global hook to jump to a specific camera stream
window.viewCameraStream = function(cameraId) {
    // Switch to tab 2
    const liveTab = document.querySelector('[data-tab="tab-live"]');
    if (liveTab) liveTab.click();
    if (window.switchLiveCamera) {
        window.switchLiveCamera(cameraId);
    }
};

// -------------------------------------------------------------
// LOCATION EDITING & CSV UPLOAD
// -------------------------------------------------------------

window.openEditLocationModal = function(cameraId, lat, lng) {
    document.getElementById("edit-location-modal").style.display = "flex";
    document.getElementById("input-loc-camera-id").value = cameraId;
    document.getElementById("input-loc-lat").value = lat;
    document.getElementById("input-loc-lng").value = lng;
    
    // Enable dragging for this specific marker
    const marker = cameraMarkers[cameraId];
    if (marker) {
        marker.dragging.enable();
        marker.on('dragend', function(e) {
            const pos = marker.getLatLng();
            document.getElementById("input-loc-lat").value = pos.lat.toFixed(6);
            document.getElementById("input-loc-lng").value = pos.lng.toFixed(6);
        });
    }
};

function closeEditLocationModal() {
    document.getElementById("edit-location-modal").style.display = "none";
    const cameraId = document.getElementById("input-loc-camera-id").value;
    const marker = cameraMarkers[cameraId];
    if (marker) {
        marker.dragging.disable();
        marker.off('dragend');
    }
}

document.getElementById("btn-close-location-modal")?.addEventListener("click", closeEditLocationModal);
document.getElementById("btn-cancel-location-modal")?.addEventListener("click", closeEditLocationModal);
    
    document.getElementById("btn-save-location")?.addEventListener("click", async () => {
        const cameraId = document.getElementById("input-loc-camera-id").value;
        const lat = parseFloat(document.getElementById("input-loc-lat").value);
        const lng = parseFloat(document.getElementById("input-loc-lng").value);
        
        try {
            const res = await fetch(`/api/cameras/${cameraId}/location`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ latitude: lat, longitude: lng })
            });
            const data = await res.json();
            if (data.success) {
                alert("Location updated successfully!");
                closeEditLocationModal();
                loadCameras(); // refresh map
            } else {
                alert(data.message || "Failed to update location.");
            }
        } catch (err) {
            alert("Error saving location: " + err);
        }
    });

    document.getElementById("btn-fetch-ip-loc")?.addEventListener("click", async () => {
        const ip = document.getElementById("input-loc-ip").value.trim();
        if (!ip) {
            alert("Please enter a valid IP address.");
            return;
        }
        try {
            const res = await fetch(`http://ip-api.com/json/${ip}`);
            const data = await res.json();
            if (data.status === "success") {
                document.getElementById("input-loc-lat").value = data.lat;
                document.getElementById("input-loc-lng").value = data.lon;
                
                // Also update the marker position dynamically if it exists
                const cameraId = document.getElementById("input-loc-camera-id").value;
                const marker = cameraMarkers[cameraId];
                if (marker) {
                    marker.setLatLng([data.lat, data.lon]);
                }
            } else {
                alert("Failed to locate IP: " + data.message);
            }
        } catch (err) {
            alert("Error fetching IP location: " + err);
        }
    });

    // CSV Upload
    const btnUploadCsv = document.getElementById("btn-upload-csv");
    const csvInput = document.getElementById("csv-upload-input");
    
    btnUploadCsv?.addEventListener("click", () => {
        csvInput.click();
    });
    
    csvInput?.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        const formData = new FormData();
        formData.append("file", file);
        
        btnUploadCsv.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Uploading...`;
        
        try {
            const res = await fetch("/api/cameras/upload_csv", {
                method: "POST",
                body: formData
            });
            const data = await res.json();
            if (data.success) {
                alert(data.message);
                loadCameras();
            } else {
                alert(data.detail || data.message || "Failed to upload CSV.");
            }
        } catch (err) {
            alert("Upload error: " + err);
        } finally {
            btnUploadCsv.innerHTML = `<i class="fa-solid fa-file-csv"></i> Upload Cameras CSV`;
            csvInput.value = "";
        }
    });
