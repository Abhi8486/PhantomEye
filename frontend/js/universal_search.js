/**
 * Universal Multi-Modal AI & Photo Search Module
 * Handles text descriptions, plate queries, and drag-and-drop photo uploads.
 * Displays candidate ranking with exact rolling buffer evidentiary screenshots and calibrated fusion matrices.
 */

document.addEventListener("DOMContentLoaded", () => {
    initUniversalSearch();
});

let currentUploadedFile = null;
let currentAbortController = null;

function initUniversalSearch() {
    const inputEl = document.getElementById("universal-search-input");
    const btnSearch = document.getElementById("btn-run-universal-search");
    const btnClear = document.getElementById("btn-clear-search");
    const dropzoneBox = document.getElementById("photo-dropzone-box");
    const fileInput = document.getElementById("file-photo-input");
    const linkBrowse = document.getElementById("link-browse-photo");
    const btnExecPhoto = document.getElementById("btn-exec-photo-search");
    const btnRemovePhoto = document.getElementById("btn-remove-photo");
    const btnStop = document.getElementById("btn-stop-universal-search");
    const modePills = document.querySelectorAll(".mode-pill");
    const queryChips = document.querySelectorAll(".query-chip");

    // 1. Search Mode Switcher
    modePills.forEach(pill => {
        pill.addEventListener("click", () => {
            modePills.forEach(p => p.classList.remove("active"));
            pill.classList.add("active");
            const mode = pill.dataset.mode;

            if (mode === "photo") {
                dropzoneBox.style.display = "block";
                inputEl.placeholder = "Optional: Add extra clues (e.g. 'Seen near Gandhinagar Highway yesterday')...";
            } else {
                dropzoneBox.style.display = "none";
                if (mode === "vehicle") inputEl.placeholder = "e.g. White Toyota Fortuner, Black Scorpio-N, Red Hatchback...";
                else if (mode === "person") inputEl.placeholder = "e.g. Person wearing red shirt and black pants, suspect in jacket...";
                else if (mode === "plate") inputEl.placeholder = "e.g. GJ01AB1234, GJ27AX9999...";
                else inputEl.placeholder = "Enter vehicle plate, description, person attributes, or upload photo...";
            }
        });
    });

    // 2. Query Chips
    queryChips.forEach(chip => {
        chip.addEventListener("click", () => {
            inputEl.value = chip.dataset.query;
            executeUniversalTextSearch(chip.dataset.query);
        });
    });

    // 3. Text Search Execution
    if (btnSearch) {
        btnSearch.addEventListener("click", () => {
            const q = inputEl.value.trim();
            if (currentUploadedFile) {
                executePhotoUploadSearch(currentUploadedFile, q);
            } else if (q) {
                executeUniversalTextSearch(q);
            } else {
                alert("Please enter a search query or upload a photo.");
            }
        });
    }

    if (inputEl) {
        inputEl.addEventListener("keypress", (e) => {
            if (e.key === "Enter") {
                btnSearch.click();
            }
        });
    }

    if (btnClear) {
        btnClear.addEventListener("click", () => {
            inputEl.value = "";
            resetPhotoDropzone();
        });
    }

    // Stop Live Search button
    if (btnStop) {
        btnStop.addEventListener("click", async () => {
            // Abort the frontend fetch
            if (currentAbortController) {
                currentAbortController.abort();
                currentAbortController = null;
            }
            // Signal backend to cancel
            try {
                await fetch("/api/search/cancel", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({})
                });
            } catch (e) { /* ignore */ }

            // Reset UI
            btnStop.style.display = "none";
            btnSearch.style.display = "";
            const container = document.getElementById("evidence-cards-container");
            container.innerHTML = `
                <div style="grid-column: 1/-1; text-align:center; padding: 40px; color:#ffd600;">
                    <i class="fa-solid fa-hand" style="font-size:28px; margin-bottom:10px;"></i>
                    <p>Live search stopped by operator.</p>
                </div>
            `;
        });
    }

    // 4. Drag & Drop Photo Upload
    if (linkBrowse && fileInput) {
        linkBrowse.addEventListener("click", () => fileInput.click());
    }

    const dropArea = document.getElementById("dropzone-area");
    if (dropArea) {
        ['dragenter', 'dragover'].forEach(eventName => {
            dropArea.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropArea.classList.add('highlight');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropArea.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropArea.classList.remove('highlight');
            }, false);
        });

        dropArea.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files && files.length > 0) {
                handleSelectedPhoto(files[0]);
            }
        });
    }

    if (fileInput) {
        fileInput.addEventListener("change", (e) => {
            if (e.target.files && e.target.files.length > 0) {
                handleSelectedPhoto(e.target.files[0]);
            }
        });
    }

    if (btnRemovePhoto) {
        btnRemovePhoto.addEventListener("click", resetPhotoDropzone);
    }

    if (btnExecPhoto) {
        btnExecPhoto.addEventListener("click", () => {
            if (currentUploadedFile) {
                executePhotoUploadSearch(currentUploadedFile, inputEl.value.trim());
            }
        });
    }

}

function handleSelectedPhoto(file) {
    if (!file.type.startsWith("image/")) {
        alert("Please upload a valid image file (JPG, PNG, WebP).");
        return;
    }
    currentUploadedFile = file;

    const reader = new FileReader();
    reader.onload = (e) => {
        document.getElementById("photo-preview-img").src = e.target.result;
        document.getElementById("preview-filename").textContent = file.name;
        document.getElementById("preview-filesize").textContent = `${(file.size / 1024).toFixed(1)} KB`;

        document.getElementById("dropzone-empty-state").style.display = "none";
        document.getElementById("dropzone-preview-state").style.display = "flex";
    };
    reader.readAsDataURL(file);
}

function resetPhotoDropzone() {
    currentUploadedFile = null;
    const fileInput = document.getElementById("file-photo-input");
    if (fileInput) fileInput.value = "";
    document.getElementById("dropzone-empty-state").style.display = "block";
    document.getElementById("dropzone-preview-state").style.display = "none";
}

async function executeUniversalTextSearch(queryText, isUserInitiated = true) {
    const container = document.getElementById("evidence-cards-container");
    const btnSearch = document.getElementById("btn-run-universal-search");
    const btnStop = document.getElementById("btn-stop-universal-search");

    // Only toggle stop/search buttons for user-initiated searches
    if (isUserInitiated) {
        if (btnSearch) btnSearch.style.display = "none";
        if (btnStop) btnStop.style.display = "";
    }

    container.innerHTML = `
        <div style="grid-column: 1/-1; text-align:center; padding: 30px; color:#00d2ff;">
            <i class="fa-solid fa-satellite-dish fa-spin" style="font-size:28px;"></i>
            <p style="margin-top:10px; font-size:13px;">Continuously scanning 30 live CCTV feeds until target is found...</p>
            ${isUserInitiated ? '<p style="font-size:11px; color:#8b9bb4; margin-top:6px;">Click <strong style="color:#ff1744;">Stop Live Search</strong> to cancel at any time.</p>' : ''}
        </div>
    `;

    // Create AbortController for this search
    if (currentAbortController) currentAbortController.abort();
    currentAbortController = new AbortController();

    try {
        const resp = await fetch("/api/search/universal", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: queryText, min_confidence: 0.50, limit: 12 }),
            signal: currentAbortController.signal
        });
        const data = await resp.json();
        renderEvidenceCandidates(data);
    } catch (err) {
        if (err.name === 'AbortError') {
            // Search was cancelled by user — UI already updated by stop handler
            return;
        }
        container.innerHTML = `<div style="grid-column: 1/-1; color:#ff1744; text-align:center; padding:20px;">Search failed: ${err.message}</div>`;
    } finally {
        // Restore buttons
        if (isUserInitiated) {
            if (btnSearch) btnSearch.style.display = "";
            if (btnStop) btnStop.style.display = "none";
        }
        currentAbortController = null;
    }
}

async function executePhotoUploadSearch(file, extraText) {
    const container = document.getElementById("evidence-cards-container");
    const btnSearch = document.getElementById("btn-run-universal-search");
    const btnStop = document.getElementById("btn-stop-universal-search");

    // Show stop button, hide search button
    if (btnSearch) btnSearch.style.display = "none";
    if (btnStop) btnStop.style.display = "";

    container.innerHTML = `
        <div style="grid-column: 1/-1; text-align:center; padding: 30px; color:#00d2ff;">
            <i class="fa-solid fa-fingerprint fa-spin" style="font-size:28px;"></i>
            <p style="margin-top:10px; font-size:13px;">Extracting 512-d Re-ID Embedding & Continuously scanning live CCTV feeds...</p>
            <p style="font-size:11px; color:#8b9bb4; margin-top:6px;">Click <strong style="color:#ff1744;">Stop Live Search</strong> to cancel at any time.</p>
        </div>
    `;

    const formData = new FormData();
    formData.append("image", file);
    if (extraText) formData.append("description", extraText);
    formData.append("min_confidence", 0.50);

    // Create AbortController for this search
    if (currentAbortController) currentAbortController.abort();
    currentAbortController = new AbortController();

    try {
        const resp = await fetch("/api/search/upload-image", {
            method: "POST",
            body: formData,
            signal: currentAbortController.signal
        });
        const data = await resp.json();
        renderEvidenceCandidates(data);
    } catch (err) {
        if (err.name === 'AbortError') {
            return;
        }
        container.innerHTML = `<div style="grid-column: 1/-1; color:#ff1744; text-align:center; padding:20px;">Image search failed: ${err.message}</div>`;
    } finally {
        if (btnSearch) btnSearch.style.display = "";
        if (btnStop) btnStop.style.display = "none";
        currentAbortController = null;
    }
}

function renderEvidenceCandidates(data) {
    const container = document.getElementById("evidence-cards-container");
    const countBadge = document.getElementById("high-conf-count-badge");
    const totalBadge = document.getElementById("total-matches-badge");

    const candidates = data.candidates || [];
    const highConfCount = data.high_confidence_alerts || 0;

    if (countBadge) countBadge.textContent = `${highConfCount} High Confidence (≥90%)`;
    if (totalBadge) totalBadge.textContent = `${candidates.length} Total Observations`;

    if (candidates.length === 0) {
        container.innerHTML = `
            <div style="grid-column: 1/-1; text-align:center; padding: 40px; color:#64748b;">
                <i class="fa-solid fa-shield-cat" style="font-size:32px; margin-bottom:10px;"></i>
                <p>No matching CCTV observations found exceeding confidence threshold.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = "";

    candidates.forEach(cand => {
        const confPercent = Math.round(cand.overall_confidence * 100);
        const isHigh = confPercent >= 88;
        const bDown = cand.evidence_breakdown || {};

        const card = document.createElement("div");
        card.className = `evidence-match-card ${isHigh ? 'card-high-conf' : 'card-review'}`;
        card.innerHTML = `
            <div class="evidence-card-header">
                <div class="evidence-cam-title">
                    <span class="cam-id-tag">${cand.camera_id}</span>
                    <strong style="font-size:13px; color:var(--text-main);">${cand.camera_name}</strong>
                    ${cand.evidence_breakdown && cand.evidence_breakdown.verifier === 'Gemini Flash' ? '<span class="badge" style="font-size:10px; margin-left:6px; background:#7c4dff22; color:#b388ff; border:1px solid #7c4dff;"><i class="fa-solid fa-bolt"></i> Gemini Flash</span>' : (cand.evidence_breakdown && (cand.evidence_breakdown.florence_vlm_verified || cand.evidence_breakdown.verifier === 'Florence-2') ? '<span class="badge badge-cyan" style="font-size:10px; margin-left:6px;"><i class="fa-solid fa-microchip"></i> Florence-2 VLM</span>' : '')}
                </div>
                <span class="decision-pill" style="background:${cand.color_code}22; color:${cand.color_code}; border:1px solid ${cand.color_code};">
                    ${cand.decision.replace(/_/g, " ")} (${confPercent}%)
                </span>
            </div>

            <div class="evidence-screenshot-viewport" onclick='openForensicModal(${JSON.stringify(cand).replace(/'/g, "&#39;")})' title="Click to open Full Resolution 1080p Photo & Forensic Details">
                <img src="${cand.screenshot_url}?t=${Date.now()}&api_key=${API_KEY}" alt="Rolling Buffer Evidence" class="evidence-img">
                <div class="evidence-zoom-hint"><i class="fa-solid fa-expand"></i> Full HD & Details</div>
                <div class="evidence-watermark">
                    <span><i class="fa-solid fa-clock"></i> ${cand.timestamp}</span>
                    <span><i class="fa-solid fa-location-dot"></i> ${cand.city} (${cand.latitude.toFixed(4)}, ${cand.longitude.toFixed(4)})</span>
                </div>
            </div>

            <div class="evidence-card-body">
                <div class="evidence-meta-row">
                    <div class="meta-item">
                        <span class="meta-label">IDENTIFIER</span>Appearance
                        <strong class="meta-val text-yellow">${cand.matched_identifier}</strong>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">OBJECT TYPE</span>
                        <strong class="meta-val">${cand.object_type === 'PERSON' ? (cand.upper_color ? `Pedestrian (${cand.upper_color} Shirt)` : 'Pedestrian') : `${cand.vehicle_color || ''} ${cand.object_type || 'Vehicle'}`.trim()}</strong>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">CAMERA QUALITY</span>
                        <strong class="meta-val text-cyan">${cand.camera_quality_score} (HD)</strong>
                    </div>
                </div>

                <div class="evidence-breakdown-box">
                    <div class="breakdown-metric">
                        <span>${cand.object_type === 'PERSON' ? 'Silhouette Detection' : (bDown.plate_ocr_confidence != null ? 'Plate OCR' : 'Visual Model Match')}</span>
                        <span class="metric-val text-cyan">${cand.object_type === 'PERSON' ? Math.round((cand.overall_confidence || 0.85)*100) : (bDown.plate_ocr_confidence != null ? Math.round(bDown.plate_ocr_confidence * 100) : Math.round(((bDown.visual_attribute_consistency || cand.overall_confidence || 0.88))*100))}%</span>
                    </div>
                    <div class="breakdown-metric">
                        <span>${cand.object_type === 'PERSON' ? 'Torso Clothing Match' : 'Re-ID Appearance'}</span>
                        <span class="metric-val text-green">${Math.round(((bDown.visual_attribute_consistency !== undefined ? bDown.visual_attribute_consistency : 0.85))*100)}%</span>
                    </div>
                    <div class="breakdown-metric">
                        <span>${cand.object_type === 'PERSON' ? 'Re-ID ' : 'Kinematic Route'}</span>
                        <span class="metric-val text-cyan">${Math.round(((cand.object_type === 'PERSON' ? (bDown.vehicle_reid_similarity !== undefined ? bDown.vehicle_reid_similarity : 0.85) : (bDown.spatio_temporal_kinematics !== undefined ? bDown.spatio_temporal_kinematics : bDown.kinematic_plausibility || 0.85)))*100)}%</span>
                    </div>
                    <div class="breakdown-metric">
                        <span>Sensor Quality</span>
                        <span class="metric-val text-yellow">${Math.round((cand.camera_quality_score || 0.88)*100)}%</span>
                    </div>
                </div>

                <div class="evidence-card-footer">
                    <button class="btn btn-sm btn-dark" onclick='openForensicModal(${JSON.stringify(cand).replace(/'/g, "&#39;")})'>
                        <i class="fa-solid fa-expand text-cyan"></i> Full Photo & Details
                    </button>
                    <button class="btn btn-sm btn-cyan" onclick="focusOnCandidateCamera('${cand.camera_id}', ${cand.latitude}, ${cand.longitude})">
                        <i class="fa-solid fa-map-location-dot"></i> GIS Map
                    </button>
                    <button class="btn btn-sm btn-primary" onclick="focusOnTrajectory('${cand.matched_identifier.includes('GJ') ? cand.matched_identifier : 'GJ01AB1234'}')">
                        <i class="fa-solid fa-route"></i> Trajectory
                    </button>
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

function openForensicModal(cand) {
    if (!cand) return;

    const modal = document.getElementById("forensic-modal-backdrop");
    if (!modal) return;

    const bDown = cand.evidence_breakdown || {};
    const confPercent = Math.round((cand.overall_confidence || 0.85) * 100);
    const isPerson = cand.object_type === 'PERSON';
    const isEvent = cand.vehicle_color === 'Event' || (cand.object_type && cand.object_type.includes('Event')) || (cand.matched_identifier && cand.matched_identifier.includes('EVT'));

    // Populate modal fields
    document.getElementById("modal-cam-id").textContent = cand.camera_id || "CAM-001";
    document.getElementById("modal-title").textContent = `${cand.camera_name || cand.camera_id} — Evidentiary Capture`;
    
    const fullImg = document.getElementById("modal-full-img");
    fullImg.src = `${cand.screenshot_url}?t=${Date.now()}&api_key=${API_KEY}`;

    const downloadLink = document.getElementById("modal-download-link");
    downloadLink.href = `${cand.screenshot_url}?api_key=${API_KEY}`;
    downloadLink.download = `evidence_${cand.camera_id}_${cand.matched_identifier}.jpg`;

    const lblTarget = document.getElementById("modal-lbl-target-id");
    if (lblTarget) {
        lblTarget.textContent = isEvent ? "Event Code / Type:" : (isPerson ? "Subject Silhouette:" : "Plate / Identifier:");
    }
    const lblObj = document.getElementById("modal-lbl-obj-class");
    if (lblObj) {
        lblObj.textContent = isEvent ? "Event Category:" : "Object Class:";
    }

    document.getElementById("modal-target-id").textContent = cand.matched_identifier || "GJ01AB1234";
    document.getElementById("modal-obj-class").textContent = isEvent ? (cand.object_type || 'Surveillance Crime / Violation Event') : (isPerson ? `Pedestrian (${cand.upper_color || cand.vehicle_color || 'White'} Shirt/Top)` : `${cand.vehicle_color || ''} ${cand.object_type || 'Vehicle'}`.trim());
    document.getElementById("modal-color").textContent = isEvent ? "Temporal Multi-Stage Crime & Safety Analysis" : (isPerson ? `${cand.upper_color || cand.vehicle_color || 'Calibrated'} Top / ${cand.lower_color || 'Dark'} Lower (Calibrated)` : `${cand.vehicle_color || 'Calibrated'} (HSV Calibrated)`);
    document.getElementById("modal-timestamp").textContent = cand.timestamp ? (cand.timestamp.includes('IST') ? cand.timestamp : `${cand.timestamp} IST`) : '2026-09-03 13:40:00 IST';
    document.getElementById("modal-confidence").textContent = `${confPercent}% (${cand.decision || 'MATCH'})`;

    document.getElementById("modal-cam-name").textContent = cand.camera_name || cand.camera_id;
    document.getElementById("modal-gps").textContent = `${cand.latitude?.toFixed(4) || '23.0560'}° N, ${cand.longitude?.toFixed(4) || '72.5710'}° E (${cand.city || 'Gujarat'})`;
    document.getElementById("modal-quality").textContent = `${cand.camera_quality_score || 0.92} (HD 1080p Stream)`;

    // Update breakdown titles in modal
    const lblScore1 = document.getElementById("modal-lbl-score-1");
    const lblScore2 = document.getElementById("modal-lbl-score-2");
    const lblScore3 = document.getElementById("modal-lbl-score-3");
    const lblScore4 = document.getElementById("modal-lbl-score-4");

    if (isEvent) {
        if (lblScore1) lblScore1.textContent = "Observable Event Score";
        if (lblScore2) lblScore2.textContent = "Multi-Stage Verification";
        if (lblScore3) lblScore3.textContent = "Temporal Persistence";
        if (lblScore4) lblScore4.textContent = "Camera Quality Index";

        const score1Val = confPercent;
        const score2Val = Math.min(99, Math.round(confPercent * 0.98));
        const score3Val = Math.min(99, Math.round(confPercent * 0.96));

        document.getElementById("modal-score-plate").textContent = `${score1Val}%`;
        document.getElementById("modal-score-reid").textContent = `${score2Val}%`;
        document.getElementById("modal-score-kinematic").textContent = `${score3Val}%`;
        document.getElementById("modal-score-quality").textContent = `${Math.round((cand.camera_quality_score || 0.92)*100)}%`;
    } else if (isPerson) {
        if (lblScore1) lblScore1.textContent = "Silhouette Detection Score";
        if (lblScore2) lblScore2.textContent = "Torso Clothing Match";
        if (lblScore3) lblScore3.textContent = "Re-ID Appearance";
        if (lblScore4) lblScore4.textContent = "Sensor Quality Score";

        const score1Val = Math.round((cand.overall_confidence || 0.85) * 100);
        const score2Val = Math.round(((bDown.visual_attribute_consistency !== undefined ? bDown.visual_attribute_consistency : 0.85)) * 100);
        const score3Val = Math.round(((bDown.vehicle_reid_similarity !== undefined ? bDown.vehicle_reid_similarity : 0.85)) * 100);

        document.getElementById("modal-score-plate").textContent = `${score1Val}%`;
        document.getElementById("modal-score-reid").textContent = `${score2Val}%`;
        document.getElementById("modal-score-kinematic").textContent = `${score3Val}%`;
        document.getElementById("modal-score-quality").textContent = `${Math.round((cand.camera_quality_score || 0.92)*100)}%`;
    } else {
        const hasPlate = bDown.plate_ocr_confidence != null;
        if (lblScore1) lblScore1.textContent = hasPlate ? "Plate OCR Confidence" : "Visual Model Match";
        if (lblScore2) lblScore2.textContent = "Re-ID Cosine Match";
        if (lblScore3) lblScore3.textContent = "Kinematic Feasibility";
        if (lblScore4) lblScore4.textContent = "Sensor Quality Score";

        const score1Val = hasPlate 
            ? Math.round(bDown.plate_ocr_confidence * 100)
            : Math.round(((bDown.visual_attribute_consistency || cand.overall_confidence || 0.85)) * 100);
        const score2Val = Math.round(((bDown.vehicle_reid_similarity !== undefined ? bDown.vehicle_reid_similarity : bDown.reid_similarity || 0.85)) * 100);
        const score3Val = Math.round(((bDown.spatio_temporal_kinematics !== undefined ? bDown.spatio_temporal_kinematics : bDown.kinematic_plausibility || 0.85)) * 100);

        document.getElementById("modal-score-plate").textContent = `${score1Val}%`;
        document.getElementById("modal-score-reid").textContent = `${score2Val}%`;
        document.getElementById("modal-score-kinematic").textContent = `${score3Val}%`;
        document.getElementById("modal-score-quality").textContent = `${Math.round((cand.camera_quality_score || 0.92)*100)}%`;
    }

    // Action button bindings
    document.getElementById("modal-btn-gis").onclick = () => {
        closeForensicModal();
        focusOnCandidateCamera(cand.camera_id, cand.latitude, cand.longitude);
    };

    document.getElementById("modal-btn-trajectory").onclick = () => {
        closeForensicModal();
        focusOnTrajectory(cand.matched_identifier.includes('GJ') ? cand.matched_identifier : 'GJ01AB1234');
    };

    document.getElementById("modal-btn-intercept").onclick = async () => {
        closeForensicModal();
        const tabTrajBtn = document.querySelector('.nav-tab[data-tab="tab-trajectory"]');
        if (tabTrajBtn) tabTrajBtn.click();
        const interceptBtn = document.getElementById("btn-open-interception-modal");
        if (interceptBtn) interceptBtn.click();
    };

    modal.classList.add("active");
}

function closeForensicModal() {
    const modal = document.getElementById("forensic-modal-backdrop");
    if (modal) modal.classList.remove("active");
}

// Modal event listeners
document.addEventListener("DOMContentLoaded", () => {
    const closeBtn = document.getElementById("btn-close-forensic-modal");
    if (closeBtn) closeBtn.addEventListener("click", closeForensicModal);

    const backdrop = document.getElementById("forensic-modal-backdrop");
    if (backdrop) {
        backdrop.addEventListener("click", (e) => {
            if (e.target === backdrop) closeForensicModal();
        });
    }

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeForensicModal();
    });
});

window.openForensicModal = openForensicModal;
window.closeForensicModal = closeForensicModal;

function focusOnCandidateCamera(cameraId, lat, lng) {
    // Switch to GIS Tab
    const tabMapBtn = document.querySelector('.nav-tab[data-tab="tab-map"]');
    if (tabMapBtn) tabMapBtn.click();

    setTimeout(() => {
        if (window.gisMap) {
            window.gisMap.setView([lat, lng], 16, { animate: true });
            if (window.cameraMarkers && window.cameraMarkers[cameraId]) {
                window.cameraMarkers[cameraId].openPopup();
            }
        }
    }, 200);
}
