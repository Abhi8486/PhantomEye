/**
 * Red EYE Core Application & Tab State Manager
 * Includes Tactical Keyboard Shortcuts, Web Audio Chime, and Real-Time Telemetry.
 */

document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initClock();
    initTabs();
    initKeyboardShortcuts();
    fetchCameras();
    loadOverviewTelemetry();
});

window.globalCameras = [];

async function fetchCameras() {
    try {
        const res = await fetch("/api/ingest");
        if (!res.ok) throw new Error("Failed to fetch cameras");
        const cameras = await res.json();
        window.globalCameras = cameras;

        const selectQuick = document.getElementById("select-cam-quick");
        if (selectQuick) {
            selectQuick.innerHTML = "";
            cameras.forEach(cam => {
                const opt = document.createElement("option");
                opt.value = cam.camera_id;
                opt.textContent = `${cam.camera_id} • ${cam.name}`;
                selectQuick.appendChild(opt);
            });
            // Select first by default
            if (cameras.length > 0) {
                selectQuick.value = cameras[0].camera_id;
                if (window.switchLiveCamera) {
                    window.switchLiveCamera(cameras[0].camera_id);
                }
            }
        }
    } catch (err) {
        console.error("Error fetching cameras:", err);
    }
}

function initClock() {
    const clockEl = document.getElementById("hud-clock");
    function update() {
        const now = new Date();
        const timeStr = now.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false });
        if (clockEl) clockEl.textContent = `${timeStr} IST`;
    }
    update();
    setInterval(update, 1000);
}

function initTabs() {
    const tabs = document.querySelectorAll(".nav-tab");
    const panes = document.querySelectorAll(".tab-pane");

    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const target = tab.getAttribute("data-tab");

            tabs.forEach(t => t.classList.remove("active"));
            panes.forEach(p => p.classList.remove("active"));

            tab.classList.add("active");
            const targetPane = document.getElementById(target);
            if (targetPane) {
                targetPane.classList.add("active");
            }

            if (target === "tab-live" && window.switchLiveCamera) {
                const imgEl = document.getElementById("live-stream-img");
                const quickSelect = document.getElementById("select-cam-quick");
                const camId = (quickSelect && quickSelect.value) ? quickSelect.value : (window.currentCamId || "CAM-001");
                if (!imgEl || !imgEl.src || !imgEl.src.includes(`/api/video/feed/${camId}`)) {
                    window.switchLiveCamera(camId);
                }
            }
            // Invalidate Leaflet map size on tab switch
            if (target === "tab-map" && window.gisMap) {
                setTimeout(() => window.gisMap.invalidateSize(), 150);
            }
            if (target === "tab-trajectory" && window.trajectoryMap) {
                setTimeout(() => window.trajectoryMap.invalidateSize(), 150);
            }
            if (target === "tab-analytics" && window.initAnalyticsCharts) {
                window.initAnalyticsCharts();
            }
            if (target === "tab-vms" && window.loadVMSMatrix) {
                window.loadVMSMatrix();
            }
            if (target === "tab-anomalies" && window.loadActiveAnomalies) {
                window.loadActiveAnomalies();
            }
        });
    });
}

function initKeyboardShortcuts() {
    const tabMap = ["tab-map", "tab-live", "tab-anpr", "tab-trajectory", "tab-vms", "tab-analytics", "tab-anomalies"];

    document.addEventListener("keydown", (e) => {
        if (!e || !e.key) return;

        // Do not trigger if typing in text inputs
        if (document.activeElement && ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) {
            if (e.key === "Escape") {
                document.activeElement.blur();
            }
            return;
        }

        // Keys 1 - 6 switch tabs
        if (e.key >= "1" && e.key <= "6") {
            const idx = parseInt(e.key) - 1;
            const targetTabId = tabMap[idx];
            const targetTabBtn = document.querySelector(`.nav-tab[data-tab="${targetTabId}"]`);
            if (targetTabBtn) targetTabBtn.click();
        }

        // "/" focuses search bar
        if (e.key === "/") {
            e.preventDefault();
            const searchTabBtn = document.querySelector(`.nav-tab[data-tab="tab-anpr"]`);
            if (searchTabBtn) searchTabBtn.click();
            setTimeout(() => {
                const sInput = document.getElementById("universal-search-input");
                if (sInput) sInput.focus();
            }, 100);
        }

        // "v" or "V" triggers Voice AI
        if (e.key.toLowerCase() === "v") {
            e.preventDefault();
            const voiceBtn = document.getElementById("btn-voice-command");
            if (voiceBtn) voiceBtn.click();
        }

        // "Escape" closes drawer
        if (e.key === "Escape") {
            const drawer = document.getElementById("alert-drawer");
            if (drawer) drawer.classList.remove("open");
        }
    });
}

// Tactical Web Audio Chime Generator
window.playTacticalAlertSound = function (isCritical = true) {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();

        osc.type = isCritical ? "sawtooth" : "sine";
        osc.frequency.setValueAtTime(isCritical ? 880 : 520, audioCtx.currentTime); // A5 or C5
        osc.frequency.exponentialRampToValueAtTime(isCritical ? 440 : 650, audioCtx.currentTime + 0.3);

        gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.35);

        osc.connect(gain);
        gain.connect(audioCtx.destination);

        osc.start();
        osc.stop(audioCtx.currentTime + 0.35);
    } catch (e) {
        // AudioContext restricted before user gesture
    }
};

async function loadOverviewTelemetry() {
    try {
        const res = await fetch("/api/analytics/overview");
        const data = await res.json();

        document.getElementById("stat-cameras").textContent = `${data.cameras.active} / 80,000`;
        document.getElementById("stat-depts").textContent = `${data.federation.departments_connected} / 26`;
        document.getElementById("stat-anpr").textContent = `${data.anpr.total_reads.toLocaleString()}`;
        document.getElementById("pending-alert-badge").textContent = data.alerts.pending;
    } catch (e) {
        console.error("Failed to load telemetry:", e);
    }
}

function initTheme() {
    const savedTheme = localStorage.getItem("redeye-theme") || localStorage.getItem("phantomeye-theme") || "light";
    setTheme(savedTheme);

    const toggleBtn = document.getElementById("btn-theme-toggle");
    if (toggleBtn) {
        toggleBtn.addEventListener("click", () => {
            const current = document.body.classList.contains("light-theme") ? "light" : "dark";
            const next = current === "light" ? "dark" : "light";
            setTheme(next);
        });
    }
}

function setTheme(theme) {
    const toggleBtn = document.getElementById("btn-theme-toggle");
    const toggleTxt = document.getElementById("theme-toggle-text");
    if (theme === "dark") {
        document.body.classList.remove("light-theme");
        document.body.classList.add("tactical-theme");
        if (toggleBtn) {
            toggleBtn.innerHTML = `<i class="fa-solid fa-sun"></i> <span id="theme-toggle-text">Light Mode</span>`;
        }
    } else {
        document.body.classList.remove("tactical-theme");
        document.body.classList.add("light-theme");
        if (toggleBtn) {
            toggleBtn.innerHTML = `<i class="fa-solid fa-moon"></i> <span id="theme-toggle-text">Dark Mode</span>`;
        }
    }
    localStorage.setItem("redeye-theme", theme);

    // Invalidate Leaflet maps & re-render analytics charts
    if (window.gisMap) setTimeout(() => window.gisMap.invalidateSize(), 150);
    if (window.trajectoryMap) setTimeout(() => window.trajectoryMap.invalidateSize(), 150);
    const activeTab = document.querySelector(".nav-tab.active");
    if (activeTab && activeTab.getAttribute("data-tab") === "tab-analytics" && window.initAnalyticsCharts) {
        setTimeout(() => window.initAnalyticsCharts(), 100);
    }
}
