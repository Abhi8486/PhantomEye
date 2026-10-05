"""
Analytics & Blind-Spot Gap Analysis Router (Model 1 & 2 Analytics)
"""

from fastapi import APIRouter
from ..database.schema import get_db_connection

router = APIRouter(prefix="/api/analytics", tags=["Analytics & Blind-Spot Analysis"])


@router.get("/overview")
def get_system_overview():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Total and Active Cameras
    cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status='ACTIVE' THEN 1 ELSE 0 END) as active FROM cameras;")
    c_row = cursor.fetchone()

    # Total ANPR reads & flagged plates
    cursor.execute("SELECT COUNT(*) as total_anpr, SUM(is_flagged) as flagged_anpr FROM vehicle_anpr;")
    v_row = cursor.fetchone()

    # Active Alerts
    cursor.execute("SELECT COUNT(*) as total_alerts, SUM(CASE WHEN is_acknowledged=0 THEN 1 ELSE 0 END) as pending_alerts FROM alerts;")
    a_row = cursor.fetchone()

    # Department count
    cursor.execute("SELECT COUNT(DISTINCT department) as depts FROM cameras;")
    d_row = cursor.fetchone()

    conn.close()

    return {
        "cameras": {
            "total": c_row["total"] or 50,
            "active": c_row["active"] or 47,
            "offline": (c_row["total"] or 50) - (c_row["active"] or 47),
            "statewide_target_scale": 80000
        },
        "anpr": {
            "total_reads": v_row["total_anpr"] or 0,
            "flagged_matches": v_row["flagged_anpr"] or 0
        },
        "alerts": {
            "total": a_row["total_alerts"] or 0,
            "pending": a_row["pending_alerts"] or 0
        },
        "federation": {
            "departments_connected": d_row["depts"] or 26,
            "vms_clusters_online": 4,
            "network_protocol": "Edge JSON Metadata (<500 Mbps Statewide WAN)"
        }
    }


@router.get("/gap-analysis")
def get_blind_spot_analysis():
    """
    Identifies geographic gaps and department surveillance blind spots across Gujarat.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT district, COUNT(*) as camera_count,
           SUM(CASE WHEN status='ACTIVE' THEN 1 ELSE 0 END) as active_count
    FROM cameras
    GROUP BY district
    ORDER BY camera_count ASC;
    """)
    rows = cursor.fetchall()
    conn.close()

    districts_analysis = []
    for r in rows:
        c_count = r["camera_count"]
        coverage_rating = "CRITICAL GAP" if c_count < 3 else ("MODERATE COVERAGE" if c_count < 6 else "OPTIMAL COVERAGE")
        districts_analysis.append({
            "district": r["district"],
            "cameras_deployed": c_count,
            "active": r["active_count"],
            "coverage_rating": coverage_rating,
            "recommended_additions": max(0, 8 - c_count)
        })

    return {"districts": districts_analysis}


@router.get("/heatmaps")
def get_spatial_heatmaps():
    """
    Returns spatial density and traffic volume heat points across Gujarat CCTV nodes.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.camera_id, c.name, c.latitude, c.longitude, c.city, c.district,
               COUNT(v.anpr_id) as vehicle_count,
               AVG(v.speed_kmh) as avg_speed
        FROM cameras c
        LEFT JOIN vehicle_anpr v ON c.camera_id = v.camera_id
        GROUP BY c.camera_id;
    """)
    rows = cursor.fetchall()
    conn.close()

    points = []
    for r in rows:
        points.append({
            "camera_id": r["camera_id"],
            "name": r["name"],
            "lat": r["latitude"],
            "lng": r["longitude"],
            "city": r["city"],
            "district": r["district"],
            "density_weight": min(1.0, (r["vehicle_count"] or 5) / 20.0),
            "avg_speed_kmh": round(r["avg_speed"] or 50.0, 1)
        })
    return {"status": "SUCCESS", "heat_points_count": len(points), "points": points}

