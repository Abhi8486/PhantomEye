/**
 * ANPR & VAHAN Intelligence Search Module
 */

document.addEventListener("DOMContentLoaded", () => {
    initANPRSearch();
    loadRecentANPR();
});

function initANPRSearch() {
    const inputEl = document.getElementById("search-plate-input");
    const btnSearch = document.getElementById("btn-run-search");
    const btnWanted = document.getElementById("btn-quick-wanted");

    if (btnSearch) {
        btnSearch.addEventListener("click", () => executeSearch(inputEl.value));
    }
    if (inputEl) {
        inputEl.addEventListener("keydown", (e) => {
            if (e.key === "Enter") executeSearch(inputEl.value);
        });
    }
    if (btnWanted) {
        btnWanted.addEventListener("click", () => executeSearch(null, true));
    }
}

async function loadRecentANPR() {
    try {
        const res = await fetch("/api/vehicles/anpr?limit=50");
        const data = await res.json();
        renderANPRTable(data.records);
    } catch (e) {
        console.warn("Failed to load recent ANPR:", e);
    }
}

async function executeSearch(queryStr, isFlaggedOnly = false) {
    try {
        let url = `/api/vehicles/search?`;
        if (queryStr) url += `query=${encodeURIComponent(queryStr)}&`;
        if (isFlaggedOnly) url += `is_flagged=true`;

        const res = await fetch(url);
        const data = await res.json();
        renderANPRTable(data.results);
    } catch (e) {
        console.error("Search failed:", e);
    }
}

function renderANPRTable(records) {
    const tbody = document.getElementById("anpr-table-body");
    tbody.innerHTML = "";

    if (!records || records.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 20px; color:#8b9bb4;">No matching vehicle records found.</td></tr>`;
        return;
    }

    records.forEach(r => {
        const tr = document.createElement("tr");
        const isFlagged = r.is_flagged === 1 || r.is_flagged === true;

        tr.innerHTML = `
            <td>${new Date(r.timestamp).toLocaleTimeString("en-IN")}</td>
            <td><span class="plate-pill">${r.plate_number}</span></td>
            <td><strong>${r.vehicle_color || ''}</strong> ${r.vahan_model || r.vehicle_type}</td>
            <td>${r.vahan_owner || 'Registered Citizen'}</td>
            <td><strong style="color:#00d2ff;">${r.camera_id}</strong> (${r.city})</td>
            <td>
                ${isFlagged ? 
                    `<span class="badge badge-danger">${r.vahan_status}</span>` : 
                    `<span class="badge badge-dark" style="color:#00e676;">${r.vahan_status || 'NOMINAL'}</span>`}
            </td>
            <td>
                <button class="btn btn-sm btn-cyan" onclick="focusOnTrajectory('${r.plate_number}')">
                    <i class="fa-solid fa-route"></i> Track Path
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}
