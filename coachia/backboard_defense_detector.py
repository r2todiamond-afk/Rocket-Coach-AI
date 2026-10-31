"""
coachia/backboard_defense_detector.py
=====================================
Detector de Defensa desde el Travesaño / Backboard (Backboard Defense & Clears).

Definición:
  El jugador defiende saltando desde su propio travesaño o pared trasera
  para despejar un tiro que ya iba directo hacia su portería.

Detección:
  - Jugador pos_y cerca del arco propio (|pos_y| > 4800.0).
  - Jugador pos_z > 400.0 (elevado cerca de la altura del travesaño ~642uu).
  - is_airborne == True.
  - dist_to_ball <= 160.0 (contacto con el balón).
  - Pelota con trayectoria previa hacia el arco propio (evaluada con is_ball_on_target).
"""

import math
from typing import Dict, Any, List, Optional
from events_detector import is_ball_on_target


def safe_round(val: Any, decimals: int = 1, default: float = 0.0) -> float:
    if val is None:
        return round(float(default), decimals)
    try:
        return round(float(val), decimals)
    except (ValueError, TypeError):
        return round(float(default), decimals)


BLUE_GOAL_Y   = -5120.0
ORANGE_GOAL_Y =  5120.0


def detect_backboard_defense(game_states: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Identifica intervenciones defensivas desde la pared trasera / travesaño.
    Returns: Lista de diccionarios con eventos BACKBOARD_DEFENSE.
    """
    backboard_events = []
    last_event_frame = {}  # player_name -> frame_idx

    for fi, gs in enumerate(game_states):
        t = gs["time"]
        ball = gs.get("ball")
        players = gs.get("players", [])

        if not ball or ball.get("pos_x") is None:
            continue

        b_pos = {"pos_x": ball["pos_x"], "pos_y": ball["pos_y"], "pos_z": ball["pos_z"]}
        b_vel = {"vel_x": ball.get("vel_x", 0.0), "vel_y": ball.get("vel_y", 0.0), "vel_z": ball.get("vel_z", 0.0)}

        for p in players:
            pname = p["name"]
            team = p["team"]
            py = p.get("pos_y") or 0.0
            pz = p.get("pos_z") or 0.0
            dist = p.get("dist_to_ball") or 9999.0
            is_air = p.get("is_airborne", False) or pz > 150.0

            # Verificar si el jugador está en su propia zona de travesaño/pared trasera
            is_near_own_backboard = (team == 0 and py < -4700.0) or (team == 1 and py > 4700.0)
            is_elevated = (pz > 380.0)

            if is_near_own_backboard and is_elevated and is_air and dist <= 160.0:
                if fi - last_event_frame.get(pname, -999) < 20:
                    continue

                # Evaluar si la pelota venía en dirección al arco propio (arco 0 o 1)
                was_shot_on_target = is_ball_on_target(b_pos, b_vel, target_team_goal=team)

                if was_shot_on_target or is_near_own_backboard:
                    last_event_frame[pname] = fi

                    vx, vy, vz = p.get("vel_x") or 0.0, p.get("vel_y") or 0.0, p.get("vel_z") or 0.0
                    speed = math.sqrt(vx*vx + vy*vy + vz*vz)

                    outcome = "BACKBOARD_CLEAR_EXITOSO" if was_shot_on_target else "INTERVENCION_BACKBOARD"

                    backboard_events.append({
                        "frame":                fi,
                        "time":                 t,
                        "type":                 "BACKBOARD_DEFENSE",
                        "team":                 team,
                        "team_name":            "Azul (Team 0)" if team == 0 else "Naranja (Team 1)",
                        "player":               pname,
                        "outcome":              outcome,
                        "player_z":             safe_round(pz, 1, 400.0),
                        "ball_z":               safe_round(ball["pos_z"], 1, 400.0),
                        "player_boost":         safe_round(p.get("boost_pct"), 1, 33.3),
                        "was_shot_on_target":   was_shot_on_target,
                        "ball_x":               safe_round(ball["pos_x"], 1, 0.0),
                        "ball_y":               safe_round(ball["pos_y"], 1, 0.0),
                        "ball_vel_x":           safe_round(ball.get("vel_x"), 1, 0.0),
                        "ball_vel_y":           safe_round(ball.get("vel_y"), 1, 0.0),
                        "ball_vel_z":           safe_round(ball.get("vel_z"), 1, 0.0),
                        "player_x":             safe_round(p.get("pos_x"), 1, 0.0),
                        "player_y":             safe_round(p.get("pos_y"), 1, 0.0),
                        "player_vel_x":         safe_round(vx, 1, 0.0),
                        "player_vel_y":         safe_round(vy, 1, 0.0),
                        "player_vel_z":         safe_round(vz, 1, 0.0),
                        "teammates_positions":  [
                            {"name": tm["name"], "pos_x": safe_round(tm.get("pos_x"), 1, 0.0), "pos_y": safe_round(tm.get("pos_y"), 1, 0.0), "pos_z": safe_round(tm.get("pos_z"), 1, 17.0)}
                            for tm in players if tm["team"] == team and tm["name"] != pname
                        ],
                        "details":              f"Defensa de Travesaño (Backboard) por {pname} a {pz:.0f}uu de altura en su propio arco"
                    })

    return backboard_events
