"""
coachia/challenge_detector.py
=============================
Detector avanzado de Challenges, 50/50s y Fake Challenges (Bait / Shadow).

Fake Challenge (Máquina de Estados 4 Fases):
  Fase 1: Aproximación Agresiva (Acelera hacia la pelota, v_towards > 250 u/s, ETA <= 1.0s, dist <= 1400 uu)
  Fase 2: Deceleración y Giro (En 5-25 frames siguientes: v_towards cae < 50 u/s y el auto gira > 45°)
  Fase 3: Sin Contacto (El jugador NUNCA toca la pelota durante la maniobra, dist_min > 150 uu)
  Fase 4: Reacción Rival (El rival de equipo opuesto realiza un Touch/Clear/Shot engañado por la finta)
"""

import math
from typing import Dict, Any, List, Optional


def dot_product_3d(v1: tuple, v2: tuple) -> float:
    return v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]


def compute_player_eta(player: Dict[str, Any], ball: Dict[str, Any]) -> tuple:
    """
    Calcula el tiempo estimado de llegada (ETA) y la velocidad del jugador hacia el balón.
    Returns: (eta_sec, v_towards, dir_unit_tuple, dist_u)
    """
    px, py, pz = player["pos_x"], player["pos_y"], player["pos_z"]
    vx, vy, vz = player["vel_x"], player["vel_y"], player["vel_z"]

    bx, by, bz = ball["pos_x"], ball["pos_y"], ball["pos_z"]

    dx = bx - px
    dy = by - py
    dz = bz - pz

    dist = math.sqrt(dx*dx + dy*dy + dz*dz)
    if dist < 1.0:
        return 0.0, 0.0, (0.0, 0.0, 0.0), dist

    ux, uy, uz = dx / dist, dy / dist, dz / dist
    u_vec = (ux, uy, uz)

    v_towards = vx * ux + vy * uy + vz * uz

    if v_towards > 50.0:
        eta = dist / v_towards
    else:
        eta = 999.0

    return round(eta, 3), round(v_towards, 1), u_vec, round(dist, 1)


def detect_challenges(game_states: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Analiza la secuencia completa de GameState e identifica Challenges, 50/50s y Fake Challenges.
    """
    challenges = []
    num_frames = len(game_states)

    last_challenge_frame = -99

    # Rastrear posibles fakes por jugador
    # player_name -> {"start_frame", "start_time", "team", "min_dist"}
    potential_fakes = {}

    for fi, gs in enumerate(game_states):
        t = gs["time"]
        ball = gs.get("ball")
        players = gs.get("players", [])

        if not ball or ball.get("pos_x") is None:
            continue

        team0_players = [p for p in players if p["team"] == 0]
        team1_players = [p for p in players if p["team"] == 1]

        if not team0_players or not team1_players:
            continue

        # ── 1. EVALUAR FAKE CHALLENGES EN CURSO (Fase 2, 3 y 4) ───────────────
        for p in players:
            pname = p["name"]
            eta, v_towards, u_vec, dist = compute_player_eta(p, ball)

            # Fase 1: Iniciar monitoreo si se aproxima agresivamente
            if dist < 1400.0 and eta <= 1.0 and v_towards > 250.0:
                if pname not in potential_fakes:
                    potential_fakes[pname] = {
                        "start_frame": fi,
                        "start_time":  t,
                        "team":        p["team"],
                        "min_dist":    dist,
                        "initial_yaw": p.get("yaw", 0.0),
                        "aborted":     False,
                        "abort_frame": None,
                    }

            # Si ya está siendo monitoreado como Fake Candidate
            if pname in potential_fakes:
                pfdata = potential_fakes[pname]
                elapsed_f = fi - pfdata["start_frame"]

                if dist < pfdata["min_dist"]:
                    pfdata["min_dist"] = dist

                # Si tocó el balón o estuvo demasiado cerca (< 140uu), NO fue Fake
                if dist < 140.0:
                    del potential_fakes[pname]
                    continue

                # Fase 2: Deceleración y giro (Abort)
                if elapsed_f >= 4 and not pfdata["aborted"]:
                    yaw_diff = abs((p.get("yaw", 0.0) or 0.0) - (pfdata["initial_yaw"] or 0.0))
                    if yaw_diff > 180.0:
                        yaw_diff = 360.0 - yaw_diff

                    if v_towards < 80.0 or yaw_diff > 40.0 or p.get("is_powersliding"):
                        pfdata["aborted"] = True
                        pfdata["abort_frame"] = fi

                # Fase 4: Reacción Rival (Rival despeja / toca en los 25 frames siguientes al abort)
                if pfdata["aborted"] and (fi - pfdata["abort_frame"]) <= 25:
                    opp_team = 1 if pfdata["team"] == 0 else 0
                    opp_touch = any(op["dist_to_ball"] < 160.0 for op in players if op["team"] == opp_team)

                    if opp_touch:
                        # ¡Fake Challenge Confirmado!
                        opp_player = next((op["name"] for op in players if op["team"] == opp_team and op["dist_to_ball"] < 160.0), "Rival")
                        challenges.append({
                            "frame":               pfdata["start_frame"],
                            "time":                pfdata["start_time"],
                            "type":                "FAKE_CHALLENGE",
                            "player":              pname,
                            "team":                pfdata["team"],
                            "baited_opponent":     opp_player,
                            "closest_approach_u":  round(pfdata["min_dist"], 1),
                            "details":             f"Finta exitosa de {pname} sobre {opp_player} (Freno/Gira a {pfdata['min_dist']:.0f}uu sin contacto)"
                        })
                        del potential_fakes[pname]
                        continue

                # Expiración si pasaron más de 35 frames sin confirmación
                if elapsed_f > 35:
                    del potential_fakes[pname]

        # ── 2. EVALUAR CHALLENGES Y 50/50s ────────────────────────────────────
        for p0 in team0_players:
            eta0, v_tow0, u0, dist0 = compute_player_eta(p0, ball)

            for p1 in team1_players:
                eta1, v_tow1, u1, dist1 = compute_player_eta(p1, ball)

                if dist0 > 1200.0 or dist1 > 1200.0:
                    continue
                if v_tow0 < 150.0 or v_tow1 < 150.0:
                    continue
                if eta0 > 1.2 or eta1 > 1.2:
                    continue

                eta_diff = abs(eta0 - eta1)
                if eta_diff > 0.35:
                    continue

                dot_u = dot_product_3d(u0, u1)
                if dot_u > -0.30:
                    continue

                approach_angle_deg = round(math.degrees(math.acos(max(-1.0, min(1.0, dot_u)))), 1)

                if (fi - last_challenge_frame) < 20:
                    continue

                last_challenge_frame = fi

                ch_type = "50_50"
                if eta_diff > 0.20:
                    ch_type = "LATE_CHALLENGE"

                future_fi = min(num_frames - 1, fi + 12)
                future_gs = game_states[future_fi]
                future_ball = future_gs.get("ball")

                winner_team = None
                outcome_desc = "SIMULTANEOUS_IMPACT"

                if future_ball and future_ball.get("vel_y") is not None:
                    fut_vy = future_ball["vel_y"]
                    if fut_vy > 250.0:
                        winner_team = 0
                        outcome_desc = f"TEAM_0_WON ({p0['name']})"
                    elif fut_vy < -250.0:
                        winner_team = 1
                        outcome_desc = f"TEAM_1_WON ({p1['name']})"

                challenges.append({
                    "frame":              fi,
                    "time":               t,
                    "type":               ch_type,
                    "player_blue":        p0["name"],
                    "player_orange":      p1["name"],
                    "eta_blue_sec":       eta0,
                    "eta_orange_sec":     eta1,
                    "eta_diff_sec":       round(eta_diff, 3),
                    "dist_blue_u":        dist0,
                    "dist_orange_u":      dist1,
                    "approach_angle_deg": approach_angle_deg,
                    "winner_team":        winner_team,
                    "outcome":            outcome_desc,
                })

    return sorted(challenges, key=lambda item: item["frame"])
