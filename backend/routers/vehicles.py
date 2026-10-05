"""
Vehicles & ANPR Router (Model 2: Vehicle Search & VAHAN Integration)
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from ..database.schema import get_db_connection

router = APIRouter(prefix="/api/vehicles", tags=["ANPR & VAHAN Intelligence"])

# Live VAHAN Mock Registry
VAHAN_MASTER = {
    "GJ01AB1234": {
        "plate": "GJ01AB1234",
        "owner": "Ramesh Patel",
        "make_model": "Toyota Fortuner (7-Seater)",
        "color": "White",
        "fuel": "Diesel",
        "rto": "Ahmedabad West RTO (GJ-01)",
        "reg_date": "2022-04-14",
        "insurance_valid": "2027-04-10",
        "puc_valid": "2026-11-20",
        "status": "🚨 WANTED IN eGujCop",
        "is_flagged": True,
        "fir_ref": "FIR #402/2026 (Crime Branch Gandhinagar)",
        "crime_type": "Interstate Contraband Smuggling"
    },
    "GJ27AX9999": {
        "plate": "GJ27AX9999",
        "owner": "Vikram Thakor",
        "make_model": "Mahindra Scorpio-N (7-Seater)",
        "color": "Black",
        "fuel": "Diesel",
        "rto": "Ahmedabad East (GJ-27)",
        "reg_date": "2023-01-20",
        "insurance_valid": "2028-01-18",
        "puc_valid": "2026-08-15",
        "status": "🚨 WANTED IN eGujCop",
        "is_flagged": True,
        "fir_ref": "FIR #189/2026 (Vehicle Theft Gang)",
        "crime_type": "High-Speed Escort Vehicle"
    },
    "GJ18ZZ7777": {
        "plate": "GJ18ZZ7777",
        "owner": "Devang Shah",
        "make_model": "Hyundai Creta",
        "color": "White",
        "fuel": "Petrol",
        "rto": "Gandhinagar (GJ-18)",
        "reg_date": "2021-08-11",
        "insurance_valid": "2026-08-10",
        "puc_valid": "2026-12-01",
        "status": "🚨 STOLEN VEHICLE ALERT",
        "is_flagged": True,
        "fir_ref": "FIR #108/2026 (Stolen Vehicle Registry)",
        "crime_type": "Active Stolen Vehicle"
    },
    "GJ05CD5678": {
        "plate": "GJ05CD5678",
        "owner": "Salim Khan",
        "make_model": "Bajaj Compact RE (Auto)",
        "color": "Yellow/Green",
        "fuel": "CNG",
        "rto": "Surat RTO (GJ-05)",
        "reg_date": "2019-03-05",
        "insurance_valid": "2025-03-01",
        "puc_valid": "EXPIRED",
        "status": "PUC EXPIRED",
        "is_flagged": False,
        "fir_ref": None,
        "crime_type": "Traffic Violation Only"
    },
    "GJ06EF4321": {
        "plate": "GJ06EF4321",
        "owner": "Anjali Sharma",
        "make_model": "Maruti Suzuki Swift",
        "color": "Silver",
        "fuel": "Petrol",
        "rto": "Vadodara RTO (GJ-06)",
        "reg_date": "2020-07-22",
        "insurance_valid": "2027-07-20",
        "puc_valid": "2027-01-15",
        "status": "NOMINAL",
        "is_flagged": False,
        "fir_ref": None,
        "crime_type": "Clean Record"
    },
    "GJ27E5539": {
        "plate": "GJ27E5539",
        "owner": "Ramdhani Travels (Gujarat)",
        "make_model": "Ashok Leyland Falcon Deluxe AC Sleeper Bus",
        "color": "White / Blue Commercial",
        "fuel": "Diesel",
        "rto": "Gandhinagar RTO (GJ-27)",
        "reg_date": "2021-11-10",
        "insurance_valid": "2026-11-09",
        "puc_valid": "2026-10-30",
        "status": "VALID COMMERCIAL PERMIT",
        "is_flagged": False,
        "fir_ref": None,
        "crime_type": "Clean Record"
    },
    "GJ01KZ9901": {
        "plate": "GJ01KZ9901",
        "owner": "Gujarat Logistics Freight Corp",
        "make_model": "Tata Prima 4028.S Container Truck",
        "color": "Blue / Orange",
        "fuel": "Diesel",
        "rto": "Ahmedabad RTO (GJ-01)",
        "reg_date": "2020-04-18",
        "insurance_valid": "2027-04-15",
        "puc_valid": "2026-09-12",
        "status": "ACTIVE TOLL FASTAG PERMIT",
        "is_flagged": False,
        "fir_ref": None,
        "crime_type": "Clean Record"
    },
    "GJ01AW6670": {
        "plate": "GJ01AW6670",
        "owner": "Rameshchandra Patel",
        "make_model": "Bajaj Compact 4S CNG Auto-Rickshaw",
        "color": "Yellow / Green",
        "fuel": "CNG",
        "rto": "Ahmedabad RTO (GJ-01)",
        "reg_date": "2022-09-05",
        "insurance_valid": "2027-09-01",
        "puc_valid": "2026-12-30",
        "status": "VALID PERMIT",
        "is_flagged": False,
        "fir_ref": None,
        "crime_type": "Clean Record"
    }
}


@router.get("/anpr")
def list_anpr_detections(
    camera_id: Optional[str] = None,
    is_flagged: Optional[int] = None,
    limit: int = Query(50, le=200)
):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    SELECT v.*, c.name as camera_name, c.city, c.department, c.latitude, c.longitude
    FROM vehicle_anpr v
    JOIN cameras c ON v.camera_id = c.camera_id
    WHERE 1=1
    """
    params = []

    if camera_id:
        query += " AND v.camera_id = ?"
        params.append(camera_id)
    if is_flagged is not None:
        query += " AND v.is_flagged = ?"
        params.append(is_flagged)

    query += " ORDER BY v.timestamp DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return {"total": len(rows), "records": [dict(r) for r in rows]}


@router.get("/search")
def search_vehicles(
    query: Optional[str] = Query(None, description="Plate number, make, model, color or FIR"),
    color: Optional[str] = None,
    vehicle_type: Optional[str] = None,
    is_flagged: Optional[bool] = None
):
    conn = get_db_connection()
    cursor = conn.cursor()

    sql = """
    SELECT v.*, c.name as camera_name, c.city, c.department, c.latitude, c.longitude
    FROM vehicle_anpr v
    JOIN cameras c ON v.camera_id = c.camera_id
    WHERE 1=1
    """
    params = []

    if query:
        words = query.strip().upper().split()
        for w in words:
            q_wild = f"%{w}%"
            sql += """ AND (
                UPPER(v.plate_number) LIKE ? OR
                UPPER(v.vahan_model) LIKE ? OR
                UPPER(v.vahan_owner) LIKE ? OR
                UPPER(v.fir_reference) LIKE ? OR
                UPPER(v.vehicle_color) LIKE ? OR
                UPPER(v.vehicle_type) LIKE ?
            )"""
            params.extend([q_wild, q_wild, q_wild, q_wild, q_wild, q_wild])

    if color:
        sql += " AND UPPER(v.vehicle_color) = ?"
        params.append(color.strip().upper())

    if vehicle_type:
        sql += " AND UPPER(v.vehicle_type) LIKE ?"
        params.append(f"%{vehicle_type.strip().upper()}%")

    if is_flagged is not None:
        sql += " AND v.is_flagged = ?"
        params.append(1 if is_flagged else 0)

    sql += " ORDER BY v.timestamp DESC LIMIT 100"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    return {"query": query, "total_matches": len(rows), "results": [dict(r) for r in rows]}


@router.get("/vahan/{plate_number}")
def get_vahan_intelligence(plate_number: str):
    clean_plate = plate_number.strip().upper().replace(" ", "").replace("-", "")
    info = VAHAN_MASTER.get(clean_plate)
    if not info:
        return {
            "found": False,
            "plate": clean_plate,
            "message": "No VAHAN registry record found for this vehicle plate",
            "owner": None,
            "make_model": None,
            "color": None,
            "fuel": None,
            "rto": f"Gujarat RTO ({clean_plate[:4]})" if len(clean_plate) >= 4 else None,
            "status": "NOT FOUND / UNREGISTERED",
            "is_flagged": False,
            "fir_ref": None,
            "crime_type": None
        }
    data = dict(info)
    data["found"] = True
    return data
