import unittest
from unittest.mock import MagicMock, patch
import os
import json

from llm_risk.game_orchestrator import GameOrchestrator
from llm_risk.game_engine.engine import GameEngine
from llm_risk.game_engine.data_structures import Player as GamePlayer, GameState, Territory, Continent
from llm_risk.ai.base_agent import BaseAIAgent

# A mock AI agent that we can control the responses of
class MockAIAgent(BaseAIAgent):
    def __init__(self, player_name, player_color):
        super().__init__(player_name, player_color)
        self.next_action = None
        self.next_thought = "Mock thought"

    def set_next_action(self, action: dict, thought: str = "Mock thought"):
        self.next_action = action
        self.next_thought = thought

    def get_thought_and_action(self, game_state_json: str, valid_actions: list, game_rules: str, system_prompt_addition: str):
        # print(f"MockAI ({self.player_name}) received valid_actions: {valid_actions}")
        # print(f"MockAI ({self.player_name}) will return action: {self.next_action}")
        if self.next_action is None:
            # Default to ending phase if no specific action is set
            for va in valid_actions:
                if va['type'] == 'END_TURN' or va['type'] == 'END_FORTIFY_PHASE': # END_FORTIFY_PHASE is not standard, but END_TURN is
                    return {"thought": "Defaulting to end turn/phase", "action": va}
            # If end turn is not available for some reason, raise error or return a problematic action
            raise ValueError("MockAI has no action set and cannot find a default END_TURN/END_FORTIFY_PHASE action.")

        # Ensure the action being returned is among the valid ones, if not None
        # This is a simple check, real AI might generate complex actions
        # For testing, we assume set_next_action provides a plausible action structure.
        return {"thought": self.next_thought, "action": self.next_action}

class TestFortifyPhase(unittest.TestCase):
    def setUp(self):
        # Create a dummy map config file for consistent test setup
        self.test_map_file = "test_map_config.json"
        dummy_map_data = {
            "continents": [
                {"name": "Testland", "bonus_armies": 2}
            ],
            "territories": {
                "TerritoryA": {"continent": "Testland", "adjacent_to": ["TerritoryB"]},
                "TerritoryB": {"continent": "Testland", "adjacent_to": ["TerritoryA", "TerritoryC"]},
                "TerritoryC": {"continent": "Testland", "adjacent_to": ["TerritoryB"]},
                "TerritoryD": {"continent": "Testland", "adjacent_to": []} # Isolated for P2
            }
        }
        with open(self.test_map_file, 'w') as f:
            json.dump(dummy_map_data, f)

        self.player_configs = [
            {"name": "Player1", "color": "Red", "ai_type": "mock"},
            {"name": "Player2", "color": "Blue", "ai_type": "mock"}
        ]

        # Patch the AI agent instantiation in the orchestrator
        # For simplicity in this test, we'll manually replace agents after orchestrator init
        self.orchestrator = GameOrchestrator(map_file=self.test_map_file, player_configs_override=self.player_configs)

        # Replace AI agents with our mock agents
        self.mock_agent_p1 = MockAIAgent("Player1", "Red")
        self.mock_agent_p2 = MockAIAgent("Player2", "Blue")

        self.orchestrator.ai_agents = {
            "Player1": self.mock_agent_p1,
            "Player2": self.mock_agent_p2
        }
        # Remap game players to these new mock AI agents
        self.orchestrator._map_game_players_to_ai_agents()

        self.game_engine = self.orchestrator.engine
        self.game_state = self.game_engine.game_state

        # Manually assign territories for predictable testing
        # Player1 gets A, B
        # Player2 gets C, D
        self.p1 = self.game_state.get_player_by_name("Player1")
        self.p2 = self.game_state.get_player_by_name("Player2")

        self.ta = self.game_state.territories["TerritoryA"]
        self.tb = self.game_state.territories["TerritoryB"]
        self.tc = self.game_state.territories["TerritoryC"]
        self.td = self.game_state.territories["TerritoryD"]

        self.ta.owner = self.p1
        self.ta.army_count = 5
        self.p1.territories = [self.ta]

        self.tb.owner = self.p1
        self.tb.army_count = 1
        self.p1.territories.append(self.tb)

        self.tc.owner = self.p2
        self.tc.army_count = 3
        self.p2.territories = [self.tc]

        self.td.owner = self.p2
        self.td.army_count = 3
        self.p2.territories.append(self.td)

        # Ensure all other territories are unassigned or assigned if map is larger
        # For this map, all are assigned.

        # Set initial turn and phase
        self.game_state.current_player_index = self.game_state.players.index(self.p1)
        self.game_state.current_game_phase = "FORTIFY"
        self.p1.has_fortified_this_turn = False
        self.p2.has_fortified_this_turn = False

        # Give P1 TerritoryC as well for non-adjacent test
        self.tc.owner = self.p1
        self.tc.army_count = 2
        self.p1.territories.append(self.tc)
        # Player2 now only has TerritoryD for simplicity in some tests if needed
        self.p2.territories = [self.td]


        # Ensure current player object is correctly fetched by orchestrator
        self.orchestrator.current_ai_context = {} # Reset context

    def tearDown(self):
        # Clean up the dummy map file
        if os.path.exists(self.test_map_file):
            os.remove(self.test_map_file)
        # Reset any global state if necessary (e.g. card trade bonus in engine)
        self.game_engine.card_trade_bonus_index = 0


    def _run_orchestrator_advance_until_ai_not_thinking_or_next_player(self, current_player_name, max_loops=10):
        """ Helper to advance game until AI is done or turn passes """
        loops = 0
        while loops < max_loops:
            self.orchestrator.advance_game_turn()
            if not self.orchestrator.ai_is_thinking or self.game_state.get_current_player().name != current_player_name:
                break
            loops += 1
        if loops >= max_loops:
            raise TimeoutError(f"Orchestrator still thinking or player {current_player_name} did not end turn after {max_loops} advances.")


    def test_fortify_successful_move(self):
        """Test a valid fortification move."""
        self.game_state.current_game_phase = "FORTIFY"
        self.p1.has_fortified_this_turn = False
        self.ta.army_count = 5 # Enough to move
        self.tb.army_count = 1

        # Mock AI action for Player1 to fortify from TerritoryA to TerritoryB
        action = {"type": "FORTIFY", "from": "TerritoryA", "to": "TerritoryB", "num_armies": 3}
        self.mock_agent_p1.set_next_action(action)

        # Orchestrator's turn: initiate fortify for P1
        self.orchestrator.advance_game_turn() # This should call _initiate_fortify_ai_action
        self.assertTrue(self.orchestrator.ai_is_thinking)

        # Orchestrator's turn: process P1's fortify action
        self.orchestrator.advance_game_turn() # This should call _process_fortify_ai_action
        self.assertFalse(self.orchestrator.ai_is_thinking) # AI should be done

        self.assertEqual(self.ta.army_count, 2) # 5 - 3 = 2
        self.assertEqual(self.tb.army_count, 4) # 1 + 3 = 4
        self.assertTrue(self.p1.has_fortified_this_turn)

        # Orchestrator's turn: should now end P1's turn and move to P2
        self.orchestrator.advance_game_turn()
        self.assertFalse(self.orchestrator.ai_is_thinking) # Should not be P1 thinking
        self.assertEqual(self.game_state.get_current_player(), self.p2)
        self.assertEqual(self.game_state.current_game_phase, "REINFORCE") # Next player starts with REINFORCE

    def test_fortify_choose_end_turn(self):
        """Test player chooses to end turn without fortifying."""
        self.game_state.current_game_phase = "FORTIFY"
        self.p1.has_fortified_this_turn = False
        initial_ta_armies = self.ta.army_count
        initial_tb_armies = self.tb.army_count

        action = {"type": "END_TURN"}
        self.mock_agent_p1.set_next_action(action)

        self.orchestrator.advance_game_turn() # Initiate
        self.assertTrue(self.orchestrator.ai_is_thinking)
        self.orchestrator.advance_game_turn() # Process
        self.assertFalse(self.orchestrator.ai_is_thinking)

        self.assertEqual(self.ta.army_count, initial_ta_armies) # No change
        self.assertEqual(self.tb.army_count, initial_tb_armies) # No change
        self.assertFalse(self.p1.has_fortified_this_turn) # Did not fortify

        self.orchestrator.advance_game_turn() # End turn
        self.assertEqual(self.game_state.get_current_player(), self.p2)
        self.assertEqual(self.game_state.current_game_phase, "REINFORCE")

    def test_fortify_already_fortified_must_end_turn(self):
        """Test if player already fortified, they can only end turn."""
        self.game_state.current_game_phase = "FORTIFY"
        self.p1.has_fortified_this_turn = True # Simulate already fortified

        # AI should be forced to END_TURN
        # The valid_actions should only contain END_TURN
        # MockAI will pick it if set_next_action isn't called, or we can explicitly set it.
        action = {"type": "END_TURN"}
        self.mock_agent_p1.set_next_action(action)

        # Orchestrator initiates fortify for P1
        self.orchestrator.advance_game_turn()
        self.assertTrue(self.orchestrator.ai_is_thinking)
        # Orchestrator processes P1's END_TURN action
        self.orchestrator.advance_game_turn()
        self.assertFalse(self.orchestrator.ai_is_thinking)

        self.assertTrue(self.p1.has_fortified_this_turn) # Still true

        # Orchestrator ends P1's turn
        self.orchestrator.advance_game_turn()
        self.assertEqual(self.game_state.get_current_player(), self.p2)

    def test_fortify_attempt_second_fortify_action_ignored(self):
        """Test AI tries to fortify again after already fortifying. Action should be ignored, turn ends."""
        self.game_state.current_game_phase = "FORTIFY"
        self.p1.has_fortified_this_turn = True # Simulate already fortified
        initial_ta_armies = self.ta.army_count
        initial_tb_armies = self.tb.army_count

        # AI tries to fortify again (this action should not be in valid_actions if already fortified)
        # However, if AI sends it, orchestrator should log and ignore, then end turn.
        action_bad_fortify = {"type": "FORTIFY", "from": "TerritoryA", "to": "TerritoryB", "num_armies": 1}
        self.mock_agent_p1.set_next_action(action_bad_fortify) # AI sends a bad action

        # Mock the get_valid_actions for this specific scenario to simulate AI having bad options
        # or the orchestrator correctly only offering END_TURN.
        # For this test, we assume the AI might send an action not in valid_actions if it's misbehaving.
        # The orchestrator's _process_fortify_ai_action should handle this gracefully.

        # What _get_valid_actions should return when player.has_fortified_this_turn is True:
        # [{'type': 'END_TURN'}]
        # If AI returns FORTIFY, _process_fortify_ai_action logs "attempted to FORTIFY again"

        self.orchestrator.advance_game_turn() # Initiate. AI will be asked for action.
        self.assertTrue(self.orchestrator.ai_is_thinking)

        self.orchestrator.advance_game_turn() # Process. AI's bad fortify action processed.
                                            # _process_fortify_ai_action logs and does nothing.
        self.assertFalse(self.orchestrator.ai_is_thinking)

        self.assertEqual(self.ta.army_count, initial_ta_armies) # No change
        self.assertEqual(self.tb.army_count, initial_tb_armies) # No change
        self.assertTrue(self.p1.has_fortified_this_turn) # Still true

        self.orchestrator.advance_game_turn() # End turn
        self.assertEqual(self.game_state.get_current_player(), self.p2)

    def test_fortify_invalid_move_not_enough_armies(self):
        """Test AI tries to fortify but not enough armies to leave one behind."""
        self.game_state.current_game_phase = "FORTIFY"
        self.p1.has_fortified_this_turn = False
        self.ta.army_count = 2 # Try to move 2, leaving 0 (invalid)
        self.tb.army_count = 1
        initial_ta_armies = self.ta.army_count
        initial_tb_armies = self.tb.army_count

        action = {"type": "FORTIFY", "from": "TerritoryA", "to": "TerritoryB", "num_armies": 2}
        self.mock_agent_p1.set_next_action(action)

        self.orchestrator.advance_game_turn() # Initiate
        self.assertTrue(self.orchestrator.ai_is_thinking)
        self.orchestrator.advance_game_turn() # Process
        self.assertFalse(self.orchestrator.ai_is_thinking)

        # Engine's perform_fortify should reject this.
        # Orchestrator's _process_fortify_ai_action logs the engine message.
        # Player's has_fortified_this_turn should remain False as no valid fortify occurred.
        self.assertEqual(self.ta.army_count, initial_ta_armies)
        self.assertEqual(self.tb.army_count, initial_tb_armies)
        self.assertFalse(self.p1.has_fortified_this_turn)

        self.orchestrator.advance_game_turn() # End turn
        self.assertEqual(self.game_state.get_current_player(), self.p2)

    def test_no_fortify_loop_occurs(self):
        """Test the main scenario that caused the loop: AI ends turn, game proceeds."""
        self.game_state.current_player_index = self.game_state.players.index(self.p1)
        self.game_state.current_game_phase = "FORTIFY"
        self.p1.has_fortified_this_turn = True # Start as if already fortified

        # AI will choose to END_TURN
        action_end_turn = {"type": "END_TURN"}
        self.mock_agent_p1.set_next_action(action_end_turn)

        # Simulate multiple calls to advance_game_turn to catch potential loops.
        # 1. Initiate fortify for P1
        self.orchestrator.advance_game_turn()
        self.assertTrue(self.orchestrator.ai_is_thinking, "AI should be thinking after first advance.")

        # 2. Process P1's END_TURN action
        self.orchestrator.advance_game_turn()
        self.assertFalse(self.orchestrator.ai_is_thinking, "AI should not be thinking after processing END_TURN.")
        # At this point, _process_fortify_ai_action has run.
        # The phase_when_action_was_initiated should be "FORTIFY" and action_processed_in_current_tick True.

        # 3. End P1's turn and move to P2
        self.orchestrator.advance_game_turn()
        # Crucial check: Game should have moved to Player2
        self.assertEqual(self.game_state.get_current_player(), self.p2, "Should be Player2's turn.")
        self.assertEqual(self.game_state.current_game_phase, "REINFORCE", "Phase should be REINFORCE for Player2.")
        self.assertFalse(self.orchestrator.ai_is_thinking, "AI should not be thinking at start of P2's REINFORCE.")

        # Check P1's state
        self.assertTrue(self.p1.has_fortified_this_turn, "P1's has_fortified_this_turn should remain True (from setup).")
        # After P1's turn ends and P2 starts, P1's has_fortified_this_turn should be reset by engine.next_turn()
        # This reset happens when P2's turn *starts* which means P1's turn *ended*.
        # So, when P1's turn *ends*, it's true. When P2's turn *begins*, P1's flag is then reset.
        # The engine's next_turn resets the *ending* player's flag.
        # Let's verify P1's flag after P2's turn is about to begin.
        # The next_turn() call that transitions from P1 to P2 will reset P1.has_fortified_this_turn.
        # So, by the time P2 is current player, P1.has_fortified_this_turn should be False.
        self.assertFalse(self.p1.has_fortified_this_turn, "P1's has_fortified_this_turn should be reset by engine.next_turn().")

    def test_fortify_fails_for_non_adjacent_connected_territories(self):
        """Test fortification fails if territories are not directly adjacent, even if connected by owned path."""
        # P1 owns A, B, C. A-B (adj), B-C (adj). A is NOT directly adjacent to C.
        # Setup: P1 owns TA, TB, TC. TA=5 armies, TB=1 army, TC=1 army.
        self.ta.owner = self.p1; self.ta.army_count = 5
        self.tb.owner = self.p1; self.tb.army_count = 1
        self.tc.owner = self.p1; self.tc.army_count = 1
        self.p1.territories = [self.ta, self.tb, self.tc]

        self.game_state.current_game_phase = "FORTIFY"
        self.p1.has_fortified_this_turn = False
        initial_ta_armies = self.ta.army_count
        initial_tc_armies = self.tc.army_count

        # 1. Check that get_valid_actions does not offer A->C
        valid_actions = self.game_engine.get_valid_actions(self.p1)
        can_fortify_A_to_C = any(
            a['type'] == 'FORTIFY' and a['from'] == 'TerritoryA' and a['to'] == 'TerritoryC'
            for a in valid_actions
        )
        self.assertFalse(can_fortify_A_to_C, "Should not be able to fortify from A to C (non-adjacent).")

        # 2. Simulate AI attempting this invalid fortify action anyway
        action_invalid_fortify = {"type": "FORTIFY", "from": "TerritoryA", "to": "TerritoryC", "num_armies": 2}
        self.mock_agent_p1.set_next_action(action_invalid_fortify)

        self.orchestrator.advance_game_turn() # Initiate
        self.assertTrue(self.orchestrator.ai_is_thinking)
        self.orchestrator.advance_game_turn() # Process
        self.assertFalse(self.orchestrator.ai_is_thinking)

        # Assert that the fortification did not happen
        self.assertEqual(self.ta.army_count, initial_ta_armies)
        self.assertEqual(self.tc.army_count, initial_tc_armies)
        self.assertFalse(self.p1.has_fortified_this_turn, "has_fortified_this_turn should be false after failed non-adjacent fortify.")

        # Assert turn still advances
        self.orchestrator.advance_game_turn() # End turn
        self.assertEqual(self.game_state.get_current_player(), self.p2)
        self.assertEqual(self.game_state.current_game_phase, "REINFORCE")

    def test_fortify_succeeds_for_directly_adjacent_territories(self):
        """Explicitly test fortification succeeds for directly adjacent territories."""
        # P1 owns A, B. A-B (adj).
        self.ta.owner = self.p1; self.ta.army_count = 5
        self.tb.owner = self.p1; self.tb.army_count = 1
        self.p1.territories = [self.ta, self.tb]
         # Remove TC from P1 for this specific test if it was added in setup
        if self.tc in self.p1.territories: self.p1.territories.remove(self.tc)
        self.tc.owner = self.p2 # Ensure TC is not P1's for this test

        self.game_state.current_game_phase = "FORTIFY"
        self.p1.has_fortified_this_turn = False

        # Check that get_valid_actions offers A->B
        valid_actions = self.game_engine.get_valid_actions(self.p1)
        can_fortify_A_to_B = any(
            a['type'] == 'FORTIFY' and a['from'] == 'TerritoryA' and a['to'] == 'TerritoryB'
            for a in valid_actions
        )
        self.assertTrue(can_fortify_A_to_B, "Should be able to fortify from A to B (adjacent).")

        action = {"type": "FORTIFY", "from": "TerritoryA", "to": "TerritoryB", "num_armies": 3}
        self.mock_agent_p1.set_next_action(action)

        self.orchestrator.advance_game_turn() # Initiate
        self.assertTrue(self.orchestrator.ai_is_thinking)
        self.orchestrator.advance_game_turn() # Process
        self.assertFalse(self.orchestrator.ai_is_thinking)

        self.assertEqual(self.ta.army_count, 2)
        self.assertEqual(self.tb.army_count, 4)
        self.assertTrue(self.p1.has_fortified_this_turn)

        self.orchestrator.advance_game_turn() # End turn
        self.assertEqual(self.game_state.get_current_player(), self.p2)


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

# To run this test:
# Ensure map_config.json exists or is not needed by orchestrator if map_file is specified.
# python -m unittest llm_risk.tests.test_fortify_phase
# Or from the root directory: python -m unittest discover llm_risk/tests
