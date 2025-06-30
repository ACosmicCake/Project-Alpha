import unittest
import json
from llm_risk.game_engine.engine import GameEngine
from llm_risk.game_engine.data_structures import Player, GameState, Territory

class TestGameVariations(unittest.TestCase):

    def setUp(self):
        self.map_file_42 = "test_map_config_42.json" # Assuming this exists from previous test setup
        # Ensure the map file is created if it doesn't exist for isolated test runs
        map_data_42 = {"continents": [], "territories": {}}
        continent_counter = 0
        for i in range(7): # 7 continents
            continent_name = f"Continent{chr(ord('A')+i)}"
            map_data_42["continents"].append({"name": continent_name, "bonus_armies": 2})
            for j in range(6): # 6 territories per continent
                terr_name = f"T{i*6 + j + 1}"
                # Create some basic adjacencies for attack tests
                adj = []
                if j > 0: adj.append(f"T{i*6 + j}") # Adj to previous in same continent
                if i > 0 and j ==0 : adj.append(f"T{(i-1)*6 + j + 1}") # Adj to first of prev continent
                map_data_42["territories"][terr_name] = {"continent": continent_name, "adjacent_to": adj}
        try:
            with open(self.map_file_42, 'w') as f:
                json.dump(map_data_42, f, indent=2)
        except IOError:
            pass # File already exists or cannot write

        self.engine = GameEngine(map_file_path=self.map_file_42)
        self.players_data_2p = [{"name": "P1", "color": "Red"}, {"name": "P2", "color": "Blue"}]

    def _setup_basic_2p_game_post_territory_claim(self) -> GameState:
        """Helper to setup a 2-player game after initial territories are claimed."""
        self.engine.initialize_game_from_map(self.players_data_2p, is_two_player_game=True)
        self.engine.setup_two_player_initial_territory_assignment() # Assigns 14 territories each
        gs = self.engine.game_state
        # For simplicity in attack tests, let's give players a few more armies on specific territories
        p1 = next(p for p in gs.players if p.name == "P1")
        p2 = next(p for p in gs.players if p.name == "P2")
        neutral_p = next(p for p in gs.players if p.is_neutral)

        if p1.territories: p1.territories[0].army_count = 5
        if neutral_p.territories: neutral_p.territories[0].army_count = 3

        # Ensure adjacency for a test attack
        # Let P1's first territory be adjacent to Neutral's first territory
        if p1.territories and neutral_p.territories:
            p1_t0 = p1.territories[0]
            n_t0 = neutral_p.territories[0]
            if n_t0 not in p1_t0.adjacent_territories:
                p1_t0.adjacent_territories.append(n_t0)
            if p1_t0 not in n_t0.adjacent_territories:
                n_t0.adjacent_territories.append(p1_t0)
        return gs

    def test_2p_neutral_defense_attack(self):
        gs = self._setup_basic_2p_game_post_territory_claim()
        p1 = next(p for p in gs.players if p.name == "P1")
        neutral_p = next(p for p in gs.players if p.is_neutral)

        attacker_terr = p1.territories[0] # Has 5 armies
        defender_terr = neutral_p.territories[0] # Has 3 armies

        # P1 attacks Neutral's territory. P2 (other human) decides neutral defense dice.
        # Assume P2 chooses to roll 2 dice for neutral.
        explicit_defender_dice = 2

        # Ensure defender_terr has enough armies for explicit_defender_dice
        defender_terr.army_count = 3 # Ensure it has at least 2 for 2 dice
        initial_defender_armies = defender_terr.army_count
        initial_attacker_armies = attacker_terr.army_count

        log = self.engine.perform_attack(
            attacker_terr.name,
            defender_terr.name,
            num_attacking_armies=3, # P1 uses 3 armies (will roll 3 dice)
            explicit_defender_dice_count=explicit_defender_dice
        )

        self.assertTrue("error" not in log, log.get("error", "No error message"))
        self.assertTrue(log.get("defender_is_neutral"))
        self.assertEqual(log.get("actual_defender_dice_count"), explicit_defender_dice)
        # Further assertions on army counts would depend on random dice rolls,
        # so we mainly check the setup and that the explicit dice count was acknowledged.
        self.assertLessEqual(defender_terr.army_count, initial_defender_armies)
        self.assertLessEqual(attacker_terr.army_count, initial_attacker_armies)

    def test_2p_reinforcements(self):
        gs = self._setup_basic_2p_game_post_territory_claim() # P1, P2, Neutral have 14 terr each
        p1 = next(p for p in gs.players if p.name == "P1")
        p2 = next(p for p in gs.players if p.name == "P2")
        neutral_p = next(p for p in gs.players if p.is_neutral)

        # P1 has 14 territories -> 14/3 = 4 armies (min 3)
        self.assertEqual(self.engine.calculate_reinforcements(p1)[0], 4)
        # P2 has 14 territories -> 4 armies
        self.assertEqual(self.engine.calculate_reinforcements(p2)[0], 4)
        # Neutral player gets 0
        self.assertEqual(self.engine.calculate_reinforcements(neutral_p)[0], 0)

    def test_2p_next_turn(self):
        gs = self._setup_basic_2p_game_post_territory_claim()
        # Assume P1 is current player (index might vary based on gs.players internal order)
        p1 = next(p for p in gs.players if p.name == "P1")
        p2 = next(p for p in gs.players if p.name == "P2")

        try:
            gs.current_player_index = gs.players.index(p1)
        except ValueError:
            self.fail("P1 not found in game state players list")

        self.engine.next_turn()
        current_player_after_next = gs.get_current_player()
        self.assertIsNotNone(current_player_after_next)
        self.assertEqual(current_player_after_next.name, p2.name, "Next turn should go to P2")
        self.assertFalse(current_player_after_next.is_neutral)

        self.engine.next_turn()
        current_player_after_next_2 = gs.get_current_player()
        self.assertIsNotNone(current_player_after_next_2)
        self.assertEqual(current_player_after_next_2.name, p1.name, "Next turn should go back to P1")
        self.assertFalse(current_player_after_next_2.is_neutral)

    def test_2p_game_over_by_elimination(self):
        gs = self._setup_basic_2p_game_post_territory_claim()
        p1 = next(p for p in gs.players if p.name == "P1")
        p2 = next(p for p in gs.players if p.name == "P2")

        # Simulate P1 losing all territories
        for t in list(p1.territories): # Iterate over a copy for safe removal
            t.owner = p2
            p2.territories.append(t)
            p1.territories.remove(t)

        self.assertEqual(len(p1.territories), 0)
        winner = self.engine.is_game_over()
        self.assertIsNotNone(winner)
        self.assertEqual(winner.name, p2.name)

        # Reset: Simulate P2 losing all territories to P1
        gs = self._setup_basic_2p_game_post_territory_claim() # Fresh state
        p1 = next(p for p in gs.players if p.name == "P1")
        p2 = next(p for p in gs.players if p.name == "P2")
        for t in list(p2.territories):
            t.owner = p1
            p1.territories.append(t)
            p2.territories.remove(t)

        self.assertEqual(len(p2.territories), 0)
        winner2 = self.engine.is_game_over()
        self.assertIsNotNone(winner2)
        self.assertEqual(winner2.name, p1.name)


if __name__ == '__main__':
    unittest.main()
