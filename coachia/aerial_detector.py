"""
coachia/aerial_detector.py
==========================
Detector de contactos aéreos genéricos (Aerials).

Definición:
  El jugador toca la pelota mientras está en el aire, con la pelota también elevada.

Detección:
  - is_airborne == True (o pos_z > 150.0)
  - pos_z > 300.0 (por encima de un salto normal/doble salto)
  - dist_to_ball <= 160.0 (contacto con el balón)
  - ball.pos_z > 300.0 (pelota elevada en el aire)

Métricas Registradas:
  - Altura del impacto (pos_z del jugador y pelota)
  - Pitch/Yaw/Roll al momento del contacto
  - Velocidad y boost del jugador antes del despegue
  - Resultado estimado (hacia arco rival, pase o pérdida de control)
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


def detect_aerials(game_states: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Recorre la secuencia completa de GameState e identifica contactos aéreos (Aerials).
    Returns: Lista de diccionarios con eventos AERIAL.
    """
    aerials = []
    num_frames = len(game_states)
    last_aerial_frame = {}  # player_name -> frame_idx

    for fi, gs in enumerate(game_states):
        t = gs["time"]
        ball = gs.get("ball")
        players = gs.get("players", [])

        if not ball or ball.get("pos_x") is None:
            continue

        bz = ball.get("pos_z") or 0.0
        if bz <= 300.0:
            continue

        for p in players:
            pname = p["name"]
            team = p["team"]
            pz = p.get("pos_z") or 0.0
            dist = p.get("dist_to_ball") or 9999.0
            is_air = p.get("is_airborne", False) or pz > 150.0

            # Criterios: airborne, ambos z > 300, dist <= 160
            if is_air and pz > 300.0 and dist <= 160.0:
                # Evitar duplicar en frames inmediatamente contiguos (cooldown de 15 frames / 0.5s)
                if fi - last_aerial_frame.get(pname, -999) < 15:
                    continue

                last_aerial_frame[pname] = fi

                vx, vy, vz = p.get("vel_x") or 0.0, p.get("vel_y") or 0.0, p.get("vel_z") or 0.0
                speed = math.sqrt(vx*vx + vy*vy + vz*vz)
                b_vx, b_vy, b_vz = ball.get("vel_x") or 0.0, ball.get("vel_y") or 0.0, ball.get("vel_z") or 0.0

                # Evaluar dirección del golpe aéreo respecto al arco rival
                target_goal_y = ORANGE_GOAL_Y if team == 0 else BLUE_GOAL_Y
                towards_rival_goal = (b_vy > 100.0) if team == 0 else (b_vy < -100.0)

                outcome = "DISPARO_AEREO" if towards_rival_goal else "CONTACTO_AEREO"

                other_tms = [other["name"] for other in players if other["team"] == team and other["name"] != pname]

                aerials.append({
                    "frame":                fi,
                    "time":                 t,
                    "type":                 "AERIAL",
                    "team":                 team,
                    "team_name":            "Azul (Team 0)" if team == 0 else "Naranja (Team 1)",
                    "player":               pname,
                    "player_z":             safe_round(pz, 1, 300.0),
                    "ball_z":               safe_round(bz, 1, 300.0),
                    "pitch":                safe_round(p.get("pitch"), 1, 0.0),
                    "yaw":                  safe_round(p.get("yaw"), 1, 0.0),
                    "roll":                 safe_round(p.get("roll"), 1, 0.0),
                    "player_speed":         safe_round(speed, 1, 0.0),
                    "player_boost":         safe_round(p.get("boost_pct"), 1, 33.3),
                    "dist_to_ball":         safe_round(dist, 1, 100.0),
                    "outcome":              outcome,
                    "ball_x":               safe_round(ball.get("pos_x"), 1, 0.0),
                    "ball_y":               safe_round(ball.get("pos_y"), 1, 0.0),
                    "ball_vel_x":           safe_round(b_vx, 1, 0.0),
                    "ball_vel_y":           safe_round(b_vy, 1, 0.0),
                    "ball_vel_z":           safe_round(b_vz, 1, 0.0),
                    "player_x":             safe_round(p.get("pos_x"), 1, 0.0),
                    "player_y":             safe_round(p.get("pos_y"), 1, 0.0),
                    "player_vel_x":         safe_round(vx, 1, 0.0),
                    "player_vel_y":         safe_round(vy, 1, 0.0),
                    "player_vel_z":         safe_round(vz, 1, 0.0),
                    "teammates_positions":  [
                        {"name": tm["name"], "pos_x": safe_round(tm.get("pos_x"), 1, 0.0), "pos_y": safe_round(tm.get("pos_y"), 1, 0.0), "pos_z": safe_round(tm.get("pos_z"), 1, 17.0)}
                        for tm in players if tm["team"] == team and tm["name"] != pname
                    ],
                    "details":              f"Aerial de {pname} a {pz:.0f}uu de altura (velocidad={speed:.0f} u/s, boost={p.get('boost_pct', 33.3):.0f}%)"
                })

    return aerials
