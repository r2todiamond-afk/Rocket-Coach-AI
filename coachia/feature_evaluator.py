"""
coachia/feature_evaluator.py
============================
Motor de Evaluación Basado en Vectores de Features y Razonamiento Ponderado.

Sustituye arboles de condicionales por un Vector de Features por Evento/Decisión:
  [
    boost_propio, boost_rival, es_primer_hombre, es_tercer_hombre,
    velocidad, dist_balon, dist_compañero, dist_rival, posesion,
    nivel_riesgo, riesgo_open_net, presion_nivel, angulo_aproximacion, eta_sec
  ]

Calcula:
  - Decision Score (0.0 a 10.0): Puntuación cuantitativa ponderada.
  - Explicación del Razonamiento (Reasoning Engine): Diagnóstico en lenguaje natural.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
import math


@dataclass
class DecisionFeatureVector:
    player_name: str
    team: int
    time_sec: float
    action_type: str
    
    # Telemetría y Recursos
    boost_propio: float              # 0.0 - 100.0
    boost_rival: float               # 0.0 - 100.0
    velocidad_propia: float          # u/s
    
    # Roles y Posicionamiento
    es_primer_hombre: bool
    es_segundo_hombre: bool
    es_tercer_hombre: bool
    dist_balon: float                # uu
    dist_compañero: float            # uu
    dist_rival: float                # uu
    
    # Contexto Global
    posesion: str                    # "PROPIA" | "RIVAL" | "DISPUTADA"
    presion_nivel: float             # 0.0 - 100.0
    riesgo_open_net: bool
    nivel_riesgo: str                # "BAJO" | "MEDIO" | "ALTO" | "CRITICO"
    
    # Geometría y Tiempos
    angulo_aproximacion_deg: float   # 0 - 180°
    eta_sec: float                   # s
    resultado_evento: str            # "EXITO" | "PERDIDO" | "ABANDONADO" | "IMPACTO_NEUTRO"


def extract_feature_vector(gs: Dict[str, Any], player_name: str, action_type: str, outcome_str: str = "IMPACTO_NEUTRO") -> Optional[DecisionFeatureVector]:
    """
    Construye un DecisionFeatureVector cuantitativo a partir del GameState actual.
    """
    ball = gs.get("ball") or {}
    players = gs.get("players", [])
    possession_team = gs.get("team_possession")
    pressure_info = gs.get("pressure", {})
    danger_info = gs.get("danger_level", {})
    tactical_roles = gs.get("tactical_roles", {})

    player = next((p for p in players if p["name"] == player_name), None)
    if not player:
        return None

    team = player["team"]
    opp_team = 1 if team == 0 else 0

    teammates = [p for p in players if p["team"] == team and p["name"] != player_name]
    opponents = [p for p in players if p["team"] == opp_team]

    d_tm = min(((p.get("dist_to_ball") or 3000.0) for p in teammates), default=3000.0) if teammates else 3000.0
    d_opp = min(((p.get("dist_to_ball") or 3000.0) for p in opponents), default=3000.0) if opponents else 3000.0
    opp_boost = sum(((p.get("boost_pct") or 0.0) for p in opponents)) / len(opponents) if opponents else 33.3

    t_roles = tactical_roles.get(f"team{team}", {})
    is_1st = (t_roles.get("first_man") == player_name)
    is_2nd = (t_roles.get("second_man") == player_name)
    is_3rd = (t_roles.get("third_man") == player_name)

    press_val = pressure_info.get(f"on_team{team}_blue" if team == 0 else f"on_team{team}_orange", 0.0)
    danger_val = danger_info.get(f"on_team{team}", 0.0)

    # Nivel de riesgo posicional
    if is_3rd and danger_val > 60.0:
        risk_lvl = "CRITICO"
    elif is_3rd or danger_val > 40.0:
        risk_lvl = "ALTO"
    elif press_val > 50.0:
        risk_lvl = "MEDIO"
    else:
        risk_lvl = "BAJO"

    vx, vy, vz = player.get("vel_x") or 0.0, player.get("vel_y") or 0.0, player.get("vel_z") or 0.0
    speed = math.sqrt(vx*vx + vy*vy + vz*vz)

    pos_str = "PROPIA" if possession_team == team else ("RIVAL" if possession_team == opp_team else "DISPUTADA")

    p_dist = player.get("dist_to_ball") or 1500.0
    eta = round(p_dist / max(100.0, speed), 2)

    dx = (ball.get("pos_x") or 0.0) - (player.get("pos_x") or 0.0)
    dy = (ball.get("pos_y") or 0.0) - (player.get("pos_y") or 0.0)
    dz = (ball.get("pos_z") or 0.0) - (player.get("pos_z") or 0.0)
    dist_3d = math.sqrt(dx*dx + dy*dy + dz*dz)

    if speed > 10.0 and dist_3d > 1.0:
        dot = (vx * dx + vy * dy + vz * dz) / (speed * dist_3d)
        dot_clamped = max(-1.0, min(1.0, dot))
        approach_angle_deg = round(math.degrees(math.acos(dot_clamped)), 1)
    else:
        approach_angle_deg = 0.0

    return DecisionFeatureVector(
        player_name=player_name,
        team=team,
        time_sec=gs["time"],
        action_type=action_type,
        boost_propio=player.get("boost_pct") or 0.0,
        boost_rival=round(opp_boost, 1),
        velocidad_propia=round(speed, 1),
        es_primer_hombre=is_1st,
        es_segundo_hombre=is_2nd,
        es_tercer_hombre=is_3rd,
        dist_balon=round(p_dist, 1),
        dist_compañero=round(d_tm, 1),
        dist_rival=round(d_opp, 1),
        posesion=pos_str,
        presion_nivel=round(press_val, 1),
        riesgo_open_net=(danger_val > 70.0),
        nivel_riesgo=risk_lvl,
        angulo_aproximacion_deg=approach_angle_deg,
        eta_sec=eta,
        resultado_evento=outcome_str,
    )


def evaluate_feature_vector(vec: DecisionFeatureVector) -> Dict[str, Any]:
    """
    Motor de Scoring y Razonamiento: Asigna una puntuación (0.0 a 10.0) y genera la explicación en lenguaje natural.
    """
    # Factores ponderados (Pesos)
    score = 7.0  # Base neutral
    reasons = []

    # 1. Posesion y Presion
    if vec.posesion == "PROPIA" and vec.presion_nivel < 30.0:
        if vec.boost_propio < 25.0 and vec.dist_balon > 2000.0:
            score -= 3.0
            reasons.append("Abandono de posesión limpia sin presión rival para buscar recursos")
        else:
            score += 1.5
            reasons.append("Buena conservación de posesión en zona de confort")
    elif vec.presion_nivel > 60.0:
        score += 1.0
        reasons.append("Despeje/Acción ejecutada bajo alta presión rival (justificado)")

    # 2. Responsabilidad de 3er Hombre
    if vec.es_tercer_hombre:
        if vec.dist_balon > 1200.0 and vec.resultado_evento == "PERDIDO":
            score -= 4.0
            reasons.append("Desafío riesgoso del 3er hombre (último defensor) sin cobertura trasera")
        elif vec.nivel_riesgo in ["ALTO", "CRITICO"]:
            score -= 2.0
            reasons.append("Exposición de la portería en situación de riesgo elevado")
        else:
            score += 1.0
            reasons.append("Buena compostura y contención como último hombre")

    # 3. Eficiencia de Recursos
    if vec.boost_propio > 80.0 and vec.velocidad_propia > 2100.0:
        score -= 1.0
        reasons.append("Malgasto de boost a velocidad supersónica")

    final_score = max(0.0, min(10.0, round(score, 1)))

    if final_score >= 8.5:
        verdict_str = "DECISION_EXCELENTE"
    elif final_score >= 6.5:
        verdict_str = "DECISION_ACEPTABLE"
    elif final_score >= 4.0:
        verdict_str = "DECISION_DUDOSA"
    else:
        verdict_str = "ERROR_DECISIONAL_GRAVE"

    return {
        "player":          vec.player_name,
        "time":            vec.time_sec,
        "action_type":     vec.action_type,
        "decision_score":  final_score,
        "verdict":         verdict_str,
        "feature_vector":  asdict(vec),
        "reasoning":       " | ".join(reasons) if reasons else "Ejecución dentro de parámetros normales"
    }
