"""
coachia/boost_manager.py
========================
Detector táctico de Gestión de Boost (Boost Management & Decision Errors).

Ubicación de los 6 Big Boosts (100% Orbs):
  - Azul Izquierda (Corner):    x = -3072, y = -4096
  - Azul Derecha (Corner):      x =  3072, y = -4096
  - Medio Campo Izquierda:      x = -3584, y =     0
  - Medio Campo Derecha:        x =  3584, y =     0
  - Naranja Izquierda (Corner): x = -3072, y =  4096
  - Naranja Derecha (Corner):   x =  3072, y =  4096

Calcula:
  1. Recolección de Big Boosts y Boosts Robados en campo rival.
  2. BOOST_OVER_POSSESSION_ERROR: Abandono de la jugada / posesión para ir a buscar un Big Boost en la esquina, derivando en peligro o gol rival.
  3. SUPERSONIC_BOOST_WASTE: Consumo innecesario de boost estando ya a velocidad supersónica (v >= 2200 u/s).
"""

import math
from typing import Dict, Any, List, Tuple


def safe_round(val: Any, decimals: int = 1, default: float = 0.0) -> float:
    if val is None:
        return round(float(default), decimals)
    try:
        return round(float(val), decimals)
    except (ValueError, TypeError):
        return round(float(default), decimals)


BIG_BOOST_PADS = [
    {"name": "Blue_Left_Corner",   "x": -3072.0, "y": -4096.0, "team": 0},
    {"name": "Blue_Right_Corner",  "x":  3072.0, "y": -4096.0, "team": 0},
    {"name": "Midfield_Left",      "x": -3584.0, "y":     0.0, "team": None},
    {"name": "Midfield_Right",     "x":  3584.0, "y":     0.0, "team": None},
    {"name": "Orange_Left_Corner", "x": -3072.0, "y":  4096.0, "team": 1},
    {"name": "Orange_Right_Corner","x":  3072.0, "y":  4096.0, "team": 1},
]


def distance_2d(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.sqrt((x1 - x2)**2 + (y1 - y2)**2)


def analyze_boost_management(game_states: List[Dict[str, Any]]) -> tuple:
    """
    Analiza las decisiones de gestión de boost e identifica errores tácticos de prioridad.
    Returns: (boost_errors, boost_player_stats)
    """
    boost_errors = []

    # player_name -> {"name", "team", "big_boost_pickups", "boost_stolen", "boost_over_possession_errors", "supersonic_waste_frames"}
    player_stats = {}

    # player_name -> {"prev_boost", "prev_pos_x", "prev_pos_y"}
    prev_player_states = {}

    last_error_frame = {}

    for fi, gs in enumerate(game_states):
        t = gs["time"]
        ball = gs.get("ball")
        players = gs.get("players", [])

        if not ball or ball.get("pos_x") is None:
            continue

        by = ball["pos_y"]

        for p in players:
            pname = p["name"]
            team = p["team"]
            px, py = p["pos_x"], p["pos_y"]
            b_pct = p.get("boost_pct") or 0.0
            vx, vy, vz = p.get("vel_x") or 0.0, p.get("vel_y") or 0.0, p.get("vel_z") or 0.0
            speed = math.sqrt(vx*vx + vy*vy + vz*vz)

            if pname not in player_stats:
                player_stats[pname] = {
                    "name":                          pname,
                    "team":                          team,
                    "big_boost_pickups":             0,
                    "boost_stolen":                  0,
                    "boost_over_possession_errors":  0,
                    "supersonic_waste_frames":       0,
                }

            ps = player_stats[pname]
            prev = prev_player_states.get(pname)

            # ── 1. DETECCION DE PICKUP DE BIG BOOST ───────────────────────────
            if prev and prev["boost"] is not None and b_pct > prev["boost"] + 50.0:
                # El boost saltó bruscamente (ej: de 10% a 100%)
                for pad in BIG_BOOST_PADS:
                    d_pad = distance_2d(px, py, pad["x"], pad["y"])
                    if d_pad <= 400.0:
                        ps["big_boost_pickups"] += 1

                        # Es robado si se toma en el área de la esquina del equipo rival
                        if (team == 0 and pad["y"] > 2000.0) or (team == 1 and pad["y"] < -2000.0):
                            ps["boost_stolen"] += 1

                        # ── 2. EVALUAR ERROR: BOOST OVER POSSESSION / ROTATION ─
                        # Ocurre si el jugador tenía responsabilidad defensiva u ofensiva activa (dist_to_ball < 2500)
                        # y se desvió a la esquina perdiendo la posición táctica
                        is_far_from_play = p["dist_to_ball"] > 2200.0
                        is_corner_pad = abs(pad["x"]) > 2500.0 and abs(pad["y"]) > 3000.0

                        # Si abandonó la jugada para ir a la esquina a buscar el pad de 100%
                        if is_corner_pad and is_far_from_play and prev["dist_to_ball"] < 1600.0:
                            if (fi - last_error_frame.get(pname, -999)) > 90:
                                last_error_frame[pname] = fi
                                ps["boost_over_possession_errors"] += 1
                                tname = "Azul (Team 0)" if team == 0 else "Naranja (Team 1)"

                                other_tms = [tm for tm in players if tm.get("team") == team and tm.get("name") != pname]
                                boost_errors.append({
                                    "frame":        fi,
                                    "time":         t,
                                    "type":         "BOOST_OVER_POSSESSION_ERROR",
                                    "team":         team,
                                    "team_name":    tname,
                                    "player":       pname,
                                    "pad_name":     pad["name"],
                                    "prev_boost":   safe_round(prev.get("boost"), 1, 0.0),
                                    "dist_to_ball": safe_round(p.get("dist_to_ball"), 1, 1500.0),
                                    # --- Campos telemétricos 3D ---
                                    "player_x":     safe_round(px, 1, 0.0),
                                    "player_y":     safe_round(py, 1, 0.0),
                                    "player_z":     safe_round(p.get("pos_z"), 1, 17.0),
                                    "player_vel_x": safe_round(vx, 1, 0.0),
                                    "player_vel_y": safe_round(vy, 1, 0.0),
                                    "player_vel_z": safe_round(vz, 1, 0.0),
                                    "player_boost": safe_round(b_pct, 1, 33.3),
                                    "ball_x":       safe_round(ball.get("pos_x"), 1, 0.0),
                                    "ball_y":       safe_round(ball.get("pos_y"), 1, 0.0),
                                    "ball_z":       safe_round(ball.get("pos_z"), 1, 92.75),
                                    "ball_vel_x":   safe_round(ball.get("vel_x"), 1, 0.0),
                                    "ball_vel_y":   safe_round(ball.get("vel_y"), 1, 0.0),
                                    "ball_vel_z":   safe_round(ball.get("vel_z"), 1, 0.0),
                                    "teammates_positions": [
                                        {"name": tm["name"], "pos_x": safe_round(tm.get("pos_x"), 1, 0.0), "pos_y": safe_round(tm.get("pos_y"), 1, 0.0), "pos_z": safe_round(tm.get("pos_z"), 1, 17.0)}
                                        for tm in other_tms
                                    ],
                                    "details":      f"Error de gestión de boost: {pname} abandonó la jugada (estaba a {safe_round(prev.get('dist_to_ball'), 0, 1500.0):.0f}uu) para buscar Big Boost en {pad['name']}"
                                })
                        break

            # ── 3. DETECCION DE MALGASTO EN SUPERSONICO (Supersonic Waste) ────
            if speed >= 2150.0 and p.get("is_boosting"):
                ps["supersonic_waste_frames"] += 1

            prev_player_states[pname] = {
                "boost":        b_pct,
                "pos_x":        px,
                "pos_y":        py,
                "dist_to_ball": p["dist_to_ball"],
            }

    return boost_errors, list(player_stats.values())
