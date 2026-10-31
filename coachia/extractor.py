"""
coachia/extractor.py
====================
Extractor generico de replays de Rocket League a partir del JSON de rrrocket (-n).

Extrae frame a frame, con identidad de jugador resuelta en tiempo real (maneja
el churn de actor_id despues de cada gol/kickoff):

  - Tiempo (segundos)
  - Jugador (nombre)
  - Equipo (0 = azul, 1 = naranja)
  - Posicion 3D: pos_x, pos_y, pos_z
  - Velocidad 3D: vel_x, vel_y, vel_z
  - Velocidad angular: ang_vel_x, ang_vel_y, ang_vel_z
  - Boost (0-100 escala, y raw 0-255)
  - kickoff_num: en que reinicio del partido estamos

Ademas exporta:
  - Pelota: frame a frame (time, pos_x, pos_y, pos_z, vel_x, vel_y, vel_z)
  - Goals: cada gol (time, scorer, team_scored_on)
  - Kickoffs: cada reinicio (frame_idx, time)
  - Metadata: mapa, fecha, score final, jugadores

Uso:
    python extractor.py --replay <archivo.replay> [--rrrocket ruta/rrrocket.exe]
    python extractor.py --json   <archivo_completo.json>  [--out resultados.json]
    python extractor.py --json salida_completa.json --csv jugadores.csv --csv-ball pelota.csv

Requiere: rrrocket.exe accesible (por defecto busca en la misma carpeta)
Sin dependencias externas (solo stdlib de Python).
"""

import json
import subprocess
import argparse
import sys
from pathlib import Path
from typing import Any, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def safe_console_str(s: Any) -> str:
    if s is None:
        return ""
    st = str(s)
    try:
        st.encode(sys.stdout.encoding or 'utf-8')
        return st
    except (UnicodeEncodeError, AttributeError):
        return st.encode('ascii', errors='replace').decode('ascii')

from game_state import compute_frame_game_state
from events_detector import detect_basic_events
from challenge_detector import detect_challenges
from shadow_defense import detect_shadow_defense
from overcommit_detector import detect_overcommits
from double_commit_detector import detect_double_commits
from rotation_tracker import analyze_rotations
from boost_manager import analyze_boost_management
from recovery_detector import analyze_recoveries
from feature_evaluator import extract_feature_vector, evaluate_feature_vector
from game_context import create_game_context, GameContext
from aerial_detector import detect_aerials
from air_dribble_detector import detect_air_dribbles
from backboard_defense_detector import detect_backboard_defense


# Nombres canonicos de los objetos que nos interesan
# (estos NOMBRES son estables entre versiones; los INDICES no lo son)
_OBJ_NAMES = {
    "pawn_pri":           "Engine.Pawn:PlayerReplicationInfo",
    "pri_name":           "Engine.PlayerReplicationInfo:PlayerName",
    "pri_team":           "Engine.PlayerReplicationInfo:Team",
    "team_index":         "Engine.TeamInfo:TeamIndex",
    "rigid_body":         "TAGame.RBActor_TA:ReplicatedRBState",
    "boost_replicated":   "TAGame.CarComponent_Boost_TA:ReplicatedBoost",
    "boost_vehicle":      "TAGame.CarComponent_TA:Vehicle",
    "scored_on_team":     "TAGame.GameEvent_Soccar_TA:ReplicatedScoredOnTeam",
    "team0":              "Archetypes.Teams.Team0",
    "team1":              "Archetypes.Teams.Team1",
    "handbrake":          "TAGame.Vehicle_TA:bReplicatedHandbrake",
    "override_handbrake": "TAGame.Car_TA:bOverrideHandbrakeOn",
    "override_boost":     "TAGame.Car_TA:bOverrideBoostOn",
    "comp_active":        "TAGame.CarComponent_TA:ReplicatedActive",
    "dodge_torque":       "TAGame.CarComponent_Dodge_TA:DodgeTorque",
    "demolish":           "TAGame.Car_TA:ReplicatedDemolish",
    "demolish_ext":       "TAGame.Car_TA:ReplicatedDemolishExtended",
    "hit_team_num":       "TAGame.Ball_TA:HitTeamNum",
    "ball_hit":           "TAGame.GameEvent_Soccar_TA:bBallHasBeenHit",
    "throttle":           "TAGame.Vehicle_TA:ReplicatedThrottle",
    "steer":              "TAGame.Vehicle_TA:ReplicatedSteer",
}


def build_oid_map(objects: list) -> dict:
    """
    Construye un mapa nombre_clave -> object_id a partir de la tabla objects[]
    del replay. Resuelve los IDs dinamicamente con fallback por sufijo para
    maxima resiliencia ante distintas versiones de Rocket League.
    """
    name_to_idx = {name: i for i, name in enumerate(objects)}

    oid = {}
    for key, canonical in _OBJ_NAMES.items():
        # 1. Coincidencia exacta
        idx = name_to_idx.get(canonical)
        if idx is None:
            # 2. Fallback por sufijo
            suffix = ":" + canonical.split(":")[-1] if ":" in canonical else canonical
            for i, o in enumerate(objects):
                if o.endswith(suffix):
                    idx = i
                    break
        oid[key] = idx

    # Ball: cualquier archetype que contenga "Ball" y sea un Default/Archetype
    ball_ids = set()
    for i, o in enumerate(objects):
        if "Ball" in o and ("Archetype" in o or "Default" in o or "Ball_TA" == o.split(".")[-1]):
            ball_ids.add(i)
    oid["ball_archetypes"] = ball_ids

    # Car: cualquier objeto Car_Default o Car.Car_
    car_ids = set()
    for i, o in enumerate(objects):
        if "Car_Default" in o or ("Car.Car_" in o and "Archetype" in o):
            car_ids.add(i)
    oid["car_archetypes"] = car_ids

    return oid


def load_json(path: str) -> dict:
    """Carga JSON con deteccion automatica de encoding (utf-16, utf-8, latin-1)."""
    for enc in ["utf-16", "utf-8", "utf-8-sig", "latin-1"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"No se pudo decodificar {path} con ningun encoding conocido.")


def run_rrrocket(replay_path: str, rrrocket: str) -> dict:
    """Ejecuta rrrocket -n sobre el .replay y retorna el JSON parseado."""
    cmd = [rrrocket, "-n", replay_path]
    out = subprocess.check_output(cmd, stderr=subprocess.PIPE)
    for enc in ["utf-8", "utf-16", "utf-8-sig", "latin-1"]:
        try:
            return json.loads(out.decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError("No se pudo parsear el JSON de rrrocket.")


# =============================================================================
# HELPERS
# =============================================================================

def quaternion_to_euler_deg(qx: float, qy: float, qz: float, qw: float) -> tuple:
    """
    Convierte un Cuaternion (x, y, z, w) de Rocket League a grados Pitch, Yaw, Roll:
      - Pitch: inclinacion vertical (-90° nariz abajo, +90° nariz arriba)
      - Yaw:   orientacion horizontal (-180° a +180°)
      - Roll:  rotacion lateral / barrel roll (-180° a +180°)
    """
    import math
    norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if norm > 0:
        qx /= norm; qy /= norm; qz /= norm; qw /= norm

    sinr_cosp = 2.0 * (qw * qx + qy * qz)
    cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (qw * qy - qz * qx)
    if abs(sinp) >= 1:
        pitch = math.copysign(math.pi / 2.0, sinp)
    else:
        pitch = math.asin(sinp)

    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return round(math.degrees(pitch), 1), round(math.degrees(yaw), 1), round(math.degrees(roll), 1)


def extract_rb(value: Any) -> Optional[dict]:
    """
    Extrae pos, vel, ang_vel y orientacion 3D (pitch, yaw, roll + cuaternión) del RigidBody state.
    """
    if value is None:
        return None

    rb = value.get("RigidBody") if isinstance(value, dict) else None
    if rb is None:
        rb = value.get("rigid_body_state", value)

    pos = rb.get("location") or rb.get("pos")
    vel = rb.get("linear_velocity") or rb.get("vel")
    ang = rb.get("angular_velocity") or rb.get("ang_vel")
    rot = rb.get("rotation") or rb.get("rot")

    if pos is None:
        return None

    pitch, yaw, roll = None, None, None
    qx, qy, qz, qw = None, None, None, None

    if isinstance(rot, dict) and "w" in rot:
        qx = rot.get("x", 0.0)
        qy = rot.get("y", 0.0)
        qz = rot.get("z", 0.0)
        qw = rot.get("w", 1.0)
        pitch, yaw, roll = quaternion_to_euler_deg(qx, qy, qz, qw)

    return {
        "pos_x":     pos.get("x"),
        "pos_y":     pos.get("y"),
        "pos_z":     pos.get("z"),
        "vel_x":     vel.get("x") if vel else None,
        "vel_y":     vel.get("y") if vel else None,
        "vel_z":     vel.get("z") if vel else None,
        "ang_vel_x": ang.get("x") if ang else None,
        "ang_vel_y": ang.get("y") if ang else None,
        "ang_vel_z": ang.get("z") if ang else None,
        "pitch":     pitch,
        "yaw":       yaw,
        "roll":      roll,
        "rot_x":     round(qx, 5) if qx is not None else None,
        "rot_y":     round(qy, 5) if qy is not None else None,
        "rot_z":     round(qz, 5) if qz is not None else None,
        "rot_w":     round(qw, 5) if qw is not None else None,
    }


def resolve_actor_ref(val: Any) -> Optional[int]:
    """
    Extrae un actor_id de un valor ActiveActor o similar.
    Formato real: {"ActiveActor": {"active": bool, "actor": int}}
    """
    if isinstance(val, int):
        return val
    if isinstance(val, dict):
        # Formato rrrocket real: {"ActiveActor": {"active": T, "actor": N}}
        if "ActiveActor" in val:
            aa = val["ActiveActor"]
            return aa.get("actor")
        return val.get("actor") or val.get("actor_id")
    return None


def get_attr_val(attribute: Any) -> tuple:
    """
    Dado el dict 'attribute' de un updated_actor, retorna (tipo, valor_crudo).
    Formato: {"RigidBody": {...}} o {"String": "..."} o {"Byte": 5} etc.
    """
    if not isinstance(attribute, dict):
        return ("Unknown", attribute)
    keys = list(attribute.keys())
    if not keys:
        return ("Empty", None)
    tipo = keys[0]
    return (tipo, attribute[tipo])


# =============================================================================
# EXTRACTOR PRINCIPAL
# =============================================================================

def extract(data: dict) -> dict:
    """
    Recorre todos los frames en orden cronologico y construye:
      - players_frames: lista de rows por jugador/frame
      - ball_frames:    lista de rows de la pelota
      - goals:          lista de eventos de gol
      - kickoffs:       lista de kickoffs
      - metadata:       info del partido
    """
    props      = data.get("properties", {})
    objects    = data.get("objects", [])

    nf = data.get("network_frames")
    if not nf or not isinstance(nf, dict) or "frames" not in nf:
        raise ValueError(
            "El archivo JSON no contiene 'network_frames' (frames de red).\n"
            "Si ejecutaste rrrocket manualmente, asegurate de incluir el parametro '-n'."
        )
    frames_raw = nf["frames"]

    # -- Metadata del partido --------------------------------------------------
    metadata = {
        "map":           props.get("MapName"),
        "date":          props.get("Date"),
        "match_type":    props.get("MatchType"),
        "replay_id":     props.get("Id"),
        "team0_score":   props.get("Team0Score"),
        "team1_score":   props.get("Team1Score"),
        "total_seconds": props.get("TotalSecondsPlayed"),
        "num_frames":    len(frames_raw),
        "record_fps":    props.get("RecordFPS"),
    }

    # -- Tabla de nombres de object_id y lookup dinamico ----------------------
    obj_name = {i: o for i, o in enumerate(objects)}

    # Resolver object_ids dinamicamente desde la tabla de este replay
    oid = build_oid_map(objects)
    OBJ_PAWN_PRI        = oid["pawn_pri"]
    OBJ_PRI_NAME        = oid["pri_name"]
    OBJ_PRI_TEAM        = oid["pri_team"]
    OBJ_TEAM_INDEX      = oid["team_index"]
    OBJ_RIGID_BODY      = oid["rigid_body"]
    OBJ_BOOST_AMOUNT    = oid["boost_replicated"]
    OBJ_CAR_BOOST_COMP  = oid["boost_vehicle"]
    OBJ_SCORED_ON_TEAM  = oid["scored_on_team"]
    OBJ_TEAM0_ARCHETYPE = oid["team0"]
    OBJ_TEAM1_ARCHETYPE = oid["team1"]
    OBJ_HANDBRAKE          = oid["handbrake"]
    OBJ_OVERRIDE_HANDBRAKE = oid["override_handbrake"]
    OBJ_OVERRIDE_BOOST     = oid["override_boost"]
    OBJ_COMP_ACTIVE        = oid["comp_active"]
    OBJ_DODGE_TORQUE       = oid["dodge_torque"]
    OBJ_DEMOLISH           = oid["demolish"]
    OBJ_DEMOLISH_EXT       = oid["demolish_ext"]
    OBJ_HIT_TEAM_NUM       = oid["hit_team_num"]
    OBJ_BALL_HIT           = oid["ball_hit"]
    OBJ_THROTTLE           = oid["throttle"]
    OBJ_STEER              = oid["steer"]
    ball_obj_ids        = oid["ball_archetypes"]
    car_obj_ids         = oid["car_archetypes"]

    # Verificacion rapida
    missing = [k for k, v in oid.items()
               if k not in ("ball_archetypes", "car_archetypes") and v is None]
    if missing:
        print(f"[WARN] object_ids no encontrados en este replay: {missing}")

    # ==========================================================================
    # Estados vivos — se actualizan frame a frame
    # ==========================================================================

    # actor_id -> object_id del archetype (de new_actors)
    live_actor_type: dict = {}

    # Identidad: car_actor_id -> pri_actor_id
    car_to_pri: dict = {}

    # PRI: pri_actor_id -> {"name": str, "team_actor": int}
    pri_info: dict = {}

    # Team: team_actor_id -> 0 o 1
    team_index: dict = {}

    # Componentes y acciones por auto / actor
    comp_type: dict = {}         # comp_aid -> "jump" | "dodge" | "boost"
    comp_to_car: dict = {}       # comp_aid -> car_aid
    boost_to_car: dict = {}      # boost_aid -> car_aid
    car_boost: dict = {}         # car_aid -> float (0-255)
    car_handbrake: dict = {}     # car_aid -> bool
    car_boost_active: dict = {}  # car_aid -> bool
    car_jumping: dict = {}       # car_aid -> bool
    car_dodging: dict = {}       # car_aid -> bool
    car_throttle: dict = {}      # car_aid -> float (-1.0 a +1.0)
    car_steer: dict = {}         # car_aid -> float (-1.0 a +1.0)

    # Ultimo RigidBody por actor_id
    last_rb: dict = {}

    # Ball actor_ids conocidos
    ball_actor_ids: set = set()

    # Eventos discretos globales (goles, kickoffs, touches, demos, flips, jumps)
    discrete_events: list = []

    # ==========================================================================
    # Salida
    # ==========================================================================
    players_frames = []
    ball_frames    = []
    goals          = []
    kickoffs       = []

    kickoff_count = 0   # empieza en 0 = kickoff inicial

    for frame_idx, frame in enumerate(frames_raw):
        t       = frame.get("time", 0.0)
        new_act = frame.get("new_actors", [])
        del_act = frame.get("deleted_actors", [])
        upd_act = frame.get("updated_actors", [])

        # ── 1. new_actors ─────────────────────────────────────────────────────
        for na in new_act:
            aid = na["actor_id"]
            oid_val = na["object_id"]
            live_actor_type[aid] = oid_val
            oname = obj_name.get(oid_val, "")

            # Component type mapping
            if "Jump" in oname:
                comp_type[aid] = "jump"
            elif "Dodge" in oname or "FlipCar" in oname:
                comp_type[aid] = "dodge"
            elif "Boost" in oname and "Pickup" not in oname:
                comp_type[aid] = "boost"

            # Es pelota?
            if oid_val in ball_obj_ids:
                ball_actor_ids.add(aid)

            # Resolver team0/1 desde archetype directamente
            if OBJ_TEAM0_ARCHETYPE is not None and oid_val == OBJ_TEAM0_ARCHETYPE:
                team_index[aid] = 0
            elif OBJ_TEAM1_ARCHETYPE is not None and oid_val == OBJ_TEAM1_ARCHETYPE:
                team_index[aid] = 1

        # ── 2. updated_actors ─────────────────────────────────────────────────
        # Formato real de rrrocket:
        # { "actor_id": N, "stream_id": N, "object_id": N,
        #   "attribute": {"RigidBody": {...}} | {"ActiveActor": {...}} |
        #                {"String": "..."} | {"Byte": N} | ... }
        for upd in upd_act:
            aid = upd.get("actor_id")
            upd_oid = upd.get("object_id")      # object_id al nivel del update
            attribute = upd.get("attribute", {})
            tipo, val = get_attr_val(attribute)

            # Car -> PRI link  (resuelve churn de actor_id de autos)
            if upd_oid == OBJ_PAWN_PRI:
                # val = {"ActiveActor": {"active": bool, "actor": int}}
                pri_aid = resolve_actor_ref(attribute)
                if pri_aid is not None:
                    car_to_pri[aid] = pri_aid

            # PRI -> PlayerName
            elif upd_oid == OBJ_PRI_NAME:
                # val puede ser str directamente o {"String": "nombre"}
                name = None
                if tipo == "String" and isinstance(val, str):
                    name = val
                elif isinstance(val, str):
                    name = val
                if name:
                    pri_info.setdefault(aid, {})["name"] = name

            # PRI -> Team actor
            elif upd_oid == OBJ_PRI_TEAM:
                # {"ActiveActor": {"active": bool, "actor": N}}
                team_aid = resolve_actor_ref(attribute)
                if team_aid is not None:
                    pri_info.setdefault(aid, {})["team_actor"] = team_aid

            # Team -> TeamIndex
            elif upd_oid == OBJ_TEAM_INDEX:
                # {"Int": N} o {"Byte": N}
                idx = val if isinstance(val, int) else None
                if idx is not None:
                    team_index[aid] = int(idx)

            # Component Vehicle (car) link
            elif upd_oid == OBJ_CAR_BOOST_COMP:
                car_aid = resolve_actor_ref(attribute)
                if car_aid is not None:
                    comp_to_car[aid] = car_aid
                    boost_to_car[aid] = car_aid

            # Throttle (Acelerador / Reversa)
            elif OBJ_THROTTLE is not None and upd_oid == OBJ_THROTTLE:
                bval = val if isinstance(val, int) else (val or {}).get("Byte")
                if bval is not None:
                    car_throttle[aid] = round((bval - 128) / 128.0, 2)

            # Steer (Direccion / Volante)
            elif OBJ_STEER is not None and upd_oid == OBJ_STEER:
                bval = val if isinstance(val, int) else (val or {}).get("Byte")
                if bval is not None:
                    car_steer[aid] = round((bval - 128) / 128.0, 2)

            # Handbrake / Powerslide
            elif OBJ_HANDBRAKE is not None and upd_oid == OBJ_HANDBRAKE:
                bval = val if isinstance(val, bool) else (val or {}).get("Boolean")
                if bval is not None:
                    car_handbrake[aid] = bool(bval)
            elif OBJ_OVERRIDE_HANDBRAKE is not None and upd_oid == OBJ_OVERRIDE_HANDBRAKE:
                bval = val if isinstance(val, bool) else (val or {}).get("Boolean")
                if bval is not None:
                    car_handbrake[aid] = bool(bval)

            # Boost activo en auto
            elif OBJ_OVERRIDE_BOOST is not None and upd_oid == OBJ_OVERRIDE_BOOST:
                bval = val if isinstance(val, bool) else (val or {}).get("Boolean")
                if bval is not None:
                    car_boost_active[aid] = bool(bval)

            # Component active (Salto, Dodge, Boost)
            elif OBJ_COMP_ACTIVE is not None and upd_oid == OBJ_COMP_ACTIVE:
                act_num = val if isinstance(val, int) else (val or {}).get("Byte", (val or {}).get("Boolean"))
                is_act = bool(act_num) if act_num is not None else False
                ctype = comp_type.get(aid)
                car_aid = comp_to_car.get(aid) or boost_to_car.get(aid)
                if car_aid:
                    if ctype == "boost":
                        car_boost_active[car_aid] = is_act
                    elif ctype == "jump":
                        was_jumping = car_jumping.get(car_aid, False)
                        car_jumping[car_aid] = is_act
                        if is_act and not was_jumping:
                            pname = pri_info.get(car_to_pri.get(car_aid), {}).get("name", f"Jugador_{car_aid}")
                            discrete_events.append({"frame": frame_idx, "time": round(t, 2), "type": "JUMP", "player": pname})
                    elif ctype == "dodge":
                        was_dodging = car_dodging.get(car_aid, False)
                        car_dodging[car_aid] = is_act
                        if is_act and not was_dodging:
                            pname = pri_info.get(car_to_pri.get(car_aid), {}).get("name", f"Jugador_{car_aid}")
                            discrete_events.append({"frame": frame_idx, "time": round(t, 2), "type": "FLIP", "player": pname})

            # DodgeTorque update (Flip / Dodge)
            elif OBJ_DODGE_TORQUE is not None and upd_oid == OBJ_DODGE_TORQUE:
                car_aid = comp_to_car.get(aid)
                if car_aid:
                    car_dodging[car_aid] = True
                    pname = pri_info.get(car_to_pri.get(car_aid), {}).get("name", f"Jugador_{car_aid}")
                    discrete_events.append({"frame": frame_idx, "time": round(t, 2), "type": "FLIP", "player": pname})

            # Demolicion
            elif (OBJ_DEMOLISH is not None and upd_oid == OBJ_DEMOLISH) or (OBJ_DEMOLISH_EXT is not None and upd_oid == OBJ_DEMOLISH_EXT):
                demo_data = val.get("DemolishExtended") if isinstance(val, dict) else (val.get("Demolish") if isinstance(val, dict) else val)
                if isinstance(demo_data, dict):
                    att_obj = demo_data.get("attacker") or {}
                    vic_obj = demo_data.get("victim") or {}
                    att_aid = att_obj.get("actor") if isinstance(att_obj, dict) else None
                    vic_aid = vic_obj.get("actor") if isinstance(vic_obj, dict) else None
                    att_p = pri_info.get(car_to_pri.get(att_aid), {}).get("name") if att_aid else "Unknown"
                    vic_p = pri_info.get(car_to_pri.get(vic_aid), {}).get("name") if vic_aid else "Unknown"
                    discrete_events.append({
                        "frame": frame_idx, "time": round(t, 2), "type": "DEMOLITION",
                        "attacker": att_p, "victim": vic_p
                    })

            # Toque de pelota
            elif (OBJ_HIT_TEAM_NUM is not None and upd_oid == OBJ_HIT_TEAM_NUM) or (OBJ_BALL_HIT is not None and upd_oid == OBJ_BALL_HIT):
                hit_team = val if isinstance(val, int) else (val or {}).get("Byte")
                if hit_team is not None and hit_team != 255:
                    best_p = None
                    min_d = 999999.0
                    ball_rb = next((last_rb[b_aid] for b_aid in ball_actor_ids if b_aid in last_rb), None)
                    if ball_rb and ball_rb.get("pos_x") is not None:
                        bx, by, bz = ball_rb["pos_x"], ball_rb["pos_y"], ball_rb["pos_z"]
                        for c_aid, p_aid in car_to_pri.items():
                            p_info = pri_info.get(p_aid, {})
                            t_act = p_info.get("team_actor")
                            t_idx = team_index.get(t_act)
                            if t_idx == hit_team:
                                crb = last_rb.get(c_aid)
                                if crb and crb.get("pos_x") is not None:
                                    dx, dy, dz = crb["pos_x"] - bx, crb["pos_y"] - by, crb["pos_z"] - bz
                                    d = (dx*dx + dy*dy + dz*dz)**0.5
                                    if d < min_d:
                                        min_d = d
                                        best_p = p_info.get("name", f"Jugador_{p_aid}")
                    if best_p:
                        discrete_events.append({"frame": frame_idx, "time": round(t, 2), "type": "TOUCH", "player": best_p, "distance_u": round(min_d, 1)})

            # Boost component -> Vehicle (car) link
            elif upd_oid == OBJ_CAR_BOOST_COMP:
                car_aid = resolve_actor_ref(attribute)
                if car_aid is not None:
                    boost_to_car[aid] = car_aid

            # Boost amount (raw 0-255)
            # Formato real: {"ReplicatedBoost": {"grant_count": N, "boost_amount": N, ...}}
            elif upd_oid == OBJ_BOOST_AMOUNT:
                rb_boost = val.get("boost_amount") if isinstance(val, dict) else None
                if rb_boost is None and tipo == "ReplicatedBoost" and isinstance(val, dict):
                    rb_boost = val.get("boost_amount")
                if rb_boost is not None:
                    car_aid = boost_to_car.get(aid)
                    if car_aid is not None:
                        car_boost[car_aid] = float(rb_boost)

            # RigidBody state (posicion + velocidad)
            elif upd_oid == OBJ_RIGID_BODY:
                rb = extract_rb(attribute)
                if rb:
                    last_rb[aid] = rb

            # Gol anotado (evento en stream)
            elif upd_oid == OBJ_SCORED_ON_TEAM:
                team_on = val if isinstance(val, int) else None
                if team_on is not None and team_on != 255:
                    kickoff_count += 1
                    kickoffs.append({
                        "frame_idx":      frame_idx,
                        "time":           round(t, 4),
                        "kickoff_number": kickoff_count,
                    })
                    discrete_events.append({"frame": frame_idx, "time": round(t, 2), "type": "GOAL", "team_scored_on": team_on})

        # ── 3. Emitir rows de jugadores (Exactamente 1 row por (frame_idx, player)) ─────────
        seen_players_this_frame = set()
        for car_aid, pri_aid in list(car_to_pri.items()):
            if pri_aid is None or pri_aid < 0:
                continue
            info = pri_info.get(pri_aid, {})
            player_name = info.get("name") or f"Jugador_{pri_aid}"

            if player_name in seen_players_this_frame:
                continue

            team_act = info.get("team_actor")
            team_idx = team_index.get(team_act) if team_act is not None else None

            rb = last_rb.get(car_aid)
            if rb is None:
                continue

            seen_players_this_frame.add(player_name)

            boost_raw = car_boost.get(car_aid)
            boost_pct = round(boost_raw / 2.55, 1) if boost_raw is not None else None

            is_boost_on = car_boost_active.get(car_aid, False)
            is_slide_on = car_handbrake.get(car_aid, False)
            is_jump_on  = car_jumping.get(car_aid, False)
            is_dodge_on = car_dodging.get(car_aid, False)

            throttle_val = car_throttle.get(car_aid, 0.0)
            steer_val    = car_steer.get(car_aid, 0.0)
            is_airborne  = bool(rb["pos_z"] > 35.0) if rb.get("pos_z") is not None else False
            air_roll     = rb["ang_vel_x"] if (is_airborne and rb.get("ang_vel_x") is not None) else 0.0

            players_frames.append({
                "frame_idx":       frame_idx,
                "time":            round(t, 4),
                "player":          player_name,
                "team":            team_idx,
                "car_actor":       car_aid,
                "pri_actor":       pri_aid,
                "kickoff_num":     kickoff_count,
                "pos_x":           rb["pos_x"],
                "pos_y":           rb["pos_y"],
                "pos_z":           rb["pos_z"],
                "vel_x":           rb["vel_x"],
                "vel_y":           rb["vel_y"],
                "vel_z":           rb["vel_z"],
                "ang_vel_x":       rb["ang_vel_x"],
                "ang_vel_y":       rb["ang_vel_y"],
                "ang_vel_z":       rb["ang_vel_z"],
                "pitch":           rb["pitch"],
                "yaw":             rb["yaw"],
                "roll":            rb["roll"],
                "rot_x":           rb["rot_x"],
                "rot_y":           rb["rot_y"],
                "rot_z":           rb["rot_z"],
                "rot_w":           rb["rot_w"],
                "boost_pct":       boost_pct,
                "boost_raw":       boost_raw,
                "throttle":        throttle_val,
                "steer":           steer_val,
                "is_boosting":     is_boost_on,
                "is_powersliding": is_slide_on,
                "is_jumping":      is_jump_on,
                "is_dodging":      is_dodge_on,
                "is_airborne":     is_airborne,
                "air_roll_rate":   air_roll,
            })

        # ── 4. Emitir rows de pelota (Exactamente 1 row por frame_idx) ───────
        seen_ball_this_frame = False
        for ball_aid in list(ball_actor_ids):
            if seen_ball_this_frame:
                break
            rb = last_rb.get(ball_aid)
            if rb is None:
                continue
            seen_ball_this_frame = True
            ball_frames.append({
                "frame_idx": frame_idx,
                "time":      round(t, 4),
                "actor_id":  ball_aid,
                "kickoff_num": kickoff_count,
                "pos_x":     rb["pos_x"],
                "pos_y":     rb["pos_y"],
                "pos_z":     rb["pos_z"],
                "vel_x":     rb["vel_x"],
                "vel_y":     rb["vel_y"],
                "vel_z":     rb["vel_z"],
            })

        # ── 5. deleted_actors ─────────────────────────────────────────────────
        # Eliminar actores destruidos para prevenir acumulación y fugas
        for del_aid in del_act:
            live_actor_type.pop(del_aid, None)
            ball_actor_ids.discard(del_aid)
            car_to_pri.pop(del_aid, None)
            last_rb.pop(del_aid, None)
            car_boost.pop(del_aid, None)
            car_handbrake.pop(del_aid, None)
            car_boost_active.pop(del_aid, None)
            car_jumping.pop(del_aid, None)
            car_dodging.pop(del_aid, None)
            comp_to_car.pop(del_aid, None)
            boost_to_car.pop(del_aid, None)

    # ── Estadisticas por jugador ───────────────────────────────────────────────
    player_stats = {}
    for row in players_frames:
        p = row["player"]
        if p not in player_stats:
            player_stats[p] = {
                "name":            p,
                "team":            row["team"],
                "total_frames":    0,
                "car_actors_used": set(),
            }
        player_stats[p]["total_frames"] += 1
        player_stats[p]["car_actors_used"].add(row["car_actor"])

    for p in player_stats:
        s = player_stats[p]
        s["car_actors_used"] = sorted(s["car_actors_used"])
        s["car_respawns"] = len(s["car_actors_used"]) - 1

    # ── Extraer goles exactos desde metadata autoritativa de properties ────────
    goals_meta = props.get("Goals", [])
    goals = []
    if isinstance(goals_meta, list) and len(goals_meta) > 0:
        for gm in goals_meta:
            if isinstance(gm, dict):
                g_frame = gm.get("frame", 0)
                g_time = round(frames_raw[g_frame]["time"], 4) if (0 <= g_frame < len(frames_raw) and "time" in frames_raw[g_frame]) else round(g_frame * 0.033333, 4)
                g_team_scored_on = 1 if gm.get("PlayerTeam") == 0 else 0
                goals.append({
                    "frame_idx":      g_frame,
                    "time":           g_time,
                    "team_scored_on": g_team_scored_on,
                    "scorer":         gm.get("PlayerName"),
                    "scorer_team":    gm.get("PlayerTeam"),
                })
    else:
        # Fallback si no hay metadata de propiedades
        unique_g_frames = set()
        for dev in discrete_events:
            if dev.get("type") == "GOAL":
                gf = dev.get("frame", 0)
                if not any(abs(gf - uf) < 120 for uf in unique_g_frames):
                    unique_g_frames.add(gf)
                    goals.append({
                        "frame_idx":      gf,
                        "time":           dev.get("time", 0.0),
                        "team_scored_on": dev.get("team_scored_on", 0),
                    })

    # ── Generar GameStates completos frame a frame ─────────────────────────────
    from collections import defaultdict
    pf_by_frame = defaultdict(list)
    for r in players_frames:
        pf_by_frame[r["frame_idx"]].append(r)
    bf_by_frame = {r["frame_idx"]: r for r in ball_frames}

    game_states = []
    num_total_frames = len(frames_raw)
    for fi in range(num_total_frames):
        p_rows = pf_by_frame.get(fi, [])
        b_row  = bf_by_frame.get(fi)
        t_sec  = p_rows[0]["time"] if p_rows else (b_row["time"] if b_row else fi * 0.0333)
        gs = compute_frame_game_state(fi, t_sec, p_rows, b_row)
        game_states.append(gs)

    # ── Detectar eventos basicos (Touch, Shot, Save, Pass, Clear) ──────────────
    basic_events = detect_basic_events(game_states)
    all_discrete_events = sorted(discrete_events + basic_events, key=lambda item: item["frame"])

    # ── Detectar Challenges y 50/50s ───────────────────────────────────────────
    challenges = detect_challenges(game_states)

    # ── Detectar Shadow Defense (Estado continuo) ──────────────────────────────
    shadow_flags, shadow_episodes = detect_shadow_defense(game_states)

    # Aplicar flag is_shadowing a cada row de jugador
    for row in players_frames:
        row["is_shadowing"] = shadow_flags.get((row["frame_idx"], row["player"]), False)

    # ── Detectar Overcommits Tácticos ─────────────────────────────────────────
    overcommits = detect_overcommits(game_states)

    # ── Determinar Contexto del Modo de Juego (1v1, 2v2, 3v3) ─────────────────
    game_context = create_game_context(list(player_stats.values()))

    # ── Detectar Double Commits entre Compañeros ──────────────────────────────
    dc_status, double_commits = detect_double_commits(game_states, game_context)

    # ── Analizar Rotaciones continuas y Errores del 3er Hombre ─────────────────
    rot_status, rotation_errors, rot_p_stats = analyze_rotations(game_states, game_context)

    # ── Analizar Gestión de Boost y Errores de Prioridad ─────────────────────
    boost_errors, boost_p_stats = analyze_boost_management(game_states)

    # ── Analizar Recuperaciones y Calificación de Aterrizajes (Recoveries) ───
    recovery_events, rec_p_stats = analyze_recoveries(game_states)

    # ── Detectar Mecánicas Aéreas Avanzadas (Aerials, Air Dribbles, Backboard) ─
    aerials = detect_aerials(game_states)
    air_dribbles = detect_air_dribbles(game_states)
    backboard_defenses = detect_backboard_defense(game_states)

    # ── Generar Evaluaciones Basadas en Vectores de Features ─────────────────
    feature_evaluations = []
    for err in boost_errors:
        fi = err["frame"]
        if fi < len(game_states):
            vec = extract_feature_vector(game_states[fi], err["player"], "BOOST_DECISION", "ABANDONADO")
            if vec:
                feature_evaluations.append(evaluate_feature_vector(vec))

    for err in rotation_errors:
        fi = err["frame"]
        if fi < len(game_states):
            vec = extract_feature_vector(game_states[fi], err["player"], "ROTATION_DECISION", "PERDIDO")
            if vec:
                feature_evaluations.append(evaluate_feature_vector(vec))

    for ch in challenges:
        fi = ch["frame"]
        if fi < len(game_states):
            pname = ch.get("player_blue") or ch.get("player")
            if pname:
                vec = extract_feature_vector(game_states[fi], pname, "CHALLENGE_DECISION", ch.get("type", "50_50"))
                if vec:
                    feature_evaluations.append(evaluate_feature_vector(vec))

    # Enriquecer player_stats con métricas de rotación, boost y recoveries
    for rps in rot_p_stats:
        pname = rps["name"]
        if pname in player_stats:
            player_stats[pname]["pct_first_man"]   = rps.get("pct_first_man", 0.0)
            player_stats[pname]["pct_second_man"]  = rps.get("pct_second_man", 0.0)
            player_stats[pname]["pct_third_man"]   = rps.get("pct_third_man", 0.0)
            player_stats[pname]["third_man_errors"] = rps.get("third_man_errors", 0)

    for bps in boost_p_stats:
        pname = bps["name"]
        if pname in player_stats:
            player_stats[pname]["big_boost_pickups"]            = bps.get("big_boost_pickups", 0)
            player_stats[pname]["boost_stolen"]                 = bps.get("boost_stolen", 0)
            player_stats[pname]["boost_over_possession_errors"] = bps.get("boost_over_possession_errors", 0)
            player_stats[pname]["supersonic_waste_frames"]      = bps.get("supersonic_waste_frames", 0)

    for rrec in rec_p_stats:
        pname = rrec["name"]
        if pname in player_stats:
            player_stats[pname]["avg_recovery_time_sec"] = rrec.get("avg_recovery_time_sec", 0.0)
            player_stats[pname]["clean_landings_pct"]    = rrec.get("clean_landings_pct", 0.0)
            player_stats[pname]["avg_recovery_score"]    = rrec.get("avg_recovery_score", 0.0)
            player_stats[pname]["excellent_recoveries"]  = rrec.get("excellent_recoveries", 0)
            player_stats[pname]["poor_recoveries"]       = rrec.get("poor_recoveries", 0)

    metadata["players"]                 = list(player_stats.values())
    metadata["total_goals"]             = len(goals)
    metadata["total_kickoffs"]          = kickoff_count + 1
    metadata["total_events"]            = len(all_discrete_events)
    metadata["total_challenges"]        = len(challenges)
    metadata["total_shadow_episodes"]   = len(shadow_episodes)
    metadata["total_overcommits"]       = len(overcommits)
    metadata["total_double_commits"]    = len(double_commits)
    metadata["total_rotation_errors"]   = len(rotation_errors)
    metadata["total_boost_errors"]      = len(boost_errors)
    metadata["total_recoveries"]        = len(recovery_events)
    metadata["total_aerials"]           = len(aerials)
    metadata["total_air_dribbles"]      = len(air_dribbles)
    metadata["total_backboard_defenses"]= len(backboard_defenses)
    metadata["total_feature_evaluations"]= len(feature_evaluations)

    # Inyectar información de GameContext en metadata
    metadata["game_context"] = {
        "mode":                game_context.mode,
        "mode_display_name":   game_context.mode_display_name,
        "team_size":           game_context.team_size,
        "coach_profile_name":  game_context.coach_profile_name,
        "double_commit_status":dc_status,
        "rotation_error_status":rot_status,
    }

    return {
        "metadata":                metadata,
        "game_context":            metadata["game_context"],
        "players_frames":          players_frames,
        "ball_frames":             ball_frames,
        "game_states":             game_states,
        "goals":                   goals,
        "kickoffs":                kickoffs,
        "discrete_events":         all_discrete_events,
        "challenges":              challenges,
        "shadow_defense_episodes": shadow_episodes,
        "overcommits":             overcommits,
        "double_commits":          double_commits,
        "rotation_errors":         rotation_errors,
        "boost_errors":            boost_errors,
        "recovery_events":         recovery_events,
        "feature_evaluations":     feature_evaluations,
        "aerials":                 aerials,
        "air_dribbles":            air_dribbles,
        "backboard_defenses":      backboard_defenses,
        "events": {
            "basic_events":            basic_events,
            "challenges":              challenges,
            "shadow_defense_episodes": shadow_episodes,
            "overcommits":             overcommits,
            "double_commits":          double_commits,
            "rotation_errors":         rotation_errors,
            "boost_errors":            boost_errors,
            "recoveries":              recovery_events,
            "feature_evaluations":     feature_evaluations,
            "aerials":                 aerials,
            "air_dribbles":            air_dribbles,
            "backboard_defenses":      backboard_defenses,
        },
        "player_stats":            player_stats,
    }


# =============================================================================
# RESUMEN EN CONSOLA
# =============================================================================

def print_summary(result: dict):
    m = result["metadata"]
    sep = "=" * 72
    print(f"\n{sep}")
    print(f"  COACHIA — EXTRACTOR DE REPLAY")
    print(f"{sep}")
    print(f"  Mapa       : {m['map']}")
    print(f"  Fecha      : {m['date']}")
    print(f"  Tipo       : {m['match_type']}")
    print(f"  Score      : Team0 {m['team0_score']} — Team1 {m['team1_score']}")
    print(f"  Duracion   : {m['total_seconds']:.1f}s ({m['num_frames']} frames @ {m['record_fps']} fps)")
    print(f"  Kickoffs   : {m['total_kickoffs']} total (1 inicial + {m['total_goals']} goles)")

    print(f"\n  {'Jugador':<22} {'Equipo':<12} {'Frames':>8} {'Actor IDs':>10} {'Respawns':>9}")
    print(f"  {'-'*22} {'-'*12} {'-'*8} {'-'*10} {'-'*9}")
    for p in m.get("players", []):
        team_str = "Azul (0)" if p["team"] == 0 else "Naranja (1)" if p["team"] == 1 else "?"
        respawns = p.get("car_respawns", len(p.get("car_actors_used", [])) - 1)
        actors   = len(p.get("car_actors_used", []))
        pname_safe = safe_console_str(p['name'])
        print(f"  {pname_safe:<22} {team_str:<12} {p['total_frames']:>8} {actors:>10} {respawns:>9}")

    if result["goals"]:
        print(f"\n  {'#':>3}  {'Tiempo':>8}  {'Scorer':<22} {'Team en que entro':>18}")
        print(f"  {'-'*3}  {'-'*8}  {'-'*22} {'-'*18}")
        for i, g in enumerate(result["goals"], 1):
            scorer = safe_console_str(g.get("scorer") or "?")
            t_on   = g.get("team_scored_on", "?")
            print(f"  {i:>3}  {g['time']:>8.1f}s  {scorer:<22} {str(t_on):>18}")

    pf = result["players_frames"]
    bf = result["ball_frames"]
    print(f"\n  Rows jugadores : {len(pf)}")
    print(f"  Rows pelota    : {len(bf)}")
    print(sep)

    if pf:
        print("\n  Muestra (primeras 5 rows de jugadores con orientacion 3D):")
        keys = ["time", "player", "pos_x", "pos_y", "pos_z", "pitch", "yaw", "roll", "boost_pct"]
        print("  " + "  ".join(f"{k:>12}" for k in keys))
        for row in pf[:5]:
            print("  " + "  ".join(f"{safe_console_str(str(row.get(k, '')))[:12]:>12}" for k in keys))
        print()


# =============================================================================
# EXPORTAR CSV (stdlib, sin pandas)
# =============================================================================

def export_csv(rows: list, path: str, label: str = "datos"):
    if not rows:
        print(f"  [!] No hay rows de {label} para exportar.")
        return
    import csv
    keys = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"  -> CSV {label}: {path}  ({len(rows)} rows)")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Coachia — Extractor de replays de Rocket League",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Requiere:")[0].strip()
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--replay", metavar="FILE.replay",
                       help="Archivo .replay (ejecuta rrrocket automaticamente)")
    group.add_argument("--json",   metavar="FILE.json",
                       help="JSON de rrrocket ya generado (con -n)")
    parser.add_argument("--rrrocket", metavar="RUTA",
                        default=str(Path(__file__).parent / "rrrocket-0.11.5-x86_64-pc-windows-msvc" / "rrrocket.exe"),
                        help="Ruta al ejecutable rrrocket.exe")
    parser.add_argument("--out",      metavar="FILE.json",
                        help="Exportar resultado completo a JSON")
    parser.add_argument("--csv",      metavar="FILE.csv",
                        help="Exportar players_frames a CSV")
    parser.add_argument("--csv-ball", metavar="FILE.csv",
                        help="Exportar ball_frames a CSV")
    args = parser.parse_args()

    # -- Cargar datos ----------------------------------------------------------
    print("[1/3] Cargando JSON del replay...")
    if args.replay:
        rr = args.rrrocket
        if not Path(rr).exists():
            print(f"ERROR: No se encontro rrrocket.exe en: {rr}", file=sys.stderr)
            sys.exit(1)
        print(f"      Ejecutando rrrocket -n sobre: {args.replay}")
        data = run_rrrocket(args.replay, rr)
    else:
        data = load_json(args.json)

    # -- Extraer ---------------------------------------------------------------
    print("[2/3] Extrayendo datos frame a frame...")
    result = extract(data)

    # -- Mostrar ---------------------------------------------------------------
    print("[3/3] Listo.")
    print_summary(result)

    # -- Exportar --------------------------------------------------------------
    if args.out:
        out_data = {
            "metadata":                result["metadata"],
            "goals":                   result["goals"],
            "kickoffs":                result["kickoffs"],
            "discrete_events":         result["discrete_events"],
            "challenges":              result["challenges"],
            "shadow_defense_episodes": result["shadow_defense_episodes"],
            "overcommits":             result["overcommits"],
            "double_commits":          result["double_commits"],
            "rotation_errors":         result["rotation_errors"],
            "boost_errors":            result["boost_errors"],
            "recovery_events":         result["recovery_events"],
            "feature_evaluations":     result["feature_evaluations"],
            "player_stats":            result["player_stats"],
            "game_states":             result["game_states"],
            "players_frames":          result["players_frames"],
            "ball_frames":             result["ball_frames"],
        }
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2, ensure_ascii=False)
            f.flush()
        print(f"\n  -> JSON completo: {args.out}")

    if args.csv:
        export_csv(result["players_frames"], args.csv, "jugadores")

    if args.csv_ball:
        export_csv(result["ball_frames"], args.csv_ball, "pelota")


if __name__ == "__main__":
    main()
