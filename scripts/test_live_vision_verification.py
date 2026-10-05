import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core_ai.universal_search import UniversalSearchEngine
from core_ai.indexer import global_indexer

def test_searches():
    print("=" * 70)
    print("EXECUTING LIVE VISION & SEARCH VERIFICATION")
    print("=" * 70)

    engine = UniversalSearchEngine()

    # --- Test 1: White Toyota Fortuner 7-Seater ---
    print("\n[TEST 1] Query: 'White Toyota Fortuner 7-Seater'")
    res_fortuner = engine.search_candidates("White Toyota Fortuner 7-Seater", min_confidence=0.75)
    candidates_fortuner = res_fortuner.get("candidates", [])
    print(f"Total Candidates Found: {len(candidates_fortuner)}")

    for i, c in enumerate(candidates_fortuner[:6]):
        print(f"  #{i+1} Cam: {c['camera_id']} ({c['camera_name']})")
        print(f"      Matched Identifier: {c['matched_identifier']}")
        print(f"      Object Type: {c['object_type']} | Vehicle Color: {c['vehicle_color']}")
        print(f"      Confidence: {c['overall_confidence']:.1%} | Decision: {c['decision']}")
        print(f"      Screenshot URL: {c['screenshot_url']}")
        print(f"      Timestamp: {c['timestamp']}")

        # Verification check: Ensure trucks, buses, rickshaws are NOT present
        ident_lower = c['matched_identifier'].lower()
        obj_lower = c['object_type'].lower()
        assert "truck" not in ident_lower, f"ERROR: Truck matched as Fortuner! {c['matched_identifier']}"
        assert "bus" not in ident_lower, f"ERROR: Bus matched as Fortuner! {c['matched_identifier']}"
        assert "rickshaw" not in ident_lower, f"ERROR: Rickshaw matched as Fortuner! {c['matched_identifier']}"
        assert "auto" not in ident_lower or "automobile" in ident_lower, f"ERROR: Auto-rickshaw matched as Fortuner! {c['matched_identifier']}"

    # --- Test 2: person wearing white shirt ---
    print("\n[TEST 2] Query: 'person wearing white shirt'")
    res_person = engine.search_candidates("person wearing white shirt", min_confidence=0.75)
    candidates_person = res_person.get("candidates", [])
    print(f"Total Candidates Found: {len(candidates_person)}")

    for i, c in enumerate(candidates_person[:6]):
        print(f"  #{i+1} Cam: {c['camera_id']} ({c['camera_name']})")
        print(f"      Matched Identifier: {c['matched_identifier']}")
        print(f"      Object Type: {c['object_type']} | Upper Color: {c.get('upper_color')}")
        print(f"      Confidence: {c['overall_confidence']:.1%} | Decision: {c['decision']}")
        print(f"      Screenshot URL: {c['screenshot_url']}")
        print(f"      Timestamp: {c['timestamp']}")

        # Verification check: Ensure matched identifier or upper color represents white shirt
        assert c['object_type'] == "PERSON", f"ERROR: Non-person matched: {c['object_type']}"
        assert "white" in c.get('upper_color', '').lower() or "white" in c['matched_identifier'].lower(), f"ERROR: Matched person without white shirt: {c['matched_identifier']}"

    print("\n" + "=" * 70)
    print("ALL SEARCH ASSERTIONS PASSED! VERIFIED ACCURATE.")
    print("=" * 70)

if __name__ == "__main__":
    test_searches()
