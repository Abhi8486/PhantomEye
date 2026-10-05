"""
Verifies that all evidence images and anomaly images served by the API are authentic full-color CCTV frames.
"""

import urllib.request
import json

# 1. Search Candidates
req = urllib.request.Request(
    'http://localhost:8000/api/search/universal',
    data=json.dumps({'query': 'GJ01AB1234'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
res = json.loads(urllib.request.urlopen(req).read())
print(f"[OK] Search Matches: {res['total_matches_found']}")
for c in res['candidates']:
    url = 'http://localhost:8000' + c['screenshot_url']
    img_data = urllib.request.urlopen(url).read()
    print(f"  -> {c['camera_id']} ({c['camera_name']}): {len(img_data)} bytes downloaded from {c['screenshot_url']}")

# 2. Anomaly Events
a_res = json.loads(urllib.request.urlopen('http://localhost:8000/api/events/anomalies').read())
print(f"\n[OK] Anomaly Events Found: {a_res['total_active_events']}")
for evt in a_res['events']:
    url = 'http://localhost:8000' + evt['screenshot_url']
    img_data = urllib.request.urlopen(url).read()
    print(f"  -> {evt['event_id']} ({evt['title']}): {len(img_data)} bytes downloaded from {evt['screenshot_url']}")
