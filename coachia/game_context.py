"""
coachia/game_context.py
=======================
Sistema de Capacidades y Contexto de Modo de Juego (GameContext & GameCapabilities).

Modos de Juego:
  - DUEL_1V1   (1v1): team_size = 1
  - DOUBLES_2V2 (2v2): team_size = 2
  - STANDARD_3V3 (3v3): team_size = 3+

Capacidades por Modo (GameCapabilities):
  - can_double_commit:  False en 1v1 | True en 2v2, 3v3
  - can_second_man:     False en 1v1 | True en 2v2, 3v3
  - can_third_man:      False en 1v1, 2v2 | True en 3v3
  - can_pass:           False en 1v1 | True en 2v2, 3v3
  - can_shadow_defense: True en 1v1, 2v2, 3v3
  - can_fake_challenge: True en 1v1, 2v2, 3v3
  - can_boost_starve:   True en 1v1, 2v2, 3v3
  - can_recoveries:     True en 1v1, 2v2, 3v3

Ponderación de Riesgo de Desafío (Challenge Risk Weight):
  - 1v1: 2.5x (Perder un challenge siendo único jugador es Gol Casi Seguro)
  - 2v2: 1.5x (Perder un challenge deja al compañero en 1v1)
  - 3v3: 1.0x (Queda cobertura de 3rd man)
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any


@dataclass
class GameCapabilities:
    can_double_commit: bool
    can_second_man: bool
    can_third_man: bool
    can_pass: bool
    can_shadow_defense: bool
    can_fake_challenge: bool
    can_boost_starve: bool
    can_recoveries: bool
    challenge_risk_weight: float


@dataclass
class GameContext:
    mode: str                    # "DUEL_1V1" | "DOUBLES_2V2" | "STANDARD_3V3"
    mode_display_name: str       # "1v1 Duel" | "2v2 Doubles" | "3v3 Standard"
    team_size: int
    num_teams: int
    capabilities: GameCapabilities
    coach_profile_name: str      # "Duel Coach (1v1)" | "Doubles Coach (2v2)" | "Standard Coach (3v3)"


def create_game_context(players_metadata: list) -> GameContext:
    """
    Determina el contexto y capacidades del partido basándose en el número de jugadores por equipo.
    """
    if not players_metadata:
        team_size = 3
    else:
        # Contar jugadores por equipo
        team_counts = {}
        for p in players_metadata:
            t = p.get("team", 0)
            team_counts[t] = team_counts.get(t, 0) + 1
        
        team_size = max(team_counts.values()) if team_counts else 3

    if team_size == 1:
        mode = "DUEL_1V1"
        mode_display = "1v1 Duel"
        coach_profile = "Duel Coach (1v1)"
        caps = GameCapabilities(
            can_double_commit=False,
            can_second_man=False,
            can_third_man=False,
            can_pass=False,
            can_shadow_defense=True,
            can_fake_challenge=True,
            can_boost_starve=True,
            can_recoveries=True,
            challenge_risk_weight=2.5
        )
    elif team_size == 2:
        mode = "DOUBLES_2V2"
        mode_display = "2v2 Doubles"
        coach_profile = "Doubles Coach (2v2)"
        caps = GameCapabilities(
            can_double_commit=True,
            can_second_man=True,
            can_third_man=False,
            can_pass=True,
            can_shadow_defense=True,
            can_fake_challenge=True,
            can_boost_starve=True,
            can_recoveries=True,
            challenge_risk_weight=1.5
        )
    else:
        mode = "STANDARD_3V3"
        mode_display = "3v3 Standard"
        coach_profile = "Standard Coach (3v3)"
        caps = GameCapabilities(
            can_double_commit=True,
            can_second_man=True,
            can_third_man=True,
            can_pass=True,
            can_shadow_defense=True,
            can_fake_challenge=True,
            can_boost_starve=True,
            can_recoveries=True,
            challenge_risk_weight=1.0
        )

    return GameContext(
        mode=mode,
        mode_display_name=mode_display,
        team_size=team_size,
        num_teams=2,
        capabilities=caps,
        coach_profile_name=coach_profile
    )
