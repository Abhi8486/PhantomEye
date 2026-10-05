"""
Universal Multi-Modal Search & Image Upload API Router
Handles text, plate number, and photo uploads (vehicle or person), executes candidate matching,
and serves high-fidelity evidentiary screenshots extracted from the rolling buffer.
"""

import uuid
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse

from core_ai.universal_search import UniversalSearchEngine
from core_ai.indexer import EVIDENCE_DIR

router = APIRouter(prefix="/api/search", tags=["Universal Multi-Modal Search & Upload"])

# Track the currently active search ID so cancel knows which one to stop
_current_search_id: Optional[str] = None


class UniversalSearchRequest(BaseModel):
    query: str
    min_confidence: Optional[float] = 0.60
    limit: Optional[int] = 10


class CancelSearchRequest(BaseModel):
    search_id: Optional[str] = None  # If None, cancels the most recent search


@router.post("/universal")
def search_universal(req: UniversalSearchRequest):
    """
    Unified text search: processes plate numbers, vehicle descriptions, or person descriptions.
    Runs continuously until results are found or cancelled via /api/search/cancel.
    """
    global _current_search_id

    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query string cannot be empty")

    search_id = f"search-{uuid.uuid4().hex[:12]}"
    _current_search_id = search_id

    try:
        results = UniversalSearchEngine.search_candidates(
            text_query=req.query,
            min_confidence=req.min_confidence or 0.60,
            limit=req.limit or 10,
            search_id=search_id
        )
        results["search_id"] = search_id
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
    finally:
        if _current_search_id == search_id:
            _current_search_id = None


@router.post("/cancel")
def cancel_search(req: CancelSearchRequest = CancelSearchRequest()):
    """
    Cancels the currently running live CCTV search.
    """
    global _current_search_id

    target_id = req.search_id or _current_search_id
    if not target_id:
        return {"status": "no_active_search", "message": "No active search to cancel."}

    UniversalSearchEngine.cancel_search(target_id)
    return {"status": "cancelled", "search_id": target_id, "message": "Search cancellation signal sent."}


@router.post("/upload-image")
async def upload_image_search(
    image: UploadFile = File(...),
    description: Optional[str] = Form(None),
    min_confidence: Optional[float] = Form(0.60),
    limit: Optional[int] = Form(10)
):
    """
    Multi-modal photo upload: extracts visual Re-ID embedding and attributes from uploaded photo,
    searches across indexed cameras, and retrieves matching evidence screenshots.
    """
    global _current_search_id

    search_id = f"search-img-{uuid.uuid4().hex[:12]}"
    _current_search_id = search_id

    try:
        contents = await image.read()
        if not contents or len(contents) == 0:
            raise HTTPException(status_code=400, detail="Uploaded image file is empty")

        results = UniversalSearchEngine.search_candidates(
            text_query=description,
            uploaded_image_bytes=contents,
            min_confidence=float(min_confidence or 0.60),
            limit=int(limit or 10),
            search_id=search_id
        )
        results["search_id"] = search_id
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload search failed: {str(e)}")
    finally:
        if _current_search_id == search_id:
            _current_search_id = None


@router.get("/evidence-frame/{filename}")
def get_evidence_frame(filename: str):
    """
    Serves the exact evidentiary screenshot file extracted from the camera's rolling buffer.
    """
    import os
    
    # Strip any directory traversal attempts (e.g., ../../../etc/passwd -> passwd)
    safe_filename = os.path.basename(filename)
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
        
    file_path = (EVIDENCE_DIR / safe_filename).resolve()
    
    # Ensure the resolved path is strictly within EVIDENCE_DIR
    if not str(file_path).startswith(str(EVIDENCE_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Forbidden access attempt")

    if not file_path.exists():
        # Fallback to sample frame if file not found
        sample_path = Path("c:/projects/crime_tracking/PhantomEye-main/PhantomEye-main/phantomeye_poc/frontend/assets/sample_feed.jpg")
        if sample_path.exists():
            return FileResponse(str(sample_path), media_type="image/jpeg")
        raise HTTPException(status_code=404, detail="Evidence frame screenshot not found")

    return FileResponse(str(file_path), media_type="image/jpeg")
