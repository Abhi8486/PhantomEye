import urllib.request
import json

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/search/universal",
    data=json.dumps({"query": "find preson with red shirt", "min_confidence": 0.60}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
try:
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read().decode("utf-8"))
    print("Total Matches:", data["total_matches_found"])
    print("High Conf Alerts:", data["high_confidence_alerts"])
    for c in data["candidates"][:4]:
        print(f"  [{c['camera_id']}] {c['camera_name']} | Conf: {c['overall_confidence']:.1%} | {c['matched_identifier']} | Screenshot: {c['screenshot_url']}")
except Exception as e:
    print("Error:", e)
