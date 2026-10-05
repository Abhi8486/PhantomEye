/**
 * Analytics Charts & VMS Federation Matrix Controller (Red EYE Command System)
 */

let deptChart = null;
let districtChart = null;

window.initAnalyticsCharts = async function() {
    try {
        const [deptRes, gapRes] = await Promise.all([
            fetch("/api/cameras/departments"),
            fetch("/api/analytics/gap-analysis")
        ]);

        const deptData = await deptRes.json();
        const gapData = await gapRes.json();

        // Safely extract arrays from backend responses
        const depts = Array.isArray(deptData) ? deptData : (deptData.departments || []);
        const districts = Array.isArray(gapData) ? gapData : (gapData.districts || []);

        renderDepartmentChart(depts);
        renderDistrictGapChart(districts);
        renderGapSummary(districts, depts);
    } catch (e) {
        console.error("Failed to load analytics data:", e);
    }
};

function renderDepartmentChart(depts) {
    const ctx = document.getElementById("chart-depts");
    if (!ctx) return;

    if (deptChart) deptChart.destroy();

    const topDepts = depts.slice(0, 8);
    const labels = topDepts.map(d => (d.department || "").replace(" Department", ""));
    const counts = topDepts.map(d => d.camera_count || d.count || 0);

    const isLight = document.body.classList.contains("light-theme");
    const legendColor = isLight ? "#090d16" : "#f0f4fc";
    const borderColor = isLight ? "#ffffff" : "#111722";

    deptChart = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: labels,
            datasets: [{
                data: counts,
                backgroundColor: [
                    "#0284c7", "#16a34a", "#eab308", "#dc2626",
                    "#8b5cf6", "#f97316", "#06b6d4", "#84cc16"
                ],
                borderWidth: 2,
                borderColor: borderColor
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "right",
                    labels: {
                        color: legendColor,
                        font: { size: 11, weight: "600", family: "Inter" },
                        padding: 12
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const val = context.parsed;
                            const pct = total > 0 ? ((val / total) * 100).toFixed(1) : 0;
                            return ` ${context.label}: ${val} cameras (${pct}%)`;
                        }
                    }
                }
            }
        }
    });
}

function renderDistrictGapChart(districts) {
    const ctx = document.getElementById("chart-districts");
    if (!ctx) return;

    if (districtChart) districtChart.destroy();

    const labels = districts.map(d => (d.district || "").replace(" District", ""));
    const deployed = districts.map(d => d.cameras_deployed || 0);
    const recommended = districts.map(d => d.recommended_additions || 0);

    const isLight = document.body.classList.contains("light-theme");
    const textColor = isLight ? "#090d16" : "#f0f4fc";
    const mutedColor = isLight ? "#334155" : "#8b9bb4";
    const gridColor = isLight ? "rgba(0, 0, 0, 0.07)" : "rgba(255, 255, 255, 0.05)";

    districtChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "Cameras Deployed",
                    data: deployed,
                    backgroundColor: "#0284c7",
                    borderRadius: 4
                },
                {
                    label: "Recommended Gap Fix",
                    data: recommended,
                    backgroundColor: isLight ? "rgba(220, 38, 38, 0.75)" : "rgba(255, 23, 68, 0.6)",
                    borderRadius: 4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    ticks: { color: mutedColor, font: { size: 11, family: "Inter" } },
                    grid: { color: gridColor }
                },
                y: {
                    ticks: { color: mutedColor, font: { size: 11, family: "Inter" } },
                    grid: { color: gridColor },
                    beginAtZero: true
                }
            },
            plugins: {
                legend: {
                    labels: { color: textColor, font: { size: 11, weight: "600", family: "Inter" } }
                },
                tooltip: {
                    callbacks: {
                        afterBody: function(items) {
                            const idx = items[0].dataIndex;
                            const d = districts[idx];
                            return `Deficit Status: ${d.coverage_rating || 'EVALUATING'}`;
                        }
                    }
                }
            }
        }
    });
}

function renderGapSummary(districts, depts) {
    const totalDeployed = districts.reduce((acc, d) => acc + (d.cameras_deployed || 0), 0);
    const totalDeficit = districts.reduce((acc, d) => acc + (d.recommended_additions || 0), 0);

    const deployedEl = document.getElementById("gap-stat-deployed");
    if (deployedEl) deployedEl.textContent = `${totalDeployed} Active`;

    const deficitEl = document.getElementById("gap-stat-deficit");
    if (deficitEl) deficitEl.textContent = `+${totalDeficit} Cameras`;

    // Find highest deficit district
    let maxDist = null;
    districts.forEach(d => {
        if (!maxDist || (d.recommended_additions || 0) > (maxDist.recommended_additions || 0)) {
            maxDist = d;
        }
    });

    const critEl = document.getElementById("gap-stat-critical");
    if (critEl && maxDist) {
        critEl.textContent = `${maxDist.district.replace(" District", "")} (+${maxDist.recommended_additions})`;
    }

    // Populate table
    const tableBody = document.getElementById("gap-table-body");
    if (!tableBody) return;

    tableBody.innerHTML = "";
    districts.forEach(d => {
        const tr = document.createElement("tr");
        const rating = d.coverage_rating || "MODERATE COVERAGE";
        const isCrit = rating.includes("CRITICAL");
        const badgeColor = isCrit ? "badge-red" : "badge-cyan";
        const priorityText = isCrit ? "HIGH PRIORITY (Phase 1)" : "STANDARD (Phase 2)";
        const priorityColor = isCrit ? "#dc2626" : "#0284c7";

        tr.innerHTML = `
            <td style="font-weight: 600;">${d.district}</td>
            <td><strong>${d.cameras_deployed}</strong></td>
            <td><span class="text-green">${d.active} Streams</span></td>
            <td><span class="badge ${badgeColor}" style="font-size:11px;">${rating}</span></td>
            <td><strong class="text-red">+${d.recommended_additions} Units</strong></td>
            <td><strong style="color:${priorityColor}; font-size:11px;"><i class="fa-solid ${isCrit ? 'fa-triangle-exclamation' : 'fa-circle-check'}"></i> ${priorityText}</strong></td>
        `;
        tableBody.appendChild(tr);
    });
}

window.loadVMSMatrix = async function() {
    const container = document.getElementById("vms-clusters-container");
    if (!container) return;

    try {
        const res = await fetch("/api/vms/clusters");
        const data = await res.json();
        container.innerHTML = "";

        data.clusters.forEach(cl => {
            const telem = cl.telemetry || {};
            const isOnline = cl.status === 'ONLINE';
            const card = document.createElement("div");
            card.className = "vms-card";
            card.innerHTML = `
                <div class="vms-card-header">
                    <strong class="vms-card-title">${cl.name}</strong>
                    <span class="vms-status-badge ${isOnline ? 'status-online' : 'status-offline'}">
                        <i class="fa-solid fa-circle ${isOnline ? 'pulse-green' : ''}" style="font-size:8px;"></i> ${cl.status}
                    </span>
                </div>
                <div class="vms-card-dept">Department: <strong>${cl.department}</strong></div>
                <div class="vms-protocol-box">
                    Adapter: <span class="vms-adapter-name">${cl.adapter_type.toUpperCase()}</span> | Protocol: <span class="vms-protocol-name">${telem.protocol || 'Standard RTSP'}</span>
                </div>
                <div class="vms-card-footer">
                    <span>Active Streams: <strong class="vms-stat-val">${cl.camera_count}</strong></span>
                    <span>Uptime: <strong class="vms-stat-uptime">${telem.uptime_hours || 100} hrs</strong></span>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (e) {
        console.error("Failed to load VMS clusters:", e);
    }
};
