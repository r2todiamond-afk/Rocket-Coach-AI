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

terms = ['throttle', 'steer', 'input', 'air', 'handbrake', 'control']

print("=== BUSQUEDA DE ENTRADAS DE CONTROL EN OBJECTS ===")
found_oids = {}
for i, o in enumerate(objects):
    for t in terms:
        if t in o.lower():
            found_oids[i] = o
            print(f"  {i}: {o}")

print("\n=== MUESTRA DE UPDATES PARA ENTRADAS DE CONTROL EN FRAMES ===")
sample_count = {}
for fi, frame in enumerate(frames):
    for upd in frame.get('updated_actors', []):
        oid = upd.get('object_id')
        if oid in found_oids:
            oname = objects[oid]
            if sample_count.get(oname, 0) < 5:
                print(f"Frame {fi} aid={upd.get('actor_id')} oid={oid} ({oname}): attr={json.dumps(upd.get('attribute'))}")
                sample_count[oname] = sample_count.get(oname, 0) + 1
