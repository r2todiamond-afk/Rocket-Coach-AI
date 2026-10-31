import unittest
from types import SimpleNamespace
from unittest.mock import patch

from advisor import _build_error_distribution
from claude_coach import generate_ssl_insight_and_training
from events_detector import detect_basic_events


def make_frame(frame_idx, velocity, player_distance=None):
    players = []
    if player_distance is not None:
        players.append({
            "name": "Player",
            "team": 0,
            "dist_to_ball": player_distance,
        })
    return {
        "frame_idx": frame_idx,
        "time": frame_idx / 30,
        "ball": {
            "pos_x": 0.0,
            "pos_y": 0.0,
            "pos_z": 500.0,
            "vel_x": velocity[0],
            "vel_y": velocity[1],
            "vel_z": velocity[2],
            "speed": sum(component * component for component in velocity) ** 0.5,
        },
        "players": players,
    }


class BasicEventRegressionTests(unittest.TestCase):
    def test_direction_change_near_player_is_redirect(self):
        frames = [
            make_frame(0, (0.0, 1000.0, 0.0)),
            make_frame(1, (1000.0, 0.0, 0.0), player_distance=100.0),
        ]

        events = detect_basic_events(frames)

        self.assertEqual(events[0]["type"], "REDIRECT")

    def test_speed_change_without_direction_change_is_touch(self):
        frames = [
            make_frame(0, (0.0, 1000.0, 0.0)),
            make_frame(1, (0.0, 1500.0, 0.0), player_distance=100.0),
        ]

        events = detect_basic_events(frames)

        self.assertEqual(events[0]["type"], "TOUCH")


class ErrorDistributionRegressionTests(unittest.TestCase):
    def test_empty_counts_produce_no_claimed_causes(self):
        distribution = _build_error_distribution(0, 0, 0, 0, 0)

        self.assertEqual(distribution, [])

    def test_percentages_sum_to_100_and_include_poor_recoveries(self):
        distribution = _build_error_distribution(1, 1, 1, 1, 1)

        self.assertEqual(sum(item["pct"] for item in distribution), 100)
        self.assertEqual([item["pct"] for item in distribution], [20, 20, 20, 40])
        self.assertEqual(distribution[-1]["label"], "Error de rotación / recovery")


class CoachingApiRegressionTests(unittest.TestCase):
    def test_play_enrichment_uses_one_api_request(self):
        response_data = {
            "conclusive_advice": "Consejo concreto.",
            "ssl_insight": "Lectura SSL.",
            "alternatives": ["Opción 1"],
            "training_pack": "Práctica recomendada",
        }
        messages = SimpleNamespace(
            calls=0,
            create=lambda **kwargs: self._response_and_count(messages, response_data),
        )
        client = SimpleNamespace(messages=messages)

        with patch("claude_coach.get_anthropic_client", return_value=client):
            result = generate_ssl_insight_and_training({"primary_cause": "Test"})

        self.assertEqual(messages.calls, 1)
        self.assertEqual(result["conclusive_advice"], "Consejo concreto.")

    def test_local_fallback_includes_conclusive_advice(self):
        with patch("claude_coach.get_anthropic_client", return_value=None):
            result = generate_ssl_insight_and_training({"primary_cause": "Test"})

        self.assertTrue(result["conclusive_advice"])

    @staticmethod
    def _response_and_count(messages, response_data):
        import json

        messages.calls += 1
        return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(response_data))])


if __name__ == "__main__":
    unittest.main()