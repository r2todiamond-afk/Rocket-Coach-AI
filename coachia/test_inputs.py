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

print("=== MUESTRA DE THROTTLE Y STEER NORMALIZADOS ===")
count = 0
for fi, frame in enumerate(frames):
    for upd in frame.get('updated_actors', []):
        oid = upd.get('object_id')
        if oid in (302, 303):
            oname = objects[oid]
            attr = upd.get('attribute', {})
            val = attr.get('Byte') if isinstance(attr, dict) else None
            if val is not None and count < 15:
                norm = round((val - 128) / 128.0, 2)
                kind = "THROTTLE (Acelerador)" if oid == 303 else "STEER (Direccion)"
                print(f"Frame {fi:4d} aid={upd.get('actor_id'):2d} {kind:<25} raw={val:3d} -> normalized={norm:+0.2f}")
                count += 1
