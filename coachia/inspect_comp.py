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

# Maps component_aid -> {"car_aid": int, "type": str}
comp_type = {}
comp_to_car = {}

for fi, frame in enumerate(frames):
    for na in frame.get('new_actors', []):
        aid = na['actor_id']
        oid = na['object_id']
        oname = objects[oid] if oid < len(objects) else ''
        if 'Jump' in oname:
            comp_type[aid] = 'jump'
        elif 'Dodge' in oname or 'FlipCar' in oname:
            comp_type[aid] = 'dodge'
        elif 'Boost' in oname and 'Pickup' not in oname:
            comp_type[aid] = 'boost'

    for upd in frame.get('updated_actors', []):
        aid = upd.get('actor_id')
        oid = upd.get('object_id')
        oname = objects[oid] if oid < len(objects) else ''
        attr = upd.get('attribute', {})
        
        # Vehicle link (CarComponent_TA:Vehicle)
        if 'Vehicle' in oname:
            val = attr.get('ActiveActor') if isinstance(attr, dict) else None
            if isinstance(val, dict) and 'actor' in val:
                comp_to_car[aid] = val['actor']

print("=== MAPPING DE COMPONENTES A AUTOS ===")
print(f"Total componentes identificados: {len(comp_type)}")
print(f"Total links comp->car: {len(comp_to_car)}")
for comp_aid, car_aid in list(comp_to_car.items())[:15]:
    t = comp_type.get(comp_aid, 'unknown')
    print(f"  Component aid={comp_aid} (tipo: {t}) -> Car aid={car_aid}")
