"""
coachia/recovery_detector.py
============================
Detector y Evaluador de Recuperaciones (Recoveries & Landing Ratings).

Calcula para cada evento de despegue/impacto aéreo:
  1. Tiempo de Aterrizaje (Landing Time): Tiempo transcurrido hasta tocar tierra con las 4 ruedas.
  2. Calidad de Aterrizaje: Alineación de Pitch y Roll al tocar suelo (Limpio vs Torpe).
  3. Tiempo a Supersónico (Time to Supersonic): Tiempo transcurrido hasta alcanzar v >= 2150 u/s.
  4. Nota / Calificación de Recuperación (Recovery Rating):
     - EXCELENTE (<= 0.85s, Aterrizaje limpio en 4 ruedas)
     - BUENO (0.85s < t <= 1.40s)
     - LENTO (1.40s < t <= 2.20s)
     - FALLIDO / MAL_ATERRISAJE (> 2.20s o choque torpe)
"""

import math
from typing import Dict, Any, List, Optional


def analyze_recoveries(game_states: List[Dict[str, Any]]) -> tuple:
    """
    Analiza las maniobras aéreas, despegues y caídas e identifica los tiempos y calificaciones de recuperación.
    Returns: (recovery_events, player_recovery_stats)
    """
    recovery_events = []
    num_frames = len(game_states)

    # Rastrear episodios de vuelo por jugador:
    # player_name -> {"start_frame", "start_time", "max_height", "peak_pitch", "peak_roll"}
    airborne_tracker = {}

    # player_name -> list of recovery dicts
    player_recoveries = {}

    for fi, gs in enumerate(game_states):
        t = gs["time"]
        players = gs.get("players", [])

        for p in players:
            pname = p["name"]
            team = p["team"]
            pz = p["pos_x"], p["pos_y"], p["pos_z"]
            z = p["pos_z"]
            vx, vy, vz = p["vel_x"], p["vel_y"], p["vel_z"]
            speed = math.sqrt(vx*vx + vy*vy + vz*vz)
            is_air = p.get("is_airborne", False) or z > 40.0

            pitch = abs(p.get("pitch") or 0.0)
            roll = abs(p.get("roll") or 0.0)

            if pname not in player_recoveries:
                player_recoveries[pname] = []

            # ── 1. INICIO DE VUELO / CAIDA ───────────────────────────────────
            if is_air and pname not in airborne_tracker:
                airborne_tracker[pname] = {
                    "start_frame": fi,
                    "start_time":  t,
                    "max_height":   z,
                    "team":        team,
                }
            elif is_air and pname in airborne_tracker:
                airborne_tracker[pname]["max_height"] = max(airborne_tracker[pname]["max_height"], z)

            # ── 2. ATERRIZAJE Y RECUPERACION ─────────────────────────────────
            elif not is_air and pname in airborne_tracker:
                ab = airborne_tracker[pname]
                air_duration = t - ab["start_time"]
                air_frames   = fi - ab["start_frame"]

                # Evaluar solo vuelos significativos (duración aérea >= 0.35s o altura >= 150uu)
                if air_duration >= 0.35 or ab["max_height"] > 150.0:
                    # Calidad del aterrizaje al tocar suelo
                    is_clean_landing = (pitch <= 20.0 and (roll <= 20.0 or roll >= 160.0))

                    # Buscar tiempo hasta alcanzar supersónico o velocidad de crucero (v >= 2100)
                    time_to_supersonic = None
                    full_recovery_time = air_duration

                    for f_future in range(fi, min(num_frames, fi + 90)):
                        fut_gs = game_states[f_future]
                        fut_p = next((fp for fp in fut_gs.get("players", []) if fp["name"] == pname), None)
                        if fut_p:
                            f_vx, f_vy, f_vz = fut_p["vel_x"], fut_p["vel_y"], fut_p["vel_z"]
                            f_speed = math.sqrt(f_vx*f_vx + f_vy*f_vy + f_vz*f_vz)
                            if f_speed >= 2100.0:
                                time_to_supersonic = round(fut_gs["time"] - ab["start_time"], 2)
                                full_recovery_time = time_to_supersonic
                                break

                    # ── 3. ASIGNAR RATING / NOTA DE RECUPERACION ──────────────
                    if is_clean_landing and full_recovery_time <= 0.85:
                        rating = "EXCELENTE"
                        grade_score = 10
                    elif is_clean_landing and full_recovery_time <= 1.40:
                        rating = "BUENO"
                        grade_score = 8
                    elif full_recovery_time <= 2.20:
                        rating = "LENTO"
                        grade_score = 5
                    else:
                        rating = "FALLIDO / MAL_ATERRISAJE"
                        grade_score = 2

                    rec_entry = {
                        "frame":               ab["start_frame"],
                        "land_frame":          fi,
                        "time":                round(ab["start_time"], 2),
                        "player":              pname,
                        "team":                team,
                        "air_time_sec":        round(air_duration, 2),
                        "max_height_u":        round(ab["max_height"], 1),
                        "recovery_time_sec":   round(full_recovery_time, 2),
                        "time_to_supersonic":  time_to_supersonic,
                        "clean_landing":       is_clean_landing,
                        "rating":              rating,
                        "grade_score":         grade_score,
                        "details":             f"Recuperación {rating}: {full_recovery_time:.2f}s (Aterrizaje {'limpio' if is_clean_landing else 'torpe'})"
                    }

                    recovery_events.append(rec_entry)
                    player_recoveries[pname].append(rec_entry)

                del airborne_tracker[pname]

    # ── 4. ESTADISTICAS CONSOLIDADAS DE RECOVERY POR JUGADOR ────────────────
    player_summary_stats = []
    for pname, recs in player_recoveries.items():
        if recs:
            avg_rec_time = sum(r["recovery_time_sec"] for r in recs) / len(recs)
            clean_pct    = (sum(1 for r in recs if r["clean_landing"]) / len(recs)) * 100.0
            avg_score    = sum(r["grade_score"] for r in recs) / len(recs)
            exc_count    = sum(1 for r in recs if r["rating"] == "EXCELENTE")
            poor_count   = sum(1 for r in recs if "FALLIDO" in r["rating"])

            player_summary_stats.append({
                "name":                     pname,
                "team":                     recs[0]["team"],
                "total_recoveries":         len(recs),
                "avg_recovery_time_sec":    round(avg_rec_time, 2),
                "clean_landings_pct":       round(clean_pct, 1),
                "avg_recovery_score":       round(avg_score, 1),
                "excellent_recoveries":     exc_count,
                "poor_recoveries":          poor_count,
            })

    return recovery_events, player_summary_stats
