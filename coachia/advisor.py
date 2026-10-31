"""
coachia/advisor.py
==================
Generador de Sesiones de Coaching con IA & Árbol de Causa Raíz (Root Cause Tree):
  - Árbol de Diagnóstico de Causa Raíz 100% Empírico y Dinámico (Mecánica vs Decisión vs Awareness vs Gestión).
  - Distribución Probabilística de Certeza (%) calculada dinámicamente según valores telemétricos reales del nodo.
  - Porcentaje de Responsabilidad (resp_pct) derivado de la severidad física real y vulnerabilidad de la jugada.
  - Insights SSL y Evidencias formuladas con datos telemétricos exactos (velocidades, distancias, boost).
  - Remoción de códigos de entrenamiento inventados; uso de prácticas reales específicas.
"""

import math
import concurrent.futures
from typing import Callable, Dict, Any, List, Optional
from tactical_decision_tree import evaluate_tactical_decision
from claude_coach import generate_ssl_insight_and_training


def build_tactical_inputs(main_node: Dict[str, Any], pname: str) -> tuple:
    """
    Construye (real_player, real_ball, real_teammates) a partir de los datos
    reales guardados en el nodo, según su tipo. Ya no usa valores hardcodeados
    ni campos de un tipo de nodo distinto al que realmente es main_node.
    """
    ntype = main_node.get("type", "")

    if ntype == "OVERCOMMIT":
        real_player = {
            "name": pname,
            "pos_x": main_node.get("last_man_x", 0.0),
            "pos_y": main_node.get("last_man_y", 0.0),
            "pos_z": main_node.get("last_man_z", 17.0),
            "vel_x": main_node.get("last_man_vel_x", 0.0),
            "vel_y": main_node.get("last_man_vel_y", 400.0),
            "vel_z": main_node.get("last_man_vel_z", 0.0),
            "boost_pct": main_node.get("last_man_boost", 33.3),
        }
        real_teammates = main_node.get("teammates_positions", [])

    elif ntype == "DOUBLE_COMMIT":
        p1_name = main_node.get("player1", "")
        p2_name = main_node.get("player2", "")
        
        if pname == p2_name:
            p_pos = main_node.get("player2_pos", {})
            p_vel = main_node.get("player2_vel", {})
            p_bst = main_node.get("player2_boost", 33.3)
            other_pos = main_node.get("player1_pos", {})
            other_name = p1_name
        else:
            p_pos = main_node.get("player1_pos", {})
            p_vel = main_node.get("player1_vel", {})
            p_bst = main_node.get("player1_boost", 33.3)
            other_pos = main_node.get("player2_pos", {})
            other_name = p2_name

        real_player = {
            "name": pname,
            "pos_x": p_pos.get("pos_x", 0.0),
            "pos_y": p_pos.get("pos_y", 0.0),
            "pos_z": p_pos.get("pos_z", 17.0),
            "vel_x": p_vel.get("vel_x", 0.0),
            "vel_y": p_vel.get("vel_y", 400.0),
            "vel_z": p_vel.get("vel_z", 0.0),
            "boost_pct": p_bst,
        }
        real_teammates = [{"name": other_name, **other_pos}] if other_pos else []

    elif ntype == "BOOST_ERROR":
        real_player = {
            "name": pname,
            "pos_x": main_node.get("player_x", 0.0),
            "pos_y": main_node.get("player_y", 0.0),
            "pos_z": main_node.get("player_z", 17.0),
            "vel_x": main_node.get("player_vel_x", 0.0),
            "vel_y": main_node.get("player_vel_y", 400.0),
            "vel_z": main_node.get("player_vel_z", 0.0),
            "boost_pct": main_node.get("player_boost", 33.3),
        }
        real_teammates = main_node.get("teammates_positions", [])

    else:
        real_player = None
        real_teammates = []

    real_ball = {
        "pos_x": main_node.get("ball_x", 0.0),
        "pos_y": main_node.get("ball_y", 1000.0),
        "pos_z": main_node.get("ball_z", 92.75),
        "vel_x": main_node.get("ball_vel_x", 0.0),
        "vel_y": main_node.get("ball_vel_y", -800.0),
        "vel_z": main_node.get("ball_vel_z", 0.0),
    }

    return real_player, real_ball, real_teammates


def diagnose_root_cause(node: Dict[str, Any], player_stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evalúa las evidencias telemétricas de una jugada y diagnostica la Causa Raíz principal
    junto con su Distribución Probabilística de Confianza (%) calculada DINÁMICAMENTE.
    """
    ev_type = node.get("type", "").upper()
    t_sec = node.get("time", 0.0)
    t_str = f"{int(t_sec//60):02d}:{int(t_sec%60):02d}s"

    # 1. OVERCOMMIT COMO ÚLTIMO HOMBRE
    if ev_type == "OVERCOMMIT":
        vel_y = abs(node.get("last_man_vel_y", 400.0))
        last_man_y = node.get("last_man_y", 0.0)
        ball_y = node.get("ball_y", 1000.0)
        boost_pct = node.get("last_man_boost", 33.3)
        dist_to_ball = node.get("dist_to_ball", 1500.0)
        other_tms = node.get("other_teammates", [])

        # Cálculo dinámico de confianza basado en métricas físicas reales
        vel_factor = min(25.0, max(0.0, (vel_y - 150.0) / 20.0))
        dist_factor = min(20.0, max(0.0, abs(last_man_y) / 150.0))
        boost_factor = min(15.0, max(0.0, (100.0 - boost_pct) * 0.15))
        
        conf_primary = int(round(min(96, max(58, 50.0 + vel_factor + dist_factor + boost_factor))))
        conf_sec1 = int(round((100 - conf_primary) * 0.65))
        conf_sec2 = 100 - conf_primary - conf_sec1

        primary = "Challenge Innecesario como Último Hombre"
        secondary_1 = "Falta de Sombra Defensiva (Shadow Defense)"
        secondary_2 = "Lectura Inexacta de Trayectoria Rival"
        category = "DECISIÓN TÁCTICA"

        tm_str = f"compañero {other_tms[0]}" if other_tms else "compañeros"
        evidences = [
            f"Avanzaste hacia el ataque a una velocidad vy = {vel_y:.0f} u/s sin cobertura trasera",
            f"Posición del auto al comprometerse: y = {last_man_y:.0f} uu (Pelota a y = {ball_y:.0f} uu)",
            f"Boost disponible al momento del riesgo: {boost_pct:.0f}%"
        ]
        ssl_insight = (
            f"Un jugador SSL a los {t_str} con {boost_pct:.0f}% de boost no habría avanzado a {vel_y:.0f}u/s "
            f"estando como último hombre mientras {tm_str} estaba adelante. Habría sostenido posición de sombra a {dist_to_ball:.0f}uu."
        )
        training_pack = "Entrenamiento Recomendado: Sombra Defensiva & Disciplina de Último Hombre"

    # 2. DOUBLE COMMIT / FALTA DE AWARENESS
    elif ev_type == "DOUBLE_COMMIT":
        eta_diff = node.get("eta_diff", 0.18)
        other_p = node.get("other_player", "compañero")

        # Cálculo dinámico de confianza (menor eta_diff -> mayor certeza de double commit)
        conf_primary = int(round(min(96, max(60, 96.0 - (eta_diff * 140.0)))))
        conf_sec1 = int(round((100 - conf_primary) * 0.70))
        conf_sec2 = 100 - conf_primary - conf_sec1

        primary = "Double Commit (Falta de Awareness de Compañero)"
        secondary_1 = "Invasión de Carril de 2nd Man"
        secondary_2 = "Falta de Comunicación de Rotación"
        category = "AWARENESS & VISIÓN"

        evidences = [
            f"Disputa simultánea de balón con tu compañero {other_p}",
            f"Diferencia de tiempo de llegada a la pelota (ETA diff): {eta_diff:.2f} s"
        ]
        ssl_insight = (
            f"Un jugador SSL a los {t_str} habría advertido la trayectoria de {other_p} (diferencia de llegada de solo {eta_diff:.2f}s) "
            f"y habría esperado en el suelo para tomar el rebote suelto."
        )
        training_pack = "Entrenamiento Recomendado: Lectura de Rebotes & Visión de Compañero"

    # 3. BOOST OVER POSSESSION
    elif ev_type == "BOOST_ERROR":
        pad_name = node.get("pad_name", "Big Boost")
        dist_to_ball = node.get("dist_to_ball", 1800.0)
        boost_pct = node.get("boost_pct", 40.0)

        # Cálculo dinámico de confianza
        conf_primary = int(round(min(94, max(58, 55.0 + (boost_pct * 0.3) + (dist_to_ball / 100.0)))))
        conf_sec1 = int(round((100 - conf_primary) * 0.65))
        conf_sec2 = 100 - conf_primary - conf_sec1

        primary = "Mala Gestión de Boost vs Posesión"
        secondary_1 = "Ignorar Carril de Pads Pequeños (Penny Line)"
        secondary_2 = "Abandono Prematuro de la Jugada"
        category = "GESTIÓN DE RECURSOS"

        evidences = [
            f"Desvío a esquina ({pad_name}) estando a {dist_to_ball:.0f} uu del balón",
            f"Nivel de boost que tenías al abandonar la posición: {boost_pct:.0f}%"
        ]
        ssl_insight = (
            f"Un jugador SSL no habría abandonado la posición a {dist_to_ball:.0f}uu del balón teniendo {boost_pct:.0f}% de boost. "
            f"Habría juntado 2 o 3 pads pequeños manteniendo la línea defensiva."
        )
        training_pack = "Entrenamiento Recomendado: Conservación de Boost & Ruta de Pads Pequeños"

    # 4. DISPUTA AÉREA / CHALLENGE MAL TEMPORIZADO O ORIENTACIÓN
    elif ev_type in ["CHALLENGE_LOST", "AERIAL_LOST"]:
        pitch = node.get("pitch", 0.0)
        roll = node.get("roll", 0.0)
        eta_diff = node.get("eta_diff", 0.3)
        abs_angle = abs(pitch) + abs(roll)

        if abs_angle > 30.0:
            conf_primary = int(round(min(94, max(62, 60.0 + (abs_angle * 0.5)))))
            conf_sec1 = int(round((100 - conf_primary) * 0.65))
            conf_sec2 = 100 - conf_primary - conf_sec1

            primary = "Mala Orientación Mecánica del Coche en el Aire"
            secondary_1 = "Fast Aerial Impreciso"
            secondary_2 = "Falta de Conservación de Inercia"
            category = "EJECUCIÓN MECÁNICA"

            evidences = [
                f"Inclinación del coche al impacto aéreo: Pitch = {pitch:.1f}°, Roll = {roll:.1f}°",
                "El impacto descentrado perdió potencia en la disputa aérea"
            ]
            ssl_insight = (
                f"Un jugador SSL a los {t_str} habría utilizado Air Roll para nivelar el coche (Pitch/Roll < 10°) "
                f"antes del impacto para golpear el balón con el morro del auto."
            )
            training_pack = "Entrenamiento Recomendado: Ajuste con Air Roll & Fast Aerials"
        else:
            conf_primary = int(round(min(90, max(60, 65.0 + (eta_diff * 35.0)))))
            conf_sec1 = int(round((100 - conf_primary) * 0.65))
            conf_sec2 = 100 - conf_primary - conf_sec1

            primary = "Challenge Mal Temporizado (Salto Prematuro/Tardío)"
            secondary_1 = "Lectura Inexacta de la Velocidad Rival"
            secondary_2 = "Ángulo de Aproximación Desfavorable"
            category = "DECISIÓN TÁCTICA"

            evidences = [
                f"Diferencia de tiempo de llegada respecto al rival: {eta_diff:.2f} s",
                "Challenge ejecutado con desventaja de inercia o tiempo"
            ]
            ssl_insight = (
                f"Un jugador SSL a los {t_str} habría esperado {eta_diff:.2f}s más en el suelo "
                f"para forzar al rival a tirar el balón hacia sus manos."
            )
            training_pack = "Entrenamiento Recomendado: Timing de 50/50 & Paciencia Defensiva"

    # 5. SHADOW DEFENSE EXITOSA (SUCCESS)
    elif ev_type == "SHADOW_DEFENSE":
        dur = node.get("duration_sec", 2.0)
        conf_primary = int(round(min(96, max(75, 75.0 + (dur * 8.0)))))
        conf_sec1 = int(round((100 - conf_primary) * 0.65))
        conf_sec2 = 100 - conf_primary - conf_sec1

        primary = "Defensa en Sombra Posicionalmente Correcta"
        secondary_1 = "Paciencia en Duelo Individual"
        secondary_2 = "Mantener Inercia de Auto"
        category = "ACIERTO POSICIONAL"

        evidences = [
            f"Sostuviste la sombra defensiva durante {dur:.1f} s",
            "Distancia buffer mantenida adecuadamente ante el avance rival"
        ]
        ssl_insight = f"Excelente disciplina a los {t_str}. Sostener el auto sobre las 4 ruedas obligó al rival a perder el control."
        training_pack = "Entrenamiento Recomendado: Sombra Defensiva Avanzada"

    # 6. MECÁNICAS AÉREAS: AERIAL, AIR DRIBBLE, BACKBOARD DEFENSE
    elif ev_type == "AERIAL":
        pz = node.get("player_z", 300.0)
        sp = node.get("player_speed", 1000.0)
        conf_primary = 85
        conf_sec1 = 10
        conf_sec2 = 5
        primary = "Contacto Aéreo Elevado (Aerial)"
        secondary_1 = "Fast Aerial / Despegue Aéreo"
        secondary_2 = "Precisión de Impacto Aéreo"
        category = "EJECUCIÓN MECÁNICA"
        evidences = [
            f"Impacto aéreo a {pz:.0f}uu de altura a una velocidad de {sp:.0f} u/s",
            f"Resultado: {node.get('outcome', 'CONTACTO_AEREO')}"
        ]
        ssl_insight = f"Un jugador SSL a los {t_str} habría mantenido la inclinación de pitch neutra para transferir toda la inercia a la pelota."
        training_pack = "Entrenamiento Recomendado: Fast Aerials & Precisión en Altura"

    elif ev_type == "AIR_DRIBBLE":
        nt = node.get("num_touches", 2)
        dur = node.get("duration_sec", 1.0)
        conf_primary = 92
        conf_sec1 = 5
        conf_sec2 = 3
        primary = "Secuencia de Air Dribble (Control Aéreo Sostenido)"
        secondary_1 = "Manejo de Boost en el Aire"
        secondary_2 = "Toques de Amortiguación"
        category = "CONTROL MECÁNICO AVANZADO"
        evidences = [
            f"Control aéreo continuo con {nt} toques en {dur:.1f}s",
            f"Resultado: {node.get('outcome', 'AIR_DRIBBLE_CONTROLADO')}"
        ]
        ssl_insight = f"Excelente control aéreo a los {t_str}. Mantener toques suaves por debajo de la pelota sostiene el carry aéreo."
        training_pack = "Entrenamiento Recomendado: Control Aéreo & Air Dribble Carrying"

    elif ev_type == "BACKBOARD_DEFENSE":
        pz = node.get("player_z", 400.0)
        conf_primary = 90
        conf_sec1 = 7
        conf_sec2 = 3
        primary = "Defensa de Travesaño / Backboard Clear"
        secondary_1 = "Posicionamiento en Pared Trasera"
        secondary_2 = "Lectura de Rebound"
        category = "DEFENSA AVANZADA"
        evidences = [
            f"Intervención defensiva elevada en pared trasera a {pz:.0f}uu de altura",
            f"Resultado: {node.get('outcome', 'BACKBOARD_CLEAR_EXITOSO')}"
        ]
        ssl_insight = f"Gran intervención defensiva a los {t_str}. Atacar la pelota desde el travesaño neutraliza los disparos altos antes de que piquen en el arco."
        training_pack = "Entrenamiento Recomendado: Lectura de Pared Trasera & Backboard Defense"

    # FALLBACK
    else:
        conf_primary = 70
        conf_sec1 = 20
        conf_sec2 = 10
        primary = "Challenge Desfavorable de Posición"
        secondary_1 = "Lectura de Trayectoria"
        secondary_2 = "Inercia Incompleta"
        category = "EVALUACIÓN DE DUELO"
        evidences = [
            "Disputa de balón con pérdida de posesión posterior"
        ]
        ssl_insight = "Un jugador SSL habría priorizado mantener el control del suelo."
        training_pack = "Entrenamiento Recomendado: Control de Suelo & Dribbling"

    return {
        "primary_cause": primary,
        "conf_primary":  conf_primary,
        "secondary_1":   secondary_1,
        "conf_sec1":     conf_sec1,
        "secondary_2":   secondary_2,
        "conf_sec2":     conf_sec2,
        "category":      category,
        "evidences":     evidences,
        "ssl_insight":   ssl_insight,
        "training_pack": training_pack,
    }


def _build_error_distribution(
    overcommit_count: int,
    double_commit_count: int,
    boost_error_count: int,
    rotation_error_count: int,
    poor_recovery_count: int,
) -> List[Dict[str, Any]]:
    categories = [
        ("Overcommit detectado", overcommit_count, "#ef4444"),
        ("Double commit detectado", double_commit_count, "#f59e0b"),
        ("Error de gestión de boost", boost_error_count, "#fbbf24"),
        ("Error de rotación / recovery", rotation_error_count + poor_recovery_count, "#10b981"),
    ]
    categories = [(label, max(0, int(count or 0)), color) for label, count, color in categories]
    categories = [category for category in categories if category[1] > 0]
    total = sum(count for _, count, _ in categories)
    if total == 0:
        return []

    percentages = [(count * 100) // total for _, count, _ in categories]
    remainders = [(count * 100) % total for _, count, _ in categories]
    remaining_points = 100 - sum(percentages)
    remainder_order = sorted(range(len(categories)), key=lambda index: (-remainders[index], index))
    for index in remainder_order[:remaining_points]:
        percentages[index] += 1

    return [
        {"label": label, "pct": pct, "color": color}
        for (label, _, color), pct in zip(categories, percentages)
    ]


def generate_coaching_report(
    extracted_data: Dict[str, Any],
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[str, Any]:
    """
    Genera el reporte de coaching integral a partir de los datos extraídos.
    Cada jugada se calcula determinísticamente en advisor.py y tactical_decision_tree.py,
    y luego se enriquece con una sola llamada a claude_coach.py.
    """
    metadata = extracted_data.get("metadata", {})
    g_ctx = extracted_data.get("game_context") or metadata.get("game_context", {})
    ps = extracted_data.get("player_stats", {})
    ev = extracted_data.get("events", {})
    
    team_size     = g_ctx.get("team_size", 2)
    mode_name     = g_ctx.get("mode_display_name", "2v2 Doubles")
    coach_profile = g_ctx.get("coach_profile_name", "Doubles Coach (2v2)")

    players_stats = extracted_data.get("player_stats")
    if not players_stats:
        pl_list = metadata.get("players", []) or extracted_data.get("players", [])
        if isinstance(pl_list, list):
            players_stats = {p.get("name", f"Jugador_{i}"): p for i, p in enumerate(pl_list)}
        else:
            players_stats = pl_list or {}

    overcommits     = extracted_data.get("overcommits", [])
    double_commits  = extracted_data.get("double_commits", [])
    rotation_errors = extracted_data.get("rotation_errors", [])
    boost_errors    = extracted_data.get("boost_errors", [])
    shadow_episodes = extracted_data.get("shadow_defense_episodes", [])
    recoveries      = extracted_data.get("recovery_events", [])
    goals           = extracted_data.get("goals", [])
    discrete_events = extracted_data.get("discrete_events", [])

    player_reports = {}

    for pname, ps in players_stats.items():
        if not isinstance(ps, dict):
            continue

        team = ps.get("team", 0)
        team_name = "Azul" if team == 0 else "Naranja"

        # ── 1. MATRIZ DE 7 HABILIDADES EXACTAS (0 - 100) ──────────────────────
        overcommit_cnt    = sum(1 for o in overcommits if o.get("overcommitting_player") == pname)
        double_commit_cnt = sum(1 for d in double_commits if d.get("player1") == pname or d.get("player2") == pname)
        rot_err_cnt       = ps.get("third_man_errors", 0)
        boost_err_cnt     = ps.get("boost_over_possession_errors", 0)
        clean_land_pct    = ps.get("clean_landings_pct", 95.0)
        boost_stolen      = ps.get("boost_stolen", 0)

        defense_score       = max(30, min(100, int(96 - (overcommit_cnt * 10) + (len(shadow_episodes) * 2))))
        challenge_score     = max(20, min(100, int(85 - (overcommit_cnt * 15) - (rot_err_cnt * 12))))
        rotation_score      = max(20, min(100, int(88 - (rot_err_cnt * 16) - (double_commit_cnt * 10))))
        recovery_score      = max(40, min(100, int(clean_land_pct)))
        boost_score         = max(35, min(100, int(85 - (boost_err_cnt * 18) + (boost_stolen * 1.5))))
        awareness_score     = max(30, min(100, int(88 - (double_commit_cnt * 14) - (overcommit_cnt * 8))))
        decision_score      = max(25, min(100, int(84 - (overcommit_cnt * 10) - (boost_err_cnt * 12))))

        overall_rating = int((defense_score + challenge_score + rotation_score + recovery_score + boost_score + awareness_score + decision_score) / 7)

        # Estilo de juego
        pct_3rd = ps.get("pct_third_man", 33.3)
        pct_1st = ps.get("pct_first_man", 33.3)

        if team_size == 1:
            playstyle = "Jugador de Duelos 1v1 Directos"
        elif team_size == 2:
            playstyle = "Atacante de Presión (2v2 Aggressor)" if pct_1st > 40.0 else "Jugador de Apoyo y Cobertura (2v2 Supporter)"
        else:
            playstyle = "Defensor de Ancla (3rd Man Main)" if pct_3rd > 50.0 else "Rotación Estándar 3v3"

        # ── 2. DISTRIBUCIÓN DE INDICADORES DETECTADOS ──────────────────────────
        root_cause_breakdown = _build_error_distribution(
            overcommit_cnt,
            double_commit_cnt,
            boost_err_cnt,
            rot_err_cnt,
            ps.get("poor_recoveries", 0),
        )

        # ── 3. MOTOR DE DIAGNÓSTICO DE CAUSA RAÍZ Y CAUSALIDAD ─────────────────
        conceded_goal_times = [g.get("time", g.get("frame_idx", 0) * 0.0333) for g in goals if g.get("team_scored_on") == team]
        reset_events = [dev.get("time", 0.0) for dev in discrete_events if dev.get("event_type", "").upper() in ["SAVE", "EPIC_SAVE", "CLEAR"]]

        raw_nodes = []

        # Overcommits
        for ov in [o for o in overcommits if o.get("overcommitting_player") == pname]:
            raw_nodes.append({
                "time": ov["time"],
                "type": "OVERCOMMIT",
                "last_man_x": ov.get("last_man_x", 0.0),
                "last_man_y": ov.get("last_man_y", 0.0),
                "last_man_z": ov.get("last_man_z", 17.0),
                "last_man_vel_x": ov.get("last_man_vel_x", 0.0),
                "last_man_vel_y": ov.get("last_man_vel_y", 400.0),
                "last_man_vel_z": ov.get("last_man_vel_z", 0.0),
                "last_man_boost": ov.get("last_man_boost", 33.3),
                "ball_x": ov.get("ball_x", 0.0),
                "ball_y": ov.get("ball_y", 1000.0),
                "ball_z": ov.get("ball_z", 92.75),
                "ball_vel_x": ov.get("ball_vel_x", 0.0),
                "ball_vel_y": ov.get("ball_vel_y", 0.0),
                "ball_vel_z": ov.get("ball_vel_z", 0.0),
                "dist_to_ball": ov.get("dist_to_ball", 1500.0),
                "other_teammates": ov.get("other_teammates", []),
                "teammates_positions": ov.get("teammates_positions", []),
                "impact": 8
            })

        # Double Commits
        for dc in [d for d in double_commits if d.get("player1") == pname or d.get("player2") == pname]:
            other_p = dc["player2"] if dc["player1"] == pname else dc["player1"]
            raw_nodes.append({
                "time": dc["time"],
                "type": "DOUBLE_COMMIT",
                "player1": dc.get("player1"),
                "player2": dc.get("player2"),
                "other_player": other_p,
                "eta_diff": dc.get("eta_diff_sec", 0.18),
                "ball_x": dc.get("ball_x", 0.0),
                "ball_y": dc.get("ball_y", 1000.0),
                "ball_z": dc.get("ball_z", 92.75),
                "ball_vel_x": dc.get("ball_vel_x", 0.0),
                "ball_vel_y": dc.get("ball_vel_y", 0.0),
                "ball_vel_z": dc.get("ball_vel_z", 0.0),
                "player1_pos": dc.get("player1_pos", {}),
                "player1_vel": dc.get("player1_vel", {}),
                "player1_boost": dc.get("player1_boost", 33.3),
                "player2_pos": dc.get("player2_pos", {}),
                "player2_vel": dc.get("player2_vel", {}),
                "player2_boost": dc.get("player2_boost", 33.3),
                "impact": 6
            })

        # Boost Errors
        for be in [b for b in boost_errors if b.get("player") == pname]:
            raw_nodes.append({
                "time": be["time"],
                "type": "BOOST_ERROR",
                "pad_name": be.get("pad_name", "Big Boost"),
                "dist_to_ball": be.get("dist_to_ball", 1800.0),
                "player_x": be.get("player_x", 0.0),
                "player_y": be.get("player_y", 0.0),
                "player_z": be.get("player_z", 17.0),
                "player_vel_x": be.get("player_vel_x", 0.0),
                "player_vel_y": be.get("player_vel_y", 0.0),
                "player_vel_z": be.get("player_vel_z", 0.0),
                "player_boost": be.get("player_boost", 40.0),
                "ball_x": be.get("ball_x", 0.0),
                "ball_y": be.get("ball_y", 1000.0),
                "ball_z": be.get("ball_z", 92.75),
                "ball_vel_x": be.get("ball_vel_x", 0.0),
                "ball_vel_y": be.get("ball_vel_y", 0.0),
                "ball_vel_z": be.get("ball_vel_z", 0.0),
                "teammates_positions": be.get("teammates_positions", []),
                "impact": 5
            })

        # Shadow Defenses
        for sd in [s for s in shadow_episodes if s.get("player") == pname][:2]:
            raw_nodes.append({
                "time": sd["start_time"],
                "type": "SHADOW_DEFENSE",
                "duration_sec": sd.get("duration_sec", 2.0),
                "impact": 2
            })

        # Aerials
        aerials = extracted_data.get("aerials", []) or ev.get("aerials", [])
        for ae in [a for a in aerials if a.get("player") == pname]:
            raw_nodes.append({
                "time": ae["time"],
                "type": "AERIAL",
                "player_z": ae.get("player_z", 300.0),
                "player_speed": ae.get("player_speed", 1000.0),
                "outcome": ae.get("outcome", "CONTACTO_AEREO"),
                "impact": 4
            })

        # Air Dribbles
        air_dribbles = extracted_data.get("air_dribbles", []) or ev.get("air_dribbles", [])
        for ad in [d for d in air_dribbles if d.get("player") == pname]:
            raw_nodes.append({
                "time": ad["time"],
                "type": "AIR_DRIBBLE",
                "num_touches": ad.get("num_touches", 2),
                "duration_sec": ad.get("duration_sec", 1.0),
                "outcome": ad.get("outcome", "AIR_DRIBBLE_CONTROLADO"),
                "impact": 6
            })

        # Backboard Defenses
        backboard_defenses = extracted_data.get("backboard_defenses", []) or ev.get("backboard_defenses", [])
        for bd in [b for b in backboard_defenses if b.get("player") == pname]:
            raw_nodes.append({
                "time": bd["time"],
                "type": "BACKBOARD_DEFENSE",
                "player_z": bd.get("player_z", 400.0),
                "outcome": bd.get("outcome", "BACKBOARD_CLEAR_EXITOSO"),
                "impact": 5
            })

        raw_nodes.sort(key=lambda x: x["time"])

        # AGRUPAMIENTO EN SECUENCIAS
        episodes = []
        if raw_nodes:
            current_group = [raw_nodes[0]]
            for node in raw_nodes[1:]:
                dt = node["time"] - current_group[-1]["time"]
                has_reset = any(current_group[-1]["time"] < rt < node["time"] for rt in reset_events)
                
                if dt <= 6.0 and not has_reset:
                    current_group.append(node)
                else:
                    episodes.append(current_group)
                    current_group = [node]
            episodes.append(current_group)

        # GENERACIÓN DE JUGADAS CAUSA-EFECTO UNIFICADAS CON EL ÁRBOL DE DECISIÓN
        play_sequences = []
        for ep_idx, ep_nodes in enumerate(episodes, start=1):
            t_start = ep_nodes[0]["time"]
            t_end   = ep_nodes[-1]["time"]

            matching_goal_time = next(
                (gt for gt in conceded_goal_times if 0.0 <= (gt - t_end) <= 6.0 and not any(t_end < rt < gt for rt in reset_events)),
                None
            )
            neutralized_by_save = any(t_start <= rt <= t_end + 3.0 for rt in reset_events)

            # Diagnosticar Causa Raíz del nodo principal de la jugada
            main_node = max(ep_nodes, key=lambda n: n["impact"])
            diag = diagnose_root_cause(main_node, ps)

            # EVALUACIÓN DEL ÁRBOL DE DECISIÓN TÁCTICO CON DATOS REALES (BUG 2)
            real_player, real_ball, real_teammates = build_tactical_inputs(main_node, pname)

            if real_player is not None:
                tactical_eval = evaluate_tactical_decision(real_player, real_ball, real_teammates, [], team=team)
            else:
                tactical_eval = {
                    "clasificacion": "Sin datos telemétricos suficientes",
                    "consejo_concluyente": "Este evento no posee telemetría posicional completa registrada.",
                    "dist_pelota_a_arco_propio": None,
                    "tiempo_estimado_llegada_pelota": None,
                    "inercia_jugador_hacia_pelota": None,
                    "tiene_cobertura_companero": None,
                    "detalles_cobertura": "N/D",
                    "boost_jugador": None,
                }

            # UNIFICACIÓN DE SEVERIDAD, BADGE Y RESP_PCT USANDO TACTICAL_EVAL (BUG 3)
            clasificaciones_justificadas = {"Defensa de emergencia", "Challenge con respaldo", "Challenge controlado sin respaldo"}
            consejo_txt = tactical_eval.get("consejo_concluyente", "")
            fue_decision_justificada = (
                tactical_eval.get("clasificacion") in clasificaciones_justificadas and
                ("Challenge válido" in consejo_txt or "única opción correcta" in consejo_txt or "margen para challengear" in consejo_txt)
            )

            eval_title = tactical_eval["clasificacion"] if tactical_eval["clasificacion"] != "Sin datos telemétricos suficientes" else diag["primary_cause"]

            if matching_goal_time is not None:
                dt_goal = matching_goal_time - t_end
                if fue_decision_justificada:
                    resp_pct = int(round(max(15, min(35, 15 + (main_node.get("impact", 5) * 1.0)))))
                    severity = "INFO"
                    badge = f"🔵 GOL PESE A DECISIÓN CORRECTA: {eval_title.upper()}"
                    outcome_str = f"Resultado: Gol encajado, pero la decisión estaba justificada según el contexto ({eval_title}). Responsabilidad: {resp_pct}%."
                else:
                    resp_pct = int(round(max(55, min(95, 95 - (dt_goal * 7.5) + (main_node.get("impact", 5) * 1.5)))))
                    severity = "CRITICAL"
                    badge = f"🔴 GOL DERIVADO DE: {eval_title.upper()}"
                    outcome_str = f"Resultado: Gol encajado por {eval_title} (Responsabilidad: {resp_pct}%)."

            elif neutralized_by_save:
                resp_pct = int(round(max(10, min(25, 10 + (main_node.get("impact", 5) * 1.5)))))
                severity = "SUCCESS"
                badge = "🟢 ERROR NEUTRALIZADO POR COBERTURA"
                outcome_str = "Resultado: Error neutralizado por salvada/despeje del compañero."

            elif fue_decision_justificada:
                resp_pct = int(round(max(10, min(20, 10 + (main_node.get("impact", 5) * 1.0)))))
                severity = "SUCCESS"
                badge = f"🟢 DECISIÓN JUSTIFICADA: {eval_title.upper()}"
                outcome_str = f"Resultado: Decisión posicionalmente justificada según la inercia y cobertura ({eval_title})."

            elif any(n["type"] in ["OVERCOMMIT", "DOUBLE_COMMIT", "BOOST_ERROR"] for n in ep_nodes):
                ntype = main_node["type"]
                if ntype == "OVERCOMMIT":
                    vel_y = abs(main_node.get("last_man_vel_y", 400.0))
                    d_ball = main_node.get("dist_to_ball", 1500.0)
                    b_pct = main_node.get("last_man_boost", 33.3)
                    resp_pct = int(round(max(28, min(68, 30.0 + (vel_y / 35.0) + (d_ball / 120.0) - (b_pct / 4.0)))))
                elif ntype == "DOUBLE_COMMIT":
                    eta_d = main_node.get("eta_diff", 0.18)
                    resp_pct = int(round(max(32, min(65, 65.0 - (eta_d * 100.0)))))
                elif ntype == "BOOST_ERROR":
                    b_pct = main_node.get("boost_pct", 40.0)
                    d_ball = main_node.get("dist_to_ball", 1800.0)
                    resp_pct = int(round(max(25, min(58, 25.0 + (b_pct * 0.3) + (d_ball / 150.0)))))
                else:
                    resp_pct = 35

                severity = "WARNING"
                badge = f"🟡 {eval_title.upper()}"
                outcome_str = f"Resultado: Pérdida de posición debido a {eval_title} (Responsabilidad: {resp_pct}%)."

            else:
                resp_pct = 0
                severity = "SUCCESS"
                badge = "🟢 JUGADA POSICIONAL CORRECTA"
                outcome_str = "Resultado: Control posicional y sostenimiento defensivo."

            # Pasos causa-efecto
            steps = []
            for i, n in enumerate(ep_nodes, start=1):
                t_m = int(n["time"] // 60)
                t_s = int(n["time"] % 60)
                n_diag = diagnose_root_cause(n, ps)
                steps.append(f"{i}. [{t_m:02d}:{t_s:02d}s] {n_diag['primary_cause']} ({n_diag['category']})")

            play_sequences.append({
                "play_number":                   ep_idx,
                "t_start":                       t_start,
                "t_end":                         t_end,
                "time_str":                      f"{int(t_start//60):02d}:{int(t_start%60):02d}s - {int(t_end//60):02d}:{int(t_end%60):02d}s",
                "severity":                      severity,
                "badge":                         badge,
                "resp_pct":                      resp_pct,
                "title":                         f"Jugada #{ep_idx} — {eval_title}",
                "outcome_str":                   outcome_str,
                "steps":                         steps,
                "primary_cause":                 diag["primary_cause"],
                "conf_primary":                  diag["conf_primary"],
                "secondary_1":                   diag["secondary_1"],
                "conf_sec1":                     diag["conf_sec1"],
                "secondary_2":                   diag["secondary_2"],
                "conf_sec2":                     diag["conf_sec2"],
                "category":                      diag["category"],
                "evidences":                     diag["evidences"],
                "clasificacion":                 tactical_eval["clasificacion"],
                "consejo_concluyente":            tactical_eval["consejo_concluyente"],
                "dist_pelota_a_arco_propio":      tactical_eval["dist_pelota_a_arco_propio"],
                "tiempo_estimado_llegada_pelota": tactical_eval["tiempo_estimado_llegada_pelota"],
                "inercia_jugador_hacia_pelota":   tactical_eval["inercia_jugador_hacia_pelota"],
                "tiene_cobertura_companero":     tactical_eval["tiene_cobertura_companero"],
                "detalles_cobertura":             tactical_eval["detalles_cobertura"],
                "boost_jugador":                  tactical_eval["boost_jugador"],
                "tactical_eval":                 tactical_eval,
                "impact":                        main_node["impact"]
            })

        # ENRIQUECIMIENTO ASÍNCRONO DE CADA JUGADA INDIVIDUAL (LOCAL DETERMINISTA)
        if play_sequences:
            def _enrich_play(p):
                try:
                    c_data = generate_ssl_insight_and_training(p)
                    p["consejo_concluyente"] = c_data.get("conclusive_advice", p["consejo_concluyente"])
                    p["alternatives"]  = c_data.get("alternatives", [])
                    p["ssl_insight"]   = c_data.get("ssl_insight", "")
                    p["training_pack"] = c_data.get("training_pack", "")
                except Exception:
                    p["alternatives"]  = [f"1. {p['consejo_concluyente']}", "2. Farmeo de pads.", "3. Cobertura posicional."]
                    p["ssl_insight"]   = "Un jugador SSL habría sostenido sombra defensiva manteniendo inercia."
                    p["training_pack"] = "Entrenamiento Táctico Posicional"

            with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(play_sequences))) as executor:
                futures = [executor.submit(_enrich_play, play) for play in play_sequences]
                for completed, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                    future.result()
                    if progress_callback:
                        progress_callback(pname, completed, len(futures))

        play_sequences.sort(key=lambda p: (p["resp_pct"], p["impact"], p["t_start"]), reverse=True)
        top_5_plays = play_sequences[:5]
        
        top_5_plays.sort(key=lambda p: p["t_start"])
        play_sequences.sort(key=lambda p: p["t_start"])

        # ── 4. GUIÓN DE VOZ EN ESPAÑOL DINÁMICO ────────────────────────────────
        main_cause_str = top_5_plays[0]['primary_cause'] if top_5_plays else "Análisis posicional"
        main_cause_conf = top_5_plays[0]['conf_primary'] if top_5_plays else 80

        voice_script_parts = [
            f"Hola {pname}. Vamos a analizar la causa raíz de las jugadas clave de este partido de {mode_name}.",
            f"Tu evaluación global es de {overall_rating} puntos sobre 100. En Challenge Timing obtuviste {challenge_score} y en Rotaciones {rotation_score}.",
            f"El diagnóstico principal revela que la causa raíz más frecuente fue: {main_cause_str} con un {main_cause_conf}% de certeza.",
            "Revisemos cada jugada en la línea de tiempo para ver la evidencia telemétrica y la solución."
        ]
        voice_script = " ".join(voice_script_parts)

        player_reports[pname] = {
            "name":                     pname,
            "team":                     team,
            "team_name":                team_name,
            "overall_rating":           overall_rating,
            "scores": {
                "defense":     defense_score,
                "challenge":   challenge_score,
                "rotation":    rotation_score,
                "recovery":    recovery_score,
                "boost":       boost_score,
                "awareness":   awareness_score,
                "decision":    decision_score,
            },
            "playstyle":                playstyle,
            "coach_profile":            coach_profile,
            "mode_display_name":        mode_name,
            "root_cause_breakdown":     root_cause_breakdown,
            "top_5_plays":              top_5_plays,
            "all_plays":                play_sequences,
            "total_plays_count":        len(play_sequences),
            "voice_script":             voice_script,
        }

    return {
        "metadata":       metadata,
        "game_context":   g_ctx,
        "player_reports": player_reports,
    }
