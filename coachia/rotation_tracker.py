"""
coachia/rotation_tracker.py
===========================
Rastreador continuo de Rotaciones y Detector de Errores del Tercer Hombre (3rd Man Errors).
Consciente del Contexto de Modo de Juego (GameContext & GameCapabilities):
  - 1v1: No hay 2nd man ni 3rd man (Rol = solo_player). Errores 3rd man = NOT_APPLICABLE.
  - 2v2: 1st man y 2nd man activos. Errores 3rd man = NOT_APPLICABLE.
  - 3v3: Habilita 1st man, 2nd man, 3rd man y Third Man Challenge Errors.
"""

import math
from typing import Dict, Any, List, Optional
from game_context import GameContext


def analyze_rotations(game_states: List[Dict[str, Any]], game_context: Optional[GameContext] = None) -> tuple:
    """
    Recorre los GameStates, asigna los roles frame a frame y detecta los errores de rotación.
    Returns: (status_str, rotation_errors, player_rotation_stats)
    """
    can_3rd = game_context.capabilities.can_third_man if game_context else True
    can_2nd = game_context.capabilities.can_second_man if game_context else True

    status_str = "OK" if can_3rd else "NOT_APPLICABLE"
    rotation_errors = []
    player_stats = {}
    last_error_frame = {0: -999, 1: -999}

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
            if not team_p_list:
                continue

            sorted_team = sorted(team_p_list, key=lambda p: p["dist_to_ball"])

            for idx, p in enumerate(sorted_team):
                pname = p["name"]
                if pname not in player_stats:
                    player_stats[pname] = {
                        "name":              pname,
                        "team":              team_idx,
                        "first_man_frames":  0,
                        "second_man_frames": 0,
                        "third_man_frames":  0,
                        "total_frames":      0,
                        "third_man_errors":  0,
                    }

                ps = player_stats[pname]
                ps["total_frames"] += 1

                # Asignación de roles según capacidades del modo
                if not can_2nd and not can_3rd:
                    p["tactical_role"] = "solo_player"
                    ps["first_man_frames"] += 1
                elif not can_3rd:
                    if idx == 0:
                        ps["first_man_frames"] += 1
                        p["tactical_role"] = "first_man"
                    else:
                        ps["second_man_frames"] += 1
                        p["tactical_role"] = "second_man"
                else:
                    if idx == 0:
                        ps["first_man_frames"] += 1
                        p["tactical_role"] = "first_man"
                    elif idx == 1:
                        ps["second_man_frames"] += 1
                        p["tactical_role"] = "second_man"
                    else:
                        ps["third_man_frames"] += 1
                        p["tactical_role"] = "third_man"

            # ── DETECCION DE ERROR DEL 3ER HOMBRE (Solo en 3v3) ────────────────
            if can_3rd and len(sorted_team) >= 3:
                third_man = sorted_team[-1]
                pname_3rd = third_man["name"]
                dist_3rd  = third_man["dist_to_ball"]

                is_jumping = third_man.get("is_jumping", False)
                is_dodging = third_man.get("is_dodging", False)

                is_in_play_zone = (team_idx == 0 and by > -2000.0) or (team_idx == 1 and by < 2000.0)
                is_risky_distance = (1000.0 <= dist_3rd <= 3200.0)
                is_diving = (is_jumping or is_dodging)

                if team_idx == 0:
                    has_cover = any(p["pos_y"] < third_man["pos_y"] - 300.0 for p in team_p_list if p["name"] != pname_3rd)
                else:
                    has_cover = any(p["pos_y"] > third_man["pos_y"] + 300.0 for p in team_p_list if p["name"] != pname_3rd)

                if is_in_play_zone and is_risky_distance and is_diving and not has_cover:
                    if (fi - last_error_frame[team_idx]) > 90:
                        last_error_frame[team_idx] = fi
                        player_stats[pname_3rd]["third_man_errors"] += 1
                        tname = "Azul (Team 0)" if team_idx == 0 else "Naranja (Team 1)"

                        rotation_errors.append({
                            "frame":         fi,
                            "time":          t,
                            "type":          "THIRD_MAN_CHALLENGE_ERROR",
                            "team":          team_idx,
                            "team_name":     tname,
                            "player":        pname_3rd,
                            "dist_to_ball":  dist_3rd,
                            "details":       f"Error de rotación: {pname_3rd} siendo 3er hombre (último defensor) salta a disputar a {dist_3rd:.0f}uu sin cobertura trasera"
                        })

    for pname, ps in player_stats.items():
        tot = ps["total_frames"]
        if tot > 0:
            ps["pct_first_man"]  = round((ps["first_man_frames"] / tot) * 100.0, 1)
            ps["pct_second_man"] = round((ps["second_man_frames"] / tot) * 100.0, 1)
            ps["pct_third_man"]  = round((ps["third_man_frames"] / tot) * 100.0, 1)
        else:
            ps["pct_first_man"]  = 0.0
            ps["pct_second_man"] = 0.0
            ps["pct_third_man"]  = 0.0

    return status_str, rotation_errors, list(player_stats.values())
