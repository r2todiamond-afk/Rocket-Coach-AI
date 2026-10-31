"""
coachia/air_dribble_detector.py
==============================
Detector de secuencias de Air Dribble (Control aéreo continuo).

Definición:
  El jugador mantiene la pelota controlada en el aire durante 2 o más toques consecutivos,
  sin que el auto ni la pelota toquen el suelo.

Detección:
  - ball.pos_z > 300.0 sostenidamente.
  - 2+ toques (TOUCH) del mismo jugador.
  - Intervalo entre toques <= 2.5 segundos (75 frames).
  - is_airborne == True en cada uno de los toques.
"""

import math
from typing import Dict, Any, List, Optional


def safe_round(val: Any, decimals: int = 1, default: float = 0.0) -> float:
    if val is None:
        return round(float(default), decimals)
    try:
        return round(float(val), decimals)
    except (ValueError, TypeError):
        return round(float(default), decimals)


BLUE_GOAL_Y   = -5120.0
ORANGE_GOAL_Y =  5120.0


def detect_air_dribbles(game_states: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Identifica secuencias continuas de Air Dribbles (2+ toques aéreos del mismo jugador).
    Returns: Lista de diccionarios con eventos AIR_DRIBBLE.
    """
    air_dribbles = []
    num_frames = len(game_states)

    # Rastrear sesiones aéreas por jugador:
    # player_name -> list of touch dicts [{"frame", "time", "ball_z", "player_z", "boost"}]
    active_sessions = {}

    for fi, gs in enumerate(game_states):
        t = gs["time"]
        ball = gs.get("ball")
        players = gs.get("players", [])

        if not ball or ball.get("pos_x") is None:
            continue

        bz = ball.get("pos_z") or 0.0

        for p in players:
            pname = p["name"]
            team = p["team"]
            pz = p.get("pos_z") or 0.0
            dist = p.get("dist_to_ball") or 9999.0
            is_air = p.get("is_airborne", False) or pz > 150.0

            is_air_touch = is_air and pz > 250.0 and bz > 250.0 and dist <= 160.0

            if is_air_touch:
                if pname not in active_sessions:
                    active_sessions[pname] = []

                session = active_sessions[pname]

                # Si el último toque fue muy reciente (menos de 8 frames), es el mismo impacto, omitir
                if session and (fi - session[-1]["frame"]) < 8:
                    continue

                # Si el tiempo desde el último toque es mayor a 2.5s (75 frames), cerrar sesión previa
                if session and (t - session[-1]["time"]) > 2.5:
                    if len(session) >= 2:
                        _record_air_dribble(session, air_dribbles, players, ball, team)
                    active_sessions[pname] = []

                active_sessions[pname].append({
                    "frame":    fi,
                    "time":     t,
                    "player":   pname,
                    "team":     team,
                    "player_z": pz,
                    "ball_z":   bz,
                    "boost":    p.get("boost_pct", 33.3),
                    "pos_x":    p.get("pos_x", 0.0),
                    "pos_y":    p.get("pos_y", 0.0),
                    "vel_x":    p.get("vel_x", 0.0),
                    "vel_y":    p.get("vel_y", 0.0),
                    "vel_z":    p.get("vel_z", 0.0),
                    "ball_x":   ball.get("pos_x", 0.0),
                    "ball_y":   ball.get("pos_y", 0.0),
                    "ball_vx":  ball.get("vel_x", 0.0),
                    "ball_vy":  ball.get("vel_y", 0.0),
                    "ball_vz":  ball.get("vel_z", 0.0)
                })

            else:
                # Si el jugador ya aterrizó o la pelota cayó al piso (bz < 100), cerrar la sesión si aplica
                if pname in active_sessions and active_sessions[pname]:
                    session = active_sessions[pname]
                    if (t - session[-1]["time"]) > 1.2 or bz < 100.0 or not is_air:
                        if len(session) >= 2:
                            _record_air_dribble(session, air_dribbles, players, ball, team)
                        active_sessions[pname] = []

    # Cerrar cualquier sesión pendiente al final del partido
    for pname, session in active_sessions.items():
        if len(session) >= 2:
            _record_air_dribble(session, air_dribbles, [], {}, 0)

    return air_dribbles


def _record_air_dribble(session: List[Dict[str, Any]], air_dribbles: List[Dict[str, Any]], players: List[Dict[str, Any]], ball: Dict[str, Any], team: int):
    first_touch = session[0]
    last_touch  = session[-1]
    pname       = first_touch["player"]
    num_touches = len(session)
    duration    = round(last_touch["time"] - first_touch["time"], 2)

    target_goal_y = ORANGE_GOAL_Y if team == 0 else BLUE_GOAL_Y
    towards_rival = (last_touch["ball_vy"] > 100.0) if team == 0 else (last_touch["ball_vy"] < -100.0)

    outcome = "GOL_AEREO_POTENCIAL" if towards_rival and num_touches >= 3 else "AIR_DRIBBLE_CONTROLADO"

    air_dribbles.append({
        "frame":                first_touch["frame"],
        "time":                 first_touch["time"],
        "duration_sec":         duration,
        "num_touches":          num_touches,
        "type":                 "AIR_DRIBBLE",
        "team":                 team,
        "team_name":            "Azul (Team 0)" if team == 0 else "Naranja (Team 1)",
        "player":               pname,
        "outcome":              outcome,
        "player_z":             safe_round(first_touch["player_z"], 1, 300.0),
        "ball_z":               safe_round(first_touch["ball_z"], 1, 300.0),
        "player_boost":         safe_round(first_touch["boost"], 1, 33.3),
        "ball_x":               safe_round(first_touch["ball_x"], 1, 0.0),
        "ball_y":               safe_round(first_touch["ball_y"], 1, 0.0),
        "ball_vel_x":           safe_round(first_touch["ball_vx"], 1, 0.0),
        "ball_vel_y":           safe_round(first_touch["ball_vy"], 1, 0.0),
        "ball_vel_z":           safe_round(first_touch["ball_vz"], 1, 0.0),
        "player_x":             safe_round(first_touch["pos_x"], 1, 0.0),
        "player_y":             safe_round(first_touch["pos_y"], 1, 0.0),
        "player_vel_x":         safe_round(first_touch["vel_x"], 1, 0.0),
        "player_vel_y":         safe_round(first_touch["vel_y"], 1, 0.0),
        "player_vel_z":         safe_round(first_touch["vel_z"], 1, 0.0),
        "teammates_positions":  [
            {"name": tm["name"], "pos_x": safe_round(tm.get("pos_x"), 1, 0.0), "pos_y": safe_round(tm.get("pos_y"), 1, 0.0), "pos_z": safe_round(tm.get("pos_z"), 1, 17.0)}
            for tm in players if tm["team"] == team and tm["name"] != pname
        ],
        "details":              f"Air Dribble de {pname}: {num_touches} toques aéreos sostenidos en {duration:.1f}s"
    })
