"""
coachia/shadow_defense.py
=========================
Detector de Shadow Defense (Defensa en Sombra) como estado continuo.

Condiciones para Shadow Defense de un Jugador (Equipo T):
  1. Posicionamiento: Entre el balón y su propia portería (y_player < y_ball para Azul, y_player > y_ball para Naranja).
  2. Alineación: Dentro del cono defensivo (|x_player| <= 2500).
  3. Retroceso Sincronizado: Moviéndose en la misma dirección que el balón hacia su arco (vy_player < -100 u/s para Azul, vy_player > 100 u/s para Naranja).
  4. Distancia Prudencial (Buffer Zone): Mantiene entre 600 uu y 2400 uu de la pelota sin arrojarse.
  5. Duración Mínima: Mantiene esta conducta durante >= 30 frames continuos (>= 1.0s).

Salida:
  - Marca bool `is_shadowing` en cada row de jugador.
  - Genera lista de intervalos `shadow_episodes` con tiempo de inicio, fin y duración.
"""

import math
from typing import Dict, Any, List, Optional


BLUE_GOAL_Y   = -5120.0
ORANGE_GOAL_Y =  5120.0


def detect_shadow_defense(game_states: List[Dict[str, Any]]) -> tuple:
    """
    Evalua la secuencia de GameStates y detecta los estados y episodios de Shadow Defense.
    Returns: (shadow_flags_by_frame_and_player, shadow_episodes)
      - shadow_flags_by_frame_and_player: dict (frame_idx, player_name) -> bool
      - shadow_episodes: lista de dicts de episodios completos de Shadow Defense
    """
    shadow_flags = {}
    episodes = []

    # Rastreador de episodios en curso por jugador:
    # player_name -> {"start_frame", "start_time", "last_frame", "team", "max_dist", "min_dist"}
    active_shadows = {}

    for fi, gs in enumerate(game_states):
        t = gs["time"]
        ball = gs.get("ball")
        players = gs.get("players", [])

        if not ball or ball.get("pos_x") is None:
            continue

        by = ball["pos_y"]
        b_vy = ball.get("vel_y") or 0.0

        current_shadow_players = set()

        for p in players:
            pname = p["name"]
            team = p["team"]
            px, py, pz = p["pos_x"], p["pos_y"], p["pos_z"]
            p_vy = p.get("vel_y") or 0.0
            dist = p["dist_to_ball"]

            # ── 1. Evaluar si cumple criterios instantáneos de Shadow ────────
            is_defensive_position = False
            is_backpedaling       = False

            if team == 0:
                # Equipo Azul (Arco en y = -5120): jugador debe estar detras del balon (py < by)
                is_defensive_position = (py < by - 150.0)
                # Balon se mueve hacia arco azul (b_vy < -50) y jugador retrocede hacia su arco (p_vy < -50)
                is_backpedaling = (b_vy < -50.0 and p_vy < -50.0)
            elif team == 1:
                # Equipo Naranja (Arco en y = +5120): jugador debe estar detras del balon (py > by)
                is_defensive_position = (py > by + 150.0)
                is_backpedaling = (b_vy > 50.0 and p_vy > 50.0)

            # Alineacion en carril defensivo y distancia prudencial (600 a 2400 uu)
            is_in_defensive_lane = (abs(px) <= 2800.0)
            is_valid_distance    = (600.0 <= dist <= 2500.0)

            is_shadowing_now = is_defensive_position and is_backpedaling and is_in_defensive_lane and is_valid_distance

            if is_shadowing_now:
                current_shadow_players.add(pname)
                if pname not in active_shadows:
                    active_shadows[pname] = {
                        "start_frame": fi,
                        "start_time":  t,
                        "last_frame":  fi,
                        "last_time":   t,
                        "team":        team,
                        "min_dist":    dist,
                        "max_dist":    dist,
                    }
                else:
                    st = active_shadows[pname]
                    st["last_frame"] = fi
                    st["last_time"]  = t
                    st["min_dist"]   = min(st["min_dist"], dist)
                    st["max_dist"]   = max(st["max_dist"], dist)

        # ── 2. Cerrar episodios que concluyeron ──────────────────────────────
        for pname in list(active_shadows.keys()):
            st = active_shadows[pname]
            if pname not in current_shadow_players or fi == len(game_states) - 1:
                duration_frames = st["last_frame"] - st["start_frame"] + 1
                duration_sec    = st["last_time"] - st["start_time"]

                # Exigir duracion minima de >= 25 frames (aprox 0.85s) para considerarlo Shadow Defense
                if duration_frames >= 25:
                    episodes.append({
                        "player":       pname,
                        "team":         st["team"],
                        "start_frame":  st["start_frame"],
                        "end_frame":    st["last_frame"],
                        "start_time":   round(st["start_time"], 2),
                        "end_time":     round(st["last_time"], 2),
                        "duration_sec": round(duration_sec, 2),
                        "min_distance": round(st["min_dist"], 1),
                        "max_distance": round(st["max_dist"], 1),
                    })

                    # Marcar flag boolean is_shadowing en todos los frames del episodio
                    for frame_i in range(st["start_frame"], st["last_frame"] + 1):
                        shadow_flags[(frame_i, pname)] = True

                del active_shadows[pname]

    return shadow_flags, sorted(episodes, key=lambda item: item["start_frame"])
