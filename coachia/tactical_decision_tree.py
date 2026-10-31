"""
coachia/tactical_decision_tree.py
=================================
Motor Determinista de Árbol de Decisión Táctica para Rocket League (Soccar Standard).

Constantes del Campo:
  - Media longitud de cancha (centro a arco): 5120.0 uu
  - Media ancho de cancha: 4096.0 uu
  - Radio de la pelota: 92.75 uu
  - Velocidad máxima del auto: 2300.0 u/s
  - Umbral de supersónico: 2200.0 u/s
  - Boost pad grande: 100.0
  - Boost pad chico: 12.0

Umbrales de Decisión:
  - UMBRAL_CRITICO_DISTANCIA_ARCO = 2000.0 uu
  - UMBRAL_TIEMPO_LLEGADA_PELOTA = 1.2 s
  - UMBRAL_INERCIA_FAVORABLE = 1400.0 u/s (en dirección a la pelota)
  - UMBRAL_BOOST_MINIMO_PARA_CHALLENGE = 20.0 %
  - UMBRAL_COBERTURA_COMPANERO = 1500.0 uu del punto de impacto y posicionado entre pelota y arco propio
"""

import math
from typing import Dict, Any, List, Tuple, Optional
from claude_coach import generate_conclusive_advice

# ── 1. CONSTANTES DEL CAMPO ───────────────────────────────────────────────────
FIELD_HALF_LENGTH = 5120.0
FIELD_HALF_WIDTH  = 4096.0
BALL_RADIUS       = 92.75
MAX_CAR_SPEED     = 2300.0
SUPERSONIC_SPEED  = 2200.0

BLUE_GOAL_POS   = (0.0, -5120.0, 0.0)
ORANGE_GOAL_POS = (0.0,  5120.0, 0.0)

# ── 2. UMBRALES DE DECISIÓN TÁCTICA ───────────────────────────────────────────
UMBRAL_CRITICO_DISTANCIA_ARCO       = 2000.0  # unidades
UMBRAL_TIEMPO_LLEGADA_PELOTA        = 1.2     # segundos
UMBRAL_INERCIA_FAVORABLE            = 1400.0  # u/s
UMBRAL_BOOST_MINIMO_PARA_CHALLENGE = 20.0    # %
UMBRAL_DISTANCIA_COBERTURA_COMPANERO = 1500.0 # unidades


def dot_product_3d(v1: Tuple[float, float, float], v2: Tuple[float, float, float]) -> float:
    return v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]


def distance_3d(p1: Tuple[float, float, float], p2: Tuple[float, float, float]) -> float:
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    dz = p1[2] - p2[2]
    return math.sqrt(dx*dx + dy*dy + dz*dz)


def evaluate_tactical_decision(
    player: Dict[str, Any],
    ball: Dict[str, Any],
    teammates: List[Dict[str, Any]],
    opponents: List[Dict[str, Any]],
    team: int
) -> Dict[str, Any]:
    """
    Ejecuta el árbol de decisión determinista sobre el GameState de un frame.

    Returns:
        dict con:
          - clasificacion: str
          - consejo_concluyente: str
          - dist_pelota_a_arco_propio: float
          - tiempo_estimado_llegada_pelota: float
          - inercia_jugador_hacia_pelota: float
          - tiene_cobertura_companero: bool
          - boost_jugador: float
          - datos_telemetricos_brutos: dict
    """
    px, py, pz = player.get("pos_x", 0.0), player.get("pos_y", 0.0), player.get("pos_z", 0.0)
    vx, vy, vz = player.get("vel_x", 0.0), player.get("vel_y", 0.0), player.get("vel_z", 0.0)
    player_boost = float(player.get("boost_pct", 0.0) or 0.0)

    bx, by, bz = ball.get("pos_x", 0.0), ball.get("pos_y", 0.0), ball.get("pos_z", 0.0)
    bvx, bvy, bvz = ball.get("vel_x", 0.0), ball.get("vel_y", 0.0), ball.get("vel_z", 0.0)

    # 1. Posición del Arco Propio (Azul = -5120y, Naranja = +5120y)
    own_goal_pos = BLUE_GOAL_POS if team == 0 else ORANGE_GOAL_POS
    gx, gy, gz = own_goal_pos

    # 2. Distancia Pelota -> Arco Propio
    dist_ball_to_own_goal = distance_3d((bx, by, bz), own_goal_pos)

    # 3. Tiempo estimado de llegada de la pelota al arco propio
    # Vector unitario desde pelota hacia el arco propio
    dx_g, dy_g, dz_g = gx - bx, gy - by, gz - bz
    dist_g = math.sqrt(dx_g*dx_g + dy_g*dy_g + dz_g*dz_g)
    
    if dist_g > 1.0:
        ux_g, uy_g, uz_g = dx_g / dist_g, dy_g / dist_g, dz_g / dist_g
        v_ball_towards_goal = bvx * ux_g + bvy * uy_g + bvz * uz_g
    else:
        v_ball_towards_goal = 0.0

    if v_ball_towards_goal > 50.0:
        tiempo_estimado_llegada_pelota = round(dist_ball_to_own_goal / v_ball_towards_goal, 2)
    else:
        tiempo_estimado_llegada_pelota = 999.0

    # 4. Inercia del jugador hacia la pelota (Velocidad proyectada en vector jugador -> pelota)
    dx_b, dy_b, dz_b = bx - px, by - py, bz - pz
    dist_b = math.sqrt(dx_b*dx_b + dy_b*dy_b + dz_b*dz_b)

    if dist_b > 1.0:
        ux_b, uy_b, uz_b = dx_b / dist_b, dy_b / dist_b, dz_b / dist_b
        inercia_jugador_hacia_pelota = round(vx * ux_b + vy * uy_b + vz * uz_b, 1)
    else:
        inercia_jugador_hacia_pelota = 0.0

    # 5. Evaluar Cobertura Real de Compañero
    # Condición: Compañero a menos de 1500u del punto proyectado y posicionado entre pelota y arco propio
    tiene_cobertura_companero = False
    detalles_cobertura = "Sin compañero en zona de seguridad"

    for tm in teammates:
        tm_x, tm_y, tm_z = tm.get("pos_x", 0.0), tm.get("pos_y", 0.0), tm.get("pos_z", 0.0)
        dist_tm_to_player = distance_3d((tm_x, tm_y, tm_z), (px, py, pz))
        
        # Verificar si el compañero está posicionado entre la pelota y el arco propio
        # En equipo Azul (arco y=-5120), estar detrás significa tm_y < py
        # En equipo Naranja (arco y=+5120), estar detrás significa tm_y > py
        is_behind_player = (tm_y < py) if team == 0 else (tm_y > py)

        if dist_tm_to_player <= UMBRAL_DISTANCIA_COBERTURA_COMPANERO and is_behind_player:
            tiene_cobertura_companero = True
            detalles_cobertura = f"Compañero {tm.get('name', 'tm')} cubriendo a {dist_tm_to_player:.0f}u hacia el arco propio"
            break

    # ── 6. EVALUACIÓN DETERMINISTA DEL ÁRBOL DE DECISIÓN (SECCIÓN 3) ───────────

    # RAMA 1: DEFENSA DE EMERGENCIA
    if (tiempo_estimado_llegada_pelota < UMBRAL_TIEMPO_LLEGADA_PELOTA) or (dist_ball_to_own_goal < UMBRAL_CRITICO_DISTANCIA_ARCO):
        clasificacion = "Defensa de emergencia"

    # RAMA 2: CHALLENGE CON RESPALDO
    elif tiene_cobertura_companero:
        clasificacion = "Challenge con respaldo"

    # RAMA 3: SIN COBERTURA REAL
    else:
        if inercia_jugador_hacia_pelota >= UMBRAL_INERCIA_FAVORABLE:
            clasificacion = "Challenge controlado sin respaldo"
        else:
            clasificacion = "Rotación/farmeo recomendado"

    momento_payload = {
        "clasificacion":                  clasificacion,
        "dist_pelota_a_arco_propio":      round(dist_ball_to_own_goal, 1),
        "tiempo_estimado_llegada_pelota": tiempo_estimado_llegada_pelota,
        "inercia_jugador_hacia_pelota":   inercia_jugador_hacia_pelota,
        "tiene_cobertura_companero":     tiene_cobertura_companero,
        "detalles_cobertura":             detalles_cobertura,
        "boost_jugador":                  round(player_boost, 1),
    }

    # Generar texto determinista instantáneo basado en telemetría
    t_cob = "con cobertura de compañero" if tiene_cobertura_companero else "sin respaldo de compañero"
    consejo_concluyente = (
        f"Jugada con clasificación '{clasificacion}' a {dist_ball_to_own_goal:.0f}u del arco. "
        f"ETA de la pelota: {tiempo_estimado_llegada_pelota:.1f}s, Inercia: {inercia_jugador_hacia_pelota:.0f} u/s, "
        f"Boost: {player_boost:.0f}%, {t_cob} ({detalles_cobertura})."
    )

    return {
        "clasificacion":                  clasificacion,
        "consejo_concluyente":            consejo_concluyente,
        "dist_pelota_a_arco_propio":      round(dist_ball_to_own_goal, 1),
        "tiempo_estimado_llegada_pelota": tiempo_estimado_llegada_pelota,
        "inercia_jugador_hacia_pelota":   inercia_jugador_hacia_pelota,
        "tiene_cobertura_companero":     tiene_cobertura_companero,
        "detalles_cobertura":             detalles_cobertura,
        "boost_jugador":                  round(player_boost, 1),
        "telemetria_calculada": {
            "dist_ball_goal": round(dist_ball_to_own_goal, 1),
            "t_arrival":      tiempo_estimado_llegada_pelota,
            "v_towards_ball": inercia_jugador_hacia_pelota,
            "has_coverage":   tiene_cobertura_companero,
            "boost":          round(player_boost, 1),
        }
    }
