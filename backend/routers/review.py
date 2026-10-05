"""
Manual Review Workflow API — Endpoints for reviewing low-confidence ANPR detections.
Operators can approve, reject, or correct uncertain plate reads.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime
from ..database.schema import get_db_connection

router = APIRouter(prefix="/api/review", tags=["Manual Review Workflow"])


@router.get("/queue")
def list_review_queue(
    status: Optional[str] = Query(None, description="Filter by review_status: PENDING, APPROVED, REJECTED, CORRECTED"),
    camera_id: Optional[str] = None,
    limit: int = Query(50, le=200)
):
    """List items in the manual review queue, optionally filtered by status or camera."""
    conn = get_db_connection()
    cursor = conn.cursor()

    sql = "SELECT * FROM review_queue WHERE 1=1"
    params = []

    if status:
        sql += " AND review_status = ?"
        params.append(status.upper())
    if camera_id:
        sql += " AND camera_id = ?"
        params.append(camera_id)

    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        return {"total": len(rows), "reviews": [dict(r) for r in rows]}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Review queue query failed: {e}")


@router.post("/{review_id}/approve")
def approve_review(review_id: str, operator_name: str = "Command Officer"):
    """Approve an OCR result — confirms the original plate text is correct."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()

    try:
        cursor.execute("SELECT * FROM review_queue WHERE review_id = ?;", (review_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Review {review_id} not found")

        cursor.execute("""
        UPDATE review_queue
        SET review_status = 'APPROVED', reviewed_by = ?, reviewed_at = ?
        WHERE review_id = ?;
        """, (operator_name, now_str, review_id))

        # Also update the linked vehicle_anpr record
        anpr_id = row["anpr_id"]
        if anpr_id:
            try:
                cursor.execute("""
                UPDATE vehicle_anpr SET review_status = 'APPROVED'
                WHERE anpr_id = ?;
                """, (anpr_id,))
            except Exception:
                pass

        conn.commit()
        conn.close()
        return {
            "status": "SUCCESS",
            "review_id": review_id,
            "action": "APPROVED",
            "reviewed_by": operator_name,
            "timestamp": now_str
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Approval failed: {e}")


@router.post("/{review_id}/reject")
def reject_review(review_id: str, operator_name: str = "Command Officer", notes: str = ""):
    """Reject an OCR result — marks it as a false positive."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()

    try:
        cursor.execute("SELECT * FROM review_queue WHERE review_id = ?;", (review_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Review {review_id} not found")

        cursor.execute("""
        UPDATE review_queue
        SET review_status = 'REJECTED', reviewed_by = ?, reviewed_at = ?, notes = ?
        WHERE review_id = ?;
        """, (operator_name, now_str, notes, review_id))

        # Update linked vehicle_anpr record
        anpr_id = row["anpr_id"]
        if anpr_id:
            try:
                cursor.execute("""
                UPDATE vehicle_anpr SET review_status = 'REJECTED'
                WHERE anpr_id = ?;
                """, (anpr_id,))
            except Exception:
                pass

        conn.commit()
        conn.close()
        return {
            "status": "SUCCESS",
            "review_id": review_id,
            "action": "REJECTED",
            "reviewed_by": operator_name,
            "timestamp": now_str
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Rejection failed: {e}")


@router.post("/{review_id}/correct")
def correct_review(review_id: str, corrected_plate: str,
                   operator_name: str = "Command Officer", notes: str = ""):
    """Submit a corrected plate text for an uncertain OCR result."""
    if not corrected_plate or len(corrected_plate) < 6:
        raise HTTPException(status_code=400, detail="Corrected plate must be at least 6 characters")

    corrected_plate = corrected_plate.upper().strip().replace(" ", "").replace("-", "")

    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()

    try:
        cursor.execute("SELECT * FROM review_queue WHERE review_id = ?;", (review_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Review {review_id} not found")

        cursor.execute("""
        UPDATE review_queue
        SET review_status = 'CORRECTED', corrected_plate_text = ?,
            reviewed_by = ?, reviewed_at = ?, notes = ?
        WHERE review_id = ?;
        """, (corrected_plate, operator_name, now_str, notes, review_id))

        # Update linked vehicle_anpr record with corrected plate
        anpr_id = row["anpr_id"]
        if anpr_id:
            try:
                cursor.execute("""
                UPDATE vehicle_anpr SET plate_number = ?, review_status = 'CORRECTED'
                WHERE anpr_id = ?;
                """, (corrected_plate, anpr_id))
            except Exception:
                pass

        conn.commit()
        conn.close()
        return {
            "status": "SUCCESS",
            "review_id": review_id,
            "action": "CORRECTED",
            "original_plate": row["original_plate_text"],
            "corrected_plate": corrected_plate,
            "reviewed_by": operator_name,
            "timestamp": now_str
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Correction failed: {e}")


@router.get("/stats")
def review_stats():
    """Get review queue statistics."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN review_status = 'PENDING' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN review_status = 'APPROVED' THEN 1 ELSE 0 END) as approved,
            SUM(CASE WHEN review_status = 'REJECTED' THEN 1 ELSE 0 END) as rejected,
            SUM(CASE WHEN review_status = 'CORRECTED' THEN 1 ELSE 0 END) as corrected
        FROM review_queue;
        """)
        row = cursor.fetchone()
        conn.close()

        return {
            "total": row["total"] or 0,
            "pending": row["pending"] or 0,
            "approved": row["approved"] or 0,
            "rejected": row["rejected"] or 0,
            "corrected": row["corrected"] or 0,
        }
    except Exception as e:
        conn.close()
        return {"total": 0, "pending": 0, "approved": 0, "rejected": 0, "corrected": 0,
                "note": "Review queue table may not exist yet. Run schema init."}
