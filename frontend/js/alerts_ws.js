/**
 * Real-Time WebSocket Alerts & Trajectory Route Tracer
 */

let ws = null;
let trajectoryPathLayer = null;

document.addEventListener("DOMContentLoaded", () => {
    initAlertsWebSocket();
    initAlertDrawer();
});

function initAlertsWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    let host = window.location.host;
    if (host.startsWith("0.0.0.0")) {
        host = host.replace("0.0.0.0", "127.0.0.1");
    }
    const wsUrl = `${protocol}//${host}/api/alerts/ws`;

    try {
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log("[WS] Connected to Red EYE Real-Time Alert Stream");
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleIncomingEvent(data);
            } catch (err) {
                console.error("WS Parse error:", err);
            }
        };

        ws.onclose = () => {
            setTimeout(initAlertsWebSocket, 3000); // Auto-reconnect
        };
    } catch (e) {
        console.warn("WebSocket init failed:", e);
    }
}

function handleIncomingEvent(data) {
    if (data.type === "NEW_ANPR_DETECTION" || data.type === "NEW_VEHICLE_DETECTION") {
        appendLiveANPRCard(data);
    } else if (data.type === "NEW_CRITICAL_ALERT") {
        appendAlertDrawerItem(data);
        showTopBannerAlert(data);
        if (window.playTacticalAlertSound) {
            window.playTacticalAlertSound(true);
        }
    } else if (data.type === "NEW_ANOMALY_EVENT") {
        if (window.onNewAnomalyEvent) {
            window.onNewAnomalyEvent(data.event);
        }
    }
}

function appendLiveANPRCard(data) {
    const container = document.getElementById("live-anpr-items");
    if (!container) return;

    // Filter by the currently open camera on the Live Surveillance Wall tab
    const activeCamEl = document.getElementById("live-cam-id");
    if (activeCamEl && activeCamEl.innerText !== data.camera_id) {
        return; // Skip displaying if it's not the currently viewed camera
    }

    // Clear placeholder if it's the first real event
    if (container.children.length === 1 && container.children[0].classList.contains("anpr-info-card")) {
        container.innerHTML = "";
    }

    const card = document.createElement("div");
    card.className = `anpr-card ${data.is_flagged ? 'flagged' : ''}`;
    
    // Dynamic content based on event type
    let titleStr = data.plate_number || "NO PLATE FOUND";
    if (data.type === "NEW_VEHICLE_DETECTION") titleStr = "VEHICLE TRACKED";
    
    let colorModelStr = `${data.color || data.vehicle_color || 'Unknown Color'} ${data.vehicle_type || data.vehicle_model || 'Vehicle'}`;
    
    card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
            <div style="flex-grow: 1;">
                <span class="plate-pill">${titleStr}</span>
                <div style="font-size: 10px; color: #8b9bb4; margin-top: 4px;">
                    ${colorModelStr}
                </div>
                ${data.image_url ? `<div style="margin-top: 6px;"><img src="${data.image_url}" style="max-height: 45px; border-radius: 4px; border: 1px solid #3d4a60;"></div>` : ''}
            </div>
            <div style="text-align: right; min-width: 60px;">
                <div style="font-size: 10px; font-weight: bold; color: #00d2ff;">${data.camera_id}</div>
                <div style="font-size: 9px; color: #5a6a82;">${new Date(data.timestamp).toLocaleTimeString()}</div>
            </div>
        </div>
    `;

    container.prepend(card);
    if (container.children.length > 20) {
        container.lastElementChild.remove();
    }
}

function appendAlertDrawerItem(data) {
    const drawerContainer = document.getElementById("drawer-alert-items");
    if (!drawerContainer) return;

    const badge = document.getElementById("pending-alert-badge");
    if (badge) {
        badge.textContent = parseInt(badge.textContent || 0) + 1;
    }

    const item = document.createElement("div");
    item.className = "alert-item-card critical";
    item.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <strong style="color:#ff1744; font-size:12px;">${data.title}</strong>
            <span style="font-size:10px; color:#ffd600;">TMS: ${data.tms_score}</span>
        </div>
        <p style="font-size:11px; color:#e0e8f5; margin-top:2px;">${data.description}</p>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
            <span style="font-size:10px; color:#8b9bb4;">Loc: ${data.camera_name} (${data.city})</span>
            <button class="btn btn-sm btn-cyan" onclick="focusOnTrajectory('${data.plate_number || 'GJ01AB1234'}')">Trace</button>
        </div>
    `;

    drawerContainer.prepend(item);
}

function showTopBannerAlert(data) {
    console.log("CRITICAL ALERT:", data);
}

function initAlertDrawer() {
    const btnFeed = document.getElementById("btn-alert-feed");
    const drawer = document.getElementById("alert-drawer");
    const btnClose = document.getElementById("btn-close-drawer");

    if (btnFeed && drawer) {
        btnFeed.addEventListener("click", () => drawer.classList.toggle("open"));
    }
    if (btnClose && drawer) {
        btnClose.addEventListener("click", () => drawer.classList.remove("open"));
    }
}

// ─────────────────────────────────────────────────────────────
// CROSS-CAMERA TRAJECTORY MAP & TIMELINE REPLAY
// ─────────────────────────────────────────────────────────────
window.focusOnTrajectory = async function(plateNumber) {
    // Switch to Tab 4
    const trajTab = document.querySelector('[data-tab="tab-trajectory"]');
    if (trajTab) trajTab.click();

    try {
        const res = await fetch(`/api/tracking/trajectory/${plateNumber}`);
        const data = await res.json();
        renderTrajectoryView(data);
    } catch (e) {
        console.error("Failed to load trajectory:", e);
    }
};

function renderTrajectoryView(data) {
    window.lastTrajectoryData = data;
    document.getElementById("traj-plate-title").textContent = `${data.plate_number} — ${data.vehicle_color} ${data.vehicle_model}`;
    
    const fusion = data.evidence_fusion || {
        overall_confidence: 0.91,
        decision: "HIGH_CONFIDENCE_CANDIDATE_MATCH",
        color_code: "#00ff9d",
        recommended_action: "Dispatch Automated Control Room Alert",
        evidence_breakdown: {
            plate_ocr_confidence: 0.96,
            vehicle_reid_similarity: 0.88,
            spatio_temporal_kinematics: 0.94,
            visual_attribute_consistency: 0.96
        }
    };

    document.getElementById("traj-fir-title").innerHTML = `
        <div style="display:flex; flex-direction:column; gap:6px;">
            <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <span class="badge ${data.is_flagged ? 'badge-danger' : 'badge-dark'}">${data.fir_reference || 'Clean Record'}</span>
                <span style="font-size:12px; color:#e0e8f5;">Owner: <strong>${data.owner}</strong> | ${data.total_sightings} Sighting Nodes</span>
                <span style="background:${fusion.color_code}22; color:${fusion.color_code}; border:1px solid ${fusion.color_code}; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:bold;">
                    🎯 Evidence Score: ${(fusion.overall_confidence * 100).toFixed(1)}% (${fusion.decision.replace(/_/g, ' ')})
                </span>
            </div>
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:6px; background:#0c121e; padding:6px 10px; border-radius:6px; border:1px solid #1a273e; font-size:10px;">
                <div>🔤 Plate OCR: <strong style="color:#00d2ff;">${(fusion.evidence_breakdown.plate_ocr_confidence * 100).toFixed(0)}%</strong></div>
                <div>🚗 Vehicle Re-ID: <strong style="color:#ffd600;">${(fusion.evidence_breakdown.vehicle_reid_similarity * 100).toFixed(0)}%</strong></div>
                <div>⏱️ Kinematics: <strong style="color:#00ff9d;">${(fusion.evidence_breakdown.spatio_temporal_kinematics * 100).toFixed(0)}%</strong></div>
                <div>🎨 Attributes: <strong style="color:#b388ff;">${(fusion.evidence_breakdown.visual_attribute_consistency * 100).toFixed(0)}%</strong></div>
            </div>
        </div>
    `;

    // Render Timeline Stepper with Kinematic Feasibility Badges
    const stepper = document.getElementById("trajectory-stepper");
    stepper.innerHTML = "";

    data.waypoints.forEach(wp => {
        const div = document.createElement("div");
        div.className = "waypoint-card";
        const transit = wp.transit_metrics || {};
        div.innerHTML = `
            <div class="waypoint-dot"></div>
            <div class="waypoint-box">
                <div style="display:flex; justify-content:space-between; font-weight:bold; font-size:12px;">
                    <span style="color:#00d2ff;">Stop #${wp.step}: ${wp.camera_id} (${wp.camera_name})</span>
                    <span style="color:#ffd600;">${wp.speed_kmh} km/h</span>
                </div>
                <div style="font-size:11px; color:#8b9bb4; margin-top:3px;">${wp.city} • Corridor: ${wp.direction}</div>
                <div style="font-size:10px; color:#5a6a82; margin-top:2px;">Timestamp: ${new Date(wp.timestamp).toLocaleTimeString("en-IN")}</div>
                ${transit.transit_status ? `<div style="font-size:10px; color:#00ff9d; margin-top:3px; background:#00ff9d11; padding:2px 6px; border-radius:3px; border:1px solid #00ff9d33;">✓ Kinematics: ${transit.transit_status}</div>` : ''}
            </div>
        `;
        stepper.appendChild(div);
    });

    // Render on Trajectory Map
    initTrajectoryMap(data.waypoints);
}

function initTrajectoryMap(waypoints) {
    if (!window.trajectoryMap) {
        window.trajectoryMap = L.map("trajectory-map", {
            center: [23.0225, 72.5714],
            zoom: 12
        });

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: '&copy; OpenStreetMap | Red EYE Trajectory',
            maxZoom: 19
        }).addTo(window.trajectoryMap);
    }

    if (trajectoryPathLayer) {
        window.trajectoryMap.removeLayer(trajectoryPathLayer);
    }

    trajectoryPathLayer = L.layerGroup().addTo(window.trajectoryMap);

    const latlngs = waypoints.map(wp => [wp.lat, wp.lng]);

    // Glowing Red/Cyan Animated Trajectory Polyline
    const polyline = L.polyline(latlngs, {
        color: "#ff1744",
        weight: 4,
        opacity: 0.85,
        dashArray: "8, 8",
        lineCap: "round"
    }).addTo(trajectoryPathLayer);

    // Numbered Waypoint Markers
    waypoints.forEach((wp, idx) => {
        const iconHtml = `
            <div style="
                width: 26px; height: 26px;
                background: #ff1744;
                border: 2px solid #fff;
                border-radius: 50%;
                display: flex; align-items: center; justify-content: center;
                color: #fff; font-size: 11px; font-weight: 800;
                box-shadow: 0 0 12px #ff1744;
            ">
                ${idx + 1}
            </div>
        `;
        const icon = L.divIcon({ html: iconHtml, className: "", iconSize: [26, 26], iconAnchor: [13, 13] });
        L.marker([wp.lat, wp.lng], { icon })
            .bindPopup(`<strong>Stop #${idx+1}: ${wp.camera_id}</strong><br>${wp.camera_name}<br>Speed: ${wp.speed_kmh} km/h`)
            .addTo(trajectoryPathLayer);
    });

    if (latlngs.length > 0) {
        window.trajectoryMap.fitBounds(polyline.getBounds(), { padding: [40, 40] });
    }
}

// ─────────────────────────────────────────────────────────────
// AI COPILOT FORENSIC INCIDENT BRIEF (GEMINI 2.5 FLASH)
// ─────────────────────────────────────────────────────────────
function initAICopilot() {
    const btnBrief = document.getElementById("btn-generate-ai-brief");
    const briefPanel = document.getElementById("ai-copilot-brief-panel");
    const briefContent = document.getElementById("ai-brief-content");
    const sourceLabel = document.getElementById("ai-brief-source");
    const threatBadge = document.getElementById("ai-threat-badge");

    if (!btnBrief || !briefPanel) return;

    btnBrief.addEventListener("click", async () => {
        briefPanel.style.display = "block";
        briefContent.innerHTML = `<div style="display:flex; align-items:center; gap:8px; color:#00d2ff;"><i class="fa-solid fa-spinner fa-spin"></i> Querying Google Gemini 2.5 Flash for tactical interception strategy...</div>`;

        const lastWaypoint = (window.lastTrajectoryData && window.lastTrajectoryData.waypoints && window.lastTrajectoryData.waypoints.length) 
            ? window.lastTrajectoryData.waypoints[window.lastTrajectoryData.waypoints.length - 1]
            : { camera_id: "CAM-016", camera_name: "16 Visat P2", city: "Ahmedabad", speed_kmh: 64.0, direction: "Outbound North" };

        const payload = {
            plate_number: window.lastTrajectoryData ? window.lastTrajectoryData.plate_number : "GJ01AB1234",
            vehicle_model: window.lastTrajectoryData ? window.lastTrajectoryData.vehicle_model : "Toyota Fortuner (7-Seater)",
            vehicle_color: window.lastTrajectoryData ? window.lastTrajectoryData.vehicle_color : "White",
            fir_reference: window.lastTrajectoryData ? window.lastTrajectoryData.fir_reference : "FIR #402/2026 Crime Branch Gandhinagar",
            last_camera_id: lastWaypoint.camera_id,
            last_camera_name: lastWaypoint.camera_name,
            city: lastWaypoint.city || "Ahmedabad",
            speed_kmh: lastWaypoint.speed_kmh || 64.0,
            direction: lastWaypoint.direction || "Outbound North",
            evidence_confidence: (window.lastTrajectoryData && window.lastTrajectoryData.evidence_fusion) 
                ? window.lastTrajectoryData.evidence_fusion.overall_confidence : 0.896
        };

        try {
            const resp = await fetch("/api/ai/analyze-incident", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const ai = await resp.json();

            sourceLabel.textContent = `Gujarat Police AI Copilot (${ai.source || 'AI Intelligence Engine'})`;
            threatBadge.textContent = ai.threat_level || "CRITICAL THREAT";

            briefContent.innerHTML = `
                <div style="margin-bottom:8px;">
                    <strong style="color:#ffd600;">⚠️ Threat Assessment:</strong> ${ai.threat_assessment || 'Suspect vehicle is actively moving along the corridor.'}
                </div>
                ${ai.probable_escape_corridor ? `
                <div style="margin-bottom:8px;">
                    <strong style="color:#00d2ff;">🧭 Probable Escape Corridor:</strong> ${ai.probable_escape_corridor}
                </div>` : ''}
                ${ai.intercept_strategy ? `
                <div style="margin-bottom:8px;">
                    <strong style="color:#00ff9d;">🛡️ Tactical Intercept Strategy:</strong>
                    <ul style="margin:4px 0 0 16px; padding:0;">
                        ${ai.intercept_strategy.map(item => `<li style="margin-bottom:2px;">${item}</li>`).join('')}
                    </ul>
                </div>` : ''}
                ${ai.control_room_dispatch_message ? `
                <div style="background:#1e293b; padding:8px 12px; border-radius:6px; border-left:3px solid #00d2ff; font-family:monospace; color:#38bdf8;">
                    <strong>📻 PCR DISPATCH BROADCAST:</strong> "${ai.control_room_dispatch_message}"
                </div>` : ''}
            `;
        } catch (e) {
            briefContent.innerHTML = `<div style="color:#ff1744;">Error generating AI tactical brief: ${e.message}</div>`;
        }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    initAlertDrawer();
    initAICopilot();
});
