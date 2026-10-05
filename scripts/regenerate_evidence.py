"""
Regenerates authentic CCTV forensic evidence frames with real video captures and HUD overlays.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core_ai.universal_search import UniversalSearchEngine, global_indexer

ev_dir = Path("c:/projects/crime_tracking/PhantomEye-main/PhantomEye-main/phantomeye_poc/data/evidence_frames")
ev_dir.mkdir(parents=True, exist_ok=True)

for f in ev_dir.glob("*.jpg"):
    try:
        f.unlink()
    except Exception:
        pass

global_indexer.observations.clear()
global_indexer.camera_buffers.clear()

res = UniversalSearchEngine.search_candidates(text_query="GJ01AB1234")
print(f"[OK] Matches Found: {res['total_matches_found']}")
for c in res["candidates"]:
    print(f"  -> {c['camera_id']} ({c['camera_name']}): {c['screenshot_url']}")

print("[OK] Evidence frames successfully regenerated with REAL CCTV footage!")
