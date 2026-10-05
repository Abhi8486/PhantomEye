import sys
sys.path.insert(0, ".")
from core_ai.universal_search import UniversalSearchEngine

queries = [
    "find person with red shirt",
    "person wearing blue shirt",
    "person with green clothing",
    "White Toyota Fortuner",
    "Black Mahindra Scorpio",
    "Green Bus",
    "GJ01AB1234"
]

for q in queries:
    res = UniversalSearchEngine.search_candidates(text_query=q)
    print(f"\n================ QUERY: '{q}' ================")
    print(f"Detected intent: {res['query']}")
    print(f"Matches found: {res['total_matches_found']} (High Conf: {res['high_confidence_alerts']})")
    for c in res["candidates"][:3]:
        print(f"  -> [{c['camera_id']}] {c['camera_name']} | Conf: {c['overall_confidence']:.1%} | {c['matched_identifier']} | Decision: {c['decision']}")
