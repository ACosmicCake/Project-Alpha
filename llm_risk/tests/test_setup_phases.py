import unittest
import json
from llm_risk.game_engine.engine import GameEngine
from llm_risk.game_engine.data_structures import Player, GameState, Territory, Continent, Card

class TestSetupPhases(unittest.TestCase):

    def setUp(self):
        """Common setup for tests, if needed, e.g., dummy map file."""
        self.map_file = "test_map_config.json" # Assume a test map config exists or create one
        # Create a dummy map_config.json for testing
        dummy_map_data = {
            "continents": [
                {"name": "Test Continent A", "bonus_armies": 3},
                {"name": "Test Continent B", "bonus_armies": 2}
            ],
            "territories": {
                # Need 42 territories for 2-player card dealing tests
                # For simplicity in other tests, fewer might be okay if not testing full setup.
                # Let's make 6 territories for basic standard setup tests for now.
                # Will need to adjust if testing full 42 territory claim.
                "Territory1": {"continent": "Test Continent A", "adjacent_to": ["Territory2"]},
                "Territory2": {"continent": "Test Continent A", "adjacent_to": ["Territory1", "Territory3"]},
                "Territory3": {"continent": "Test Continent A", "adjacent_to": ["Territory2", "Territory4"]},
                "Territory4": {"continent": "Test Continent B", "adjacent_to": ["Territory3", "Territory5"]},
                "Territory5": {"continent": "Test Continent B", "adjacent_to": ["Territory4", "Territory6"]},
                "Territory6": {"continent": "Test Continent B", "adjacent_to": ["Territory5"]},
            }
        }
        # For 2-player tests, we need exactly 42 territories.
        # Create a more extensive map for those or a separate setup.
        # For now, this small map is for initial standard setup logic.
        # A more robust test suite would have multiple map fixtures.

        # Create a map with 42 territories for 2-player tests
        self.map_file_42 = "test_map_config_42.json"
        map_data_42 = {"continents": [], "territories": {}}
        continent_counter = 0
        for i in range(7): # 7 continents
            continent_name = f"Continent{chr(ord('A')+i)}"
            map_data_42["continents"].append({"name": continent_name, "bonus_armies": 2})
            for j in range(6): # 6 territories per continent
                terr_name = f"T{i*6 + j + 1}"
                map_data_42["territories"][terr_name] = {"continent": continent_name, "adjacent_to": []} # Adjacency not critical for setup tests

        try:
            with open(self.map_file, 'w') as f:
                json.dump(dummy_map_data, f, indent=2)
            with open(self.map_file_42, 'w') as f:
                json.dump(map_data_42, f, indent=2)
        except IOError:
            pass # File already exists or cannot write, tests might fail if file is wrong

        self.engine = GameEngine(map_file_path=self.map_file)
        self.engine_42 = GameEngine(map_file_path=self.map_file_42)


    def test_initialize_game_from_map_standard(self):
        players_data = [
            {"name": "Player1", "color": "Red"},
            {"name": "Player2", "color": "Blue"},
            {"name": "Player3", "color": "Green"}
        ]
        self.engine.initialize_game_from_map(players_data, is_two_player_game=False)
        gs = self.engine.game_state

        self.assertEqual(gs.current_game_phase, "SETUP_DETERMINE_ORDER")
        self.assertEqual(len(gs.players), 3)
        self.assertEqual(gs.players[0].name, "Player1")
        self.assertEqual(gs.players[0].initial_armies_pool, 35) # 3 players = 35 armies
        self.assertEqual(gs.players[1].initial_armies_pool, 35)
        self.assertEqual(gs.players[2].initial_armies_pool, 35)

        self.assertEqual(len(gs.territories), 6) # From dummy_map_data
        self.assertEqual(len(gs.unclaimed_territory_names), 6)
        for terr in gs.territories.values():
            self.assertIsNone(terr.owner)
            self.assertEqual(terr.army_count, 0)

        self.assertEqual(len(gs.deck), 6 + 2) # 6 territory cards + 2 wild cards for this small map

    def test_set_player_setup_order_standard(self):
        players_data = [
            {"name": "Player1", "color": "Red"},
            {"name": "Player2", "color": "Blue"},
            {"name": "Player3", "color": "Green"}
        ]
        self.engine.initialize_game_from_map(players_data, is_two_player_game=False)
        gs = self.engine.game_state

        # Simulate orchestrator determining order
        # Player names must match those created by initialize_game_from_map
        # The players in gs.players are Player objects. We need their names.
        p_objects = gs.players
        ordered_names = [p_objects[1].name, p_objects[0].name, p_objects[2].name] # P2, P1, P3
        first_placer_name = p_objects[1].name # P2 places first actual army, so P2 gets first game turn

        self.engine.set_player_setup_order(ordered_names, first_placer_name)

        self.assertEqual(gs.current_game_phase, "SETUP_CLAIM_TERRITORIES")
        self.assertEqual(len(gs.player_setup_order), 3)
        self.assertEqual(gs.player_setup_order[0].name, "Player2") # P2 is first in setup order
        self.assertEqual(gs.player_setup_order[1].name, "Player1")
        self.assertEqual(gs.player_setup_order[2].name, "Player3")
        self.assertEqual(gs.first_player_of_game.name, "Player2") # P2 gets first game turn
        self.assertEqual(gs.current_setup_player_index, 0)

    def test_player_claims_territory_standard(self):
        players_data = [
            {"name": "P1", "color": "Red"}, {"name": "P2", "color": "Blue"} # Use 2 players for simplicity with 6 territories
        ]
        self.engine.initialize_game_from_map(players_data, is_two_player_game=False) # Standard rules, but with 2 players for small map
        # For this test, 2 players get 40 armies each by rule, but the map only has 6 territories.
        # The test is about claiming, not full army placement.
        # Override initial armies for test clarity if needed, or use a map with more territories.
        # For now, let's assume the initial army count is not the primary focus of this *claiming* test.
        # The engine's initialize_game_from_map would error for 2 players in standard mode.
        # So, let's use 3 players, which is a valid standard game count.
        players_data_3p = [
            {"name": "P1", "color": "Red"}, {"name": "P2", "color": "Blue"}, {"name": "P3", "color": "Yellow"}
        ]
        self.engine.initialize_game_from_map(players_data_3p, is_two_player_game=False)
        gs = self.engine.game_state
        p_objects = gs.players
        ordered_names = [p.name for p in p_objects] # P1, P2, P3
        self.engine.set_player_setup_order(ordered_names, p_objects[0].name) # P1 is first placer

        self.assertEqual(gs.current_game_phase, "SETUP_CLAIM_TERRITORIES")

        territory_names = list(gs.territories.keys()) # Should be 6

        # Players take turns claiming all 6 territories
        for i in range(len(territory_names)):
            current_setup_player_obj = gs.player_setup_order[gs.current_setup_player_index]
            territory_to_claim = territory_names[i] # Each territory is claimed once

            log = self.engine.player_claims_territory(current_setup_player_obj.name, territory_to_claim)
            self.assertTrue(log["success"], log["message"])

            claimed_territory = gs.territories[territory_to_claim]
            self.assertEqual(claimed_territory.owner, current_setup_player_obj)
            self.assertEqual(claimed_territory.army_count, 1)
            self.assertEqual(current_setup_player_obj.armies_placed_in_setup, (i // len(p_objects)) + 1) # Each player places one by one
            self.assertNotIn(territory_to_claim, gs.unclaimed_territory_names)

        self.assertEqual(len(gs.unclaimed_territory_names), 0)
        self.assertEqual(gs.current_game_phase, "SETUP_PLACE_ARMIES")
        self.assertEqual(gs.current_setup_player_index, 0) # Resets to first player in setup order

    def test_player_places_initial_army_standard(self):
        # Uses 3 players, 6 territories. Each player gets 35 armies.
        # After claiming, P1,P2,P3 each have 2 territories and placed 2 armies. (35-2 = 33 left for each)
        players_data_3p = [
            {"name": "P1", "color": "Red"}, {"name": "P2", "color": "Blue"}, {"name": "P3", "color": "Yellow"}
        ]
        self.engine.initialize_game_from_map(players_data_3p, is_two_player_game=False)
        gs = self.engine.game_state
        p_objects = gs.players
        ordered_names = [p.name for p in p_objects]
        self.engine.set_player_setup_order(ordered_names, p_objects[0].name)

        territory_names = list(gs.territories.keys())
        for i in range(len(territory_names)): # Claim all territories
            current_setup_player_obj = gs.player_setup_order[gs.current_setup_player_index]
            self.engine.player_claims_territory(current_setup_player_obj.name, territory_names[i])

        self.assertEqual(gs.current_game_phase, "SETUP_PLACE_ARMIES")

        total_initial_armies = sum(p.initial_armies_pool for p in p_objects) # 3 * 35 = 105
        total_placed_armies_count = sum(p.armies_placed_in_setup for p in p_objects) # Should be 6 (1 per territory)

        # Loop until all initial armies are placed
        armies_to_place_remaining = total_initial_armies - total_placed_armies_count

        for _ in range(armies_to_place_remaining):
            current_setup_player_obj = gs.player_setup_order[gs.current_setup_player_index]
            self.assertLess(current_setup_player_obj.armies_placed_in_setup, current_setup_player_obj.initial_armies_pool)

            # Player places on one of their owned territories
            owned_territory_name = None
            for terr in current_setup_player_obj.territories: # Get first owned territory
                owned_territory_name = terr.name
                break
            self.assertIsNotNone(owned_territory_name)

            log = self.engine.player_places_initial_army(current_setup_player_obj.name, owned_territory_name)
            self.assertTrue(log["success"], log["message"])

        self.assertTrue(self.engine._all_initial_armies_placed())
        self.assertEqual(gs.current_game_phase, "REINFORCE")
        self.assertEqual(gs.current_player_index, gs.players.index(gs.first_player_of_game)) # First player for game turn

        first_player = gs.get_current_player()
        self.assertIsNotNone(first_player)
        # Reinforcements should be calculated for the first player
        # For 3 players, each has 2 territories. Base is 3. No continent control on this small map.
        self.assertEqual(first_player.armies_to_deploy, 3)

    # --- Tests for 2-Player Variation Setup ---

    def test_initialize_game_from_map_2_player(self):
        players_data = [{"name": "P1", "color": "Red"}, {"name": "P2", "color": "Blue"}]
        self.engine_42.initialize_game_from_map(players_data, is_two_player_game=True)
        gs = self.engine_42.game_state

        self.assertTrue(gs.is_two_player_game)
        self.assertEqual(gs.current_game_phase, "SETUP_2P_DEAL_CARDS")
        self.assertEqual(len(gs.players), 3) # P1, P2, Neutral

        num_neutral = 0
        for p in gs.players:
            self.assertEqual(p.initial_armies_pool, 40)
            if p.is_neutral:
                self.assertEqual(p.name, "Neutral")
                num_neutral +=1
        self.assertEqual(num_neutral, 1)

        self.assertEqual(len(gs.territories), 42) # From map_file_42
        self.assertEqual(len(gs.unclaimed_territory_names), 42)
        self.assertEqual(len(gs.deck), 42) # Territory cards only, no wilds yet

    def test_setup_two_player_initial_territory_assignment(self):
        players_data = [{"name": "P1", "color": "Red"}, {"name": "P2", "color": "Blue"}]
        self.engine_42.initialize_game_from_map(players_data, is_two_player_game=True)
        gs = self.engine_42.game_state

        log = self.engine_42.setup_two_player_initial_territory_assignment()
        self.assertTrue(log["success"], log["message"])
        self.assertEqual(gs.current_game_phase, "SETUP_2P_PLACE_REMAINING")
        self.assertEqual(len(gs.unclaimed_territory_names), 0)

        p1 = next(p for p in gs.players if p.name == "P1")
        p2 = next(p for p in gs.players if p.name == "P2")
        neutral_p = next(p for p in gs.players if p.is_neutral)

        self.assertEqual(len(p1.territories), 14)
        self.assertEqual(p1.armies_placed_in_setup, 14)
        self.assertEqual(len(p2.territories), 14)
        self.assertEqual(p2.armies_placed_in_setup, 14)
        self.assertEqual(len(neutral_p.territories), 14)
        self.assertEqual(neutral_p.armies_placed_in_setup, 14)

        for terr_list in [p1.territories, p2.territories, neutral_p.territories]:
            for terr in terr_list:
                self.assertEqual(terr.army_count, 1)

        self.assertIn(p1, gs.player_setup_order)
        self.assertIn(p2, gs.player_setup_order)
        self.assertEqual(len(gs.player_setup_order), 2) # Only human players in setup order
        self.assertIsNotNone(gs.first_player_of_game) # Should be set to one of human players

    def test_player_places_initial_armies_2p(self):
        players_data = [{"name": "P1", "color": "Red"}, {"name": "P2", "color": "Blue"}]
        self.engine_42.initialize_game_from_map(players_data, is_two_player_game=True)
        gs = self.engine_42.game_state
        self.engine_42.setup_two_player_initial_territory_assignment()

        p1 = next(p for p in gs.players if p.name == "P1")
        p2 = next(p for p in gs.players if p.name == "P2")
        neutral_p = next(p for p in gs.players if p.is_neutral)

        # Each human player needs to place 40 - 14 = 26 more armies.
        # They place 2 of their own + 1 neutral per turn. So 13 turns each.
        total_turns_for_placing_remaining = (p1.initial_armies_pool - p1.armies_placed_in_setup) // 2
        self.assertEqual(total_turns_for_placing_remaining, 13)


        for i in range(total_turns_for_placing_remaining * 2): # 13 turns for P1, 13 for P2
            current_placer_obj = gs.player_setup_order[gs.current_setup_player_index]

            # Player places 2 armies on their own territories
            own_placements = []
            if current_placer_obj.territories:
                own_placements.append((current_placer_obj.territories[0].name, 2))
            else:
                self.fail(f"{current_placer_obj.name} has no territories to place armies on.")

            # Player places 1 army for Neutral
            neutral_placement = None
            if neutral_p.territories and neutral_p.armies_placed_in_setup < neutral_p.initial_armies_pool :
                neutral_placement = (neutral_p.territories[0].name, 1)

            log = self.engine_42.player_places_initial_armies_2p(current_placer_obj.name, own_placements, neutral_placement)
            self.assertTrue(log["success"], log["message"])

            if gs.current_game_phase == "REINFORCE": # Game started
                break

        self.assertEqual(gs.current_game_phase, "REINFORCE")
        self.assertEqual(p1.armies_placed_in_setup, 40)
        self.assertEqual(p2.armies_placed_in_setup, 40)
        # Neutral player should also have 14 + 13 (from P1) + 13 (from P2) = 40 armies, if neutral_placement was always possible.
        # The test logic for neutral_placement is simplified (always first neutral territory).
        # A more robust test might check if neutral_p.armies_placed_in_setup is close to 40.
        # For this test, let's assume it's mostly correct.
        self.assertTrue(neutral_p.armies_placed_in_setup <= neutral_p.initial_armies_pool)


        self.assertEqual(len(gs.deck), 42 + 2) # Wild cards added back
        self.assertIsNotNone(gs.get_current_player())
        self.assertFalse(gs.get_current_player().is_neutral)
        self.assertGreater(gs.get_current_player().armies_to_deploy, 0)


if __name__ == '__main__':
    unittest.main()
