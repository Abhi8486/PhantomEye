import sys
sys.path.insert(0, ".")
from core_ai.universal_search import UniversalSearchEngine

# Test 1: Person in red shirt query (with typo 'preson')
res_person = UniversalSearchEngine.search_candidates(text_query="find preson with red shirt")
print("=== PERSON SEARCH QUERY: find preson with red shirt ===")
print("Query meta:", res_person["query"])
print("Total matches found:", res_person["total_matches_found"])
print("High confidence alerts (>=88%):", res_person["high_confidence_alerts"])
for c in res_person["candidates"][:6]:
    print(f"  [{c['camera_id']}] {c['camera_name']} | Conf: {c['overall_confidence']:.1%} | {c['vehicle_color']} {c['object_type']} | {c['decision']} | {c['screenshot_url']}")

# Test 2: Suspect Plate query
res_plate = UniversalSearchEngine.search_candidates(text_query="GJ01AB1234")
print("\n=== PLATE SEARCH QUERY: GJ01AB1234 ===")
print("Total matches found:", res_plate["total_matches_found"])
print("High confidence alerts (>=88%):", res_plate["high_confidence_alerts"])
for c in res_plate["candidates"][:6]:
    print(f"  [{c['camera_id']}] {c['camera_name']} | Conf: {c['overall_confidence']:.1%} | {c['matched_identifier']} | {c['decision']} | {c['screenshot_url']}")
