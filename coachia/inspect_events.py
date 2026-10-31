import json

path = r'rrrocket-0.11.5-x86_64-pc-windows-msvc\salida_completa.json'
for enc in ['utf-16','utf-8']:
    try:
        with open(path,'r',encoding=enc) as f:
            data = json.load(f)
        break
    except: pass

objects = data['objects']
frames  = data['network_frames']['frames']

target_oids = {306, 316, 317, 323, 324, 332, 334, 339, 341, 346, 66, 128}

print("=== SAMPLE UPDATES FOR EVENT FLAGS ===")
found = {}
for fi, frame in enumerate(frames):
    # Check new actors for component linkage
    for na in frame.get('new_actors', []):
        aid = na['actor_id']
        oid = na['object_id']
        oname = objects[oid] if oid < len(objects) else ''
        if any(c in oname for c in ['Jump', 'Dodge', 'Flip', 'Boost']):
            if oname not in found:
                print(f"new_actor: aid={aid} oid={oid} ({oname})")
                found[oname] = aid

    # Check updated actors
    for upd in frame.get('updated_actors', []):
        oid = upd.get('object_id')
        if oid in target_oids:
            oname = objects[oid]
            if oname not in found or found[oname] < 3:
                attr = upd.get('attribute')
                print(f"Frame {fi} aid={upd.get('actor_id')} oid={oid} ({oname}): attr={json.dumps(attr)}")
                found[oname] = found.get(oname, 0) + 1
