import urllib.request
import json

def verify():
    data = json.dumps({"query": "find person with red t shirt"}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:8000/api/search/universal", data=data, headers={"Content-Type": "application/json"})
    res = urllib.request.urlopen(req)
    out = json.loads(res.read())
    
    print("=== LIVE UNIVERSAL SEARCH API VERIFICATION ===")
    print("Total Matches Found:", out["total_matches_found"])
    print("High Confidence Alerts:", out["high_confidence_alerts"])
    
    for i, c in enumerate(out["candidates"], 1):
        print(f"\nMatch #{i}:")
        print("  Identifier:", c["matched_identifier"])
        print("  Object Type:", c["object_type"])
        print("  Camera:", c["camera_name"], f"({c['camera_id']})")
        print("  Confidence:", f"{c['overall_confidence']:.1%}")
        print("  Evidence Breakdown:", c["evidence_breakdown"])
        print("  Screenshot Web URL:", c["screenshot_url"])

if __name__ == "__main__":
    verify()
