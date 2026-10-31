"""
coachia/events_detector.py
==========================
Detector dinamico de eventos basicos a partir de la secuencia de GameState:

  1. Touch: Coche-balon <= 160 uu + cambio de velocidad / cercania minima
  2. Shot:  Touch + trayectoria predicha en arco rival (x in [-1050, 1050], z in [0, 750])
  3. Save:  Shot activo en arco propio + Touch de defensor que desvia la trayectoria del arco
  4. Pass:  Touch de Jugador A + Touch posterior de Jugador B (mismo equipo) sin toques rivales
  5. Clear: Touch en tercio defensivo + balon sale de zona defensiva/cruza mitad de cancha
"""

import math
from typing import Dict, Any, List, Optional


BLUE_GOAL_Y   = -5120.0
ORANGE_GOAL_Y =  5120.0
GOAL_X_BOUND  =  1050.0  # tolerancia un poco mayor que 896 para postes
GOAL_Z_BOUND  =   750.0
GRAVITY_Z     =   650.0  # u/s^2 gravedad RL


def is_ball_on_target(b_pos: Dict[str, float], b_vel: Dict[str, float], target_team_goal: int) -> bool:
    """
    Evalua si la trayectoria actual de la pelota esta dirigida hacia la porteria objetivo:
      target_team_goal = 0 -> Porteria Azul (y = -5120)
      target_team_goal = 1 -> Porteria Naranja (y = +5120)
    """
    if not b_pos or not b_vel:
        return False

    bx, by, bz = b_pos["pos_x"], b_pos["pos_y"], b_pos["pos_z"]
    vx, vy, vz = b_vel["vel_x"], b_vel["vel_y"], b_vel["vel_z"]

    speed = math.sqrt(vx*vx + vy*vy + vz*vz)
    if speed < 200.0:  # tiro requiere velocidad minima
        return False

    if target_team_goal == 0:
        # Tiro hacia porteria Azul (y = -5120) -> vy debe ser negativo
        if vy >= -150.0:
            return False
        t_impact = (BLUE_GOAL_Y - by) / vy
        if t_impact <= 0 or t_impact > 5.0:
            return False
    else:
        # Tiro hacia porteria Naranja (y = +5120) -> vy debe ser positivo
        if vy <= 150.0:
            return False
        t_impact = (ORANGE_GOAL_Y - by) / vy
        if t_impact <= 0 or t_impact > 5.0:
            return False

    # Prediccion de coordenadas de impacto en el plano del arco
    x_impact = bx + vx * t_impact
    z_impact = bz + vz * t_impact - 0.5 * GRAVITY_Z * (t_impact ** 2)

    return (abs(x_impact) <= GOAL_X_BOUND) and (0.0 <= z_impact <= GOAL_Z_BOUND)


def detect_basic_events(game_states: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Recorre la secuencia completa de GameState e identifica toques, disparos, atajadas, pases y despejes.
    """
    events = []

    last_touch_info = None  # {"player": str, "team": int, "frame": int, "time": float}
    active_shot = None      # {"shooter": str, "team": int, "target_goal_team": int, "frame": int, "time": float}
    pending_clear = None    # {"player": str, "team": int, "frame": int, "time": float}

    last_ball_vel = None
    last_touch_frame = -999

    for i, gs in enumerate(game_states):
        fi = gs["frame_idx"]
        t = gs["time"]
        ball = gs.get("ball")
        players = gs.get("players", [])

        if not ball or ball.get("pos_x") is None:
            continue

        bx, by, bz = ball["pos_x"], ball["pos_y"], ball["pos_z"]
        vx, vy, vz = ball["vel_x"], ball["vel_y"], ball["vel_z"]
        curr_vel = {"vel_x": vx, "vel_y": vy, "vel_z": vz}
        previous_ball_vel = last_ball_vel

        # ── 1. DETECCION DE TOUCH (Toque) ────────────────────────────────────
        vel_change = 0.0
        if previous_ball_vel:
            dvx = vx - previous_ball_vel["vel_x"]
            dvy = vy - previous_ball_vel["vel_y"]
            dvz = vz - previous_ball_vel["vel_z"]
            vel_change = math.sqrt(dvx*dvx + dvy*dvy + dvz*dvz)

        last_ball_vel = curr_vel

        # Buscar jugador muy cercano a la pelota
        candidates = [p for p in players if p["dist_to_ball"] <= 160.0]
        current_touch_player = None
        current_touch_team = None

        if candidates and (vel_change > 30.0 or (fi - last_touch_frame) > 8):
            closest_p = min(candidates, key=lambda item: item["dist_to_ball"])
            current_touch_player = closest_p["name"]
            current_touch_team   = closest_p["team"]
            last_touch_frame     = fi

            is_defensive_zone = (current_touch_team == 0 and by < -1800.0) or (current_touch_team == 1 and by > 1800.0)

            # Reclasificación a REDIRECT si hay cambio significativo de trayectoria (>45°) y velocidad post-impacto > 300 u/s
            event_type = "TOUCH"
            if previous_ball_vel:
                v1_mag = math.sqrt(previous_ball_vel["vel_x"]**2 + previous_ball_vel["vel_y"]**2 + previous_ball_vel["vel_z"]**2)
                v2_mag = math.sqrt(vx**2 + vy**2 + vz**2)
                if v1_mag > 100.0 and v2_mag > 300.0:
                    dot = (previous_ball_vel["vel_x"]*vx + previous_ball_vel["vel_y"]*vy + previous_ball_vel["vel_z"]*vz) / (v1_mag * v2_mag)
                    dot_clamped = max(-1.0, min(1.0, dot))
                    angle_deg = math.degrees(math.acos(dot_clamped))
                    if angle_deg > 45.0:
                        event_type = "REDIRECT"

            events.append({
                "frame":      fi,
                "time":       t,
                "type":       event_type,
                "player":     current_touch_player,
                "team":       current_touch_team,
                "distance_u": closest_p["dist_to_ball"],
                "vel_change": round(vel_change, 1)
            })

            # ── 4. DETECCION DE PASS (Pase) ──────────────────────────────────
            if last_touch_info and last_touch_info["team"] == current_touch_team:
                if last_touch_info["player"] != current_touch_player and (fi - last_touch_info["frame"]) < 150:
                    events.append({
                        "frame":    fi,
                        "time":     t,
                        "type":     "PASS",
                        "passer":   last_touch_info["player"],
                        "receiver": current_touch_player,
                        "team":     current_touch_team,
                    })

            # ── 3. DETECCION DE SAVE (Atajada / Parada) ───────────────────────
            if active_shot and active_shot["target_goal_team"] == current_touch_team:
                # El defensor toco la pelota durante un disparo al arco propio
                if not is_ball_on_target(ball, curr_vel, current_touch_team):
                    events.append({
                        "frame":   fi,
                        "time":    t,
                        "type":    "SAVE",
                        "saver":   current_touch_player,
                        "shooter": active_shot["shooter"],
                        "team":    current_touch_team,
                    })
                    active_shot = None

            # Registrar pendiente de CLEAR si el toque es defensivo
            if is_defensive_zone:
                pending_clear = {
                    "player": current_touch_player,
                    "team":   current_touch_team,
                    "frame":  fi,
                    "time":   t
                }

            last_touch_info = {
                "player": current_touch_player,
                "team":   current_touch_team,
                "frame":  fi,
                "time":   t,
                "is_defensive": is_defensive_zone
            }

        # ── 2. DETECCION DE SHOT (Disparo a Portería) ─────────────────────────
        if current_touch_player:
            target_goal = 1 if current_touch_team == 0 else 0
            if is_ball_on_target(ball, curr_vel, target_goal):
                active_shot = {
                    "shooter":          current_touch_player,
                    "team":             current_touch_team,
                    "target_goal_team": target_goal,
                    "frame":            fi,
                    "time":             t
                }
                events.append({
                    "frame":       fi,
                    "time":        t,
                    "type":        "SHOT",
                    "shooter":     current_touch_player,
                    "team":        current_touch_team,
                    "target_goal": target_goal,
                    "speed":       ball["speed"]
                })

        # Cancelar active_shot si transcurren mas de 150 frames desatendido
        if active_shot and (fi - active_shot["frame"]) > 150:
            active_shot = None

        # ── 5. DETECCION DE CLEAR (Despeje Completo) ──────────────────────────
        if pending_clear:
            c_team = pending_clear["team"]
            cleared_out = (c_team == 0 and by > -1000.0) or (c_team == 1 and by < 1000.0)
            if cleared_out:
                events.append({
                    "frame":   fi,
                    "time":    t,
                    "type":    "CLEAR",
                    "player":  pending_clear["player"],
                    "team":    c_team,
                })
                pending_clear = None
            elif (fi - pending_clear["frame"]) > 180:
                pending_clear = None

    return events
