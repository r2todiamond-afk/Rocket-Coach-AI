"""
coachia/overcommit_detector.py
==============================
Detector táctico de Overcommit (Compromiso Excesivo / Desprotección Total del Arco).

Condiciones de Overcommit:
  1. Contexto Ofensivo: El balón está en campo rival (y > 500 para Azul, y < -500 para Naranja).
  2. Puso de Avanzada Completa (All-In Push): Todos los jugadores del equipo están adelantados (y > -1000 para Azul, y < 1000 para Naranja).
  3. Ausencia de Cobertura (Last Man Overcommit): Ningún jugador permanece en la zona de seguridad defensiva (y < -1500 para Azul, y > 1500 para Naranja).
  4. Movimiento hacia adelante: El último hombre se compromete hacia el ataque (vy > 150 u/s) en lugar de mantener rotación.

Salida:
  - Evento de Overcommit con el jugador que cometió el overcommit (último hombre en arrojarse), el contexto y la severidad.
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


def detect_overcommits(game_states: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Analiza la secuencia completa de GameState e identifica situaciones tácticas de Overcommit.
    """
    overcommits = []

    last_overcommit_frame = {0: -999, 1: -999}

    for fi, gs in enumerate(game_states):
        t = gs["time"]
        ball = gs.get("ball")
        players = gs.get("players", [])

        if not ball or ball.get("pos_x") is None:
            continue

        by = ball["pos_y"]

        team0_players = [p for p in players if p["team"] == 0]
        team1_players = [p for p in players if p["team"] == 1]

        # ── 1. Evaluar Overcommit del Equipo 0 (Azul) ───────────────────────
        # Contexto: Pelota en campo Naranja (by > 500)
        if by > 500.0 and len(team0_players) >= 2:
            # Verificar si NINGUNO está en zona de seguridad defensiva (y < -1500)
            defenders_in_back = [p for p in team0_players if p["pos_y"] < -1500.0]
            if len(defenders_in_back) == 0:
                # Todos están adelantados (y > -1000)
                all_forward = all(p["pos_y"] > -1000.0 for p in team0_players)
                if all_forward:
                    # Identificar quién es el último hombre que debió quedarse a cubrir (el más cercano a su arco pero avanzando)
                    sorted_t0 = sorted(team0_players, key=lambda p: p["pos_y"])
                    last_man = sorted_t0[0]  # El más cercano al arco azul entre los adelantados

                    if last_man["vel_y"] > 150.0 and (fi - last_overcommit_frame[0]) > 90:
                        last_overcommit_frame[0] = fi
                        other_tms = [p for p in team0_players if p["name"] != last_man["name"]]
                        d_ball = last_man.get("dist_to_ball")
                        b_pct = last_man.get("boost_pct")
                        overcommits.append({
                            "frame":                fi,
                            "time":                 t,
                            "team":                 0,
                            "team_name":            "Azul (Team 0)",
                            "overcommitting_player": last_man["name"],
                            "ball_x":               safe_round(ball.get("pos_x"), 1, 0.0),
                            "ball_y":               safe_round(by, 1, 0.0),
                            "ball_z":               safe_round(ball.get("pos_z"), 1, 92.75),
                            "ball_vel_x":           safe_round(ball.get("vel_x"), 1, 0.0),
                            "ball_vel_y":           safe_round(ball.get("vel_y"), 1, 0.0),
                            "ball_vel_z":           safe_round(ball.get("vel_z"), 1, 0.0),
                            "last_man_x":           safe_round(last_man.get("pos_x"), 1, 0.0),
                            "last_man_y":           safe_round(last_man.get("pos_y"), 1, 0.0),
                            "last_man_z":           safe_round(last_man.get("pos_z"), 1, 17.0),
                            "last_man_vel_x":       safe_round(last_man.get("vel_x"), 1, 0.0),
                            "last_man_vel_y":       safe_round(last_man.get("vel_y"), 1, 0.0),
                            "last_man_vel_z":       safe_round(last_man.get("vel_z"), 1, 0.0),
                            "last_man_boost":       safe_round(b_pct, 1, 33.3),
                            "dist_to_ball":         safe_round(d_ball, 1, 1500.0),
                            "other_teammates":      [p["name"] for p in other_tms],
                            "teammates_positions":  [
                                {"name": p["name"], "pos_x": safe_round(p.get("pos_x"), 1, 0.0), "pos_y": safe_round(p.get("pos_y"), 1, 0.0), "pos_z": safe_round(p.get("pos_z"), 1, 17.0)}
                                for p in other_tms
                            ],
                            "details":              f"Overcommit de {last_man['name']}: avanza al ataque (vy={safe_round(last_man.get('vel_y'), 0, 0.0):.0f}) sin cobertura defensiva atrás"
                        })

        # ── 2. Evaluar Overcommit del Equipo 1 (Naranja) ────────────────────
        # Contexto: Pelota en campo Azul (by < -500)
        if by < -500.0 and len(team1_players) >= 2:
            defenders_in_back = [p for p in team1_players if p["pos_y"] > 1500.0]
            if len(defenders_in_back) == 0:
                all_forward = all(p["pos_y"] < 1000.0 for p in team1_players)
                if all_forward:
                    sorted_t1 = sorted(team1_players, key=lambda p: p["pos_y"], reverse=True)
                    last_man = sorted_t1[0]  # El más cercano al arco naranja entre los adelantados

                    if last_man["vel_y"] < -150.0 and (fi - last_overcommit_frame[1]) > 90:
                        last_overcommit_frame[1] = fi
                        other_tms = [p for p in team1_players if p["name"] != last_man["name"]]
                        d_ball = last_man.get("dist_to_ball")
                        b_pct = last_man.get("boost_pct")
                        overcommits.append({
                            "frame":                fi,
                            "time":                 t,
                            "team":                 1,
                            "team_name":            "Naranja (Team 1)",
                            "overcommitting_player": last_man["name"],
                            "ball_x":               safe_round(ball.get("pos_x"), 1, 0.0),
                            "ball_y":               safe_round(by, 1, 0.0),
                            "ball_z":               safe_round(ball.get("pos_z"), 1, 92.75),
                            "ball_vel_x":           safe_round(ball.get("vel_x"), 1, 0.0),
                            "ball_vel_y":           safe_round(ball.get("vel_y"), 1, 0.0),
                            "ball_vel_z":           safe_round(ball.get("vel_z"), 1, 0.0),
                            "last_man_x":           safe_round(last_man.get("pos_x"), 1, 0.0),
                            "last_man_y":           safe_round(last_man.get("pos_y"), 1, 0.0),
                            "last_man_z":           safe_round(last_man.get("pos_z"), 1, 17.0),
                            "last_man_vel_x":       safe_round(last_man.get("vel_x"), 1, 0.0),
                            "last_man_vel_y":       safe_round(last_man.get("vel_y"), 1, 0.0),
                            "last_man_vel_z":       safe_round(last_man.get("vel_z"), 1, 0.0),
                            "last_man_boost":       safe_round(b_pct, 1, 33.3),
                            "dist_to_ball":         safe_round(d_ball, 1, 1500.0),
                            "other_teammates":      [p["name"] for p in other_tms],
                            "teammates_positions":  [
                                {"name": p["name"], "pos_x": safe_round(p.get("pos_x"), 1, 0.0), "pos_y": safe_round(p.get("pos_y"), 1, 0.0), "pos_z": safe_round(p.get("pos_z"), 1, 17.0)}
                                for p in other_tms
                            ],
                            "details":              f"Overcommit de {last_man['name']}: avanza al ataque (vy={safe_round(last_man.get('vel_y'), 0, 0.0):.0f}) sin cobertura defensiva atrás"
                        })

    return overcommits
