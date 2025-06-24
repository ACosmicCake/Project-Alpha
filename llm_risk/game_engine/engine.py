from .data_structures import GameState, Player, Territory, Continent, Card
import json
import random

class GameEngine:
    def __init__(self, map_file_path: str = "map_config.json"):
        self.game_state = GameState()
        self.map_file_path = map_file_path
        # self.initialize_board() # Will be called by orchestrator typically

    def initialize_board(self, players_data: list[dict]):
        """
        Initializes the board from a map configuration file,
        creates players, assigns territories randomly, and places initial armies.
        """
        try:
            with open(self.map_file_path, 'r') as f:
                map_data = json.load(f)
        except FileNotFoundError:
            print(f"Error: Map file '{self.map_file_path}' not found.")
            # Potentially raise an exception or handle more gracefully
            return
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from map file '{self.map_file_path}'.")
            return

        # 1. Create Continents
        for cont_data in map_data.get("continents", []):
            continent = Continent(name=cont_data["name"], bonus_armies=cont_data["bonus_armies"])
            self.game_state.continents[continent.name] = continent

        # 2. Create Territories and assign them to Continents
        for terr_name, terr_data in map_data.get("territories", {}).items():
            continent_name = terr_data.get("continent")
            continent = self.game_state.continents.get(continent_name)
            if not continent:
                print(f"Warning: Continent '{continent_name}' for territory '{terr_name}' not found. Skipping continent assignment.")

            territory = Territory(name=terr_name, continent=continent)
            self.game_state.territories[territory.name] = territory
            if continent:
                continent.territories.append(territory)

        # 3. Link adjacent territories
        for terr_name, terr_data in map_data.get("territories", {}).items():
            territory = self.game_state.territories.get(terr_name)
            if territory:
                for adj_name in terr_data.get("adjacent_to", []):
                    adj_territory = self.game_state.territories.get(adj_name)
                    if adj_territory:
                        territory.adjacent_territories.append(adj_territory)
                    else:
                        print(f"Warning: Adjacent territory '{adj_name}' for '{terr_name}' not found.")

        # 4. Create Players
        if not players_data:
            print("Error: No player data provided for initialization.")
            return

        for player_info in players_data:
            player = Player(name=player_info["name"], color=player_info["color"])
            self.game_state.players.append(player)

        if not self.game_state.players:
            print("Error: No players were created. Cannot assign territories.")
            return

        # 5. Assign territories randomly and place initial armies
        all_territory_names = list(self.game_state.territories.keys())
        random.shuffle(all_territory_names)

        num_players = len(self.game_state.players)
        territories_per_player = len(all_territory_names) // num_players
        extra_territories = len(all_territory_names) % num_players

        current_territory_idx = 0
        for i, player in enumerate(self.game_state.players):
            num_to_assign = territories_per_player + (1 if i < extra_territories else 0)
            for _ in range(num_to_assign):
                if current_territory_idx < len(all_territory_names):
                    terr_name = all_territory_names[current_territory_idx]
                    territory = self.game_state.territories[terr_name]
                    territory.owner = player
                    territory.army_count = 1 # Start with 1 army
                    player.territories.append(territory)
                    current_territory_idx += 1

        # Initial army deployment (example: 35 armies for 4 players, can be adjusted)
        # This is a simplified initial deployment. Classic Risk has more complex rules.
        initial_armies_per_player = 0
        if num_players == 2: initial_armies_per_player = 40
        elif num_players == 3: initial_armies_per_player = 35
        elif num_players == 4: initial_armies_per_player = 30
        elif num_players == 5: initial_armies_per_player = 25
        elif num_players == 6: initial_armies_per_player = 20

        for player in self.game_state.players:
            armies_to_distribute = initial_armies_per_player - len(player.territories)
            player.armies_to_deploy = armies_to_distribute # Store for manual placement later if desired

            # For now, distribute remaining armies somewhat evenly after the initial 1 per territory
            idx = 0
            while armies_to_distribute > 0 and player.territories:
                player.territories[idx % len(player.territories)].army_count += 1
                armies_to_distribute -= 1
                idx += 1

        # 6. Create Deck of Cards
        # One card for each territory: 1/3 infantry, 1/3 cavalry, 1/3 artillery (approx)
        # Plus two wild cards
        symbols = ["Infantry", "Cavalry", "Artillery"]
        symbol_idx = 0
        for terr_name in self.game_state.territories.keys():
            self.game_state.deck.append(Card(terr_name, symbols[symbol_idx % 3]))
            symbol_idx +=1
        self.game_state.deck.append(Card(None, "Wildcard"))
        self.game_state.deck.append(Card(None, "Wildcard"))
        random.shuffle(self.game_state.deck)

        self.game_state.current_player_index = random.randrange(num_players) # Random first player


    def calculate_reinforcements(self, player: Player) -> int:
        """
        Computes armies based on territories owned, continent bonuses, and card trade-ins.
        This method calculates and *returns* the number of reinforcements.
        The actual update to player.armies_to_deploy should happen elsewhere (e.g. in orchestrator or a dedicated deploy phase method)
        """
        if not player:
            return 0

        # 1. Territories owned
        num_territories = len(player.territories)
        reinforcements = max(3, num_territories // 3)

        # 2. Continent bonuses
        for continent in self.game_state.continents.values():
            is_owner_of_all = True
            if not continent.territories: # Skip empty continents
                is_owner_of_all = False
            for territory in continent.territories:
                if territory.owner != player:
                    is_owner_of_all = False
                    break
            if is_owner_of_all:
                reinforcements += continent.bonus_armies

        # 3. Card trade-ins (This is a simplified version. Usually involves sets)
        # For now, let's assume a simple rule: if player has 3+ cards, they can trade.
        # A more complete implementation would check for valid sets (3 of a kind, 1 of each, etc.)
        # and handle the increasing value of sets.
        # This logic should ideally be separate and called when a player chooses to trade cards.
        # For now, this part is just a placeholder for where card logic would influence reinforcements.

        # player.armies_to_deploy += reinforcements # This should be done by the caller
        return reinforcements

    def perform_attack(self, attacker_territory_name: str, defender_territory_name: str, num_attacking_armies: int) -> dict:
        """
        Handles dice rolling logic, army reduction, territory ownership changes,
        and card drawing upon conquering a territory.
        Returns a log of the battle's result.
        """
        attacker_territory = self.game_state.territories.get(attacker_territory_name)
        defender_territory = self.game_state.territories.get(defender_territory_name)
        log = {"event": "attack", "attacker": None, "defender": None, "results": [], "conquered": False, "card_drawn": None}

        # Validations
        if not attacker_territory or not defender_territory:
            log["error"] = "Invalid territory specified."
            return log

        log["attacker"] = attacker_territory.owner.name if attacker_territory.owner else "N/A"
        log["defender"] = defender_territory.owner.name if defender_territory.owner else "N/A"

        if attacker_territory.owner == defender_territory.owner:
            log["error"] = "Cannot attack your own territory."
            return log
        if defender_territory not in attacker_territory.adjacent_territories:
            log["error"] = f"{defender_territory.name} is not adjacent to {attacker_territory.name}."
            return log
        if attacker_territory.army_count <= 1:
            log["error"] = f"{attacker_territory.name} must have more than 1 army to attack."
            return log
        if num_attacking_armies < 1 or num_attacking_armies >= attacker_territory.army_count:
            log["error"] = f"Invalid number of attacking armies ({num_attacking_armies}). Must be between 1 and {attacker_territory.army_count - 1}."
            return log

        max_attacker_dice = min(3, num_attacking_armies) # Attacker can use at most 3 dice, or fewer if they have fewer armies involved
        max_defender_dice = min(2, defender_territory.army_count) # Defender can use at most 2 dice

        attacker_dice_rolls = sorted([random.randint(1, 6) for _ in range(max_attacker_dice)], reverse=True)
        defender_dice_rolls = sorted([random.randint(1, 6) for _ in range(max_defender_dice)], reverse=True)

        log["attacker_rolls"] = attacker_dice_rolls
        log["defender_rolls"] = defender_dice_rolls

        attacker_losses = 0
        defender_losses = 0

        for i in range(min(len(attacker_dice_rolls), len(defender_dice_rolls))):
            roll_log = {"attacker_roll": attacker_dice_rolls[i], "defender_roll": defender_dice_rolls[i]}
            if attacker_dice_rolls[i] > defender_dice_rolls[i]:
                defender_losses += 1
                roll_log["outcome"] = f"Defender loses 1 army ({defender_territory.name})"
            else:
                attacker_losses += 1
                roll_log["outcome"] = f"Attacker loses 1 army ({attacker_territory.name})"
            log["results"].append(roll_log)

        attacker_territory.army_count -= attacker_losses
        defender_territory.army_count -= defender_losses

        log["summary"] = f"Attacker lost {attacker_losses} armies. Defender lost {defender_losses} armies."

        if defender_territory.army_count <= 0:
            log["conquered"] = True
            log["summary"] += f" {attacker_territory.owner.name} conquered {defender_territory.name}!"

            old_owner = defender_territory.owner
            new_owner = attacker_territory.owner

            if old_owner:
                old_owner.territories.remove(defender_territory)

            defender_territory.owner = new_owner
            new_owner.territories.append(defender_territory)

            # Move attacking armies: must move at least num_attacking_dice, up to num_attacking_armies that survived
            # For simplicity, let's say the player *must* move the armies they attacked with, if they survived.
            # The game rules require at least the number of dice rolled to move.
            # The player can choose to move more, up to the total number of armies that attacked minus one (one must remain).
            # This part needs to be an AI decision or player input.
            # For now, move all `num_attacking_armies` that were specified (minus losses).
            # A minimum of max_attacker_dice must move.

            armies_to_move = max(max_attacker_dice, num_attacking_armies - attacker_losses) # Must move at least num dice, or all attackers if fewer survived
            armies_to_move = min(armies_to_move, attacker_territory.army_count -1) # Cannot leave attacker territory empty

            if armies_to_move > 0 :
                defender_territory.army_count = armies_to_move
                attacker_territory.army_count -= armies_to_move
            else: # Should not happen if validation is correct, but as a fallback
                defender_territory.army_count = 1
                attacker_territory.army_count -=1


            # Draw a card if one is available and player hasn't drawn one this turn yet
            # (This "has_drawn_card_this_turn" flag needs to be managed at player or turn level)
            # For now, assume they can draw if deck is not empty.
            if self.game_state.deck:
                card = self.game_state.deck.pop(0)
                new_owner.hand.append(card)
                log["card_drawn"] = card.to_dict()

            # Check if the old owner is eliminated
            if old_owner and not old_owner.territories:
                log["eliminated_player"] = old_owner.name
                # Transfer cards from eliminated player to conqueror
                new_owner.hand.extend(old_owner.hand)
                old_owner.hand.clear()
                # Note: GameState.players list should be updated by orchestrator if a player is eliminated.

        return log

    def perform_fortify(self, from_territory_name: str, to_territory_name: str, num_armies: int) -> dict:
        """
        Moves armies between two connected territories owned by the same player.
        Returns a log of the fortification.
        """
        log = {"event": "fortify", "success": False, "message": ""}
        from_territory = self.game_state.territories.get(from_territory_name)
        to_territory = self.game_state.territories.get(to_territory_name)

        if not from_territory or not to_territory:
            log["message"] = "Invalid 'from' or 'to' territory specified."
            return log
        if from_territory.owner != to_territory.owner:
            log["message"] = "Territories must have the same owner."
            return log
        if not from_territory.owner: # Should not happen if previous check passes
            log["message"] = "Territories are unowned."
            return log

        # Check connectivity (BFS or DFS)
        if not self._are_territories_connected(from_territory, to_territory, from_territory.owner):
            log["message"] = f"{to_territory.name} is not connected to {from_territory.name} through owned territories."
            return log

        if num_armies <= 0:
            log["message"] = "Number of armies to move must be positive."
            return log
        if from_territory.army_count - num_armies < 1:
            log["message"] = f"Cannot move {num_armies} armies from {from_territory.name}. At least 1 army must remain."
            return log

        from_territory.army_count -= num_armies
        to_territory.army_count += num_armies

        log["success"] = True
        log["message"] = f"Successfully moved {num_armies} armies from {from_territory.name} to {to_territory.name}."
        log["from_territory"] = from_territory.name
        log["to_territory"] = to_territory.name
        log["num_armies"] = num_armies
        return log

    def _are_territories_connected(self, start_territory: Territory, end_territory: Territory, player: Player) -> bool:
        """
        Checks if two territories are connected via a path of territories owned by the given player.
        Uses Breadth-First Search (BFS).
        """
        if start_territory == end_territory:
            return True

        queue = [start_territory]
        visited = {start_territory}

        while queue:
            current_territory = queue.pop(0)
            for neighbor in current_territory.adjacent_territories:
                if neighbor == end_territory and neighbor.owner == player:
                    return True
                if neighbor.owner == player and neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return False

    def is_game_over(self) -> Player | None:
        """
        Checks for the win condition (one player owns all territories).
        Returns the winning player or None.
        """
        if not self.game_state.territories: # No territories, game can't be won
            return None

        first_owner = None
        for territory in self.game_state.territories.values():
            if territory.owner is None: # Unowned territory means game is not over
                return None
            if first_owner is None:
                first_owner = territory.owner
            elif territory.owner != first_owner: # Different owners means game is not over
                return None
        return first_owner # If loop completes, first_owner owns all territories

    def next_turn(self):
        """
        Advances to the next player and resets turn-specific state.
        """
        if not self.game_state.players:
            return

        current_player = self.game_state.get_current_player()
        # Reset any turn-specific flags for current_player if necessary (e.g., has_drawn_card_this_turn)

        active_players = [p for p in self.game_state.players if p.territories] # Only consider players with territories
        if not active_players:
            # This case should ideally be handled by is_game_over, but as a safeguard
            print("Warning: No active players with territories found during next_turn.")
            return

        # Find the index of the current player in the list of active players
        try:
            current_active_player_idx = active_players.index(current_player)
            next_active_player_idx = (current_active_player_idx + 1) % len(active_players)
            next_player_overall_idx = self.game_state.players.index(active_players[next_active_player_idx])
        except ValueError: # Current player might have been eliminated
            # Default to the first active player if current player is not found (e.g. eliminated)
            # Or, if the list of players was modified, find the one after the last recorded index.
            # This logic might need refinement based on how player elimination is handled by the orchestrator.
            # For now, a simple wrap around on the original player list, then find the next active one.

            # A robust way is to find the next player in self.game_state.players who is still active
            start_idx = (self.game_state.current_player_index + 1) % len(self.game_state.players)
            for i in range(len(self.game_state.players)):
                check_idx = (start_idx + i) % len(self.game_state.players)
                if self.game_state.players[check_idx] in active_players:
                    next_player_overall_idx = check_idx
                    break
            else: # Should not happen if there's at least one active player
                print("Error finding next active player.")
                return


        self.game_state.current_player_index = next_player_overall_idx

        if self.game_state.current_player_index == 0: # Wrapped around to the first player
             self.game_state.current_turn_number += 1

        self.game_state.current_game_phase = "REINFORCE"

        # New current player calculates reinforcements for their turn
        new_current_player = self.game_state.get_current_player()
        if new_current_player:
            new_current_player.armies_to_deploy = self.calculate_reinforcements(new_current_player)

    def get_valid_actions(self, player: Player) -> list:
        """
        Generates a list of valid actions for the current player in the current phase.
        This is a placeholder and will need significant expansion.
        """
        # This will be a complex function depending on the game phase and state.
        # For now, returning a generic list.
        actions = []
        phase = self.game_state.current_game_phase

        if phase == "REINFORCE":
            # Valid deploy actions: (territory_name, num_armies)
            # Must have armies_to_deploy > 0
            if player.armies_to_deploy > 0:
                for territory in player.territories:
                    actions.append({"type": "DEPLOY", "territory": territory.name, "max_armies": player.armies_to_deploy})
            # Option to trade cards if conditions met (e.g., 3+ cards, valid set)
            # actions.append({"type": "TRADE_CARDS", "cards_to_trade": [...]})
            if player.armies_to_deploy == 0 : # or if no valid deploy moves left
                 actions.append({"type": "END_REINFORCE_PHASE"})


        elif phase == "ATTACK":
            # Valid attack actions: (from_territory, to_territory, num_armies)
            for territory in player.territories:
                if territory.army_count > 1:
                    for neighbor in territory.adjacent_territories:
                        if neighbor.owner != player:
                            # Max armies that can attack: territory.army_count - 1
                            # Max dice: min(3, territory.army_count - 1)
                            actions.append({
                                "type": "ATTACK",
                                "from": territory.name,
                                "to": neighbor.name,
                                "max_armies_for_attack": territory.army_count - 1
                            })
            actions.append({"type": "END_ATTACK_PHASE"}) # Always possible to end attack phase
            # Add CHAT actions later

        elif phase == "FORTIFY":
            # Valid fortify actions: (from_territory, to_territory, num_armies)
            # Can only fortify once per turn. This state needs to be tracked.
            # For now, assume it's always possible if connected territories exist.
            owned_territories = player.territories
            for i in range(len(owned_territories)):
                for j in range(len(owned_territories)):
                    if i == j: continue
                    from_t = owned_territories[i]
                    to_t = owned_territories[j]
                    if from_t.army_count > 1 and self._are_territories_connected(from_t, to_t, player):
                        actions.append({
                            "type": "FORTIFY",
                            "from": from_t.name,
                            "to": to_t.name,
                            "max_armies_to_move": from_t.army_count - 1
                        })
            actions.append({"type": "END_TURN"}) # Or "SKIP_FORTIFY"

        # Global actions (available in some phases)
        # actions.append({"type": "GLOBAL_CHAT", "message": "..."})
        # actions.append({"type": "PRIVATE_CHAT", "target_player": "...", "message": "..."})

        return actions


if __name__ == '__main__':
    # Basic Test for GameEngine
    engine = GameEngine(map_file_path="map_config.json") # Assuming map_config.json is in the same directory or path is correct

    # Create a dummy map_config.json for testing if it doesn't exist
    dummy_map_data = {
        "continents": [
            {"name": "North America", "bonus_armies": 5, "territories": ["Alaska", "Alberta", "Western US"]},
            {"name": "Asia", "bonus_armies": 7, "territories": ["Kamchatka", "Japan"]}
        ],
        "territories": {
            "Alaska": {"continent": "North America", "adjacent_to": ["Alberta", "Kamchatka"]},
            "Alberta": {"continent": "North America", "adjacent_to": ["Alaska", "Western US"]},
            "Western US": {"continent": "North America", "adjacent_to": ["Alberta"]},
            "Kamchatka": {"continent": "Asia", "adjacent_to": ["Alaska", "Japan"]},
            "Japan": {"continent": "Asia", "adjacent_to": ["Kamchatka"]}
        }
    }
    try:
        with open("map_config.json", 'w') as f:
            json.dump(dummy_map_data, f, indent=2)
        print("Created dummy map_config.json for testing.")
    except IOError:
        print("Could not create dummy map_config.json. Ensure you have write permissions or create it manually.")

    players_setup = [
        {"name": "PlayerA", "color": "Red"},
        {"name": "PlayerB", "color": "Blue"}
    ]
    engine.initialize_board(players_setup)

    print("Initial Game State:")
    print(engine.game_state.to_json())
    print("-" * 20)

    current_player = engine.game_state.get_current_player()
    if current_player:
        print(f"Current Player: {current_player.name}")
        reinforcements = engine.calculate_reinforcements(current_player)
        current_player.armies_to_deploy = reinforcements # Manually assign for this test
        print(f"{current_player.name} gets {current_player.armies_to_deploy} reinforcements.")

        # Simulate deploying armies
        if current_player.armies_to_deploy > 0 and current_player.territories:
            deploy_territory = current_player.territories[0]
            deploy_amount = current_player.armies_to_deploy
            deploy_territory.army_count += deploy_amount
            print(f"{current_player.name} deployed {deploy_amount} armies to {deploy_territory.name} (new count: {deploy_territory.army_count})")
            current_player.armies_to_deploy = 0

        engine.game_state.current_game_phase = "ATTACK"
        print(f"Game phase set to: {engine.game_state.current_game_phase}")

        # Try a test attack if possible
        attacker_territory = None
        defender_territory = None
        for t in current_player.territories:
            if t.army_count > 1:
                for adj_t in t.adjacent_territories:
                    if adj_t.owner != current_player:
                        attacker_territory = t
                        defender_territory = adj_t
                        break
            if attacker_territory:
                break

        if attacker_territory and defender_territory:
            num_attackers = attacker_territory.army_count - 1
            print(f"\n{current_player.name} attacking from {attacker_territory.name} ({attacker_territory.army_count} armies) to {defender_territory.name} ({defender_territory.army_count} armies, owner: {defender_territory.owner.name}) with {num_attackers} armies.")
            attack_result = engine.perform_attack(attacker_territory.name, defender_territory.name, num_attackers)
            print("Attack Result:")
            print(json.dumps(attack_result, indent=2))
            print(f"State after attack: {attacker_territory.name} has {attacker_territory.army_count}, {defender_territory.name} has {defender_territory.army_count}")
        else:
            print("\nNo valid attack opportunity found for testing.")

        engine.game_state.current_game_phase = "FORTIFY"
        # Try a test fortify
        if len(current_player.territories) >= 2:
            from_t = current_player.territories[0]
            to_t = None
            for t_potential_to in current_player.territories[1:]:
                 if engine._are_territories_connected(from_t, t_potential_to, current_player):
                     to_t = t_potential_to
                     break

            if from_t and to_t and from_t.army_count > 1:
                armies_to_move = 1
                print(f"\n{current_player.name} fortifying from {from_t.name} to {to_t.name} with {armies_to_move} army.")
                fortify_result = engine.perform_fortify(from_t.name, to_t.name, armies_to_move)
                print("Fortify Result:")
                print(json.dumps(fortify_result, indent=2))
                print(f"State after fortify: {from_t.name} has {from_t.army_count}, {to_t.name} has {to_t.army_count}")
            else:
                print("\nNo valid fortify opportunity for testing or from_territory has only 1 army.")
        else:
            print("\nNot enough territories to test fortify.")


        engine.next_turn()
        print("-" * 20)
        print("After next_turn():")
        new_current_player = engine.game_state.get_current_player()
        if new_current_player:
            print(f"New Current Player: {new_current_player.name}")
            print(f"Turn: {engine.game_state.current_turn_number}, Phase: {engine.game_state.current_game_phase}")
            print(f"{new_current_player.name} has {new_current_player.armies_to_deploy} reinforcements calculated.")

        print("\nFinal Game State:")
        print(engine.game_state.to_json())

        winner = engine.is_game_over()
        if winner:
            print(f"\nGame Over! Winner is {winner.name}")
        else:
            print("\nGame is not over.")

    else:
        print("No current player to test with.")
