"""
coachia/double_commit_detector.py
=================================
Detector táctico de Double Commit entre compañeros.
Utiliza itertools.combinations(team, 2) para garantizar matemática pura:
  - 1v1: Comb(1, 2) = 0 pares (Imposible self-comparison o falso positivo)
  - 2v2: Comb(2, 2) = 1 par único
  - 3v3: Comb(3, 2) = 3 pares únicos

Si el modo de juego es 1v1 (team_size = 1), el detector retorna NOT_APPLICABLE.
"""

import math
from itertools import combinations
from typing import Dict, Any, List, Optional
from game_context import GameContext


def safe_round(val: Any, decimals: int = 1, default: float = 0.0) -> float:
    if val is None:
        return round(float(default), decimals)
    try:
        return round(float(val), decimals)
    except (ValueError, TypeError):
        return round(float(default), decimals)


def compute_player_eta(player: Dict[str, Any], ball: Dict[str, Any]) -> tuple:
    px, py, pz = player["pos_x"], player["pos_y"], player["pos_z"]
    vx, vy, vz = player["vel_x"], player["vel_y"], player["vel_z"]

    bx, by, bz = ball["pos_x"], ball["pos_y"], ball["pos_z"]

    dx = bx - px
    dy = by - py
    dz = bz - pz

    dist = math.sqrt(dx*dx + dy*dy + dz*dz)
    if dist < 1.0:
        return 0.0, 0.0, dist

    ux, uy, uz = dx / dist, dy / dist, dz / dist
    v_towards = vx * ux + vy * uy + vz * uz

    if v_towards > 50.0:
        eta = dist / v_towards
    else:
        eta = 999.0

    return round(eta, 3), round(v_towards, 1), round(dist, 1)


def detect_double_commits(game_states: List[Dict[str, Any]], game_context: Optional[GameContext] = None) -> tuple:
    """
    Analiza la secuencia completa de GameState e identifica errores tácticos de Double Commit entre compañeros.
    Returns: (status_str, double_commits_list)
      - status_str: "OK" o "NOT_APPLICABLE"
    """
    # ── VALIDACION DE CAPACIDADES POR MODO DE JUEGO ─────────────────────────
    if game_context and not game_context.capabilities.can_double_commit:
        return "NOT_APPLICABLE", []

    double_commits = []
    last_dc_frame = {0: -999, 1: -999}

    for fi, gs in enumerate(game_states):
        t = gs["time"]
        ball = gs.get("ball")
        players = gs.get("players", [])

        if not ball or ball.get("pos_x") is None:
            continue

        by = ball["pos_y"]

        team0_players = [p for p in players if p["team"] == 0]
        team1_players = [p for p in players if p["team"] == 1]

        for team_idx, team_p_list in [(0, team0_players), (1, team1_players)]:
            # itertools.combinations(team_p_list, 2):
            # En 1v1 produce 0 iteraciones (matemáticamente limpio)
            for p1, p2 in combinations(team_p_list, 2):
                eta1, v_tow1, dist1 = compute_player_eta(p1, ball)
                eta2, v_tow2, dist2 = compute_player_eta(p2, ball)

                if dist1 > 1200.0 or dist2 > 1200.0:
                    continue
                if v_tow1 < 150.0 or v_tow2 < 150.0:
                    continue
                if eta1 > 1.2 or eta2 > 1.2:
                    continue

                eta_diff = abs(eta1 - eta2)
                if eta_diff > 0.25:
                    continue

                p1_committing = p1.get("is_jumping") or p1.get("is_dodging") or p1.get("is_airborne") or (dist1 < 300.0)
                p2_committing = p2.get("is_jumping") or p2.get("is_dodging") or p2.get("is_airborne") or (dist2 < 300.0)

                if not (p1_committing and p2_committing):
                    continue

                if (fi - last_dc_frame[team_idx]) < 25:
                    continue

                last_dc_frame[team_idx] = fi

                dist_teammates = math.sqrt((p1["pos_x"] - p2["pos_x"])**2 +
                                           (p1["pos_y"] - p2["pos_y"])**2 +
                                           (p1["pos_z"] - p2["pos_z"])**2)

                is_defensive = (team_idx == 0 and by < 0.0) or (team_idx == 1 and by > 0.0)
                context_str = "DEFENSIVE_DOUBLE_COMMIT" if is_defensive else "OFFENSIVE_DOUBLE_COMMIT"
                tname = "Azul (Team 0)" if team_idx == 0 else "Naranja (Team 1)"

                double_commits.append({
                    "frame":                 fi,
                    "time":                  t,
                    "type":                  context_str,
                    "team":                  team_idx,
                    "team_name":             tname,
                    "player1":               p1["name"],
                    "player2":               p2["name"],
                    "eta1_sec":              safe_round(eta1, 2, 0.0),
                    "eta2_sec":              safe_round(eta2, 2, 0.0),
                    "eta_diff_sec":          safe_round(eta_diff, 3, 0.0),
                    "dist_teammates_u":      safe_round(dist_teammates, 1, 0.0),
                    # --- Campos telemétricos 3D ---
                    "ball_x":                safe_round(ball.get("pos_x"), 1, 0.0),
                    "ball_y":                safe_round(by, 1, 0.0),
                    "ball_z":                safe_round(ball.get("pos_z"), 1, 92.75),
                    "ball_vel_x":            safe_round(ball.get("vel_x"), 1, 0.0),
                    "ball_vel_y":            safe_round(ball.get("vel_y"), 1, 0.0),
                    "ball_vel_z":            safe_round(ball.get("vel_z"), 1, 0.0),
                    "player1_pos":           {"pos_x": safe_round(p1.get("pos_x"), 1, 0.0), "pos_y": safe_round(p1.get("pos_y"), 1, 0.0), "pos_z": safe_round(p1.get("pos_z"), 1, 17.0)},
                    "player1_vel":           {"vel_x": safe_round(p1.get("vel_x"), 1, 0.0), "vel_y": safe_round(p1.get("vel_y"), 1, 0.0), "vel_z": safe_round(p1.get("vel_z"), 1, 0.0)},
                    "player1_boost":         safe_round(p1.get("boost_pct"), 1, 33.3),
                    "player2_pos":           {"pos_x": safe_round(p2.get("pos_x"), 1, 0.0), "pos_y": safe_round(p2.get("pos_y"), 1, 0.0), "pos_z": safe_round(p2.get("pos_z"), 1, 17.0)},
                    "player2_vel":           {"vel_x": safe_round(p2.get("vel_x"), 1, 0.0), "vel_y": safe_round(p2.get("vel_y"), 1, 0.0), "vel_z": safe_round(p2.get("vel_z"), 1, 0.0)},
                    "player2_boost":         safe_round(p2.get("boost_pct"), 1, 33.3),
                    "details":               f"Double Commit en {tname}: {p1['name']} y {p2['name']} saltaron/disputaron el balón al mismo tiempo (ETA diff={safe_round(eta_diff, 2, 0.0):.2f}s)"
                })

    return "OK", double_commits
