"""
coachia/contextual_evaluator.py
===============================
Evaluador Contextual de Toma de Decisiones para Coachia.

Filtro Evaluativo de 5 Preguntas:
  1. ¿Quién tenía la posesión? (OWN_POSSESSION | CONTESTED | OPPONENT_POSSESSION)
  2. ¿Quién era el tercer hombre? (is_third_man, last_defender_safety)
  3. ¿Había presión? (pressure_level 0–100, is_high_pressure)
  4. ¿Qué hacían los compañeros? (teammate_positions, coverage_status)
  5. ¿Existía una opción mejor? (better_alternative_analysis)

En lugar de reglas ciegas (ej: "boost < 20 = mal"), este evaluador analiza
si la decisión fue la óptima Dado el Contexto Completo.
"""

import math
from typing import Dict, Any, List, Optional


def evaluate_decision_context(
    gs: Dict[str, Any],
    player_name: str,
    action_type: str,
    action_details: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Somete una decisión/evento al Filtro Evaluativo Contextual de 5 Preguntas.
    Returns dict con la evaluación contextual completa y la recomendación del Coach.
    """
    ball = gs.get("ball") or {}
    players = gs.get("players", [])
    possession_team = gs.get("team_possession")
    pressure_info = gs.get("pressure", {})
    danger_info = gs.get("danger_level", {})
    tactical_roles = gs.get("tactical_roles", {})

    player = next((p for p in players if p["name"] == player_name), None)
    if not player:
        return {"eval": "NEUTRAL", "reason": "Jugador no encontrado en el frame"}

    team = player["team"]
    opp_team = 1 if team == 0 else 0

    # ── Pregunta 1: ¿Quién tenía la posesión? ────────────────────────────────
    if possession_team == team:
        possession_ctx = "OWN_POSSESSION"
    elif possession_team == opp_team:
        possession_ctx = "OPPONENT_POSSESSION"
    else:
        possession_ctx = "CONTESTED_BALL"

    # ── Pregunta 2: ¿Quién era el tercer hombre? ─────────────────────────────
    t_roles = tactical_roles.get(f"team{team}", {})
    is_third_man = (t_roles.get("third_man") == player_name)

    # ── Pregunta 3: ¿Había presión? ──────────────────────────────────────────
    press_val = pressure_info.get(f"on_team{team}_blue" if team == 0 else f"on_team{team}_orange", 0.0)
    is_high_pressure = (press_val >= 60.0)

    # ── Pregunta 4: ¿Qué hacían los compañeros? ──────────────────────────────
    teammates = [p for p in players if p["team"] == team and p["name"] != player_name]
    teammates_forward = sum(1 for tm in teammates if (team == 0 and tm["pos_y"] > player["pos_y"]) or (team == 1 and tm["pos_y"] < player["pos_y"]))

    # ── Pregunta 5: ¿Existía una opción mejor? ────────────────────────────────
    is_justified = True
    better_option = None
    severity = "NONE"

    if action_type == "BOOST_DECISION":
        # Evaluando recarga de boost o desvío a esquina
        b_pct = player.get("boost_pct") or 0.0
        if b_pct < 25.0:
            if is_high_pressure:
                # Bajo presión alta, buscar boost rápido o despejar de pánico está JUSTIFICADO
                is_justified = True
                better_option = "Despeje rápido de pánico o recolección de pads centrales bajo presión"
            elif possession_ctx == "OWN_POSSESSION" and not is_high_pressure:
                # Sin presión y con posesión propia: desviarse a la esquina es UN ERROR
                is_justified = False
                severity = "HIGH"
                better_option = "Recolectar 2-3 pads pequeños centrales (+24-36% boost) y mantener el control del balón"
            elif is_third_man:
                # Siendo 3er hombre sin presión: abandonar la posición es UN ERROR
                is_justified = False
                severity = "CRITICAL"
                better_option = "Mantener cobertura en sombra (Shadow Defense) y recolectar pads en la línea de retorno"

    elif action_type == "CHALLENGE_DECISION":
        # Evaluando salto / choque a la pelota
        if is_third_man and teammates_forward >= len(teammates):
            # 3er hombre arrojándose sin cobertura trasera
            if possession_ctx == "OPPONENT_POSSESSION":
                is_justified = False
                severity = "CRITICAL"
                better_option = "Retroceder en Shadow Defense para ganar tiempo y esperar el regreso del 1st/2nd man"

    evaluation_result = {
        "player":                 player_name,
        "team":                   team,
        "time":                   gs["time"],
        "action_type":            action_type,
        "q1_possession":          possession_ctx,
        "q2_is_third_man":        is_third_man,
        "q3_pressure_level":      press_val,
        "q3_is_high_pressure":    is_high_pressure,
        "q4_teammates_forward":   teammates_forward,
        "q5_is_justified":        is_justified,
        "q5_better_option":       better_option,
        "severity":               severity,
        "coach_verdict":          "DECISION_CORRECTA" if is_justified else f"ERROR_DECISIONAL ({severity}): {better_option}"
    }

    return evaluation_result
