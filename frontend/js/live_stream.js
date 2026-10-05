/**
 * Live Surveillance Stream & Florence-2 VLM Controller
 * Streams real-time MJPEG video with live bounding boxes and ANPR from /api/video/feed/{camera_id}
 */

let currentCamId = "CAM-001";

document.addEventListener("DOMContentLoaded", () => {
    initLiveControls();
    // Default to CAM-001 on startup
    window.switchLiveCamera("CAM-001");
    pollCameraStatus();
    setInterval(pollCameraStatus, 30000);
});

function pollCameraStatus() {
    fetch('/api/cameras/realtime_status')
        .then(res => res.json())
        .then(data => {
            const offlineCams = data.offline_cameras || [];
            const selectBox = document.getElementById("select-cam-quick");
            if (selectBox) {
                Array.from(selectBox.options).forEach(opt => {
                    const cid = opt.value;
                    const isOffline = offlineCams.includes(cid);

                    // Clean the text first
                    let text = opt.text.replace(" (OFFLINE)", "").replace("🔴 ", "").replace("🟢 ", "");

                    if (isOffline) {
                        opt.text = "🔴 " + text + " (OFFLINE)";
                        opt.style.color = "#ff4444";
                    } else {
                        opt.text = "🟢 " + text;
                        opt.style.color = ""; // reset to default
                    }
                });
            }
        })
        .catch(err => console.warn("Could not poll camera status:", err));
}

function initLiveControls() {
    const btnVlm = document.getElementById("btn-vlm-scan");
    if (btnVlm) {
        btnVlm.addEventListener("click", runVLMScan);
    }

    const btnCloseVlm = document.getElementById("btn-close-ai-scene");
    if (btnCloseVlm) {
        btnCloseVlm.addEventListener("click", () => {
            const containerEl = document.getElementById("vlm-structured-results");
            const textEl = document.getElementById("florence-output-text");
            if (containerEl) {
                containerEl.style.display = "none";
                containerEl.innerHTML = "";
            }
            if (textEl) {
                textEl.innerHTML = "Active 1080p surveillance feed. Click <strong>AI Scene Scan</strong> to run deep multimodal detection of vehicle makes/models, license plates, and subject attire.";
            }
        });
    }

    const selectQuick = document.getElementById("select-cam-quick");
    if (selectQuick) {
        selectQuick.addEventListener("change", (e) => {
            window.switchLiveCamera(e.target.value);
        });
    }

    // Video Fit Mode Toggle (Contain -> Fill/Stretch -> Cover)
    const btnFit = document.getElementById("btn-toggle-fit");
    const fitLabel = document.getElementById("fit-btn-label");
    const streamImg = document.getElementById("live-stream-video");
    let fitMode = "contain"; // "contain", "fill", "cover"

    if (btnFit && streamImg) {
        btnFit.addEventListener("click", () => {
            if (fitMode === "contain") {
                fitMode = "fill";
                streamImg.className = "fit-fill";
                if (fitLabel) fitLabel.textContent = "Fit: Stretch";
                btnFit.classList.add("active");
            } else if (fitMode === "fill") {
                fitMode = "cover";
                streamImg.className = "fit-cover";
                if (fitLabel) fitLabel.textContent = "Fit: Zoom/Cover";
            } else {
                fitMode = "contain";
                streamImg.className = "";
                if (fitLabel) fitLabel.textContent = "Fit: Window";
                btnFit.classList.remove("active");
            }
        });
    }

    // HTML5 Fullscreen Toggle
    const btnFullscreen = document.getElementById("btn-toggle-fullscreen");
    const videoViewport = document.getElementById("stream-display-box") || document.querySelector(".video-viewport");

    if (btnFullscreen && videoViewport) {
        btnFullscreen.addEventListener("click", () => {
            if (!document.fullscreenElement) {
                if (videoViewport.requestFullscreen) {
                    videoViewport.requestFullscreen();
                } else if (videoViewport.webkitRequestFullscreen) {
                    videoViewport.webkitRequestFullscreen();
                }
                btnFullscreen.innerHTML = `<i class="fa-solid fa-compress"></i> Exit Full`;
            } else {
                if (document.exitFullscreen) {
                    document.exitFullscreen();
                }
                btnFullscreen.innerHTML = `<i class="fa-solid fa-maximize"></i> Fullscreen`;
            }
        });

        document.addEventListener("fullscreenchange", () => {
            if (!document.fullscreenElement && btnFullscreen) {
                btnFullscreen.innerHTML = `<i class="fa-solid fa-maximize"></i> Fullscreen`;
            }
        });
    }

    // Gemini Modal
    const btnGeminiModal = document.getElementById("btn-gemini-key-modal");
    const modalGemini = document.getElementById("gemini-config-modal");
    const btnCloseGemini = document.getElementById("btn-close-gemini-modal");
    const btnCancelGemini = document.getElementById("btn-cancel-gemini-modal");
    const btnSaveGemini = document.getElementById("btn-save-gemini-key");
    const inputGeminiKey = document.getElementById("input-gemini-api-key");
    const statusFeedback = document.getElementById("gemini-status-feedback");

    if (btnGeminiModal && modalGemini) {
        btnGeminiModal.addEventListener("click", async () => {
            modalGemini.style.display = "flex";
            try {
                const res = await fetch("/api/ai/gemini_status");
                const data = await res.json();
                if (statusFeedback) {
                    if (data.configured) {
                        statusFeedback.innerHTML = `<i class="fa-solid fa-circle-check text-green"></i> <strong>Active Engine:</strong> ${data.engine}`;
                        statusFeedback.style.color = "#10b981";
                        statusFeedback.style.borderColor = "rgba(16, 185, 129, 0.3)";
                    } else {
                        statusFeedback.innerHTML = `<i class="fa-solid fa-microchip text-cyan"></i> <strong>Local Fallback:</strong> ${data.engine} on ${data.device_name}`;
                        statusFeedback.style.color = "#0284c7";
                    }
                }
            } catch (e) {
                console.warn(e);
            }
        });
    }

    const closeModal = () => { if (modalGemini) modalGemini.style.display = "none"; };
    if (btnCloseGemini) btnCloseGemini.addEventListener("click", closeModal);
    if (btnCancelGemini) btnCancelGemini.addEventListener("click", closeModal);

    if (btnSaveGemini && inputGeminiKey) {
        btnSaveGemini.addEventListener("click", async () => {
            const key = inputGeminiKey.value.trim();
            if (!key) {
                alert("Please enter a valid Gemini API key.");
                return;
            }
            btnSaveGemini.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Activating...`;
            try {
                const res = await fetch("/api/ai/configure_gemini", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ api_key: key })
                });
                const data = await res.json();
                if (data.success) {
                    alert(data.message);
                    closeModal();
                    const badge = document.getElementById("vlm-engine-badge");
                    if (badge) badge.textContent = "Gemini 2.5 Flash";
                } else {
                    alert(data.message || "Failed to configure key.");
                }
            } catch (err) {
                alert("Error configuring Gemini: " + err);
            } finally {
                btnSaveGemini.innerHTML = `<i class="fa-solid fa-check"></i> Activate Key`;
            }
        });
    }
}

window.switchLiveCamera = async function (cameraId) {
    currentCamId = cameraId;
    window.currentCamId = cameraId;
    const selectQuick = document.getElementById("select-cam-quick");
    if (selectQuick && selectQuick.value !== cameraId) {
        selectQuick.value = cameraId;
    }

    try {
        const res = await fetch(`/api/vms/stream/${cameraId}`);
        const data = await res.json();

        const idEl = document.getElementById("live-cam-id");
        const titleEl = document.getElementById("live-cam-title");
        if (idEl) idEl.textContent = data.camera_id;
        if (titleEl) titleEl.textContent = `${data.name} (${data.resolution} @ ${data.fps} FPS)`;

        let container = document.getElementById("stream-display-box");
        let videoEl = document.getElementById("live-stream-video");

        // Ensure we have a <video> element instead of an <img> for WebRTC
        if (videoEl && videoEl.tagName.toLowerCase() === "img") {
            let newVideoEl = document.createElement("video");
            newVideoEl.id = "live-stream-video";
            newVideoEl.autoplay = true;
            newVideoEl.playsInline = true;
            newVideoEl.muted = true;
            newVideoEl.style.width = "100%";
            newVideoEl.style.height = "100%";
            newVideoEl.style.objectFit = "contain";
            newVideoEl.style.background = "#000";
            container.replaceChild(newVideoEl, videoEl);
            videoEl = newVideoEl;
        } else if (!videoEl) {
            videoEl = document.createElement("video");
            videoEl.id = "live-stream-video";
            videoEl.autoplay = true;
            videoEl.playsInline = true;
            videoEl.muted = true;
            videoEl.style.width = "100%";
            videoEl.style.height = "100%";
            videoEl.style.objectFit = "contain";
            videoEl.style.background = "#000";
            container.appendChild(videoEl);
        }

        // Extract the actual path (e.g. "stream/cam01") from the RTSP URI to match the remote server exactly
        let actualPath = cameraId;
        if (data.stream_uri) {
            try {
                const urlObj = new URL(data.stream_uri);
                actualPath = urlObj.pathname.replace(/^\/+/, ''); // e.g. "stream/cam01"
            } catch(e) {}
        }

        // Pointing to local Docker MediaMTX Transcoder
        const webrtcEndpoint = `http://127.0.0.1:8889/${actualPath}/whep`;

        try {
            await startWHEP(videoEl, webrtcEndpoint);
        } catch (err) {
            console.error("Failed to connect WebRTC stream:", err);
            // Fallback UI or logic can go here
        }

        // Refresh camera list in GIS tab if loaded so active badge reflects immediately
        if (window.allCameras && window.allCameras.length) {
            window.allCameras.forEach(c => {
                c.operational_status = (c.camera_id === cameraId) ? "LIVE" : "ONLINE";
            });
            if (window.renderCameraList) {
                window.renderCameraList(window.allCameras);
            }
        }
    } catch (e) {
        console.warn("Failed to switch camera stream:", e);
    }
};

async function runVLMScan() {
    const textEl = document.getElementById("florence-output-text");
    const badgeEl = document.getElementById("vlm-engine-badge");
    const containerEl = document.getElementById("vlm-structured-results");

    if (textEl) textEl.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-cyan"></i> Running Multimodal VLM Forensic Analysis on <strong>${currentCamId}</strong>...`;
    if (containerEl) {
        containerEl.style.display = "none";
        containerEl.innerHTML = "";
    }

    try {
        const res = await fetch("/api/ai/vlm_scan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ camera_id: currentCamId })
        });
        const data = await res.json();

        if (data.error) {
            textEl.innerHTML = `<span style="color:#ef4444;"><i class="fa-solid fa-triangle-exclamation"></i> ${data.error}</span>`;
            return;
        }

        if (badgeEl) {
            badgeEl.textContent = data.configured ? "Gemini 2.5 Flash" : "Florence-2 GPU";
            badgeEl.style.color = data.configured ? "#a855f7" : "#0284c7";
            badgeEl.style.borderColor = data.configured ? "#a855f7" : "#0284c7";
        }

        if (textEl) {
            textEl.innerHTML = `<strong>${data.engine || 'VLM Engine'}:</strong> ${data.scene_summary || 'Forensic scene analysis complete.'}`;
        }

        if (containerEl) {
            containerEl.style.display = "flex";
            let html = "";

            // 1. Vehicles
            if (data.vehicles && data.vehicles.length > 0) {
                data.vehicles.forEach(v => {
                    const isRickshaw = (v.type && v.type.toLowerCase().includes("rickshaw")) || (v.make_model && v.make_model.toLowerCase().includes("rickshaw"));
                    const tagClass = isRickshaw ? "rickshaw" : "vehicle";
                    html += `
                        <div class="vlm-item-card">
                            <div class="vlm-title">
                                <span><i class="fa-solid fa-car-side text-cyan"></i> ${v.make_model || v.type}</span>
                                <span class="vlm-tag ${tagClass}">${v.type || 'Vehicle'}</span>
                            </div>
                            <div style="font-size:10px; color:var(--text-secondary); display:flex; gap:8px; align-items:center; margin-top:2px;">
                                <span><i class="fa-solid fa-palette"></i> ${v.color || 'Color'}</span>
                                ${v.plate_number && v.plate_number !== 'UNKNOWN' ? `<span class="vlm-tag plate">${v.plate_number}</span>` : ''}
                                ${v.details ? `<span>${v.details}</span>` : ''}
                            </div>
                        </div>
                    `;
                });
            }

            // 2. People & Clothing
            if (data.people && data.people.length > 0) {
                data.people.forEach(p => {
                    html += `
                        <div class="vlm-item-card">
                            <div class="vlm-title">
                                <span><i class="fa-solid fa-user text-green"></i> ${p.role || 'Person'}</span>
                                <span class="vlm-tag person">Attire</span>
                            </div>
                            <div style="font-size:10px; color:var(--text-secondary); display:flex; gap:10px; margin-top:2px;">
                                <span><strong>Upper:</strong> ${p.upper_clothing || 'Standard'}</span>
                                <span><strong>Lower:</strong> ${p.lower_clothing || 'Standard'}</span>
                                ${p.helmet === false ? '<span style="color:#ef4444; font-weight:bold;"><i class="fa-solid fa-triangle-exclamation"></i> NO HELMET</span>' : ''}
                            </div>
                        </div>
                    `;
                });
            }

            // 3. Traffic Anomalies
            if (data.traffic_anomalies && data.traffic_anomalies.length > 0) {
                html += `
                    <div class="vlm-item-card" style="border-color:#f59e0b; background:rgba(245, 158, 11, 0.08);">
                        <div class="vlm-title" style="color:#f59e0b;">
                            <span><i class="fa-solid fa-triangle-exclamation"></i> Observational Safety Alerts</span>
                        </div>
                        <div style="font-size:10px; color:var(--text-primary); margin-top:2px;">
                            ${data.traffic_anomalies.join(" • ")}
                        </div>
                    </div>
                `;
            }

            containerEl.innerHTML = html || `<div style="font-size:11px; color:var(--text-secondary);">No foreground subjects localized.</div>`;
        }
    } catch (e) {
        if (textEl) textEl.innerHTML = `<span style="color:#ef4444;"><i class="fa-solid fa-triangle-exclamation"></i> VLM Scan failed: ${e.message}</span>`;
    }
}

async function loadInitialANPRFeed() {
    const container = document.getElementById("live-anpr-items");
    if (!container) return;

    // Start with a clean slate for the real-time WebSocket feed
    container.innerHTML = `
        <div class="anpr-info-card" style="padding:12px; font-size:11px; color:var(--text-muted); background:var(--bg-card); border:1px solid var(--border-color); border-radius:6px;">
            <div style="font-weight:600; color:var(--text-main); margin-bottom:4px;">
                <i class="fa-solid fa-camera text-cyan"></i> Real-Time Telemetry Active
            </div>
            Visual tracking active. Detections for this specific camera will appear here dynamically as vehicles pass by.
        </div>
    `;
}

document.addEventListener("DOMContentLoaded", () => {
    loadInitialANPRFeed();
});

let currentWhepConnection = null;

async function startWHEP(videoElement, whepUrl) {
    if (currentWhepConnection) {
        currentWhepConnection.close();
        currentWhepConnection = null;
    }

    // Configure your TURN server credentials here
    const rtcConfig = {
        iceServers: [
            { urls: 'stun:stun.l.google.com:19302' },
            {
                urls: 'turn:YOUR_TURN_SERVER_IP:3478',
                username: 'ab835d950897622e10c8082b',
                credential: 'mnvd7fQ0r2Z0rskz'
            }
        ]
    };

    const peerConnection = new RTCPeerConnection(rtcConfig);
    currentWhepConnection = peerConnection;

    peerConnection.addTransceiver('video', { direction: 'recvonly' });

    peerConnection.ontrack = (event) => {
        if (videoElement.srcObject !== event.streams[0]) {
            videoElement.srcObject = event.streams[0];
        }
    };

    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);

    let fetchUrl = whepUrl;
    let headers = { 'Content-Type': 'application/sdp' };

    try {
        const urlObj = new URL(whepUrl);
        if (urlObj.username && urlObj.password) {
            headers['Authorization'] = 'Basic ' + btoa(urlObj.username + ':' + urlObj.password);
            urlObj.username = '';
            urlObj.password = '';
            fetchUrl = urlObj.toString();
        }
    } catch (e) {
        console.warn("Could not parse WHEP URL credentials", e);
    }

    const response = await fetch(fetchUrl, {
        method: 'POST',
        headers: headers,
        body: offer.sdp
    });

    if (!response.ok) {
        throw new Error("WHEP connection failed with status " + response.status);
    }

    const answerSdp = await response.text();
    await peerConnection.setRemoteDescription(new RTCSessionDescription({
        type: 'answer',
        sdp: answerSdp
    }));
    return peerConnection;
}
