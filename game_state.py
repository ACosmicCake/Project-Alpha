"""
Manages the dynamic state of the Risk game.
"""
from map_data import TERRITORIES, PLAYER_COLORS

class Player:
    def __init__(self, player_id, name, color, player_type="human"): # Added player_type
        self.id = player_id
        self.name = name
        self.color = color # This will be an RGB or RGBA tuple
        self.player_type = player_type # "human" or "ai_easy", "ai_normal" etc.
        self.cards = [] # List of Risk cards
        self.reinforcements_to_place = 0

    def __repr__(self):
        return f"Player(id={self.id}, name='{self.name}', type='{self.player_type}')"

class GameState:
    def __init__(self):
        self.players = [] # List of Player objects
        self.current_player_index = 0
        # Game phases: SETUP_CLAIM, SETUP_REINFORCE, REINFORCE, ATTACK, FORTIFY, GAME_OVER
        self.current_phase = "SETUP_CLAIM"
        self.reinforcements_available_for_player = 0

        # Attack phase state
        self.selected_attacker_tid = None
        self.selected_defender_tid = None
        self.attack_dice_results = {"attacker": [], "defender": []}
        self.combat_results_message = ""

        # Fortify phase state
        self.selected_fortify_source_tid = None
        self.selected_fortify_dest_tid = None
        self.fortification_complete_this_turn = False
        self.fortify_message = ""
        self.active_players = [] # List of player IDs who are still in the game - For turn cycling

        self.territories_state = TERRITORIES

        self.game_over = False
        self.winner = None # Player object
        self.turn_log = []

    def add_player(self, player_id, name, player_type="human"): # Added player_type
        if len(self.players) < len(PLAYER_COLORS):
            color = PLAYER_COLORS[len(self.players)]
            player = Player(player_id, name, color, player_type) # Pass player_type
            self.players.append(player)
            if player.id not in self.active_players:
                self.active_players.append(player.id)
            self.log_action(f"Added Player {len(self.players)}: {name} ({player_type.capitalize()}) with ID {player_id}")
            return player
        else:
            print("Maximum number of players reached.")
            return None

    def get_player_by_id(self, player_id):
        for player in self.players:
            if player.id == player_id:
                return player
        return None

    def get_current_player(self):
        if self.game_over or not self.active_players:
            return None
        # current_player_index should always be valid for active_players list
        player_id = self.active_players[self.current_player_index]
        return self.get_player_by_id(player_id)

    def next_player(self):
        if self.game_over or not self.active_players:
            return

        self.current_player_index = (self.current_player_index + 1) % len(self.active_players)
        new_player = self.get_current_player()

        if new_player:
            self.log_action(f"--- {new_player.name}'s Turn ---")
        else: # Should ideally be caught by game_over check before calling next_player
            self.log_action("Error: No active player found for next turn. Checking game over.")
            self.check_for_game_over()


    def set_phase(self, phase_name):
        if self.game_over: # Don't change phase if game is over
            return

        self.current_phase = phase_name
        self.log_action(f"Phase: {phase_name}") # Shortened log
        if phase_name == "REINFORCE":
            self.calculate_reinforcements_for_current_player()
            self.fortification_complete_this_turn = False
            self.clear_fortify_selection()
        elif phase_name == "ATTACK":
            self.clear_attack_selection()
        elif phase_name == "FORTIFY":
            self.clear_fortify_selection()

    def calculate_reinforcements_for_current_player(self):
        player = self.get_current_player()
        if not player or self.game_over: # Added game_over check
            self.reinforcements_available_for_player = 0
            return

        owned_territories_count = sum(1 for data in self.territories_state.values() if data["owner"] == player.id)

        # If player has 0 territories but is somehow still in active_players list (should not happen if elimination is correct)
        if owned_territories_count == 0 and player.id in self.active_players:
            self.log_action(f"Player {player.name} has 0 territories, removing from active players.")
            self.handle_player_elimination(player.id) # This will re-check game over
            self.reinforcements_available_for_player = 0
            # Potentially advance to next player if current player got eliminated before their turn really started
            # This might need careful handling if next_player() is called immediately after this.
            return

        reinforcements = max(3, owned_territories_count // 3)

        # 2. Continent bonuses
        # Need to import CONTINENTS from map_data
        from map_data import CONTINENTS
        for cont_id, cont_data in CONTINENTS.items():
            is_owner_of_all = True
            if not cont_data["territories"]: # Skip if continent has no territories defined
                is_owner_of_all = False
            else:
                for terr_id_in_cont in cont_data["territories"]:
                    if terr_id_in_cont not in self.territories_state or \
                       self.territories_state[terr_id_in_cont]["owner"] != player.id:
                        is_owner_of_all = False
                        break
            if is_owner_of_all:
                reinforcements += cont_data["bonus_armies"]

        self.reinforcements_available_for_player = reinforcements
        player.reinforcements_to_place = reinforcements # Also store on player if needed for other logic
        self.log_action(f"Player {player.name} gets {reinforcements} reinforcements.")

    def assign_territory_owner(self, territory_id, player_id, num_armies=1):
        if territory_id in self.territories_state:
            player = self.get_player_by_id(player_id)
            if player:
                self.territories_state[territory_id]["owner"] = player_id
                self.territories_state[territory_id]["armies"] = num_armies
                # self.log_action(f"Territory {self.territories_state[territory_id]['name']} assigned to Player {player.name} with {num_armies} army/ies.")
            else:
                print(f"Error: Player ID {player_id} not found.")
        else:
            print(f"Error: Territory ID {territory_id} not found.")

    def update_armies(self, territory_id, new_army_count):
        if territory_id in self.territories_state:
            self.territories_state[territory_id]["armies"] = new_army_count
            # self.log_action(f"Armies in {self.territories_state[territory_id]['name']} updated to {new_army_count}.")
        else:
            print(f"Error: Territory ID {territory_id} not found during army update.")

    def get_territory_owner_color(self, territory_id):
        if territory_id in self.territories_state:
            owner_id = self.territories_state[territory_id].get("owner")
            if owner_id:
                owner_player = self.get_player_by_id(owner_id)
                if owner_player:
                    return owner_player.color
        return None # Or a default color for unowned territories

    def log_action(self, action_description):
        self.turn_log.append(action_description)
        print(action_description)

    def clear_attack_selection(self):
        self.selected_attacker_tid = None
        self.selected_defender_tid = None
        self.attack_dice_results = {"attacker": [], "defender": []}
        self.combat_results_message = ""

    def resolve_attack(self):
        if not self.selected_attacker_tid or not self.selected_defender_tid:
            self.combat_results_message = "Attacker or defender not selected."
            self.log_action(self.combat_results_message)
            return

        attacker_data = self.territories_state[self.selected_attacker_tid]
        defender_data = self.territories_state[self.selected_defender_tid]
        current_player = self.get_current_player()

        if attacker_data["owner"] != current_player.id:
            self.combat_results_message = "Attacker territory not owned by current player."
            self.log_action(self.combat_results_message)
            return
        if defender_data["owner"] == current_player.id:
            self.combat_results_message = "Cannot attack own territory."
            self.log_action(self.combat_results_message)
            return
        if attacker_data["armies"] <= 1:
            self.combat_results_message = "Attacking territory must have more than 1 army."
            self.log_action(self.combat_results_message)
            return

        # Simplified dice rolling (Step 5.3)
        # Attacker: min 1, max 3 dice. Max dice = armies - 1.
        num_attacker_dice = min(3, attacker_data["armies"] - 1)
        if num_attacker_dice == 0 : # Should be caught by armies <=1 check, but as safety
            self.combat_results_message = "Attacker has no armies to attack with."
            self.log_action(self.combat_results_message)
            return

        # Defender: min 1, max 2 dice. Max dice = armies.
        num_defender_dice = min(2, defender_data["armies"])
        if num_defender_dice == 0: # Defender has no armies
             self.combat_results_message = "Defender has no armies (should have been captured already)." # Should not happen if capture logic is correct
             self.log_action(self.combat_results_message)
             # This case should ideally lead to immediate capture if not already handled.
             # For now, we'll assume it means the defender was already eliminated in a prior step.
             self.capture_territory(self.selected_attacker_tid, self.selected_defender_tid, num_attacker_dice)
             return


        import random
        attacker_rolls = sorted([random.randint(1, 6) for _ in range(num_attacker_dice)], reverse=True)
        defender_rolls = sorted([random.randint(1, 6) for _ in range(num_defender_dice)], reverse=True)
        self.attack_dice_results = {"attacker": attacker_rolls, "defender": defender_rolls}

        attacker_losses = 0
        defender_losses = 0

        self.log_action(f"Attack: {attacker_data['name']} ({attacker_rolls}) vs {defender_data['name']} ({defender_rolls})")

        comparisons = min(len(attacker_rolls), len(defender_rolls))
        for i in range(comparisons):
            if attacker_rolls[i] > defender_rolls[i]:
                defender_losses += 1
            else: # Defender wins on ties
                attacker_losses += 1

        attacker_data["armies"] -= attacker_losses
        defender_data["armies"] -= defender_losses

        self.combat_results_message = (
            f"Attacker lost {attacker_losses} army/ies. Defender lost {defender_losses} army/ies.\n"
            f"{attacker_data['name']} has {attacker_data['armies']}. {defender_data['name']} has {defender_data['armies']}."
        )
        self.log_action(self.combat_results_message)

        # Territory Capture (Step 5.4)
        if defender_data["armies"] <= 0:
            self.capture_territory(self.selected_attacker_tid, self.selected_defender_tid, num_attacker_dice)

        # After combat, if attacker has no more armies to attack FROM this territory, clear selection.
        if attacker_data["armies"] <= 1:
            self.log_action(f"{attacker_data['name']} can no longer attack from this territory.")
            self.clear_attack_selection()


    def capture_territory(self, attacker_tid, defender_tid, num_dice_rolled_by_attacker):
        attacker_data = self.territories_state[attacker_tid]
        defender_data = self.territories_state[defender_tid]
        attacking_player = self.get_player_by_id(attacker_data["owner"])

        defender_name = defender_data['name'] # Store name before owner changes
        original_defender_owner_id = defender_data['owner']


        self.log_action(f"Player {attacking_player.name} captured {defender_name} from Player {original_defender_owner_id}!")
        defender_data["owner"] = attacking_player.id

        # Attacker must move in at least num_dice_rolled (min 1), but not more than available attacking armies -1
        armies_to_move = min(max(1, num_dice_rolled_by_attacker), attacker_data["armies"] - 1)

        if attacker_data["armies"] - armies_to_move < 1: # Must leave at least 1 army
            armies_to_move = attacker_data["armies"] - 1 # Move all but one

        if armies_to_move < 1 and attacker_data["armies"] > 0 : # if only 1 army left, it must move.
             armies_to_move = 1 # This case is tricky if attacker_data["armies"] was 1 to begin with.
                                # The initial check attacker_data["armies"] <=1 should prevent attacking.
                                # If attacker_data["armies"] becomes 1 due to losses, then armies_to_move is 0.
                                # This part of logic might need more refinement for edge cases.
                                # For simplified: if capture, move 1.

        # Simplified: move 1 army for now if capture. Can be expanded for player choice.
        # Let's stick to the rule: move armies equal to dice rolled, ensuring attacker_tid has at least 1 left.
        # armies_to_move was calculated above.

        if armies_to_move > 0 :
            defender_data["armies"] = armies_to_move
            attacker_data["armies"] -= armies_to_move
            self.log_action(f"{attacking_player.name} moved {armies_to_move} army/ies into {defender_name}.")
        else: # This means attacker had only 1 army left after winning, which is unusual but could happen if they lost all but 1 dice in the attack
              # Or if num_dice_rolled was 0 (which shouldn't happen).
              # Default to moving 1 if the above logic fails to produce a positive number to move.
            if attacker_data["armies"] > 0: # if attacker still has armies
                 defender_data["armies"] = 1
                 attacker_data["armies"] -=1
                 self.log_action(f"{attacking_player.name} moved 1 army into {defender_name} (default capture move).")
            else: # Attacker somehow lost all armies, this is an error state.
                 defender_data["armies"] = 0 # Defender is still captured but with 0 armies.
                 self.log_action(f"Error: Attacker has 0 armies after capturing {defender_name}.")


        # Check for player elimination (simplified)
        if original_defender_owner_id: # If it was owned (not unassigned)
            self.handle_player_elimination(original_defender_owner_id) # Call new method

        self.clear_attack_selection()
        self.check_for_game_over() # Check game over after any capture

    def handle_player_elimination(self, player_id_to_check):
        """Checks if a player is eliminated and updates active_players list."""
        if self.game_over or player_id_to_check not in self.active_players:
            return # Already eliminated or game is over

        player_still_has_territories = any(
            t["owner"] == player_id_to_check for t in self.territories_state.values()
        )
        if not player_still_has_territories:
            eliminated_player_obj = self.get_player_by_id(player_id_to_check)
            if eliminated_player_obj: # Should always exist if in active_players
                self.log_action(f"--- Player {eliminated_player_obj.name} has been eliminated! ---")
                self.active_players.remove(player_id_to_check)
                # TODO: Handle card transfer to conqueror.
                self.check_for_game_over() # Check if this elimination ends the game

    def check_for_game_over(self):
        """Checks game over conditions and sets game_state.game_over and game_state.winner."""
        if self.game_over: # Already determined
            return True

        # Condition 1: Only one player left active
        if len(self.active_players) == 1:
            self.game_over = True
            winner_id = self.active_players[0]
            self.winner = self.get_player_by_id(winner_id)
            self.log_action(f"!!! GAME OVER! Player {self.winner.name} is the last one standing! !!!")
            self.current_phase = "GAME_OVER"
            return True

        # Condition 2: One player owns all territories (should also mean only 1 active player, but good check)
        first_owner_id = None
        all_territories_controlled_by_one = True
        if self.active_players: # Only check this if there are still active players
            for terr_data in self.territories_state.values():
                if terr_data["owner"] is None: # Unowned territory, game not over by this rule
                    all_territories_controlled_by_one = False; break
                if first_owner_id is None:
                    first_owner_id = terr_data["owner"]
                elif terr_data["owner"] != first_owner_id:
                    all_territories_controlled_by_one = False; break

            if all_territories_controlled_by_one and first_owner_id is not None:
                self.game_over = True
                self.winner = self.get_player_by_id(first_owner_id)
                if self.winner: # Ensure winner object is found
                     self.log_action(f"!!! GAME OVER! Player {self.winner.name} controls all territories! !!!")
                     self.current_phase = "GAME_OVER"
                else: # Should not happen if owner ID is valid
                    self.log_action(f"!!! GAME OVER! Player ID {first_owner_id} controls all territories but player object not found. !!!")
                return True

        if not self.active_players and len(self.players) > 0: # All players eliminated, but game started
            self.game_over = True
            self.winner = None # Or could be the last one to eliminate someone? Rules vary.
            self.log_action("!!! GAME OVER! All players have been eliminated. No winner. !!!")
            self.current_phase = "GAME_OVER"
            return True

        return False


    def clear_fortify_selection(self):
        self.selected_fortify_source_tid = None
        self.selected_fortify_dest_tid = None
        self.fortify_message = ""

    def resolve_fortification(self, num_armies_to_move):
        if self.game_over: return # Check game over
        if self.fortification_complete_this_turn:
            self.fortify_message = "You have already fortified this turn."
            self.log_action(self.fortify_message); return

        if not self.selected_fortify_source_tid or not self.selected_fortify_dest_tid:
            self.fortify_message = "Source or destination for fortification not selected."
            self.log_action(self.fortify_message); return

        source_data = self.territories_state[self.selected_fortify_source_tid]
        dest_data = self.territories_state[self.selected_fortify_dest_tid]
        current_player = self.get_current_player()

        if not current_player or source_data["owner"] != current_player.id or dest_data["owner"] != current_player.id: # Added current_player check
            self.fortify_message = "Both source and destination must be owned by you."
            self.log_action(self.fortify_message); return

        if self.selected_fortify_source_tid == self.selected_fortify_dest_tid:
            self.fortify_message = "Cannot fortify to the same territory."
            self.log_action(self.fortify_message); return

        if self.selected_fortify_dest_tid not in source_data.get("adjacencies", []):
            self.fortify_message = "For now, can only fortify between directly adjacent territories."
            self.log_action(self.fortify_message); return

        if num_armies_to_move <= 0:
            self.fortify_message = "Must move at least 1 army."
            self.log_action(self.fortify_message); return

        if source_data["armies"] - num_armies_to_move < 1:
            self.fortify_message = f"Not enough armies. Source: {source_data['armies']}, trying to move {num_armies_to_move}."
            self.log_action(self.fortify_message); return

        source_data["armies"] -= num_armies_to_move
        dest_data["armies"] += num_armies_to_move
        self.fortification_complete_this_turn = True
        self.fortify_message = (f"Moved {num_armies_to_move} from {source_data['name']} to {dest_data['name']}.\n"
                                f"Press SPACE to end turn.")
        self.log_action(self.fortify_message)


# Example Usage (will be driven by the main game UI later)
if __name__ == "__main__":
    gs = GameState()
    p1 = gs.add_player("p1", "Player Alpha")
    p2 = gs.add_player("p2", "Player Beta")

    if p1 and p2:
        gs.log_action(f"Game started with players: {gs.players}")
        gs.log_action(f"Current player: {gs.get_current_player().name}")
        gs.log_action(f"Current phase: {gs.current_phase}")

        # Example: Assign some territories during a setup phase
        gs.assign_territory_owner("alaska", p1.id, 1)
        gs.assign_territory_owner("great_britain", p2.id, 1)
        gs.assign_territory_owner("brazil", p1.id, 5)

        print("\nTerritory States:")
        for terr_id in ["alaska", "great_britain", "brazil", "egypt"]:
            t_data = gs.territories_state[terr_id]
            owner_name = "None"
            if t_data["owner"]:
                owner_name = gs.get_player_by_id(t_data["owner"]).name
            print(f"  {t_data['name']}: Owner - {owner_name}, Armies - {t_data['armies']}")

        print(f"\nColor for Alaska: {gs.get_territory_owner_color('alaska')}")

        gs.next_player()
        gs.log_action(f"Current player after next_player(): {gs.get_current_player().name}")

        gs.set_phase("ATTACK")

    print("\nFull Turn Log:")
    for entry in gs.turn_log:
        print(entry)
