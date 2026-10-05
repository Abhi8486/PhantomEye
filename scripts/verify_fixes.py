import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pickle
from core_ai.universal_search import UniversalSearchEngine
from core_ai.indexer import global_indexer

with open('data/indexed_tracks_cache.pkl', 'rb') as f:
    obs_list = pickle.load(f)

global_indexer.observations = obs_list
print(f"Total loaded observations: {len(obs_list)}")

# Check persons in CAM-001
cam1_persons = [o for o in obs_list if o['camera_id'] == 'CAM-001' and o['object_type'] == 'PERSON']
print(f"CAM-001 persons count: {len(cam1_persons)}")
for p in cam1_persons:
    print(f"  CAM-001 person: {p['model']} bbox: {p['bbox']} frame_idx: {p.get('frame_idx')} screenshot: {p.get('screenshot_url')}")

# Check persons in CAM-005
cam5_persons = [o for o in obs_list if o['camera_id'] == 'CAM-005' and o['object_type'] == 'PERSON']
print(f"CAM-005 persons count: {len(cam5_persons)}")
for p in cam5_persons:
    print(f"  CAM-005 person: {p['model']} bbox: {p['bbox']} frame_idx: {p.get('frame_idx')} screenshot: {p.get('screenshot_url')}")

# Test Universal Search for 'Person in Red shirt'
engine = UniversalSearchEngine()
res_red = engine.search_candidates('Person in Red shirt', min_confidence=0.50)
print(f"\nSearch 'Person in Red shirt' matches (>=50%): {len(res_red['candidates'])}")
for c in res_red['candidates'][:5]:
    print(f"  Match: {c['camera_id']} | {c['matched_identifier']} | {c['object_type']} | {c['vehicle_color']} | {c['overall_confidence']:.1%} | {c['decision']}")

# Test Universal Search for 'Person in White shirt'
res_white = engine.search_candidates('Person in White shirt', min_confidence=0.50)
print(f"\nSearch 'Person in White shirt' matches (>=50%): {len(res_white['candidates'])}")
for c in res_white['candidates'][:5]:
    print(f"  Match: {c['camera_id']} | {c['matched_identifier']} | {c['object_type']} | {c['vehicle_color']} | {c['overall_confidence']:.1%} | {c['decision']}")
