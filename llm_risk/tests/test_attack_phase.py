import unittest
from unittest.mock import MagicMock, patch
import os
import json

from llm_risk.game_orchestrator import GameOrchestrator
from llm_risk.game_engine.engine import GameEngine
from llm_risk.game_engine.data_structures import Player as GamePlayer, GameState, Territory, Continent, Card
from llm_risk.ai.base_agent import BaseAIAgent
from llm_risk.tests.test_fortify_phase import MockAIAgent # Reuse MockAIAgent

class TestAttackPhase(unittest.TestCase):
    def setUp(self):
        self.test_map_file = "test_attack_map_config.json"
        # Territories: P1 owns A, B. P2 owns C, D.
        # A (P1) -- C (P2)
        # B (P1) -- D (P2)
        # A also adjacent to B (for PAF/fortify tests if needed within attack context)
        dummy_map_data = {
            "continents": [
                {"name": "TestContinent", "bonus_armies": 3}
            ],
            "territories": {
                "A": {"continent": "TestContinent", "adjacent_to": ["C", "B"]},
                "B": {"continent": "TestContinent", "adjacent_to": ["D", "A"]},
                "C": {"continent": "TestContinent", "adjacent_to": ["A"]},
                "D": {"continent": "TestContinent", "adjacent_to": ["B"]}
            }
        }
        with open(self.test_map_file, 'w') as f:
            json.dump(dummy_map_data, f)

        self.player_configs = [
            {"name": "AttackerPlayer", "color": "Red", "ai_type": "mock"},
            {"name": "DefenderPlayer", "color": "Blue", "ai_type": "mock"}
        ]

        self.orchestrator = GameOrchestrator(map_file_path_override=self.test_map_file, player_configs_override=self.player_configs)

        self.attacker_agent = MockAIAgent("AttackerPlayer", "Red")
        self.defender_agent = MockAIAgent("DefenderPlayer", "Blue")

        self.orchestrator.ai_agents = {
            "AttackerPlayer": self.attacker_agent,
            "DefenderPlayer": self.defender_agent
        }
        self.orchestrator._map_game_players_to_ai_agents()

        self.game_engine = self.orchestrator.engine
        self.game_state = self.game_engine.game_state

        self.p1 = self.game_state.get_player_by_name("AttackerPlayer")
        self.p2 = self.game_state.get_player_by_name("DefenderPlayer")

        self.tA = self.game_state.territories["A"]
        self.tB = self.game_state.territories["B"]
        self.tC = self.game_state.territories["C"]
        self.tD = self.game_state.territories["D"]

        # Setup initial state: P1 to attack P2
        self.tA.owner = self.p1; self.tA.army_count = 10 # Strong attacker
        self.tB.owner = self.p1; self.tB.army_count = 1
        self.p1.territories = [self.tA, self.tB]

        self.tC.owner = self.p2; self.tC.army_count = 2 # Weak defender
        self.tD.owner = self.p2; self.tD.army_count = 5
        self.p2.territories = [self.tC, self.tD]

        self.game_state.current_player_index = self.game_state.players.index(self.p1)
        self.game_state.current_game_phase = "ATTACK"
        self.p1.has_conquered_territory_this_turn = False
        self.p1.has_fortified_this_turn = False # Should be false at start of ATTACK
        self.orchestrator.current_ai_context = {}

        # Ensure deck has cards for drawing
        self.game_state.deck = [Card("CardTerritory1", "Infantry"), Card("CardTerritory2", "Cavalry")]


    def tearDown(self):
        if os.path.exists(self.test_map_file):
            os.remove(self.test_map_file)
        self.game_engine.card_trade_bonus_index = 0

    def _run_orchestrator_advance_until_ai_not_thinking(self, max_loops=5):
        """ Advances game until current AI is done thinking or max_loops hit. """
        loops = 0
        initial_player = self.game_state.get_current_player()
        while self.orchestrator.ai_is_thinking and loops < max_loops:
            self.orchestrator.advance_game_turn()
            loops += 1
        if self.orchestrator.ai_is_thinking:
            # If it's still thinking, it might be for the *next* player if a turn transition happened.
            # This helper is more for ensuring a single AI action completes.
            if self.game_state.get_current_player() == initial_player:
                 raise TimeoutError(f"Orchestrator's AI ({self.orchestrator.active_ai_player_name}) still thinking after {max_loops} advances.")


    def test_successful_attack_conquest_and_paf(self):
        """Test a successful attack, conquest, card draw, and post-attack fortification."""
        self.game_state.current_game_phase = "ATTACK"
        self.p1.has_conquered_territory_this_turn = False

        # --- 1. AI chooses to ATTACK A -> C ---
        attack_action = {"type": "ATTACK", "from": "A", "to": "C", "num_armies": 3} # AI provides num_armies
        self.attacker_agent.set_next_action(attack_action)

        # Mock dice rolls for a guaranteed win for attacker without losses
        with patch.object(self.game_engine, 'random') as mock_random:
            # Attacker rolls 3 dice (e.g., 6,6,6), Defender rolls 2 dice (e.g., 1,1)
            # Attacker dice (max 3): num_armies = 3 -> 3 dice
            # Defender dice (max 2): tC.army_count = 2 -> 2 dice
            mock_random.randint.side_effect = [6, 6, 6, 1, 1] # Attacker high, Defender low

            self.orchestrator.advance_game_turn() # Initiate ATTACK for P1
            self._run_orchestrator_advance_until_ai_not_thinking() # AI thinks & returns action
            self.orchestrator.advance_game_turn() # Process P1's ATTACK action
            self._run_orchestrator_advance_until_ai_not_thinking() # Ensure processing completes

        self.assertEqual(self.tC.owner, self.p1, "Territory C should be conquered by P1")
        self.assertTrue(self.p1.has_conquered_territory_this_turn, "P1 should have conquered this turn")
        self.assertEqual(len(self.p1.hand), 1, "P1 should have drawn a card")
        self.assertTrue(self.game_state.requires_post_attack_fortify, "PAF should be required")
        self.assertIsNotNone(self.game_state.conquest_context)
        self.assertEqual(self.game_state.conquest_context["from_territory_name"], "A")
        self.assertEqual(self.game_state.conquest_context["to_territory_name"], "C")
        # tA had 10, attacked with 3. Defender lost 2. Attacker lost 0. tA = 10. tC = 0 (before PAF).
        # Min movable is 3 (dice rolled). Max movable is 3 (armies sent).
        self.assertEqual(self.game_state.conquest_context["min_movable"], 3)
        self.assertEqual(self.game_state.conquest_context["max_movable"], 3)
        self.assertEqual(self.tA.army_count, 10 - 0) # Armies in A after battle (before PAF move)
        self.assertEqual(self.tC.army_count, 0) # Armies in C after battle (before PAF move)

        # --- 2. AI chooses to PAF ---
        paf_action = {"type": "POST_ATTACK_FORTIFY", "from_territory": "A", "to_territory": "C", "num_armies": 3}
        self.attacker_agent.set_next_action(paf_action)

        self.orchestrator.advance_game_turn() # Initiate PAF for P1
        self._run_orchestrator_advance_until_ai_not_thinking()
        self.orchestrator.advance_game_turn() # Process P1's PAF action
        self._run_orchestrator_advance_until_ai_not_thinking()

        self.assertFalse(self.game_state.requires_post_attack_fortify, "PAF should be cleared")
        self.assertIsNone(self.game_state.conquest_context, "Conquest context should be cleared")
        self.assertEqual(self.tA.army_count, 7) # 10 - 3 moved
        self.assertEqual(self.tC.army_count, 3) # 0 + 3 moved
        self.assertEqual(self.game_state.current_game_phase, "ATTACK", "Should return to ATTACK phase after PAF")

        # --- 3. AI chooses to END_ATTACK_PHASE ---
        end_attack_action = {"type": "END_ATTACK_PHASE"}
        self.attacker_agent.set_next_action(end_attack_action)

        self.orchestrator.advance_game_turn() # Initiate next ATTACK sub-turn
        self._run_orchestrator_advance_until_ai_not_thinking()
        self.orchestrator.advance_game_turn() # Process END_ATTACK_PHASE
        self._run_orchestrator_advance_until_ai_not_thinking()

        self.assertEqual(self.game_state.current_game_phase, "FORTIFY", "Phase should be FORTIFY")
        self.assertEqual(self.game_state.get_current_player(), self.p1, "Should still be P1's turn for FORTIFY")

    def test_attack_no_conquest(self):
        """Test an attack where the defender holds."""
        self.tA.army_count = 3 # Attacker less strong
        self.tC.army_count = 5 # Defender stronger

        attack_action = {"type": "ATTACK", "from": "A", "to": "C", "num_armies": 2} # Attack with 2 armies (2 dice)
        self.attacker_agent.set_next_action(attack_action)

        # Mock dice for defender win: Attacker (2 dice): 1,1. Defender (2 dice): 6,6
        with patch.object(self.game_engine, 'random') as mock_random:
            mock_random.randint.side_effect = [1, 1, 6, 6]

            self.orchestrator.advance_game_turn() # Initiate ATTACK
            self._run_orchestrator_advance_until_ai_not_thinking()
            self.orchestrator.advance_game_turn() # Process ATTACK
            self._run_orchestrator_advance_until_ai_not_thinking()

        self.assertEqual(self.tC.owner, self.p2, "Territory C should still be owned by P2")
        self.assertFalse(self.p1.has_conquered_territory_this_turn)
        self.assertEqual(len(self.p1.hand), 0)
        self.assertFalse(self.game_state.requires_post_attack_fortify)
        self.assertEqual(self.tA.army_count, 1) # Lost 2 armies
        self.assertEqual(self.tC.army_count, 5) # Lost 0 armies
        self.assertEqual(self.game_state.current_game_phase, "ATTACK", "Should still be in ATTACK phase")

    def test_ai_chooses_end_attack_phase_immediately(self):
        """Test AI immediately ends attack phase."""
        end_attack_action = {"type": "END_ATTACK_PHASE"}
        self.attacker_agent.set_next_action(end_attack_action)

        self.orchestrator.advance_game_turn() # Initiate ATTACK
        self._run_orchestrator_advance_until_ai_not_thinking()
        self.orchestrator.advance_game_turn() # Process END_ATTACK_PHASE
        self._run_orchestrator_advance_until_ai_not_thinking()

        self.assertEqual(self.game_state.current_game_phase, "FORTIFY")
        self.assertEqual(self.game_state.get_current_player(), self.p1)

    def test_no_attack_options_transitions_to_fortify(self):
        """Test if no attack options, game auto-transitions to FORTIFY."""
        # Make P1 unable to attack (e.g., all owned territories have 1 army, or no adjacent enemies)
        self.tA.army_count = 1
        self.tB.army_count = 1
        # P2 still owns C and D

        # _initiate_attack_ai_action should see no valid attacks (or only END_ATTACK_PHASE)
        # and change phase to FORTIFY.

        self.orchestrator.advance_game_turn() # Call advance_game_turn. It will try to initiate ATTACK.
                                            # _initiate_attack_ai_action changes phase to FORTIFY.
                                            # The while loop in advance_game_turn should then call _initiate_fortify_ai_action.

        # By this point, AI should be thinking about FORTIFY action.
        self.assertTrue(self.orchestrator.ai_is_thinking, "AI should be thinking about FORTIFY action")
        self.assertEqual(self.game_state.current_game_phase, "FORTIFY")
        self.assertEqual(self.orchestrator.active_ai_player_name, self.p1.name, "Active AI should be P1 for FORTIFY")

        # Now let AI end the FORTIFY phase
        self.attacker_agent.set_next_action({"type": "END_TURN"})
        self._run_orchestrator_advance_until_ai_not_thinking() # AI thinks & returns END_TURN
        self.orchestrator.advance_game_turn() # Process END_TURN

        self.assertEqual(self.game_state.get_current_player(), self.p2, "Should be P2's turn after P1's fortify/end.")


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
