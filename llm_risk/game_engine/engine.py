from .data_structures import GameState, Player, Territory, Continent, Card
import json
import random

class GameEngine:
    def __init__(self, map_file_path: str = "map_config.json"):
        self.game_state = GameState()
        self.map_file_path = map_file_path
        self.card_trade_bonus_index = 0
        self.card_trade_bonuses = [4, 6, 8, 10, 12, 15]

    def initialize_game_from_map(self, players_data: list[dict], is_two_player_game: bool = False):
        """
        Initializes continents, territories (unowned), creates players,
        allocates initial army pools, and prepares the deck.
        This method sets up the game for the interactive setup phases.
        If is_two_player_game is True, specific 2-player setup rules are applied.
        """
        gs = self.game_state
        gs.current_game_phase = "SETUP_START" # Ensure fresh start
        gs.is_two_player_game = is_two_player_game # Store this mode

        if gs.is_two_player_game:
            if len(players_data) != 2:
                print("Error: Two-player game mode selected, but players_data does not contain 2 players.")
                gs.current_game_phase = "ERROR"
                return
            print("Initializing for 2-Player Game Rules (Neutral player will be added by orchestrator/rules).")


        try:
            with open(self.map_file_path, 'r') as f:
                map_data = json.load(f)
        except FileNotFoundError:
            print(f"Error: Map file '{self.map_file_path}' not found.")
            gs.current_game_phase = "ERROR"
            return
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from map file '{self.map_file_path}'.")
            gs.current_game_phase = "ERROR"
            return

        # 1. Create Continents
        gs.continents.clear()
        for cont_data in map_data.get("continents", []):
            continent = Continent(name=cont_data["name"], bonus_armies=cont_data["bonus_armies"])
            gs.continents[continent.name] = continent

        # 2. Create Territories (unowned) and assign them to Continents
        gs.territories.clear()
        gs.unclaimed_territory_names.clear()
        for terr_name, terr_data in map_data.get("territories", {}).items():
            continent_name = terr_data.get("continent")
            continent = gs.continents.get(continent_name)
            if not continent:
                print(f"Warning: Continent '{continent_name}' for territory '{terr_name}' not found. Skipping continent assignment.")

            territory = Territory(name=terr_name, continent=continent, owner=None, army_count=0) # Initially unowned
            gs.territories[territory.name] = territory
            gs.unclaimed_territory_names.append(terr_name)
            if continent:
                continent.territories.append(territory)
        random.shuffle(gs.unclaimed_territory_names) # Shuffle for fairness if multiple AIs pick simultaneously

        # 3. Link adjacent territories
        for terr_name, terr_data in map_data.get("territories", {}).items():
            territory = gs.territories.get(terr_name)
            if territory:
                territory.adjacent_territories.clear() # Clear previous links if any
                for adj_name in terr_data.get("adjacent_to", []):
                    adj_territory = gs.territories.get(adj_name)
                    if adj_territory:
                        territory.adjacent_territories.append(adj_territory)
                    else:
                        print(f"Warning: Adjacent territory '{adj_name}' for '{terr_name}' not found during linking.")

        # 4. Create Players and allocate initial armies
        if not players_data:
            print("Error: No player data provided for initialization.")
            gs.current_game_phase = "ERROR"
            return

        gs.players.clear()
        human_players = []
        for player_info in players_data: # Should be 2 for 2-player mode
            player = Player(name=player_info["name"], color=player_info["color"])
            human_players.append(player)

        gs.players.extend(human_players)

        if gs.is_two_player_game:
            # Add Neutral player
            # Find a color for Neutral that isn't used by human players
            used_colors = [p.color.lower() for p in human_players]
            neutral_color = "Gray" # Default
            if "gray" in used_colors: # Find another color if gray is taken
                possible_colors = ["LightBlue", "Brown", "Pink", "Orange"]
                for pc in possible_colors:
                    if pc.lower() not in used_colors:
                        neutral_color = pc
                        break
            neutral_player = Player(name="Neutral", color=neutral_color, is_neutral=True)
            gs.players.append(neutral_player)

        if not gs.players: # Should be caught by earlier checks if players_data was empty
            print("Error: No players were created (including potential neutral).")
            gs.current_game_phase = "ERROR"
            return

        num_actual_players_for_army_calc = len(players_data) # Use original players_data count for standard rules
        if gs.is_two_player_game:
            initial_armies_per_entity = 40 # P1, P2, Neutral each get 40
            for player in gs.players: # This now includes Neutral
                player.initial_armies_pool = initial_armies_per_entity
                player.armies_placed_in_setup = 0
        else: # Standard game army allocation
            initial_armies_per_player = 0
            if num_actual_players_for_army_calc == 3: initial_armies_per_player = 35
            elif num_actual_players_for_army_calc == 4: initial_armies_per_player = 30
            elif num_actual_players_for_army_calc == 5: initial_armies_per_player = 25
            elif num_actual_players_for_army_calc == 6: initial_armies_per_player = 20
            # Note: Standard rules don't explicitly cover 2 players without the 2-player variation.
            # If is_two_player_game is False and num_actual_players_for_army_calc is 2, this will error.
            # The orchestrator should ensure correct mode or player count.
            else:
                print(f"Error: Invalid number of players ({num_actual_players_for_army_calc}) for standard game mode. Must be 3-6.")
                gs.current_game_phase = "ERROR"
                return
            for player in gs.players: # Only human players in this branch
                player.initial_armies_pool = initial_armies_per_player
                player.armies_placed_in_setup = 0

        # 5. Create Deck of Cards
        gs.deck.clear()
        symbols = ["Infantry", "Cavalry", "Artillery"]
        symbol_idx = 0
        territory_names_for_cards = list(gs.territories.keys())

        # For 2-player game, wild cards are initially excluded for territory dealing
        # They are added back before main play starts.
        if not gs.is_two_player_game:
            for terr_name in territory_names_for_cards:
                gs.deck.append(Card(terr_name, symbols[symbol_idx % 3]))
                symbol_idx +=1
            gs.deck.append(Card(None, "Wildcard"))
            gs.deck.append(Card(None, "Wildcard"))
            random.shuffle(gs.deck)
        else: # 2-player game: create territory cards only for initial deal
            if len(territory_names_for_cards) != 42:
                print(f"Error: Map does not have 42 territories for 2-player card dealing (found {len(territory_names_for_cards)}).")
                gs.current_game_phase = "ERROR"
                return
            for terr_name in territory_names_for_cards: # Create all 42 territory cards
                gs.deck.append(Card(terr_name, symbols[symbol_idx % 3]))
                symbol_idx +=1
            random.shuffle(gs.deck) # Shuffle territory cards

        if gs.is_two_player_game:
            gs.current_game_phase = "SETUP_2P_DEAL_CARDS"
        else:
            gs.current_game_phase = "SETUP_DETERMINE_ORDER"

        print(f"Game initialized. Phase: {gs.current_game_phase}. Players: {[p.name for p in gs.players]}. Unclaimed territories: {len(gs.unclaimed_territory_names)}")

    def setup_two_player_initial_territory_assignment(self) -> dict:
        """
        Specific for 2-player setup: Deals territory cards to assign initial 14 territories
        to each human player and the neutral player. Each gets 1 army.
        Wild cards are NOT in the deck at this point.
        """
        gs = self.game_state
        log = {"event": "setup_2p_deal_cards", "success": False, "message": ""}

        if not gs.is_two_player_game or gs.current_game_phase != "SETUP_2P_DEAL_CARDS":
            log["message"] = f"Cannot perform 2-player card dealing in current state (is_2p: {gs.is_two_player_game}, phase: {gs.current_game_phase})."
            return log

        if len(gs.players) != 3: # P1, P2, Neutral
            log["message"] = "Error: Expected 3 players (P1, P2, Neutral) for 2-player card setup."
            return log

        # Deck should contain 42 territory cards, shuffled.
        if len(gs.deck) != 42:
            log["message"] = f"Error: Deck should have 42 territory cards for 2-player setup, found {len(gs.deck)}."
            return log

        human_players = [p for p in gs.players if not p.is_neutral]
        neutral_player = next((p for p in gs.players if p.is_neutral), None)

        if len(human_players) != 2 or not neutral_player:
            log["message"] = "Error: Could not identify 2 human players and 1 neutral player."
            return log

        players_for_deal = human_players + [neutral_player] # Order of dealing can be fixed or random

        assigned_territories_log = {p.name: [] for p in players_for_deal}

        for i in range(14): # Each gets 14 cards
            for player_receiving_card in players_for_deal:
                if not gs.deck:
                    log["message"] = "Error: Deck ran out of cards during 2-player territory assignment."
                    log["assigned_territories"] = assigned_territories_log
                    return log # Should not happen with 42 cards and 3x14 assignment

                card = gs.deck.pop(0)
                territory_name = card.territory_name
                if not territory_name: # Should be a territory card
                    log["message"] = f"Error: Drew a non-territory card '{card}' during 2-player setup."
                    return log

                territory = gs.territories.get(territory_name)
                if not territory or territory_name not in gs.unclaimed_territory_names:
                    log["message"] = f"Error: Territory '{territory_name}' from card not found or already claimed."
                    return log

                if player_receiving_card.armies_placed_in_setup >= player_receiving_card.initial_armies_pool:
                    log["message"] = f"{player_receiving_card.name} has no armies in pool for initial territory claim."
                    return log # Should have 40 initially.

                territory.owner = player_receiving_card
                territory.army_count = 1
                player_receiving_card.territories.append(territory)
                player_receiving_card.armies_placed_in_setup += 1
                gs.unclaimed_territory_names.remove(territory_name)
                assigned_territories_log[player_receiving_card.name].append(territory_name)

        if gs.unclaimed_territory_names:
            log["message"] = f"Error: {len(gs.unclaimed_territory_names)} territories remained unclaimed after 2P card dealing."
            log["success"] = False
        else:
            log["success"] = True
            log["message"] = "All 42 territories assigned via cards for 2-player setup. Each has 1 army."
            gs.current_game_phase = "SETUP_2P_PLACE_REMAINING"
            # Determine who places remaining armies first (e.g., player 1 from initial setup, or fixed)
            # For now, assume human_players[0] (original player 1) starts this. Orchestrator will manage turns.
            gs.player_setup_order = human_players # Only human players take turns placing remaining.
            gs.current_setup_player_index = 0
            # The player who gets the *first game turn* after setup needs to be decided.
            # PDF: "Whoever placed the first army takes the first turn." - this is complex with card dealing.
            # For 2-player, often P1 just starts. Let's assume human_players[0] for now.
            gs.first_player_of_game = human_players[0]


        log["assigned_territories_map"] = assigned_territories_log
        # Wild cards are added back to the deck *after* this entire setup phase, before regular play.
        # This will be handled by a method called by orchestrator, or end of setup logic.
        return log

    def player_places_initial_armies_2p(self, acting_player_name: str, own_army_placements: list[tuple[str, int]], neutral_army_placement: tuple[str, int] | None) -> dict:
        """
        For 2-player setup: allows the acting_player to place 2 of their own armies
        and 1 neutral army.
        own_army_placements: list of (territory_name, count), sum of counts must be 2.
        neutral_army_placement: (territory_name, count=1)
        """
        gs = self.game_state
        log = {"event": "place_initial_armies_2p", "player": acting_player_name, "success": False, "message": ""}

        if not gs.is_two_player_game or gs.current_game_phase != "SETUP_2P_PLACE_REMAINING":
            log["message"] = f"Cannot place 2P initial armies in current state (is_2p: {gs.is_two_player_game}, phase: {gs.current_game_phase})."
            return log

        acting_player = gs.get_current_setup_player() # player_setup_order should contain the two human players
        if not acting_player or acting_player.name != acting_player_name or acting_player.is_neutral:
            log["message"] = f"Invalid acting player '{acting_player_name}' or not their turn."
            return log

        neutral_player = next((p for p in gs.players if p.is_neutral), None)
        if not neutral_player: # Should exist in 2p mode
            log["message"] = "Neutral player not found."
            return log

        # Validate and place player's own 2 armies
        player_armies_to_place_this_turn = sum(count for _, count in own_army_placements)
        if player_armies_to_place_this_turn != 2:
            log["message"] = f"Player must place exactly 2 of their own armies, attempted {player_armies_to_place_this_turn}."
            return log

        armies_left_in_player_pool = acting_player.initial_armies_pool - acting_player.armies_placed_in_setup
        if armies_left_in_player_pool < 2 and armies_left_in_player_pool > 0: # Player has 1 army left
             if player_armies_to_place_this_turn != armies_left_in_player_pool : # Must place remaining 1
                log["message"] = f"Player has only {armies_left_in_player_pool} army left, must place that many."
                return log
        elif armies_left_in_player_pool <= 0 :
             log["message"] = f"Player {acting_player_name} has no more armies in their pool ({armies_left_in_player_pool})."
             # This case should ideally be handled by get_valid_actions not offering this.
             # If they have 0 left, they can't place their 2.
             # But they might still need to place a neutral army if neutral has some left.
             # For simplicity now, if player has 0, they can't do this action.
             return log


        for terr_name, count in own_army_placements:
            territory = gs.territories.get(terr_name)
            if not territory or territory.owner != acting_player:
                log["message"] = f"Invalid territory '{terr_name}' for {acting_player_name}'s army placement."
                return log
            if count <=0:
                log["message"] = f"Army count for {terr_name} must be positive."
                return log

            # Check if placing 'count' exceeds remaining armies for this turn (2) or total pool
            # This is implicitly handled by player_armies_to_place_this_turn check and armies_left_in_player_pool

            territory.army_count += count
            acting_player.armies_placed_in_setup += count
            log["message"] += f"Placed {count} on {terr_name}. "

        log["player_armies_placed_total"] = acting_player.armies_placed_in_setup

        # Place 1 neutral army
        if neutral_army_placement:
            neut_terr_name, neut_count = neutral_army_placement
            if neut_count != 1:
                log["message"] += "Must place exactly 1 neutral army."
                # Rollback player's own army placement for this turn if strict atomicity is needed, or just fail here.
                # For now, fail and player has to retry.
                return log

            neutral_territory = gs.territories.get(neut_terr_name)
            if not neutral_territory or neutral_territory.owner != neutral_player:
                log["message"] += f"Invalid territory '{neut_terr_name}' for neutral army placement."
                return log

            if neutral_player.armies_placed_in_setup < neutral_player.initial_armies_pool:
                neutral_territory.army_count += 1
                neutral_player.armies_placed_in_setup += 1
                log["message"] += f"Placed 1 neutral army on {neut_terr_name}. Neutral armies placed: {neutral_player.armies_placed_in_setup}."
            else:
                log["message"] += "Neutral player has no armies left in pool. Skipped neutral placement."

        log["neutral_armies_placed_total"] = neutral_player.armies_placed_in_setup
        log["success"] = True

        # Check if all armies for all (human) players are placed
        # Neutral armies are placed by humans; their pool depletion is a consequence.
        all_human_players_done = True
        for p in gs.player_setup_order: # player_setup_order contains the two human players
            if p.armies_placed_in_setup < p.initial_armies_pool:
                all_human_players_done = False
                break

        if all_human_players_done:
            log["message"] += " All human player initial armies placed."
            # Add wild cards back to deck and shuffle
            gs.deck.append(Card(None, "Wildcard"))
            gs.deck.append(Card(None, "Wildcard"))
            random.shuffle(gs.deck)
            log["message"] += " Wild cards added to deck."

            gs.current_game_phase = "REINFORCE"
            try:
                gs.current_player_index = gs.players.index(gs.first_player_of_game)
                # Ensure first player is not neutral
                if gs.players[gs.current_player_index].is_neutral:
                    # This means first_player_of_game was set to Neutral, which is an error for 2P mode.
                    # Default to the first human player in original list.
                    first_human = next(p for p in gs.players if not p.is_neutral)
                    gs.current_player_index = gs.players.index(first_human)
            except ValueError:
                gs.current_player_index = 0 # Fallback

            first_active_player = gs.get_current_player()
            if first_active_player and not first_active_player.is_neutral:
                first_active_player.armies_to_deploy = self.calculate_reinforcements(first_active_player)
                log["message"] += f" Game setup complete. First turn: {first_active_player.name}. Reinforcements: {first_active_player.armies_to_deploy}."
            else: # Should not happen if first_player_of_game is set correctly to a human
                 log["message"] += " Game setup complete. Error finding first non-neutral player."

        else: # Not all human armies placed, advance to next human player in setup order
            gs.current_setup_player_index = (gs.current_setup_player_index + 1) % len(gs.player_setup_order)
            log["message"] += f" Next player to place armies: {gs.player_setup_order[gs.current_setup_player_index].name}."

        return log


    def set_player_setup_order(self, ordered_player_names: list[str], first_placer_for_game_turn_name: str):
        """
        Sets the order for setup actions and identifies the first player for the main game.
        Called by the orchestrator after player order is determined (e.g., by dice rolls).
        Relevant for standard setup, not 2-player card-based setup.
        """
        gs = self.game_state
        if gs.is_two_player_game:
            # For 2-player, setup order for placing remaining armies is typically fixed (P1, P2)
            # and first game turn player is also often fixed or determined differently.
            # This method might not be directly used, or used just to set first_player_of_game.
            human_players = [p for p in gs.players if not p.is_neutral]
            if not human_players: return False # Should not happen

            first_player_obj = next((p for p in human_players if p.name == first_placer_for_game_turn_name), None)
            if not first_player_obj: first_player_obj = human_players[0] # Default if name not found
            gs.first_player_of_game = first_player_obj
            # player_setup_order for 2P remaining armies is set in setup_two_player_initial_territory_assignment
            print(f"2P Game: First game turn set to {gs.first_player_of_game.name}.")
            # Phase transition for 2P happens in other setup methods.
            return True

        if gs.current_game_phase != "SETUP_DETERMINE_ORDER":
            print(f"Error: Cannot set player setup order in phase {gs.current_game_phase}")
            return False

        name_to_player_map = {p.name: p for p in gs.players}
        # Filter out neutral player if it accidentally got into ordered_player_names for standard setup
        gs.player_setup_order = [name_to_player_map[name] for name in ordered_player_names if name in name_to_player_map and not name_to_player_map[name].is_neutral]

        # Check if number of players in setup order matches non-neutral players
        non_neutral_players_count = sum(1 for p in gs.players if not p.is_neutral)
        if len(gs.player_setup_order) != non_neutral_players_count:
            print(f"Error: Mismatch in ordered_player_names ({len(gs.player_setup_order)}) and game's non-neutral players ({non_neutral_players_count}).")
            return False

        first_player_obj = name_to_player_map.get(first_placer_for_game_turn_name)
        if not first_player_obj or first_player_obj.is_neutral:
            print(f"Error: First placer for game turn '{first_placer_for_game_turn_name}' not found or is neutral.")
            return False
        gs.first_player_of_game = first_player_obj

        gs.current_setup_player_index = 0
        gs.current_game_phase = "SETUP_CLAIM_TERRITORIES"
        print(f"Player setup order set: {[p.name for p in gs.player_setup_order]}. First game turn: {gs.first_player_of_game.name}. Phase: {gs.current_game_phase}")
        return True

    def player_claims_territory(self, player_name: str, territory_name: str) -> dict:
        """
        Allows a player to claim an unoccupied territory during setup.
        """
        gs = self.game_state
        log = {"event": "claim_territory", "player": player_name, "territory": territory_name, "success": False, "message": ""}

        if gs.current_game_phase != "SETUP_CLAIM_TERRITORIES":
            log["message"] = f"Cannot claim territory in phase: {gs.current_game_phase}"
            return log

        current_setup_player = gs.player_setup_order[gs.current_setup_player_index]
        if current_setup_player.name != player_name:
            log["message"] = f"Not {player_name}'s turn to claim. Current: {current_setup_player.name}"
            return log

        if territory_name not in gs.unclaimed_territory_names:
            log["message"] = f"Territory '{territory_name}' is not available or already claimed."
            return log

        territory = gs.territories.get(territory_name)
        if not territory: # Should not happen if unclaimed_territory_names is synced with territories
            log["message"] = f"Territory object for '{territory_name}' not found (internal error)."
            return log

        if current_setup_player.armies_placed_in_setup >= current_setup_player.initial_armies_pool:
            log["message"] = f"{player_name} has no more armies in their initial pool to place for claiming."
            # This implies an issue with initial army counts or logic, as claiming should use 1 army.
            return log

        territory.owner = current_setup_player
        territory.army_count = 1
        current_setup_player.territories.append(territory)
        current_setup_player.armies_placed_in_setup += 1
        gs.unclaimed_territory_names.remove(territory_name)

        log["success"] = True
        log["message"] = f"{player_name} claimed {territory_name}. Armies placed by {player_name}: {current_setup_player.armies_placed_in_setup}/{current_setup_player.initial_armies_pool}."

        # Advance to next player in setup order
        gs.current_setup_player_index = (gs.current_setup_player_index + 1) % len(gs.player_setup_order)

        if not gs.unclaimed_territory_names: # All territories claimed
            gs.current_game_phase = "SETUP_PLACE_ARMIES"
            gs.current_setup_player_index = 0 # Reset for placing remaining armies, starting with first in setup order
            log["message"] += " All territories claimed. Moving to SETUP_PLACE_ARMIES phase."
            print("All territories claimed. Phase: SETUP_PLACE_ARMIES")

        return log

    def _all_initial_armies_placed(self) -> bool:
        """Checks if all players have placed all their initial armies."""
        return all(p.armies_placed_in_setup >= p.initial_armies_pool for p in self.game_state.players)

    def player_places_initial_army(self, player_name: str, territory_name: str) -> dict:
        """
        Allows a player to place one additional army on an owned territory during setup.
        """
        gs = self.game_state
        log = {"event": "place_initial_army", "player": player_name, "territory": territory_name, "success": False, "message": ""}

        if gs.current_game_phase != "SETUP_PLACE_ARMIES":
            log["message"] = f"Cannot place initial army in phase: {gs.current_game_phase}"
            return log

        current_setup_player = gs.player_setup_order[gs.current_setup_player_index]
        if current_setup_player.name != player_name:
            log["message"] = f"Not {player_name}'s turn to place. Current: {current_setup_player.name}"
            return log

        territory = gs.territories.get(territory_name)
        if not territory or territory.owner != current_setup_player:
            log["message"] = f"Territory '{territory_name}' not found or not owned by {player_name}."
            return log

        if current_setup_player.armies_placed_in_setup >= current_setup_player.initial_armies_pool:
            log["message"] = f"{player_name} has no more armies in their initial pool to place."
            # This player is done placing, but others might not be.
            # The orchestrator should only offer this action if player has armies left.
            # We should still advance turn if this state is reached.
            log["success"] = True # No action taken, but not an error for this player.
        else:
            territory.army_count += 1
            current_setup_player.armies_placed_in_setup += 1
            log["success"] = True
            log["message"] = f"{player_name} placed 1 army on {territory_name} (now {territory.army_count}). Total placed by {player_name}: {current_setup_player.armies_placed_in_setup}/{current_setup_player.initial_armies_pool}."

        # Advance to next player in setup order, only if current player successfully placed or had no more to place.
        if log["success"]:
            gs.current_setup_player_index = (gs.current_setup_player_index + 1) % len(gs.player_setup_order)

        if self._all_initial_armies_placed():
            gs.current_game_phase = "REINFORCE" # First game phase after setup
            try:
                gs.current_player_index = gs.players.index(gs.first_player_of_game)
            except ValueError:
                print(f"Error: First player of game '{gs.first_player_of_game.name if gs.first_player_of_game else 'None'}' not found in players list. Defaulting to index 0.")
                gs.current_player_index = 0

            first_player_for_turn = gs.get_current_player()
            if first_player_for_turn:
                first_player_for_turn.armies_to_deploy = self.calculate_reinforcements(first_player_for_turn)
                log["message"] += f" All initial armies placed. Game starts! First turn: {first_player_for_turn.name}. Reinforcements: {first_player_for_turn.armies_to_deploy}."
                print(f"All initial armies placed. Phase: REINFORCE. First player: {first_player_for_turn.name}")
            else: # Should not happen
                log["message"] += " All initial armies placed. Game starts! Error finding first player."
                print("All initial armies placed. Phase: REINFORCE. Error finding first player.")

        return log

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
        # Card trade-in reinforcements are handled by `perform_card_trade` now.

        # player.armies_to_deploy += reinforcements # This is done by the caller
        if player.is_neutral: # Neutral players do not get reinforcements
            return 0

        # 1. Territories owned
        num_territories = len(player.territories)
        reinforcements = max(3, num_territories // 3)

        # 2. Continent bonuses
        for continent in self.game_state.continents.values():
            is_owner_of_all = True
            if not continent.territories:
                is_owner_of_all = False
            for territory in continent.territories:
                if territory.owner != player:
                    is_owner_of_all = False
                    break
            if is_owner_of_all:
                reinforcements += continent.bonus_armies
        return reinforcements

    def _get_card_trade_bonus(self) -> int:
        """Gets the current bonus for trading cards, and escalates for next time."""
        if self.card_trade_bonus_index < len(self.card_trade_bonuses):
            bonus = self.card_trade_bonuses[self.card_trade_bonus_index]
        else:
            bonus = self.card_trade_bonuses[-1] + (self.card_trade_bonus_index - len(self.card_trade_bonuses) + 1) * 5
        return bonus

    def _increment_card_trade_bonus(self):
        self.card_trade_bonus_index += 1

    def find_valid_card_sets(self, player: Player) -> list[list[Card]]:
        """
        Finds all valid sets of cards a player can trade.
        A set is:
        - 3 cards of the same symbol (e.g., 3 Infantry)
        - 1 card of each of the 3 symbols (e.g., 1 Infantry, 1 Cavalry, 1 Artillery)
        - Wildcards can substitute for any symbol.
        Returns a list of sets, where each set is a list of 3 Card objects.
        """
        valid_sets = []
        hand = player.hand
        if len(hand) < 3:
            return []

        from collections import Counter
        import itertools

        # Iterate through all combinations of 3 cards
        for combo_indices in itertools.combinations(range(len(hand)), 3):
            combo = [hand[i] for i in combo_indices]

            symbols_in_combo = [c.symbol for c in combo]
            num_wildcards = symbols_in_combo.count("Wildcard")
            non_wild_symbols = [s for s in symbols_in_combo if s != "Wildcard"]

            # Check for 3 of a kind (possibly with wildcards)
            if num_wildcards == 3: # 3 wildcards is a valid set
                valid_sets.append(list(combo))
                continue
            if num_wildcards == 2 and len(non_wild_symbols) == 1: # 2 wildcards + 1 other is 3 of that kind
                valid_sets.append(list(combo))
                continue
            if num_wildcards == 1 and len(non_wild_symbols) == 2:
                if non_wild_symbols[0] == non_wild_symbols[1]: # 1 wildcard + 2 same symbols is 3 of that kind
                    valid_sets.append(list(combo))
                    continue
            if num_wildcards == 0 and len(set(non_wild_symbols)) == 1: # 3 same non-wild symbols
                 valid_sets.append(list(combo))
                 continue

            # Check for 1 of each unique symbol (possibly with wildcards)
            # The symbols are Infantry, Cavalry, Artillery
            unique_symbols = {"Infantry", "Cavalry", "Artillery"}
            present_symbols = set(non_wild_symbols)

            if num_wildcards == 0:
                if len(present_symbols) == 3: # All 3 unique symbols present, no wildcards
                    valid_sets.append(list(combo))
            elif num_wildcards == 1:
                if len(present_symbols) == 2: # 1 wildcard can complete a set of 3 unique if 2 are already present
                    valid_sets.append(list(combo))
            elif num_wildcards == 2:
                if len(present_symbols) == 1: # 2 wildcards can complete a set of 3 unique if 1 is already present
                    valid_sets.append(list(combo))
            # 3 wildcards already handled by "3 of a kind" logic (counts as any set)

        # Ensure we don't return duplicate sets if multiple card objects are identical but different instances
        # This current implementation identifies sets by card objects, so if cards are unique, sets will be too.
        # If card objects could be identical, further deduplication by card content might be needed.
        return valid_sets


    def perform_card_trade(self, player: Player, cards_to_trade_indices: list[int]) -> dict:
        """
        Performs a card trade for a player.
        - Validates the set.
        - Removes cards from hand.
        - Adds cards to discard pile (or back to deck, depending on rules).
        - Grants reinforcement bonus.
        - Updates player's armies_to_deploy.
        Returns a log of the trade.
        """
        log = {"event": "card_trade", "player": player.name, "success": False, "message": "", "armies_gained": 0}

        if len(cards_to_trade_indices) != 3:
            log["message"] = "Exactly 3 cards must be selected for a trade."
            return log

        # Ensure indices are valid and unique
        if len(set(cards_to_trade_indices)) != 3:
            log["message"] = "Card indices must be unique."
            return log

        cards_to_trade = []
        for i in sorted(cards_to_trade_indices, reverse=True): # Sort reverse to pop correctly
            if i < 0 or i >= len(player.hand):
                log["message"] = "Invalid card index provided."
                return log
            cards_to_trade.append(player.hand[i])
        cards_to_trade.reverse() # Get them back in original order for set checking

        # Validate the set (re-using find_valid_card_sets logic on the selected cards)
        # This is a bit inefficient but ensures the selected cards form a valid set among themselves.
        # A more direct validation of the specific 3 cards would be better.

        # Direct validation of the 3 chosen cards:
        symbols_in_trade = [c.symbol for c in cards_to_trade]
        num_wildcards = symbols_in_trade.count("Wildcard")
        non_wild_symbols = [s for s in symbols_in_trade if s != "Wildcard"]
        is_valid_set = False

        # Check 3 of a kind
        if num_wildcards == 3: is_valid_set = True
        elif num_wildcards == 2 and len(non_wild_symbols) == 1: is_valid_set = True
        elif num_wildcards == 1 and len(non_wild_symbols) == 2 and non_wild_symbols[0] == non_wild_symbols[1]: is_valid_set = True
        elif num_wildcards == 0 and len(set(non_wild_symbols)) == 1: is_valid_set = True

        # Check 1 of each unique
        if not is_valid_set:
            expected_unique = {"Infantry", "Cavalry", "Artillery"}
            present_unique = set(non_wild_symbols)
            if num_wildcards == 0 and len(present_unique) == 3: is_valid_set = True
            elif num_wildcards == 1 and len(present_unique) == 2: is_valid_set = True # Wildcard completes the set
            elif num_wildcards == 2 and len(present_unique) == 1: is_valid_set = True # 2 Wildcards complete the set
            # 3 wildcards is already covered by "3 of a kind"

        if not is_valid_set:
            log["message"] = "The selected cards do not form a valid set."
            log["selected_cards_symbols"] = symbols_in_trade
            return log

        # If valid, remove cards, grant bonus
        for i in sorted(cards_to_trade_indices, reverse=True):
            card_removed = player.hand.pop(i)
            self.game_state.deck.append(card_removed) # Add to bottom of deck (or a discard pile)
        random.shuffle(self.game_state.deck) # Shuffle after adding back

        bonus_armies = self._get_card_trade_bonus()
        player.armies_to_deploy += bonus_armies
        self._increment_card_trade_bonus()

        # Check for territory bonus (if any card matches an owned territory)
        for card in cards_to_trade:
            if card.territory_name: # Wildcards don't have territory names
                territory = self.game_state.territories.get(card.territory_name)
                if territory and territory.owner == player:
                    territory.army_count += 2 # Add 2 armies to that specific territory
                    log["territory_bonus"] = f"Player {player.name} received +2 armies on {card.territory_name} for matching card."
                    break # Only one such bonus per trade

        log["success"] = True
        log["message"] = f"{player.name} traded cards for {bonus_armies} armies."
        log["armies_gained"] = bonus_armies
        log["traded_card_symbols"] = symbols_in_trade
        return log

    def perform_attack(self, attacker_territory_name: str, defender_territory_name: str, num_attacking_armies: int, explicit_defender_dice_count: int | None = None) -> dict:
        """
        Handles dice rolling logic, army reduction, territory ownership changes,
        and card drawing upon conquering a territory.
        explicit_defender_dice_count: If provided (e.g., for Neutral player in 2P mode, chosen by other human),
                                      this exact number of dice will be used for defense if valid.
        Returns a log of the battle's result.
        """
        attacker_territory = self.game_state.territories.get(attacker_territory_name)
        defender_territory = self.game_state.territories.get(defender_territory_name)
        log = {"event": "attack", "attacker": None, "defender": None, "results": [], "conquered": False, "card_drawn": None}
        gs = self.game_state

        # Validations
        if not attacker_territory or not defender_territory:
            log["error"] = "Invalid territory specified."
            return log

        attacker_player = attacker_territory.owner
        defender_player = defender_territory.owner # This could be the Neutral player

        log["attacker"] = attacker_player.name if attacker_player else "N/A"
        log["defender"] = defender_player.name if defender_player else "N/A"
        if defender_player and defender_player.is_neutral:
            log["defender_is_neutral"] = True

        if attacker_player == defender_player: # Also covers attacking own neutral territories if that were possible
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

        # Determine number of defender dice
        actual_defender_dice_count = 0
        if explicit_defender_dice_count is not None:
            # Validate explicit_defender_dice_count against defender's army count
            if explicit_defender_dice_count == 1 and defender_territory.army_count >= 1:
                actual_defender_dice_count = 1
            elif explicit_defender_dice_count == 2 and defender_territory.army_count >= 2:
                actual_defender_dice_count = 2
            elif explicit_defender_dice_count > 0 and defender_territory.army_count > 0 : # e.g. chose 2 but only 1 army
                actual_defender_dice_count = 1 # Default to 1 if choice is invalid but can still defend
            else: # Choice is 0, or defender has 0 armies
                actual_defender_dice_count = 0
            log["defender_dice_choice_is_explicit"] = True
        else: # Standard calculation
            if defender_territory.army_count >= 2:
                actual_defender_dice_count = 2
            elif defender_territory.army_count == 1:
                actual_defender_dice_count = 1
            else:
                actual_defender_dice_count = 0

        log["actual_defender_dice_count"] = actual_defender_dice_count

        max_attacker_dice = min(3, num_attacking_armies)

        attacker_dice_rolls = sorted([random.randint(1, 6) for _ in range(max_attacker_dice)], reverse=True)
        defender_dice_rolls = sorted([random.randint(1, 6) for _ in range(actual_defender_dice_count)], reverse=True)

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

            # armies_to_move = max(max_attacker_dice, num_attacking_armies - attacker_losses) # Must move at least num dice, or all attackers if fewer survived
            # armies_to_move = min(armies_to_move, attacker_territory.army_count -1) # Cannot leave attacker territory empty

            # if armies_to_move > 0 :
            #     defender_territory.army_count = armies_to_move
            #     attacker_territory.army_count -= armies_to_move
            # else: # Should not happen if validation is correct, but as a fallback
            #     defender_territory.army_count = 1 # Move 1 by default if calculation leads to 0
            #     attacker_territory.army_count -=1

            # Instead of automatic movement, set flag and context for AI decision
            self.game_state.requires_post_attack_fortify = True
            # num_attacking_armies_survived is the number of armies from the attacking stack that survived.
            # It's num_attacking_armies (which came from attacker_territory.army_count -1 or less) minus attacker_losses.
            # The number of armies available to move into the new territory is num_attacking_armies - attacker_losses.
            # These armies are currently still conceptually in attacker_territory.
            # The attacker_territory itself must retain at least 1 army.

            # The number of armies that *actually* participated in the final winning battle round
            # is effectively `max_attacker_dice` if we consider Risk rules where dice count is crucial.
            # The player must move at least this many into the conquered territory.
            min_move = max_attacker_dice # Number of dice rolled by attacker in the last battle

            # Max movable is the total number of armies that were designated for the attack, survived,
            # and can be moved while leaving at least 1 behind in the attacker_territory.

            available_to_move_from_attacker_stack = num_attacking_armies - attacker_losses

            # The armies in attacker_territory have already been reduced by attacker_losses.
            # So, attacker_territory.army_count is its current state.
            # The maximum number of armies that can be moved out of attacker_territory is attacker_territory.army_count - 1.
            # The actual number of armies that can move is the minimum of what's available from the attacking stack
            # and what can be physically moved from the territory while leaving one behind.
            max_move = min(available_to_move_from_attacker_stack, attacker_territory.army_count - 1)

            # Ensure min_move is not more than what's available or more than what can be moved from the territory
            # And min_move should not be more than max_move.
            min_move = min(min_move, max_move)
            # Ensure min_move is at least 1 if max_move is positive. If max_move is 0, min_move must also be 0.
            min_move = max(1, min_move) if max_move > 0 else 0
            # If after adjustments, min_move > max_move (e.g. max_move became 0 but min_move was 1 from dice), then set min_move to max_move.
            if min_move > max_move:
                min_move = max_move


            if max_move <= 0 : # No armies survived the attack to move, or only 1 left in attacking territory to move (which means it becomes 0)
                # This implies the territory was taken with the last possible army, which is unusual.
                # Or the num_attacking_armies was 1, and it survived.
                # Standard rules: must move at least `max_attacker_dice` armies.
                # If `max_move` is 0, it means `available_to_move_from_attacker_stack` is 0.
                # This suggests `num_attacking_armies == attacker_losses`. All attacking armies died.
                # This path should not be taken if `defender_territory.army_count <= 0`
                # because it means attacker won. So `attacker_losses` must be less than `num_attacking_armies`
                # if `attacker_dice_rolls[i] > defender_dice_rolls[i]` happened at least once for the final blow.
                # This case needs careful thought. If all attacking armies died, but territory was conquered,
                # it implies defender also lost all armies.
                # For now, if max_move is 0, it's an issue. Default to moving 1 from attacker_territory if possible.
                # This means the `perform_post_attack_fortify` will handle it.
                # The conquered territory starts with 0.
                defender_territory.army_count = 0 # Explicitly set to 0, to be filled by post_attack_fortify
                log["message_debug"] = f"Conquest occurred, but available_to_move_from_attacker_stack is {available_to_move_from_attacker_stack}. Min_move: {min_move}, Max_move: {max_move}"

            else:
                 defender_territory.army_count = 0 # Explicitly set to 0, to be filled by post_attack_fortify

            self.game_state.conquest_context = {
                "from_territory_name": attacker_territory_name,
                "to_territory_name": defender_territory_name,
                "min_movable": min_move, # Must move at least this many
                "max_movable": max_move, # Can move up to this many
                "armies_in_attacking_territory_after_battle": attacker_territory.army_count
            }
            log["post_attack_fortify_required"] = True
            log["conquest_context"] = self.game_state.conquest_context

            # Draw a card if one is available and player hasn't drawn one this turn yet
            # Draw a card if one is available and player hasn't drawn one this turn yet
            if not new_owner.has_conquered_territory_this_turn and self.game_state.deck:
                card = self.game_state.deck.pop(0)
                new_owner.hand.append(card)
                new_owner.has_conquered_territory_this_turn = True # Mark that they've received a card for conquest this turn
                log["card_drawn"] = card.to_dict()
            elif new_owner.has_conquered_territory_this_turn:
                log["card_skipped_reason"] = "Player already received a card this turn for conquest."
            elif not self.game_state.deck:
                log["card_skipped_reason"] = "Deck is empty."


            # Check if the old owner is eliminated
            if old_owner and not old_owner.territories:
                log["eliminated_player_name"] = old_owner.name # Log name for orchestrator
                new_owner.hand.extend(old_owner.hand)
                old_owner.hand.clear()
                log["cards_transferred_count"] = len(new_owner.hand) # Log new hand size for orchestrator

                # Check for mandatory card trade
                if len(new_owner.hand) >= 6: # As per rule: "If winning them gives you 6 or more cards"
                    self.game_state.elimination_card_trade_player_name = new_owner.name
                    log["mandatory_card_trade_initiated"] = new_owner.name
                # Note: GameState.players list (actual removal of player object) should be updated by orchestrator
                # after processing the elimination event from this log.

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

        current_player = from_territory.owner # Should be same as to_territory.owner
        if current_player:
            current_player.has_fortified_this_turn = True

        log["success"] = True
        log["message"] = f"Successfully moved {num_armies} armies from {from_territory.name} to {to_territory.name}."
        log["from_territory"] = from_territory.name
        log["to_territory"] = to_territory.name
        log["num_armies"] = num_armies
        return log

    def perform_post_attack_fortify(self, player: Player, num_armies_to_move: int) -> dict:
        """
        Moves armies into a newly conquered territory based on player's decision.
        This is called after a conquest when game_state.requires_post_attack_fortify is True.
        """
        log = {"event": "post_attack_fortify", "player": player.name, "success": False, "message": ""}

        if not self.game_state.requires_post_attack_fortify or not self.game_state.conquest_context:
            log["message"] = "No post-attack fortification is currently required or context is missing."
            return log

        context = self.game_state.conquest_context
        from_territory_name = context["from_territory_name"]
        to_territory_name = context["to_territory_name"] # This is the newly conquered one
        min_movable = context["min_movable"]
        max_movable = context["max_movable"]
        # armies_in_attacking_territory_after_battle = context["armies_in_attacking_territory_after_battle"] # Informational

        from_territory = self.game_state.territories.get(from_territory_name)
        to_territory = self.game_state.territories.get(to_territory_name)

        if not from_territory or not to_territory:
            log["message"] = f"Invalid territories in conquest context: {from_territory_name}, {to_territory_name}."
            # This would be an internal error, reset state to be safe
            self.game_state.requires_post_attack_fortify = False
            self.game_state.conquest_context = None
            return log

        if to_territory.owner != player:
            log["message"] = f"Player {player.name} does not own the conquered territory {to_territory_name} according to current state."
            # This implies an issue, perhaps state changed. Reset.
            self.game_state.requires_post_attack_fortify = False
            self.game_state.conquest_context = None
            return log

        if from_territory.owner != player:
            log["message"] = f"Player {player.name} does not own the attacking territory {from_territory_name}."
            self.game_state.requires_post_attack_fortify = False # Reset to avoid getting stuck
            self.game_state.conquest_context = None
            return log

        # Validate num_armies_to_move
        if not (min_movable <= num_armies_to_move <= max_movable):
            log["message"] = f"Invalid number of armies to move: {num_armies_to_move}. Must be between {min_movable} and {max_movable}."
            # Do not reset requires_post_attack_fortify here, let orchestrator call again with valid actions.
            return log

        # Ensure the attacking territory retains at least 1 army
        if from_territory.army_count - num_armies_to_move < 1:
            log["message"] = f"Cannot move {num_armies_to_move} armies from {from_territory.name}. It would leave less than 1 army. (Current: {from_territory.army_count}, Max movable was {max_movable})"
            # This condition should ideally be caught by max_movable logic derived in perform_attack.
            # If max_movable was calculated such that (armies_in_attacking_territory_after_battle - max_movable) < 1,
            # then max_movable should have been capped at armies_in_attacking_territory_after_battle - 1.
            # The current max_movable is num_attacking_armies - attacker_losses.
            # The from_territory.army_count is original_army_count - attacker_losses.
            # If num_attacking_armies was from_territory.army_count - X (where X >= 1 for the one left behind),
            # then (num_attacking_armies - attacker_losses) should be less than (from_territory.army_count (after losses) -1)
            # Let's assume max_movable calculation in perform_attack is correct:
            # max_move = available_to_move_from_attacker_stack
            # available_to_move_from_attacker_stack = num_attacking_armies - attacker_losses
            # If AI requests to move N armies, and N <= max_movable:
            # We need to check: from_territory.army_count (which is original count - losses) - N >= 1
            # This check is vital.
            # The max_movable should have already ensured this.
            # If num_armies_to_move == from_territory.army_count, then it means max_movable was too high.
            # Max_movable should be min(available_to_move_from_attacker_stack, from_territory.army_count - 1)
            # This check here is a safeguard.
            return log # Let AI try again with a valid number based on updated valid actions.

        # Perform the move
        from_territory.army_count -= num_armies_to_move
        to_territory.army_count += num_armies_to_move # Conquered territory army count was set to 0

        log["success"] = True
        log["message"] = f"{player.name} moved {num_armies_to_move} armies from {from_territory.name} to {to_territory.name}."
        log["from_territory_final_armies"] = from_territory.army_count
        log["to_territory_final_armies"] = to_territory.army_count

        # Reset the flag and context
        self.game_state.requires_post_attack_fortify = False
        self.game_state.conquest_context = None

        return log

    def _are_territories_connected(self, start_territory: Territory, end_territory: Territory, player: Player) -> bool:
        """
        Checks if two territories are ADJACENT and owned by the given player.
        This is for the strict Risk rule for fortification.
        """
        if start_territory.owner != player or end_territory.owner != player:
            return False # Should be pre-filtered by caller, but good check

        # Check for direct adjacency
        if end_territory in start_territory.adjacent_territories:
            return True

        return False

    def is_game_over(self) -> Player | None:
        """
        Checks for win conditions:
        - Standard: One player owns all territories.
        - 2-Player: One human player eliminates the other human player.
        Returns the winning player or None.
        """
        gs = self.game_state
        if not gs.territories:
            return None

        if gs.is_two_player_game:
            human_players_with_territories = [p for p in gs.players if not p.is_neutral and p.territories]
            if len(human_players_with_territories) == 1:
                # The one remaining human player is the winner.
                # Neutral territories don't need to be conquered.
                return human_players_with_territories[0]
            elif not human_players_with_territories: # Should not happen if game ends with one winner
                print("Error: 2-player game, but no human players with territories found.")
                return None # Or handle as a draw/error
            else: # More than one human player still has territories
                return None
        else: # Standard game mode (3-6 players)
            first_owner = None
            all_territories_owned_by_one_player = True
            for territory in gs.territories.values():
                if territory.owner is None or territory.owner.is_neutral : # Unowned or neutral owned means not over for standard
                    all_territories_owned_by_one_player = False
                    break
                if first_owner is None:
                    first_owner = territory.owner
                elif territory.owner != first_owner:
                    all_territories_owned_by_one_player = False
                    break

            if all_territories_owned_by_one_player and first_owner:
                return first_owner # This first_owner is not neutral due to check above

            # Additional check: if only one non-neutral player remains with territories
            # This should only apply if the game is past the initial setup phases.
            setup_phases = [
                "SETUP_START", "SETUP_DETERMINE_ORDER",
                "SETUP_CLAIM_TERRITORIES", "SETUP_PLACE_ARMIES",
                "SETUP_2P_DEAL_CARDS", "SETUP_2P_PLACE_REMAINING" # Included for completeness
            ]
            if gs.current_game_phase not in setup_phases:
                active_non_neutral_players = [p for p in gs.players if not p.is_neutral and p.territories]
                if len(active_non_neutral_players) == 1:
                    # This check implies that if only one player has territories AND we are past setup, they win.
                    # This is a valid win condition by elimination.
                    return active_non_neutral_players[0]

            return None

    def next_turn(self):
        """
        Advances to the next player and resets turn-specific state.
        """
        gs = self.game_state
        if not gs.players:
            return

        current_player_obj = gs.get_current_player()
        if current_player_obj:
            current_player_obj.has_fortified_this_turn = False
            current_player_obj.has_conquered_territory_this_turn = False

        # Determine active (non-neutral, territory-holding) players for turn progression
        active_human_players = [p for p in gs.players if not p.is_neutral and p.territories]

        if not active_human_players:
            print("Warning: No active human players with territories found during next_turn.")
            # Game over should be caught by is_game_over, but this is a fallback.
            # If is_two_player_game, this means one human player eliminated the other.
            # If not, it means all human players are eliminated (e.g. by some other logic or error).
            return

        if len(active_human_players) == 1 and gs.is_two_player_game:
            # Game over condition for 2-player game is handled by is_game_over
            print(f"Next_turn called when only one human player ({active_human_players[0].name}) remains in 2P game. Game should be over.")
            return


        next_player_found = False
        original_player_count = len(gs.players) # Total players including neutral

        for i in range(1, original_player_count + 1):
            next_potential_idx = (gs.current_player_index + i) % original_player_count
            potential_next_player = gs.players[next_potential_idx]

            if not potential_next_player.is_neutral and potential_next_player in active_human_players:
                # Check if we wrapped around to the start of the active human player list
                # This is a simplified way to detect a new round for turn counting
                # More robust: compare new index to old index relative to active_human_players

                # If the new index is less than or equal to the old index (after wrapping), it's a new round for turn counting.
                # This needs to be careful if players are eliminated.
                # A simpler way for turn counting: if the new current_player_index (overall list)
                # means we passed the original first_player_of_game or index 0.
                # Let's count a new turn if the chosen next_potential_idx is 0 (or index of first_player_of_game)
                # AND it's not the same player starting again immediately (e.g. single player left).

                old_overall_idx = gs.current_player_index
                gs.current_player_index = next_potential_idx

                # Check if this constitutes a full round of active human players
                # This is tricky if active_human_players list changes due to elimination
                # A simpler check: if the new player index is less than the old one (after modulo),
                # it often means a new round for turn counting.
                # Or, if the new player is the very first player in the overall list of human players.
                first_human_player_overall_idx = -1
                for idx, p_obj in enumerate(gs.players):
                    if not p_obj.is_neutral:
                        first_human_player_overall_idx = idx
                        break

                if gs.current_player_index == first_human_player_overall_idx and gs.current_player_index != old_overall_idx :
                     gs.current_turn_number += 1

                next_player_found = True
                break

        if not next_player_found:
            # This should not happen if there's at least one active human player.
            # Could mean current_player_index was pointing at Neutral and loop didn't find next human.
            # Try to reset to the first active human player.
            if active_human_players:
                try:
                    gs.current_player_index = gs.players.index(active_human_players[0])
                    print(f"Warning: Next player not found by iteration, reset to first active human: {active_human_players[0].name}")
                except ValueError:
                    print("Error: Could not find first active human player in main player list after next_turn error.")
                    return # Critical error
            else: # No active human players, game should be over.
                print("Error: No next player found and no active human players.")
                return


        gs.current_game_phase = "REINFORCE"
        new_current_player_obj = gs.get_current_player() # This should now be a non-neutral, active player

        if new_current_player_obj:
            if new_current_player_obj.is_neutral: # Should not happen if logic above is correct
                print(f"CRITICAL ERROR in next_turn: New current player {new_current_player_obj.name} is Neutral.")
                # Attempt recovery: find next non-neutral.
                # This indicates a flaw in the player iteration logic above.
                # For now, let the game proceed, but this needs fixing.
            else:
                new_current_player_obj.armies_to_deploy = self.calculate_reinforcements(new_current_player_obj)
        else:
            print("CRITICAL ERROR in next_turn: No current player after advancing turn.")


    def get_valid_actions(self, player: Player) -> list:
        """
        Generates a list of valid actions for the current player in the current phase.
        This is a placeholder and will need significant expansion.
        """
        # This will be a complex function depending on the game phase and state.
        # For now, returning a generic list.
        actions = []
        gs = self.game_state
        phase = gs.current_game_phase

        # Check for mandatory post-elimination card trade first. This overrides other actions.
        if gs.elimination_card_trade_player_name == player.name:
            if len(player.hand) <= 4: # Target is 4 or fewer cards
                gs.elimination_card_trade_player_name = None # Requirement met
                # Fall through to regular actions for the current phase (e.g. post_attack_fortify or attack)
            else:
                valid_card_sets = self.find_valid_card_sets(player)
                if not valid_card_sets:
                    # Player has > 4 cards but no sets to trade. This is an edge case.
                    # As per rules "once your hand is reduced to 4,3, or 2 cards, you must stop trading."
                    # If they have 5 with no sets, they can't reduce further.
                    # If they have 6+ with no sets, this is problematic. For now, assume they can always make sets if >4.
                    # If they truly cannot make sets to get to 4 or less, the flag should be cleared.
                    # This logic implies: if len(player.hand) >= 5 and no sets, then this state is problematic.
                    # For now, if no sets, they can't trade, so clear the flag.
                    # The rule "reduce your hand to 4 or fewer cards" implies you trade *if possible*.
                    # "But once your hand is reduced to 4, 3, or 2 cards, you must stop trading."
                    # This means if you have 5 cards and make a trade, you get to 2 + new armies.
                    # If you have 5 cards and CANNOT make a trade, you stop.
                    if len(player.hand) >=5 and not valid_card_sets: # Cannot make a trade to reduce hand
                         gs.elimination_card_trade_player_name = None # Consider requirement met as impossible to proceed
                    # Fall through to regular actions.
                else: # Has sets and must trade
                    for card_set in valid_card_sets:
                        card_indices_in_hand = [player.hand.index(c) for c in card_set if c in player.hand]
                        if len(card_indices_in_hand) == 3:
                            actions.append({
                                "type": "TRADE_CARDS",
                                "card_indices": sorted(card_indices_in_hand),
                                "must_trade": True, # This is a mandatory trade due to elimination
                                "reason": "Post-elimination mandatory trade"
                            })
                    if actions: # Only trade actions are allowed
                        return actions
                    else: # No valid sets found, despite hand > 4. Clear flag.
                        gs.elimination_card_trade_player_name = None
                        # Fall through to regular actions.

        # Check for mandatory post-attack fortification next, as this takes precedence over other phase actions.
        if gs.requires_post_attack_fortify and gs.conquest_context:
            context = gs.conquest_context
            if context["max_movable"] >= 0 : # Allow 0 move if that's the only option
                actions.append({
                    "type": "POST_ATTACK_FORTIFY",
                    "from_territory": context["from_territory_name"],
                    "to_territory": context["to_territory_name"],
                    "min_armies": context["min_movable"],
                    "max_armies": context["max_movable"],
                })
            # If max_movable is < 0 (should not happen), no valid PAF action.
            # This implies an issue in conquest_context setup.
            # If actions list is empty here, orchestrator might need to auto-resolve PAF.
            return actions # Return immediately, only PAF is valid.

        # Handle 2-Player Specific Setup Phases first
        if gs.is_two_player_game:
            if phase == "SETUP_2P_DEAL_CARDS":
                # This is an automatic engine step triggered by orchestrator, no player actions.
                return [{"type": "AUTO_SETUP_2P_DEAL_CARDS"}] # Orchestrator will call specific engine method

            if phase == "SETUP_2P_PLACE_REMAINING":
                if player.is_neutral: return [] # Neutral player doesn't act

                armies_left_in_player_pool = player.initial_armies_pool - player.armies_placed_in_setup
                can_place_own = armies_left_in_player_pool > 0

                neutral_player = next((p for p in gs.players if p.is_neutral), None)
                can_place_neutral = neutral_player and neutral_player.armies_placed_in_setup < neutral_player.initial_armies_pool

                if not can_place_own and not can_place_neutral: # Player and Neutral are done
                    # This state means this player has no more armies, and neutral has no more.
                    # Orchestrator should detect if all players are done.
                    # For this player, they effectively pass.
                    return [{"type": "SETUP_2P_DONE_PLACING"}] # Signal this player is done

                # Action structure for 2P remaining placement:
                # The AI needs to choose 2 armies for itself and 1 for neutral (if possible)
                # This is complex for a single action.
                # Alternative: Orchestrator asks for player's 2 armies, then asks for neutral placement.
                # For now, let's generate a composite action type that orchestrator will parse.
                action_template = {
                    "type": "SETUP_2P_PLACE_ARMIES_TURN",
                    "player_can_place_own": can_place_own,
                    "player_armies_to_place_this_turn": min(2, armies_left_in_player_pool) if can_place_own else 0,
                    "player_owned_territories": [t.name for t in player.territories],
                    "neutral_can_place": can_place_neutral,
                    "neutral_owned_territories": [t.name for t in neutral_player.territories] if neutral_player else []
                }
                actions.append(action_template)
                return actions

        # Standard Setup Phases (not 2-player specific card dealing/placing)
        if phase == "SETUP_DETERMINE_ORDER":
            # Usually handled by orchestrator rolling dice, then calling set_player_setup_order.
            # No direct player actions here, more of an orchestrator state.
            return [{"type": "AWAIT_SETUP_ORDER"}]

        if phase == "SETUP_CLAIM_TERRITORIES":
            if player.is_neutral: return [] # Should not happen if setup_order is correct
            if gs.unclaimed_territory_names:
                for terr_name in gs.unclaimed_territory_names:
                     actions.append({"type": "SETUP_CLAIM", "territory": terr_name})
            return actions

        if phase == "SETUP_PLACE_ARMIES": # Standard setup
            if player.is_neutral: return []
            if player.armies_placed_in_setup < player.initial_armies_pool:
                for territory in player.territories:
                    actions.append({
                        "type": "SETUP_PLACE_ARMY",
                        "territory": territory.name,
                        "armies_left_in_pool": player.initial_armies_pool - player.armies_placed_in_setup
                        })
            else: # Player is done placing their initial armies
                 actions.append({"type": "SETUP_STANDARD_DONE_PLACING"})
            return actions

        # Regular Game Phases - ensure neutral player doesn't act
        if player.is_neutral:
            return []

        if phase == "REINFORCE":
            # Option to trade cards
            # Player must trade cards if they have 5 or more.
            # Otherwise, they can choose to trade if they have a valid set.

            must_trade = len(player.hand) >= 5
            valid_card_sets = self.find_valid_card_sets(player)
            trade_actions = []

            if valid_card_sets:
                for card_set in valid_card_sets:
                    card_indices_in_hand = [player.hand.index(c) for c in card_set if c in player.hand]
                    if len(card_indices_in_hand) == 3: # Ensure all cards are found
                        trade_actions.append({
                            "type": "TRADE_CARDS",
                            "card_indices": sorted(card_indices_in_hand),
                            "must_trade": must_trade # Correctly reflects if the trade is mandatory
                        })

            if must_trade:
                if trade_actions: # If player must trade and has valid sets
                    actions.extend(trade_actions)
                    # If must_trade is true, only TRADE_CARDS actions should be available.
                    # No DEPLOY or END_REINFORCE_PHASE until card situation is resolved.
                else:
                    # Player must trade but has no valid sets. This is a problematic state.
                    # For now, the player will have no valid actions in reinforce phase.
                    # This might need a specific game rule (e.g., discard cards, lose turn phase).
                    # Current behavior: no actions, AI might be stuck or orchestrator handles it.
                    pass # No actions available
            else:
                # Player does not have to trade (less than 5 cards)
                # Add deployment actions if any armies to deploy
                if player.armies_to_deploy > 0:
                    for territory in player.territories:
                        actions.append({"type": "DEPLOY", "territory": territory.name, "max_armies": player.armies_to_deploy})

                # Add optional card trade actions
                if trade_actions: # These will have must_trade: False
                    actions.extend(trade_actions)

                # Add END_REINFORCE_PHASE if no armies to deploy
                # Or if there are armies but player might want to end reinforcement without deploying all
                # (though current Risk rules usually mean deploy all reinforcements from territories/continents)
                # For card trade armies, they are added, then deployment continues.
                # END_REINFORCE_PHASE is valid if not in a must_trade situation and (armies_to_deploy == 0 OR has deploy options)
                if player.armies_to_deploy == 0:
                    actions.append({"type": "END_REINFORCE_PHASE"})
                elif any(action["type"] == "DEPLOY" for action in actions): # If there are deployment options, allow ending too.
                    # This allows AI to end phase even if it has armies but no territories (edge case)
                    # or if it simply wants to (though not standard Risk for initial reinforcements)
                    actions.append({"type": "END_REINFORCE_PHASE"})


            # If after all logic, no actions are available (e.g. must_trade but no sets, or no armies and no cards)
            # and END_REINFORCE_PHASE wasn't added, add it.
            # Exception: if must_trade is active and trade_actions were available, don't add END_REINFORCE_PHASE.
            # The only way to proceed is to trade.
            is_must_trade_with_options = must_trade and any(a["type"] == "TRADE_CARDS" for a in actions)
            if not actions and not is_must_trade_with_options :
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
            if not player.has_fortified_this_turn:
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

            # Always possible to end the turn (which skips fortification if not done)
            actions.append({"type": "END_TURN"})

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
