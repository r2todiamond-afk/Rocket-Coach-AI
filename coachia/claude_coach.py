"""
coachia/claude_coach.py
=======================
Módulo de Integración con Anthropic Claude API para Auditoría Táctica,
Verificación de Conclusiones de Telemetría y Conversación por Voz (Microfono).

Funciones principales:
  - get_anthropic_client(): Singleton del cliente Anthropic con timeout de 60s.
  - audit_and_enhance_report(): Envía los datos calculados de telemetría a Claude
    para que verifique las conclusiones y elabore el guión de voz refinado.
  - chat_with_claude_coach_voice(): Responde a la consulta de voz del jugador recibida
    por el micrófono sobre una jugada específica.
"""

import json
import os
import logging
from typing import Dict, Any, List, Optional

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# ── Logging Configuration ───────────────────────────────────────────────────
logger = logging.getLogger("claude_coach")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [ClaudeCoach] %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def load_api_key() -> str:
    """
    Lee la API Key de Anthropic desde apikeyclaude.txt, ApiKeyClaudeAnthropic.txt o ANTHROPIC_API_KEY.
    """
    base_dir = os.path.dirname(__file__)
    candidate_files = [
        "apikeyclaude.txt",
        "ApiKeyClaudeAnthropic.txt",
        "api_key_claude.txt",
        "api_key.txt"
    ]
    for fname in candidate_files:
        k_path = os.path.join(base_dir, fname)
        if os.path.exists(k_path):
            try:
                with open(k_path, "r", encoding="utf-8") as f:
                    key = f.read().strip()
                    if key:
                        logger.info("API Key de Anthropic cargada desde %s", fname)
                        return key
            except Exception as e:
                logger.warning("No se pudo leer %s: %s", fname, e)

    return os.environ.get("ANTHROPIC_API_KEY", "")


_client_instance: Optional[Any] = None


def get_anthropic_client(api_key: Optional[str] = None) -> Optional[Any]:
    """
    Retorna la instancia singleton del cliente Anthropic.
    """
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    if not HAS_ANTHROPIC:
        logger.warning("Librería 'anthropic' no instalada. Se usará el motor local determinista.")
        return None

    key = api_key or load_api_key()
    if not key:
        logger.warning("No se encontró API Key de Anthropic. Se usará el motor local determinista.")
        return None

    os.environ["ANTHROPIC_API_KEY"] = key
    try:
        logger.info("Inicializando cliente singleton de Anthropic (timeout=60.0s)...")
        _client_instance = anthropic.Anthropic(api_key=key, timeout=60.0)
        return _client_instance
    except Exception as e:
        logger.error("Fallo al inicializar Anthropic client: %s", e)
        return None


def generate_conclusive_advice(momento: Dict[str, Any]) -> str:
    """
    Genera el consejo concluyente basado en telemetría real.
    Si Claude API está disponible, solicita verificación y refinamiento táctico.
    """
    client = get_anthropic_client()
    
    ev_type = momento.get("type") or momento.get("event_type") or momento.get("clasificacion") or momento.get("primary_cause") or "JUGADA"
    dist_goal = float(momento.get("dist_pelota_a_arco_propio") or momento.get("dist_ball_goal") or 3000.0)
    t_arrival = float(momento.get("tiempo_estimado_llegada_pelota") or momento.get("t_arrival") or 2.0)
    inercia = float(momento.get("inercia_jugador_hacia_pelota") or momento.get("v_towards_ball") or momento.get("player_speed") or 1000.0)
    boost = float(momento.get("boost_jugador") if momento.get("boost_jugador") is not None else momento.get("player_boost", 33.3))
    tiene_cobertura = "SÍ" if momento.get("tiene_cobertura_companero") else "NO"
    cause = momento.get("primary_cause", ev_type)

    local_fallback = (
        f"Jugada [{cause}] a {dist_goal:.0f}u del arco. "
        f"Inercia: {inercia:.0f} u/s, Boost: {boost:.0f}%, Cobertura: {tiene_cobertura}."
    )

    if not client:
        return local_fallback

    try:
        user_prompt = f"""
DATOS CALCULADOS EN TIEMPO REAL DEL REPLAY DE ROCKET LEAGUE:
- Tipo de Evento / Causa Raíz: {cause}
- Distancia Pelota-Arco Propio: {dist_goal:.1f} uu
- Tiempo Estimado Llegada Pelota (ETA): {t_arrival:.2f} s
- Inercia del Jugador hacia la Pelota: {inercia:.1f} u/s
- Boost Disponible: {boost:.1f}%
- Cobertura de Compañero: {tiene_cobertura} ({momento.get('detalles_cobertura', '')})

INSTRUCCIÓN PARA CLAUDE (HEAD COACH SSL):
Verifica la exactitud táctica de estos datos calculados y redacta en 2 oraciones directas
el consejo concluyente final para el jugador, citando explícitamente la distancia y el boost.
"""
        res = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=250,
            temperature=0.2,
            messages=[{"role": "user", "content": user_prompt}]
        )
        if res and res.content:
            return res.content[0].text.strip()
    except Exception as e:
        logger.warning("Fallo en llamada a Claude API (generate_conclusive_advice): %s", e)

    return local_fallback


def generate_ssl_insight_and_training(momento: Dict[str, Any]) -> Dict[str, Any]:
    """
    Genera consejo, perspectiva SSL y alternativas en una sola llamada a Claude.
    """
    client = get_anthropic_client()
    dist_goal = float(momento.get("dist_pelota_a_arco_propio") or 2500.0)
    inercia = float(momento.get("inercia_jugador_hacia_pelota") or 1000.0)
    boost = float(momento.get("boost_jugador") if momento.get("boost_jugador") is not None else 33.3)
    cause = momento.get("primary_cause", "Análisis Posicional")
    coverage = "con respaldo de compañero" if momento.get("tiene_cobertura_companero") else "sin respaldo de compañero"
    conclusive = (
        f"Jugada [{cause}] a {dist_goal:.0f}u del arco. Inercia: {inercia:.0f} u/s, "
        f"Boost: {boost:.0f}%, {coverage}."
    )

    local_insight = f"Un jugador SSL a {dist_goal:.0f}u con {boost:.0f}% de boost no habría arriesgado la posición sin respaldo."
    local_alts = [
        f"1. {conclusive}",
        f"2. Sostener sombra defensiva a 1200u para demorar la jugada.",
        f"3. Recolectar carril de pads pequeños (Penny Line) manteniendo inercia."
    ]
    local_pack = "Entrenamiento Táctico Posicional SSL"

    if not client:
        return {
            "conclusive_advice": conclusive,
            "ssl_insight": local_insight,
            "alternatives": local_alts,
            "training_pack": local_pack
        }

    try:
        user_prompt = f"""
DATOS DE LA JUGADA:
- Diagnóstico: {cause}
- Distancia al Arco: {dist_goal:.0f}u
- Inercia: {inercia:.0f} u/s
- Boost: {boost:.0f}%

Genera un JSON en este formato estricto:
{{
    "conclusive_advice": "Dos oraciones directas y concretas basadas en los datos.",
  "ssl_insight": "Una frase comparando qué habría hecho un jugador SSL basado en los datos.",
  "alternatives": [
    "1. Opción óptima basada en el consejo concluyente",
    "2. Segunda alternativa táctica específica",
    "3. Tercera alternativa de posicionamiento"
  ],
  "training_pack": "Nombre de un entrenamiento táctico recomendado"
}}
"""
        res = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=350,
            temperature=0.2,
            messages=[{"role": "user", "content": user_prompt}]
        )
        if res and res.content:
            txt = res.content[0].text.strip()
            if "{" in txt and "}" in txt:
                s_json = txt[txt.find("{"):txt.rfind("}")+1]
                data = json.loads(s_json)
                return {
                    "conclusive_advice": data.get("conclusive_advice", conclusive),
                    "ssl_insight": data.get("ssl_insight", local_insight),
                    "alternatives": data.get("alternatives", local_alts),
                    "training_pack": data.get("training_pack", local_pack)
                }
    except Exception as e:
        logger.warning("Fallo en llamada a Claude API (generate_ssl_insight_and_training): %s", e)

    return {
        "conclusive_advice": conclusive,
        "ssl_insight": local_insight,
        "alternatives": local_alts,
        "training_pack": local_pack
    }


def analyze_moment(momento: Dict[str, Any]) -> str:
    return generate_conclusive_advice(momento)


def chat_with_claude_coach(player_name: str, user_question: str, play_context: Dict[str, Any]) -> str:
    """
    Procesa las preguntas escritas o habladas por micrófono del jugador con la API de Claude.
    """
    client = get_anthropic_client()
    ts = play_context.get('time_str', '00:00')
    cause = play_context.get('primary_cause') or play_context.get('clasificacion', 'Jugada Táctica')
    dist = float(play_context.get('dist_pelota_a_arco_propio', 2500))
    inercia = float(play_context.get('inercia_jugador_hacia_pelota', 1000))
    boost = float(play_context.get('boost_jugador', 33.3))

    fallback_reply = (
        f"{player_name}, a los {ts} ({cause}), la telemetría registra {dist:.0f}u de distancia al arco, "
        f"{inercia:.0f} u/s de inercia y {boost:.0f}% de boost. "
        f"Respecto a tu consulta por micrófono ('{user_question}'): la recomendación táctica fue mantener la sombra defensiva."
    )

    if not client:
        return fallback_reply

    try:
        system_prompt = (
            "Eres Coachia, un Head Coach SSL/RLCS de Rocket League. "
            "Responde de forma concisa, profesional y directa al jugador por voz/chat, "
            "fundamentando tu respuesta en los datos telemétricos de la jugada."
        )
        user_prompt = f"""
JUGADOR: {player_name}
MOMENTO REPLAY: {ts}
DIAGNÓSTICO CALCULADO: {cause}
TELEMETRÍA REAL: Distancia al Arco={dist:.0f}u, Inercia={inercia:.0f}u/s, Boost={boost:.0f}%

PREGUNTA HABLANDO POR MICRÓFONO / CHAT DEL JUGADOR:
"{user_question}"

Responde en 2-3 oraciones directas habladas para que el motor de voz TTS las reproduzca al jugador.
"""
        res = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            temperature=0.3,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        if res and res.content:
            return res.content[0].text.strip()
    except Exception as e:
        logger.error("Error en chat_with_claude_coach: %s", e)

    return fallback_reply


def analyze_full_extracted_data_with_claude(extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    return {}
