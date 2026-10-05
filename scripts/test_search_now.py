import urllib.request
import json
import time

def test_query(q):
    print("=" * 50)
    print(f"[*] Testing Universal Search for: '{q}'")
    print("=" * 50)
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/search/universal",
        data=json.dumps({"query": q, "min_confidence": 0.70, "limit": 6}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
            dt = time.time() - t0
            total = data.get("total_matches_found", 0)
            print(f"[OK] Completed in {dt:.2f}s | Matches: {total}")
            for idx, c in enumerate(data.get("candidates", []), 1):
                cid = c.get("camera_id")
                cname = c.get("camera_name")
                ident = c.get("matched_identifier")
                conf = c.get("overall_confidence", 0)
                ev = c.get("evidence_path")
                ts = c.get("timestamp")
                print(f"  {idx}. [{cid} - {cname}] {ident} ({conf:.0%}) | Time: {ts} | Ev: {ev}")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    test_query("black car")
    test_query("white car")
    test_query("auto rickshaw")
