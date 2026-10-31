"""
coachia/knowledge_base.py
=========================
Base de Conocimiento Táctico de Élite (SSL & RLCS Knowledge Base).
Contiene principios tácticos, patrones de jugadores profesionales y reglas de toma de decisiones.
"""

from typing import Dict, Any, List

SSL_TACTICAL_PRINCIPLES = {
    "DUEL_1V1": {
        "title": "Principios de Duelos 1v1 (SSL Level)",
        "principles": [
            "Nunca abandones el carril central del arco para ir por un Big Boost de 100% si el rival tiene la pelota controlada.",
            "Mantén la sombra defensiva (Shadow Defense) a una distancia buffer de 1000uu a 1400uu.",
            "No saltes a disputar (Challenge) hasta que el rival inicie la animación del salto o flick.",
            "Utiliza Fake Challenges para forzar al rival a tirar el balón hacia tus manos.",
            "Recoge el carril de pads pequeños (Penny Line) en tu ruta de retroceso para acumular 36%-48% de boost sin perder inercia."
        ]
    },
    "DOUBLES_2V2": {
        "title": "Principios de 2v2 Doubles (SSL Level)",
        "principles": [
            "Como último hombre (2nd Man), nunca te lances en una pelota dividida si tu compañero no ha vuelto al carril defensivo.",
            "El 2nd man debe mantener una distancia de apoyo de 1500uu por detrás del 1st man en el carril opuesto.",
            "Evita los Double Commits: Si tu compañero tiene mejor ángulo de aproximación, respeta su toque y prepárate para el rebote.",
            "Utiliza pases de pared a tierra en lugar de tiros directos contra dos defensores formados en poste lejano.",
            "Sostiene la presión con robos de boost en la esquina rival (Boost Starvation) solo cuando el 1st man tenga el control."
        ]
    },
    "STANDARD_3V3": {
        "title": "Principios de 3v3 Standard (SSL Level)",
        "principles": [
            "El 3rd man debe ser una muralla inexpugnable: jamás salta a menos que tenga 100% de garantía de ganar el balón o que un compañero ya esté cubriendo el arco.",
            "Rotación por poste lejano (Backpost Rotation): Entra a la meta siempre por el poste opuesto al balón.",
            "Evita los cortes de rotación (Rotation Cuts) si cortan el carril directo de un compañero que viene con mayor inercia.",
            "Genera pases hacia el centro (Infield Passes) cuando la defensa rival esté replegada en su arco."
        ]
    }
}

PRO_PLAYER_PROFILES = {
    "Zen": {
        "playstyle": "Presión Total y Sombra Agresiva",
        "philosophy": "Reduce el espacio del rival al mínimo sin arrogarse. Solo salta cuando el rival comete el micro-error de toque."
    },
    "MonkeyMoon": {
        "playstyle": "Control de Recursos y Paciencia Impecable",
        "philosophy": "Prefiere esperar en el suelo y colectar pads pequeños. Deja que el rival tire la pelota para tomar el contraataque."
    },
    "Vatira": {
        "playstyle": "Defensa de Ancla e Inexpugnabilidad en Poste Lejano",
        "philosophy": "Perfecta disciplina de 3rd man. Entra siempre por el poste lejano y asegura la meta antes de proyectarse."
    }
}


def get_knowledge_context(mode: str) -> str:
    """
    Retorna el resumen de conocimiento táctico SSL relevante para inyectar en el Prompt de Ollama.
    """
    mode_key = mode if mode in SSL_TACTICAL_PRINCIPLES else "DOUBLES_2V2"
    p_data = SSL_TACTICAL_PRINCIPLES[mode_key]

    lines = [f"=== CONOCIMIENTO TÁCTICO SSL ({p_data['title']}) ==="]
    for p in p_data["principles"]:
        lines.append(f"• {p}")

    lines.append("\n=== PATRONES TEÓRICOS DE LA COMUNIDAD (Conocimiento general conceptual, NO derivado de replays reales analizados) ===")
    for pro_name, pro_info in PRO_PLAYER_PROFILES.items():
        lines.append(f"• {pro_name}: {pro_info['playstyle']} -> {pro_info['philosophy']}")

    return "\n".join(lines)
