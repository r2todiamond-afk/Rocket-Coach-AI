"""
coachia/game_state.py
=====================
Generador deterministico de estado completo del partido (GameState) frame a frame.

Calcula:
  - GameState por frame: time, ball, players[]
  - Roles tacticos: first_man, second_man, third_man por equipo (0 y 1)
  - team_possession: equipo en control/mas cercano
  - nearest_player: jugador mas cercano al balon y su distancia
  - open_net: deteccion de arco desprotegido (sin defensores entre pelota y arco)
  - pressure: puntuacion de presion ofensiva (0–100) sobre cada equipo
  - danger_level: nivel de peligro inmediato (0–100) en cada arco
  - boost_distribution: distribucion y promedios de boost por equipo
"""

import math
from typing import Dict, Any, List, Optional


# Coordenadas reglamentarias de arcos en Rocket League
BLUE_GOAL_Y   = -5120.0   # Arco Azul (Team 0)
ORANGE_GOAL_Y =  5120.0   # Arco Naranja (Team 1)
GOAL_X_MIN    = -896.0
GOAL_X_MAX    =  896.0
GOAL_Z_MAX    =  640.0


def distance_3d(x1: float, y1: float, z1: float, x2: float, y2: float, z2: float) -> float:
    return math.sqrt((x1 - x2)**2 + (y1 - y2)**2 + (z1 - z2)**2)


def compute_frame_game_state(
    frame_idx: int,
    time_sec: float,
    players_frame_rows: List[Dict[str, Any]],
    ball_row: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Construye el objeto GameState completo para un único frame.
    """
    # ── 1. Ball state ─────────────────────────────────────────────────────────
    ball_state = None
    if ball_row and ball_row.get("pos_x") is not None:
        bx = float(ball_row["pos_x"])
        by = float(ball_row["pos_y"])
        bz = float(ball_row["pos_z"])
        vx = float(ball_row.get("vel_x") or 0.0)
        vy = float(ball_row.get("vel_y") or 0.0)
        vz = float(ball_row.get("vel_z") or 0.0)
        speed = math.sqrt(vx*vx + vy*vy + vz*vz)
        ball_state = {
            "pos_x": round(bx, 2),
            "pos_y": round(by, 2),
            "pos_z": round(bz, 2),
            "vel_x": round(vx, 2),
            "vel_y": round(vy, 2),
            "vel_z": round(vz, 2),
            "speed": round(speed, 2),
        }
    else:
        bx, by, bz = 0.0, 0.0, 0.0

    # ── 2. Process Players ───────────────────────────────────────────────────
    team0_players = []
    team1_players = []
    all_players_state = []

    nearest_p = None
    min_ball_dist = 999999.0

    for p in players_frame_rows:
        px = float(p.get("pos_x") or 0.0)
        py = float(p.get("pos_y") or 0.0)
        pz = float(p.get("pos_z") or 0.0)

        dist_ball = distance_3d(px, py, pz, bx, by, bz) if ball_state else 999999.0

        p_info = {
            "name":            p["player"],
            "team":            p["team"],
            "pos_x":           round(px, 2),
            "pos_y":           round(py, 2),
            "pos_z":           round(pz, 2),
            "vel_x":           round(float(p.get("vel_x") or 0.0), 2),
            "vel_y":           round(float(p.get("vel_y") or 0.0), 2),
            "vel_z":           round(float(p.get("vel_z") or 0.0), 2),
            "pitch":           p.get("pitch"),
            "yaw":             p.get("yaw"),
            "roll":            p.get("roll"),
            "boost_pct":       p.get("boost_pct"),
            "throttle":        p.get("throttle"),
            "steer":           p.get("steer"),
            "is_boosting":     p.get("is_boosting", False),
            "is_powersliding": p.get("is_powersliding", False),
            "is_jumping":      p.get("is_jumping", False),
            "is_dodging":      p.get("is_dodging", False),
            "is_airborne":     p.get("is_airborne", False),
            "dist_to_ball":    round(dist_ball, 1),
        }
        all_players_state.append(p_info)

        if dist_ball < min_ball_dist:
            min_ball_dist = dist_ball
            nearest_p = p["player"]

        if p["team"] == 0:
            team0_players.append(p_info)
        elif p["team"] == 1:
            team1_players.append(p_info)

    # ── 3. Roles Tacticos (First Man, Second Man, Third Man) ──────────────────
    def sort_team_roles(team_list: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
        # Ordenar por cercania al balon
        sorted_p = sorted(team_list, key=lambda item: item["dist_to_ball"])
        return {
            "first_man":  sorted_p[0]["name"] if len(sorted_p) > 0 else None,
            "second_man": sorted_p[1]["name"] if len(sorted_p) > 1 else None,
            "third_man":  sorted_p[2]["name"] if len(sorted_p) > 2 else (sorted_p[-1]["name"] if len(sorted_p) > 0 else None),
        }

    t0_roles = sort_team_roles(team0_players)
    t1_roles = sort_team_roles(team1_players)

    # ── 4. Team Possession & Nearest Player ───────────────────────────────────
    possession_team = None
    if nearest_p:
        # Encontrar equipo del nearest_player
        for p in all_players_state:
            if p["name"] == nearest_p:
                possession_team = p["team"]
                break

    if min_ball_dist > 3500.0:
        possession_team = None  # Balon neutral desatendido

    # ── 5. Boost Distribution ─────────────────────────────────────────────────
    def calc_boost_stats(team_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        boosts = [p["boost_pct"] for p in team_list if p["boost_pct"] is not None]
        if not boosts:
            return {"avg_boost": 0.0, "total_boost": 0.0, "low_boost_players": 0}
        avg_b = sum(boosts) / len(boosts)
        low_b = sum(1 for b in boosts if b < 20.0)
        return {
            "avg_boost":         round(avg_b, 1),
            "total_boost":       round(sum(boosts), 1),
            "low_boost_players": low_b,
        }

    b0 = calc_boost_stats(team0_players)
    b1 = calc_boost_stats(team1_players)

    # ── 6. Open Net Detection ─────────────────────────────────────────────────
    # Arco Azul (Team 0, y = -5120): abierto si el balón está en su campo (by < -1000)
    # y NINGÚN defensor de Team 0 está detrás del balón (py < by).
    # Arco Naranja (Team 1, y = +5120): abierto si el balón está en su campo (by > 1000)
    # y NINGÚN defensor de Team 1 está detrás del balón (py > by).

    open_net_info = {"is_open": False, "target_team": None, "reason": None}

    if ball_state:
        # Check Team 0 (Blue) defense
        if by < -500.0:
            defenders = [p for p in team0_players if p["pos_y"] < by]
            if len(defenders) == 0:
                open_net_info = {
                    "is_open": True,
                    "target_team": 0,
                    "reason": f"Arco Azul desprotegido — 0 defensores detras del balon (by={by:.0f})"
                }
        # Check Team 1 (Orange) defense
        elif by > 500.0:
            defenders = [p for p in team1_players if p["pos_y"] > by]
            if len(defenders) == 0:
                open_net_info = {
                    "is_open": True,
                    "target_team": 1,
                    "reason": f"Arco Naranja desprotegido — 0 defensores detras del balon (by={by:.0f})"
                }

    # ── 7. Pressure & Danger Level (0–100) ────────────────────────────────────
    # Danger Level Team 0 (Blue Goal):
    # Peligro alto si la pelota está cerca de y = -5120, alta vel_y hacia el arco (< 0),
    # y pocos defensores.
    dist_blue_goal = distance_3d(bx, by, bz, 0.0, BLUE_GOAL_Y, 0.0) if ball_state else 99999.0
    dist_orange_goal = distance_3d(bx, by, bz, 0.0, ORANGE_GOAL_Y, 0.0) if ball_state else 99999.0

    b_vy = ball_state["vel_y"] if ball_state else 0.0

    # Danger 0 (Blue)
    danger0 = max(0.0, min(100.0, (5000.0 - dist_blue_goal) / 45.0 + (-b_vy / 30.0)))
    if open_net_info["is_open"] and open_net_info["target_team"] == 0:
        danger0 = min(100.0, danger0 + 35.0)

    # Danger 1 (Orange)
    danger1 = max(0.0, min(100.0, (5000.0 - dist_orange_goal) / 45.0 + (b_vy / 30.0)))
    if open_net_info["is_open"] and open_net_info["target_team"] == 1:
        danger1 = min(100.0, danger1 + 35.0)

    # Pressure (Presión en el campo rival)
    # Team 0 presionando en campo Naranja (by > 0)
    pressure_on_team1 = max(0.0, min(100.0, (by / 50.0) + (len(team0_players) * 10.0)))
    # Team 1 presionando en campo Azul (by < 0)
    pressure_on_team0 = max(0.0, min(100.0, (-by / 50.0) + (len(team1_players) * 10.0)))

    # ── 8. Ensamblar GameState ────────────────────────────────────────────────
    return {
        "frame_idx":       frame_idx,
        "time":            round(time_sec, 4),
        "ball":            ball_state,
        "players":         all_players_state,
        "team_possession": possession_team,
        "nearest_player":  {
            "name":       nearest_p,
            "distance_u": round(min_ball_dist, 1) if nearest_p else None
        },
        "tactical_roles": {
            "team0": t0_roles,
            "team1": t1_roles,
        },
        "boost_distribution": {
            "team0": b0,
            "team1": b1,
        },
        "open_net": open_net_info,
        "pressure": {
            "on_team0_blue":   round(pressure_on_team0, 1),
            "on_team1_orange": round(pressure_on_team1, 1),
        },
        "danger_level": {
            "team0_blue_goal":   round(danger0, 1),
            "team1_orange_goal": round(danger1, 1),
        }
    }
