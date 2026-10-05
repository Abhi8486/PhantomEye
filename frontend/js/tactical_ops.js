/**
 * Tactical Operations Module:
 * - Voice-Activated Tactical Radio AI Command
 * - Convoy & Syndicate Vehicle Association Matrix
 * - Predictive Police Roadblock & Geofence Interception Grid
 * - Tamper-Evident SHA-256 Forensic Dossier Export (Section 65B Admissibility)
 */

document.addEventListener("DOMContentLoaded", () => {
    initVoiceCommander();
    initConvoyDetector();
    initInterceptionPlanner();
    initForensicDossierExport();
});

// ─────────────────────────────────────────────────────────────
// 1. VOICE-ACTIVATED AI RADIO COMMAND
// ─────────────────────────────────────────────────────────────
function initVoiceCommander() {
    const btnVoice = document.getElementById("btn-voice-command");
    const voiceLabel = document.getElementById("voice-btn-label");
    const searchInput = document.getElementById("universal-search-input");
    const btnExec = document.getElementById("btn-run-universal-search");

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        if (btnVoice) {
            btnVoice.title = "Speech Recognition not supported in this browser.";
            btnVoice.addEventListener("click", () => {
                const simulated = prompt("Enter spoken police radio command (e.g. 'Find white Fortuner on Gandhinagar Highway'):");
                if (simulated) processVoiceSpokenText(simulated);
            });
        }
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.lang = "en-IN";
    recognition.interimResults = false;

    let isListening = false;

    if (btnVoice) {
        btnVoice.addEventListener("click", () => {
            if (isListening) {
                recognition.stop();
            } else {
                try {
                    recognition.start();
                    isListening = true;
                    btnVoice.classList.add("recording");
                    if (voiceLabel) voiceLabel.textContent = "Listening...";
                } catch (e) {
                    console.error("Speech start error:", e);
                }
            }
        });
    }

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        if (searchInput) searchInput.value = transcript;
        processVoiceSpokenText(transcript);
    };

    recognition.onerror = (event) => {
        console.warn("Speech recognition error:", event.error);
        isListening = false;
        if (btnVoice) btnVoice.classList.remove("recording");
        if (voiceLabel) voiceLabel.textContent = "Voice AI";
    };

    recognition.onend = () => {
        isListening = false;
        if (btnVoice) btnVoice.classList.remove("recording");
        if (voiceLabel) voiceLabel.textContent = "Voice AI";
    };
}

async function processVoiceSpokenText(text) {
    const searchInput = document.getElementById("universal-search-input");
    const btnExec = document.getElementById("btn-run-universal-search");

    try {
        const resp = await fetch("/api/tactical/voice-command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ spoken_text: text })
        });
        const data = await resp.json();

        if (searchInput && data.target_query) {
            searchInput.value = data.target_query;
        }

        // Show brief audio confirmation via browser speech synthesis
        if ('speechSynthesis' in window && data.radio_response) {
            const utter = new SpeechSynthesisUtterance(data.radio_response);
            utter.rate = 1.05;
            utter.pitch = 0.95;
            window.speechSynthesis.speak(utter);
        }

        if (btnExec) btnExec.click();
    } catch (e) {
        if (btnExec) btnExec.click();
    }
}

// ─────────────────────────────────────────────────────────────
// 2. CONVOY & SYNDICATE DETECTION
// ─────────────────────────────────────────────────────────────
function initConvoyDetector() {
    const btnConvoy = document.getElementById("btn-detect-convoy");
    const panel = document.getElementById("convoy-analysis-panel");

    if (!btnConvoy || !panel) return;

    btnConvoy.addEventListener("click", async () => {
        const isShown = panel.style.display === "block";
        panel.style.display = isShown ? "none" : "block";

        if (!isShown) {
            panel.scrollIntoView({ behavior: "smooth" });
            const grid = document.getElementById("convoy-cards-grid");
            grid.innerHTML = `<div style="color:#ffd600; padding:10px;"><i class="fa-solid fa-spinner fa-spin"></i> Analyzing co-traveling vehicle graph...</div>`;

            try {
                const resp = await fetch("/api/tactical/convoy/GJ01AB1234");
                const data = await resp.json();
                renderConvoyGrid(data);
            } catch (err) {
                grid.innerHTML = `<div style="color:#ff1744;">Failed to load convoy data: ${err.message}</div>`;
            }
        }
    });
}

function renderConvoyGrid(data) {
    const grid = document.getElementById("convoy-cards-grid");
    const vehicles = data.detected_convoy_vehicles || [];

    grid.innerHTML = "";

    vehicles.forEach(v => {
        const card = document.createElement("div");
        card.style.cssText = `
            background: #1e293b; border: 1px solid ${v.color_code}; border-radius: 6px; padding: 10px;
        `;
        card.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <span style="font-family:monospace; font-weight:bold; color:#ffd600; font-size:12px;">${v.plate_number}</span>
                <span style="background:${v.color_code}22; color:${v.color_code}; border:1px solid ${v.color_code}; padding:1px 6px; border-radius:3px; font-size:10px; font-weight:bold;">
                    ${Math.round(v.convoy_probability * 100)}% CONVOY PROB
                </span>
            </div>
            <div style="font-size:11px; color:#e2e8f0; font-weight:bold;">${v.make_model}</div>
            <div style="font-size:10px; color:#38bdf8; margin:2px 0;"><i class="fa-solid fa-user-ninja"></i> Role: ${v.syndicate_role}</div>
            <div style="font-size:10px; color:#94a3b8;"><i class="fa-solid fa-camera"></i> Shared Junctions: ${v.co_occurring_cameras.join(", ")} (Avg Δt: ${v.avg_delta_seconds}s)</div>
            <div style="margin-top:8px;">
                <button class="btn btn-sm btn-danger" style="width:100%; justify-content:center;" onclick="alert('🚨 Interception alert dispatched for convoy accomplice: ${v.plate_number}')">
                    <i class="fa-solid fa-triangle-exclamation"></i> Issue Interception Order
                </button>
            </div>
        `;
        grid.appendChild(card);
    });
}

// ─────────────────────────────────────────────────────────────
// 3. PREDICTIVE ROADBLOCK & GEOFENCE INTERCEPTION
// ─────────────────────────────────────────────────────────────
function initInterceptionPlanner() {
    const btnRoadblock = document.getElementById("btn-open-interception-modal");
    const panel = document.getElementById("interception-planner-panel");

    if (!btnRoadblock || !panel) return;

    btnRoadblock.addEventListener("click", async () => {
        const isShown = panel.style.display === "block";
        panel.style.display = isShown ? "none" : "block";

        if (!isShown) {
            panel.scrollIntoView({ behavior: "smooth" });
            const grid = document.getElementById("interception-checkpoints-grid");
            grid.innerHTML = `<div style="color:#ff1744; padding:10px;"><i class="fa-solid fa-spinner fa-spin"></i> Calculating downstream escape cone & roadblock ETAs...</div>`;

            try {
                const resp = await fetch("/api/tactical/predict-interception", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ plate_number: "GJ01AB1234", current_speed_kmh: 68.0, last_camera_id: "CAM-016" })
                });
                const data = await resp.json();
                renderInterceptionGrid(data);
            } catch (err) {
                grid.innerHTML = `<div style="color:#ff1744;">Failed to load interception plan: ${err.message}</div>`;
            }
        }
    });
}

function renderInterceptionGrid(data) {
    const grid = document.getElementById("interception-checkpoints-grid");
    const checkpoints = data.checkpoints || [];

    grid.innerHTML = "";

    checkpoints.forEach((cp, idx) => {
        const card = document.createElement("div");
        card.style.cssText = `
            background: #1e293b; border: 1px solid ${cp.color_code}; border-radius: 6px; padding: 10px;
        `;
        card.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <span style="font-weight:bold; color:#f8fafc; font-size:12px;">${cp.checkpoint_id}: ${cp.name}</span>
                <span style="background:${cp.color_code}22; color:${cp.color_code}; border:1px solid ${cp.color_code}; padding:1px 6px; border-radius:3px; font-size:10px; font-weight:bold;">
                    ETA ${cp.eta_minutes}m (${cp.eta_timestamp})
                </span>
            </div>
            <div style="font-size:10px; color:#38bdf8; margin:2px 0;"><i class="fa-solid fa-route"></i> ${cp.road_type} (${cp.distance_km} km ahead)</div>
            <div style="font-size:10px; color:#cbd5e1; margin-bottom:6px;"><i class="fa-solid fa-shield"></i> Deployment: ${cp.recommended_deployment}</div>
            <button class="btn btn-sm btn-green" style="width:100%; justify-content:center;" onclick="dispatchCheckpointLock('${cp.checkpoint_id}', '${cp.name}')">
                <i class="fa-solid fa-lock"></i> Lock Checkpoint Grid
            </button>
        `;
        grid.appendChild(card);
    });
}

function dispatchCheckpointLock(cpId, name) {
    alert(`✅ COMMAND CONFIRMED:\nRoadblock grid locked at ${cpId} (${name}).\nDispatched portable spike strips & PCR interceptors.`);
}

// ─────────────────────────────────────────────────────────────
// 4. TAMPER-EVIDENT FORENSIC DOSSIER EXPORT (SEC 65B SHA-256)
// ─────────────────────────────────────────────────────────────
function initForensicDossierExport() {
    const btnDossier = document.getElementById("btn-export-dossier");
    if (!btnDossier) return;

    btnDossier.addEventListener("click", async () => {
        try {
            btnDossier.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Generating Hash...`;
            const resp = await fetch("/api/tactical/forensic-dossier/GJ01AB1234");
            const dossier = await resp.json();

            btnDossier.innerHTML = `<i class="fa-solid fa-file-shield text-cyan"></i> Sec 65B Dossier`;

            // Trigger JSON download with cryptographic hash
            const blob = new Blob([JSON.stringify(dossier, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `GJ_POLICE_DOSSIER_${dossier.target_plate}_${dossier.dossier_id}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);

            alert(`📜 SECTION 65B LEGAL DOSSIER GENERATED:\n\nDossier ID: ${dossier.dossier_id}\nSHA-256 Digital Signature:\n${dossier.digital_signature_sha256}\n\nDownloaded to your computer for court submission.`);
        } catch (err) {
            btnDossier.innerHTML = `<i class="fa-solid fa-file-shield text-cyan"></i> Sec 65B Dossier`;
            alert("Failed to export dossier: " + err.message);
        }
    });
}
