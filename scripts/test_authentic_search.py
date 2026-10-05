import sys
sys.path.insert(0, ".")
from core_ai.universal_search import UniversalSearchEngine

print("\n--- TEST 1: Searching for 'Person wearing red shirt and black pants' ---")
res1 = UniversalSearchEngine.search_candidates("Person wearing red shirt and black pants", min_confidence=0.60)
print(f"Total Matches Found: {res1['total_matches_found']}")
for idx, c in enumerate(res1['candidates'][:5], 1):
    print(f"  #{idx} Cam: {c['camera_id']} ({c['camera_name']}) | Target: {c['matched_identifier']} | Conf: {c['overall_confidence']:.1%} | Dur: {c['duration_sec']}s | Time: {c['timestamp']} | Img: {c['screenshot_url']}")

print("\n--- TEST 2: Searching for 'White SUV / Car' ---")
res2 = UniversalSearchEngine.search_candidates("White SUV", min_confidence=0.60)
print(f"Total Matches Found: {res2['total_matches_found']}")
for idx, c in enumerate(res2['candidates'][:5], 1):
    print(f"  #{idx} Cam: {c['camera_id']} ({c['camera_name']}) | Target: {c['matched_identifier']} | Conf: {c['overall_confidence']:.1%} | Dur: {c['duration_sec']}s | Time: {c['timestamp']} | Img: {c['screenshot_url']}")
