import sys
sys.path.insert(0, ".")
from core_ai.universal_search import UniversalSearchEngine
from core_ai.indexer import global_indexer

print("[*] Re-seeding runtime observations with strict morphological detector...")
UniversalSearchEngine._seed_runtime_observations()
print(f"[OK] Total indexed observations: {len(global_indexer.observations)}")

# Test query for red shirt
res = UniversalSearchEngine.search_candidates("find person with red t shirt", min_confidence=0.50)
print(f"\n[QUERY RESULT] Total matches found: {res['total_matches_found']}")
for i, c in enumerate(res['candidates'], 1):
    print(f"Match #{i}:")
    print(f"  Camera: {c['camera_name']} ({c['camera_id']})")
    print(f"  Target: {c['matched_identifier']}")
    print(f"  Confidence: {c['overall_confidence']:.1%}")
    print(f"  Screenshot: {c['screenshot_url']}")
