from .data_structures import GameState, Player, Territory, Continent, Card
import json
import random

class GameEngine:
    def __init__(self, game_mode: str = "standard", custom_map_file_path: str | None = None):
        self.game_state = GameState()
        self.game_mode = game_mode

        # Set game mode flags on GameState instance
        if self.game_mode == "world_map":
            self.map_file_path = custom_map_file_path if custom_map_file_path else "world_map_config.json"
            self.game_state.is_truthful_world_map_mode = True
            self.game_state.is_two_player_game = False # Default for world_map, can be overridden by orchestrator if player count is 2
        elif self.game_mode == "2_player_standard":
            self.map_file_path = custom_map_file_path if custom_map_file_path else "map_config.json"
            self.game_state.is_two_player_game = True
            self.game_state.is_truthful_world_map_mode = False
        else: # Standard game
            self.map_file_path = custom_map_file_path if custom_map_file_path else "map_config.json"
            self.game_state.is_two_player_game = False
            self.game_state.is_truthful_world_map_mode = False

        self.card_trade_bonus_index = 0
        self.card_trade_bonuses = [4, 6, 8, 10, 12, 15]
        print(f"GameEngine initialized with game_mode: {self.game_mode}, map_file_path: {self.map_file_path}, is_truthful_world_map: {self.game_state.is_truthful_world_map_mode}, is_two_player: {self.game_state.is_two_player_game}")

    def initialize_game_from_map(self, players_data: list[dict]):
        gs = self.game_state
        gs.current_game_phase = "SETUP_START"

        if gs.is_truthful_world_map_mode:
            print("Initializing for Truthful World Map mode.")
            if not (2 <= len(players_data) <= 6):
                print(f"Error: Truthful World Map mode requires 2-6 players, got {len(players_data)}.")
                gs.current_game_phase = "ERROR"; return
            if len(players_data) == 2:
                 gs.is_two_player_game = True # Set flag if 2 players are playing world map
                 print("Truthful World Map mode with 2 players detected. Applying 2-player game logic for win conditions etc.")
        elif gs.is_two_player_game: # Standard 2-player (implies not truthful_world_map_mode here)
            if len(players_data) != 2:
                print("Error: Standard 2-player game mode set, but players_data does not contain 2 players.")
                gs.current_game_phase = "ERROR"; return
            print("Initializing for 2-Player Standard Game Rules.")

        try:
            with open(self.map_file_path, 'r') as f:
                map_data = json.load(f)
        except FileNotFoundError:
            print(f"Error: Map file '{self.map_file_path}' not found.")
            gs.current_game_phase = "ERROR"; return
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from map file '{self.map_file_path}'.")
            gs.current_game_phase = "ERROR"; return

        gs.continents.clear()
        for cont_data in map_data.get("continents", []):
            continent = Continent(name=cont_data["name"], bonus_armies=cont_data["bonus_armies"])
            gs.continents[continent.name] = continent

        gs.territories.clear()
        gs.unclaimed_territory_names.clear()

        # Create ACTUAL Players first
        if not players_data:
            print("Error: No player data provided for initialization.")
            gs.current_game_phase = "ERROR"; return

        gs.players.clear()
        active_players = []
        for player_info in players_data:
            player = Player(name=player_info["name"], color=player_info["color"])
            active_players.append(player)
        gs.players.extend(active_players)

        # Add Neutral player for standard 2-player mode
        if gs.is_two_player_game and not gs.is_truthful_world_map_mode:
            used_colors = [p.color.lower() for p in active_players]
            neutral_color = "Gray"
            if "gray" in used_colors:
                possible_colors = ["LightBlue", "Brown", "Pink", "Orange"]
                for pc in possible_colors:
                    if pc.lower() not in used_colors: neutral_color = pc; break
            neutral_2p_player = Player(name="Neutral", color=neutral_color, is_neutral=True)
            gs.players.append(neutral_2p_player)

        if not gs.players:
             print("Error: No players were set up."); gs.current_game_phase = "ERROR"; return

        # Territory Initialization & Assignment for World Map Mode
        if gs.is_truthful_world_map_mode:
            territories_to_assign_ranked = []
            for terr_name, terr_data in map_data.get("territories", {}).items():
                initial_armies = terr_data.get("initial_armies_override", 1)
                continent_name = terr_data.get("continent")
                continent = gs.continents.get(continent_name)
                territories_to_assign_ranked.append({
                    "name": terr_name, "data": terr_data,
                    "armies": initial_armies, "continent_obj": continent
                })

            # Sort territories by military power (descending)
            territories_to_assign_ranked.sort(key=lambda t: t["armies"], reverse=True)

            non_neutral_players_for_assignment = [p for p in gs.players if not p.is_neutral]
            if not non_neutral_players_for_assignment:
                print("Error: No non-neutral players to assign territories to in Truthful World Map mode.")
                gs.current_game_phase = "ERROR"; return

            for i, terr_info in enumerate(territories_to_assign_ranked):
                player_to_assign = non_neutral_players_for_assignment[i % len(non_neutral_players_for_assignment)]
                territory = Territory(name=terr_info["name"], continent=terr_info["continent_obj"],
                                      owner=player_to_assign, army_count=terr_info["armies"])
                gs.territories[territory.name] = territory
                player_to_assign.territories.append(territory)
                if terr_info["continent_obj"]:
                    terr_info["continent_obj"].territories.append(territory)
                print(f"Assigned {territory.name} ({territory.army_count} armies) to {player_to_assign.name}")
            gs.unclaimed_territory_names.clear() # All territories are assigned
        else: # Standard or 2-player standard mode
            for terr_name, terr_data in map_data.get("territories", {}).items():
                continent_name = terr_data.get("continent")
                continent = gs.continents.get(continent_name)
                if not continent:
                    print(f"Warning: Continent '{continent_name}' for territory '{terr_name}' not found.")
                territory = Territory(name=terr_name, continent=continent, owner=None, army_count=0)
                gs.territories[territory.name] = territory
                gs.unclaimed_territory_names.append(terr_name)
                if continent: continent.territories.append(territory)
            random.shuffle(gs.unclaimed_territory_names)

        # Link adjacent territories
        for terr_name, terr_data in map_data.get("territories", {}).items():
            territory = gs.territories.get(terr_name)
            if territory:
                territory.adjacent_territories.clear()
                for adj_name in terr_data.get("adjacent_to", []):
                    adj_territory = gs.territories.get(adj_name)
                    if adj_territory: territory.adjacent_territories.append(adj_territory)
                    else: print(f"Warning: Adjacent territory '{adj_name}' for '{terr_name}' not found.")

        # Army pool allocation (not for truthful_world_map)
        if not gs.is_truthful_world_map_mode:
            if gs.is_two_player_game:
                initial_armies_per_entity = 40
                for player in gs.players:
                    player.initial_armies_pool = initial_armies_per_entity
                    player.armies_placed_in_setup = 0
            else:
                num_actual_players_for_army_calc = len([p for p in gs.players if not p.is_neutral])
                initial_armies_per_player = 0
                if num_actual_players_for_army_calc == 3: initial_armies_per_player = 35
                elif num_actual_players_for_army_calc == 4: initial_armies_per_player = 30
                elif num_actual_players_for_army_calc == 5: initial_armies_per_player = 25
                elif num_actual_players_for_army_calc == 6: initial_armies_per_player = 20
                else:
                    print(f"Error: Invalid non-neutral player count ({num_actual_players_for_army_calc}) for standard game. Must be 3-6.")
                    gs.current_game_phase = "ERROR"; return
                for player in gs.players:
                    if not player.is_neutral:
                        player.initial_armies_pool = initial_armies_per_player
                        player.armies_placed_in_setup = 0
        else: # Truthful World Map: players start with 0 pool, armies are on territories.
             for player in gs.players:
                 if not player.is_neutral:
                     player.initial_armies_pool = 0
                     player.armies_placed_in_setup = 0

        gs.deck.clear()
        symbols = ["Infantry", "Cavalry", "Artillery"]
        symbol_idx = 0
        territory_names_for_cards = list(gs.territories.keys())

        if gs.is_two_player_game and not gs.is_truthful_world_map_mode:
            if len(territory_names_for_cards) != 42:
                print(f"Error: Map for 2-player standard needs 42 territories, found {len(territory_names_for_cards)}.")
                gs.current_game_phase = "ERROR"; return
            for terr_name in territory_names_for_cards:
                gs.deck.append(Card(terr_name, symbols[symbol_idx % 3])); symbol_idx +=1
            random.shuffle(gs.deck)
        else:
            for terr_name in territory_names_for_cards:
                gs.deck.append(Card(terr_name, symbols[symbol_idx % 3])); symbol_idx +=1
            gs.deck.append(Card(None, "Wildcard"))
            gs.deck.append(Card(None, "Wildcard"))
            random.shuffle(gs.deck)

        if gs.is_truthful_world_map_mode:
            gs.current_game_phase = "SETUP_DETERMINE_ORDER"
            gs.player_setup_order = [p for p in gs.players if not p.is_neutral]
            if not gs.player_setup_order: # Should not happen if players_data was valid
                 print("Error: No non-neutral players for Truthful World Map turn order."); gs.current_game_phase = "ERROR"; return
            random.shuffle(gs.player_setup_order)
            gs.first_player_of_game = gs.player_setup_order[0]
            gs.current_setup_player_index = 0 # Not used for placing, but set for consistency if needed
            print("Truthful World Map: Territories auto-assigned. Proceeding to determine turn order.")
        elif gs.is_two_player_game:
            gs.current_game_phase = "SETUP_2P_DEAL_CARDS"
        else:
            gs.current_game_phase = "SETUP_DETERMINE_ORDER"

        print(f"Game initialized. Mode: {self.game_mode}. Phase: {gs.current_game_phase}. Players: {[p.name for p in gs.players if not p.is_neutral]}.")
        if not gs.is_truthful_world_map_mode:
            print(f"Unclaimed territories: {len(gs.unclaimed_territory_names)}")
        else:
            unowned_check = [t_name for t_name, t in gs.territories.items() if t.owner is None or t.owner.is_neutral]
            if unowned_check:
                print(f"Warning: Truthful World Map mode has {len(unowned_check)} unowned/neutral territories after init: {unowned_check}")
            else:
                print("Truthful World Map: All territories assigned to players with pre-set armies.")

    def setup_two_player_initial_territory_assignment(self) -> dict:
        gs = self.game_state
        log = {"event": "setup_2p_deal_cards", "success": False, "message": ""}

        if not (gs.is_two_player_game and not gs.is_truthful_world_map_mode) or gs.current_game_phase != "SETUP_2P_DEAL_CARDS":
            log["message"] = f"Cannot perform 2-player card dealing in current state (is_2p_std: {gs.is_two_player_game and not gs.is_truthful_world_map_mode}, phase: {gs.current_game_phase})."
            return log

        # Expecting 2 human players + 1 Neutral already in gs.players from initialize_game_from_map
        if len(gs.players) != 3:
            log["message"] = f"Error: Expected 3 players (P1, P2, Neutral) for 2-player card setup, found {len(gs.players)}."
            return log

        if len(gs.deck) != 42:
            log["message"] = f"Error: Deck should have 42 territory cards for 2-player setup, found {len(gs.deck)}."
            return log

        human_players = [p for p in gs.players if not p.is_neutral]
        neutral_player = next((p for p in gs.players if p.is_neutral and p.name == "Neutral"), None) # Standard 2P neutral

        if len(human_players) != 2 or not neutral_player:
            log["message"] = "Error: Could not identify 2 human players and 1 standard Neutral player."
            return log

        players_for_deal = human_players + [neutral_player]
        assigned_territories_log = {p.name: [] for p in players_for_deal}

        for _ in range(14):
            for player_receiving_card in players_for_deal:
                if not gs.deck:
                    log["message"] = "Error: Deck ran out during 2P territory assignment."; return log
                card = gs.deck.pop(0)
                territory_name = card.territory_name
                if not territory_name:
                    log["message"] = f"Error: Drew non-territory card '{card}' during 2P setup."; return log
                territory = gs.territories.get(territory_name)
                if not territory or territory_name not in gs.unclaimed_territory_names:
                    log["message"] = f"Error: Territory '{territory_name}' not found or already claimed."; return log
                if player_receiving_card.armies_placed_in_setup >= player_receiving_card.initial_armies_pool:
                    log["message"] = f"{player_receiving_card.name} has no armies for initial claim."; return log

                territory.owner = player_receiving_card
                territory.army_count = 1
                player_receiving_card.territories.append(territory)
                player_receiving_card.armies_placed_in_setup += 1
                gs.unclaimed_territory_names.remove(territory_name)
                assigned_territories_log[player_receiving_card.name].append(territory_name)

        if gs.unclaimed_territory_names:
            log["message"] = f"Error: {len(gs.unclaimed_territory_names)} territories unclaimed after 2P card dealing."
        else:
            log["success"] = True
            log["message"] = "All 42 territories assigned via cards for 2P setup. Each has 1 army."
            gs.current_game_phase = "SETUP_2P_PLACE_REMAINING"
            gs.player_setup_order = human_players
            gs.current_setup_player_index = 0
            gs.first_player_of_game = human_players[0]
        log["assigned_territories_map"] = assigned_territories_log
        return log

    def player_places_initial_armies_2p(self, acting_player_name: str, own_army_placements: list[tuple[str, int]], neutral_army_placement: tuple[str, int] | None) -> dict:
        gs = self.game_state
        log = {"event": "place_initial_armies_2p", "player": acting_player_name, "success": False, "message": ""}

        if not (gs.is_two_player_game and not gs.is_truthful_world_map_mode) or gs.current_game_phase != "SETUP_2P_PLACE_REMAINING":
            log["message"] = f"Cannot place 2P initial armies in current state."
            return log

        # Get current setup player from gs.player_setup_order
        if not gs.player_setup_order or gs.current_setup_player_index >= len(gs.player_setup_order):
            log["message"] = "Error: Invalid setup player index or order for 2P placing."
            return log
        acting_player = gs.player_setup_order[gs.current_setup_player_index]

        if acting_player.name != acting_player_name:
            log["message"] = f"Invalid acting player '{acting_player_name}' or not their turn. Expected: {acting_player.name}"
            return log

        neutral_player = next((p for p in gs.players if p.is_neutral and p.name == "Neutral"), None) # Standard 2P neutral
        if not neutral_player:
            log["message"] = "Standard Neutral player not found."; return log

        player_armies_to_place_this_turn = sum(count for _, count in own_army_placements)
        armies_left_in_player_pool = acting_player.initial_armies_pool - acting_player.armies_placed_in_setup

        required_player_placements = min(2, armies_left_in_player_pool)
        if player_armies_to_place_this_turn != required_player_placements:
            log["message"] = f"Player must place {required_player_placements} of their own armies, attempted {player_armies_to_place_this_turn}."
            return log
        if armies_left_in_player_pool <= 0 and required_player_placements == 0: # Player has no armies left.
             pass # Allow to proceed to place neutral if possible
        elif armies_left_in_player_pool <= 0:
             log["message"] = f"Player {acting_player_name} has no more armies in their pool."; return log

        for terr_name, count in own_army_placements:
            territory = gs.territories.get(terr_name)
            if not territory or territory.owner != acting_player:
                log["message"] = f"Invalid territory '{terr_name}' for {acting_player_name}'s placement."; return log
            if count <=0 and required_player_placements > 0 : # only error if they were supposed to place
                log["message"] = f"Army count for {terr_name} must be positive."; return log
            if count > 0: # Only process if count > 0
                territory.army_count += count
                acting_player.armies_placed_in_setup += count
                log["message"] += f"Placed {count} on {terr_name}. "
        log["player_armies_placed_total"] = acting_player.armies_placed_in_setup

        if neutral_army_placement:
            neut_terr_name, neut_count = neutral_army_placement
            if neut_count != 1:
                log["message"] += "Must place exactly 1 neutral army."; return log
            neutral_territory = gs.territories.get(neut_terr_name)
            if not neutral_territory or neutral_territory.owner != neutral_player:
                log["message"] += f"Invalid territory '{neut_terr_name}' for neutral placement."; return log
            if neutral_player.armies_placed_in_setup < neutral_player.initial_armies_pool:
                neutral_territory.army_count += 1
                neutral_player.armies_placed_in_setup += 1
                log["message"] += f"Placed 1 neutral army on {neut_terr_name}. Neutral armies placed: {neutral_player.armies_placed_in_setup}."
            else:
                log["message"] += "Neutral player has no armies left in pool. Skipped neutral placement."
        log["neutral_armies_placed_total"] = neutral_player.armies_placed_in_setup
        log["success"] = True

        all_human_players_done = all(p.armies_placed_in_setup >= p.initial_armies_pool for p in gs.player_setup_order)

        if all_human_players_done:
            log["message"] += " All human player initial armies placed."
            gs.deck.append(Card(None, "Wildcard")); gs.deck.append(Card(None, "Wildcard"))
            random.shuffle(gs.deck)
            log["message"] += " Wild cards added to deck."
            gs.current_game_phase = "REINFORCE"
            try:
                gs.current_player_index = gs.players.index(gs.first_player_of_game)
                if gs.players[gs.current_player_index].is_neutral:
                    first_human = next(p for p in gs.players if not p.is_neutral)
                    gs.current_player_index = gs.players.index(first_human)
            except (ValueError, StopIteration): gs.current_player_index = 0

            first_active_player = gs.get_current_player()
            if first_active_player and not first_active_player.is_neutral:
                reinforcements, _ = self.calculate_reinforcements(first_active_player)
                first_active_player.armies_to_deploy = reinforcements
                log["message"] += f" Game setup complete. First turn: {first_active_player.name}. Reinforcements: {reinforcements}."
            else:
                 log["message"] += " Game setup complete. Error finding first non-neutral player."
        else:
            gs.current_setup_player_index = (gs.current_setup_player_index + 1) % len(gs.player_setup_order)
            log["message"] += f" Next player to place armies: {gs.player_setup_order[gs.current_setup_player_index].name}."
        return log

    def set_player_setup_order(self, ordered_player_names: list[str], first_placer_for_game_turn_name: str):
        gs = self.game_state
        # This method is primarily for standard 3-6 player games or potentially Truthful World Map order.
        # Standard 2-player setup order is handled within its specific methods.
        if gs.is_two_player_game and not gs.is_truthful_world_map_mode:
             print(f"Info: set_player_setup_order called in 2P standard mode, but order is usually fixed. Setting first game player only.")
             human_players = [p for p in gs.players if not p.is_neutral and p.name != "Neutral"]
             first_player_obj = next((p for p in human_players if p.name == first_placer_for_game_turn_name), human_players[0] if human_players else None)
             if not first_player_obj: print("Error: Could not set first player in 2P mode."); return False
             gs.first_player_of_game = first_player_obj
             print(f"2P Game: First game turn set to {gs.first_player_of_game.name}.")
             return True

        if gs.current_game_phase != "SETUP_DETERMINE_ORDER":
            print(f"Error: Cannot set player setup order in phase {gs.current_game_phase}"); return False

        name_to_player_map = {p.name: p for p in gs.players if not p.is_neutral}
        gs.player_setup_order = [name_to_player_map[name] for name in ordered_player_names if name in name_to_player_map]

        non_neutral_players_count = len([p for p in gs.players if not p.is_neutral])
        if len(gs.player_setup_order) != non_neutral_players_count:
            print(f"Error: Mismatch in ordered_player_names and game's non-neutral players."); return False

        first_player_obj = name_to_player_map.get(first_placer_for_game_turn_name)
        if not first_player_obj:
            print(f"Error: First placer '{first_placer_for_game_turn_name}' not found among non-neutral players."); return False
        gs.first_player_of_game = first_player_obj
        gs.current_setup_player_index = 0

        if gs.is_truthful_world_map_mode: # Directly to REINFORCE after order determination
            gs.current_game_phase = "REINFORCE"
            try:
                gs.current_player_index = gs.players.index(gs.first_player_of_game)
                if gs.players[gs.current_player_index].is_neutral : # Should not be
                     first_actual = next(p for p in gs.player_setup_order)
                     gs.current_player_index = gs.players.index(first_actual)
            except (ValueError, StopIteration):
                gs.current_player_index = 0
                while gs.players[gs.current_player_index].is_neutral:
                    gs.current_player_index = (gs.current_player_index + 1) % len(gs.players)

            player_for_first_turn = gs.get_current_player()
            if player_for_first_turn:
                reinforcements, _ = self.calculate_reinforcements(player_for_first_turn)
                player_for_first_turn.armies_to_deploy = reinforcements
            print(f"Truthful World Map: Player order set. First game turn: {gs.first_player_of_game.name}. Phase: {gs.current_game_phase}")

        else: # Standard game
            gs.current_game_phase = "SETUP_CLAIM_TERRITORIES"
            print(f"Player setup order set: {[p.name for p in gs.player_setup_order]}. First game turn: {gs.first_player_of_game.name}. Phase: {gs.current_game_phase}")
        return True

    def player_claims_territory(self, player_name: str, territory_name: str) -> dict: # Standard setup
        gs = self.game_state
        log = {"event": "claim_territory", "player": player_name, "territory": territory_name, "success": False, "message": ""}
        if gs.is_truthful_world_map_mode: # This method is not for truthful world map
            log["message"] = "Territory claiming is not part of Truthful World Map setup."; return log
        if gs.current_game_phase != "SETUP_CLAIM_TERRITORIES":
            log["message"] = f"Cannot claim territory in phase: {gs.current_game_phase}"; return log
        current_setup_player = gs.player_setup_order[gs.current_setup_player_index]
        if current_setup_player.name != player_name:
            log["message"] = f"Not {player_name}'s turn. Current: {current_setup_player.name}"; return log
        if territory_name not in gs.unclaimed_territory_names:
            log["message"] = f"Territory '{territory_name}' unavailable/claimed."; return log
        territory = gs.territories.get(territory_name)
        if not territory:
            log["message"] = f"Territory '{territory_name}' not found (internal error)."; return log
        if current_setup_player.armies_placed_in_setup >= current_setup_player.initial_armies_pool:
            log["message"] = f"{player_name} no armies in pool for claiming."; return log
        territory.owner = current_setup_player
        territory.army_count = 1
        current_setup_player.territories.append(territory)
        current_setup_player.armies_placed_in_setup += 1
        gs.unclaimed_territory_names.remove(territory_name)
        log["success"] = True
        log["message"] = f"{player_name} claimed {territory_name}. Armies placed: {current_setup_player.armies_placed_in_setup}/{current_setup_player.initial_armies_pool}."
        gs.current_setup_player_index = (gs.current_setup_player_index + 1) % len(gs.player_setup_order)
        if not gs.unclaimed_territory_names:
            gs.current_game_phase = "SETUP_PLACE_ARMIES"
            gs.current_setup_player_index = 0
            log["message"] += " All territories claimed. Moving to SETUP_PLACE_ARMIES."
            print("All territories claimed. Phase: SETUP_PLACE_ARMIES")
        return log

    def _all_initial_armies_placed(self) -> bool: # For standard setup
        # For truthful world map, this check is different or not applicable in the same way
        if self.game_state.is_truthful_world_map_mode:
            return True # Armies are pre-placed, player pools are not used for initial setup placement.

        # For standard and 2P standard, check if all non-neutral players have placed their pool.
        # Neutral player in 2P standard also has a pool that gets depleted during player turns.
        relevant_players = self.game_state.players # Includes Neutral in 2P standard.
        return all(p.armies_placed_in_setup >= p.initial_armies_pool for p in relevant_players)


    def player_places_initial_army(self, player_name: str, territory_name: str) -> dict: # Standard setup
        gs = self.game_state
        log = {"event": "place_initial_army", "player": player_name, "territory": territory_name, "success": False, "message": ""}
        if gs.is_truthful_world_map_mode:
             log["message"] = "Army placement is not part of Truthful World Map setup."; return log
        if gs.current_game_phase != "SETUP_PLACE_ARMIES":
            log["message"] = f"Cannot place army in phase: {gs.current_game_phase}"; return log
        current_setup_player = gs.player_setup_order[gs.current_setup_player_index]
        if current_setup_player.name != player_name:
            log["message"] = f"Not {player_name}'s turn. Current: {current_setup_player.name}"; return log
        territory = gs.territories.get(territory_name)
        if not territory or territory.owner != current_setup_player:
            log["message"] = f"Territory '{territory_name}' not found or not owned by {player_name}."; return log
        if current_setup_player.armies_placed_in_setup >= current_setup_player.initial_armies_pool:
            log["message"] = f"{player_name} has no more armies in pool."
            log["success"] = True # Not an error for this player, but turn advances.
        else:
            territory.army_count += 1
            current_setup_player.armies_placed_in_setup += 1
            log["success"] = True
            log["message"] = f"{player_name} placed 1 on {territory_name} ({territory.army_count}). Total placed: {current_setup_player.armies_placed_in_setup}/{current_setup_player.initial_armies_pool}."

        if log["success"]:
            gs.current_setup_player_index = (gs.current_setup_player_index + 1) % len(gs.player_setup_order)

        # Check all players, including Neutral for 2P standard
        all_players_for_check = gs.players if gs.is_two_player_game else [p for p in gs.players if not p.is_neutral]
        all_done_placing = all(p.armies_placed_in_setup >= p.initial_armies_pool for p in all_players_for_check)

        if all_done_placing:
            gs.current_game_phase = "REINFORCE"
            try:
                gs.current_player_index = gs.players.index(gs.first_player_of_game)
                if gs.players[gs.current_player_index].is_neutral: # Ensure first player is not Neutral
                    first_actual_player = next(p for p in gs.player_setup_order) # from original setup order
                    gs.current_player_index = gs.players.index(first_actual_player)
            except (ValueError, StopIteration):
                gs.current_player_index = 0
                while gs.players[gs.current_player_index].is_neutral:
                     gs.current_player_index = (gs.current_player_index + 1) % len(gs.players)

            first_player_for_turn = gs.get_current_player()
            if first_player_for_turn and not first_player_for_turn.is_neutral:
                reinforcements, _ = self.calculate_reinforcements(first_player_for_turn)
                first_player_for_turn.armies_to_deploy = reinforcements
                log["message"] += f" All initial armies placed. Game starts! First turn: {first_player_for_turn.name}. Reinforcements: {reinforcements}."
                print(f"All initial armies placed. Phase: REINFORCE. First player: {first_player_for_turn.name}")
            else:
                log["message"] += " All initial armies placed. Error finding first non-neutral player for turn."
                print("All initial armies placed. Phase: REINFORCE. Error finding first player.")
        return log

    def calculate_reinforcements(self, player: Player) -> tuple[int, list[str]]:
        if not player or player.is_neutral: return 0, []
        num_territories = len(player.territories)
        reinforcements = max(3, num_territories // 3)
        controlled_continents = []
        for continent in self.game_state.continents.values():
            if not continent.territories: continue
            is_owner_of_all = all(territory.owner == player for territory in continent.territories)
            if is_owner_of_all:
                reinforcements += continent.bonus_armies
                controlled_continents.append(continent.name)
        return reinforcements, controlled_continents

    def _get_card_trade_bonus(self) -> int:
        if self.card_trade_bonus_index < len(self.card_trade_bonuses):
            bonus = self.card_trade_bonuses[self.card_trade_bonus_index]
        else:
            bonus = self.card_trade_bonuses[-1] + (self.card_trade_bonus_index - len(self.card_trade_bonuses) + 1) * 5
        return bonus

    def _increment_card_trade_bonus(self):
        self.card_trade_bonus_index += 1

    def find_valid_card_sets(self, player: Player) -> list[list[Card]]:
        valid_sets = []
        hand = player.hand
        if len(hand) < 3: return []
        from collections import Counter
        import itertools
        for combo_indices in itertools.combinations(range(len(hand)), 3):
            combo = [hand[i] for i in combo_indices]
            symbols_in_combo = [c.symbol for c in combo]
            num_wildcards = symbols_in_combo.count("Wildcard")
            non_wild_symbols = [s for s in symbols_in_combo if s != "Wildcard"]
            is_valid_set_current_combo = False
            if num_wildcards == 3: is_valid_set_current_combo = True
            elif num_wildcards == 2 and len(non_wild_symbols) == 1: is_valid_set_current_combo = True
            elif num_wildcards == 1 and len(non_wild_symbols) == 2 and non_wild_symbols[0] == non_wild_symbols[1]: is_valid_set_current_combo = True
            elif num_wildcards == 0 and len(set(non_wild_symbols)) == 1: is_valid_set_current_combo = True
            if not is_valid_set_current_combo:
                present_symbols = set(non_wild_symbols)
                if num_wildcards == 0 and len(present_symbols) == 3: is_valid_set_current_combo = True
                elif num_wildcards == 1 and len(present_symbols) == 2: is_valid_set_current_combo = True
                elif num_wildcards == 2 and len(present_symbols) == 1: is_valid_set_current_combo = True
            if is_valid_set_current_combo:
                valid_sets.append(list(combo))
        return valid_sets

    def perform_card_trade(self, player: Player, cards_to_trade_indices: list[int]) -> dict:
        log = {"event": "card_trade", "player": player.name, "success": False, "message": "", "armies_gained": 0}
        if len(cards_to_trade_indices) != 3 or len(set(cards_to_trade_indices)) != 3:
            log["message"] = "Exactly 3 unique card indices must be selected."; return log
        cards_to_trade = []
        for i in sorted(cards_to_trade_indices, reverse=True):
            if not (0 <= i < len(player.hand)):
                log["message"] = "Invalid card index."; return log
            cards_to_trade.append(player.hand[i])
        cards_to_trade.reverse()
        symbols_in_trade = [c.symbol for c in cards_to_trade]
        num_wildcards = symbols_in_trade.count("Wildcard")
        non_wild_symbols = [s for s in symbols_in_trade if s != "Wildcard"]
        is_valid_set = False
        if num_wildcards == 3 or (num_wildcards == 2 and len(non_wild_symbols) == 1) or \
           (num_wildcards == 1 and len(non_wild_symbols) == 2 and non_wild_symbols[0] == non_wild_symbols[1]) or \
           (num_wildcards == 0 and len(set(non_wild_symbols)) == 1):
            is_valid_set = True
        if not is_valid_set:
            present_symbols = set(non_wild_symbols)
            if (num_wildcards == 0 and len(present_symbols) == 3) or \
               (num_wildcards == 1 and len(present_symbols) == 2) or \
               (num_wildcards == 2 and len(present_symbols) == 1):
                is_valid_set = True
        if not is_valid_set:
            log["message"] = "Selected cards do not form a valid set."; log["selected_cards_symbols"] = symbols_in_trade; return log
        for i in sorted(cards_to_trade_indices, reverse=True):
            self.game_state.deck.append(player.hand.pop(i))
        random.shuffle(self.game_state.deck)
        bonus_armies = self._get_card_trade_bonus()
        player.armies_to_deploy += bonus_armies
        self._increment_card_trade_bonus()
        for card in cards_to_trade:
            if card.territory_name:
                territory = self.game_state.territories.get(card.territory_name)
                if territory and territory.owner == player:
                    territory.army_count += 2
                    log["territory_bonus"] = f"Player {player.name} received +2 armies on {card.territory_name}."; break
        log["success"] = True; log["message"] = f"{player.name} traded cards for {bonus_armies} armies."
        log["armies_gained"] = bonus_armies; log["traded_card_symbols"] = symbols_in_trade
        return log

    def perform_attack(self, attacker_territory_name: str, defender_territory_name: str, num_attacking_armies: int, explicit_defender_dice_count: int | None = None) -> dict:
        attacker_territory = self.game_state.territories.get(attacker_territory_name)
        defender_territory = self.game_state.territories.get(defender_territory_name)
        log = {"event": "attack", "attacker": None, "defender": None, "results": [], "conquered": False, "card_drawn": None, "betrayal": False}
        gs = self.game_state
        if not attacker_territory or not defender_territory:
            log["error"] = "Invalid territory specified."; return log
        attacker_player = attacker_territory.owner
        defender_player = defender_territory.owner
        log["attacker"] = attacker_player.name if attacker_player else "N/A"
        log["defender"] = defender_player.name if defender_player else "N/A"
        if defender_player and defender_player.is_neutral: log["defender_is_neutral"] = True
        if attacker_player and defender_player and not defender_player.is_neutral:
            diplomatic_key = frozenset({attacker_player.name, defender_player.name})
            if gs.diplomacy.get(diplomatic_key) == "ALLIANCE":
                gs.diplomacy[diplomatic_key] = "WAR"; log["betrayal"] = True
                log["old_diplomatic_status"] = "ALLIANCE"; log["new_diplomatic_status"] = "WAR"
        if attacker_player == defender_player:
            log["error"] = "Cannot attack your own territory."; return log
        if defender_territory not in attacker_territory.adjacent_territories:
            log["error"] = f"{defender_territory.name} not adjacent to {attacker_territory.name}."; return log
        if attacker_territory.army_count <= 1:
            log["error"] = f"{attacker_territory.name} must have >1 army."; return log
        if not (1 <= num_attacking_armies < attacker_territory.army_count):
            log["error"] = f"Invalid num_attacking_armies: {num_attacking_armies}."; return log

        actual_defender_dice_count = 0
        if explicit_defender_dice_count is not None:
            if explicit_defender_dice_count == 1 and defender_territory.army_count >= 1: actual_defender_dice_count = 1
            elif explicit_defender_dice_count == 2 and defender_territory.army_count >= 2: actual_defender_dice_count = 2
            elif explicit_defender_dice_count > 0 and defender_territory.army_count > 0 : actual_defender_dice_count = 1
            log["defender_dice_choice_is_explicit"] = True
        else:
            if defender_territory.army_count >= 2: actual_defender_dice_count = 2
            elif defender_territory.army_count == 1: actual_defender_dice_count = 1
        log["actual_defender_dice_count"] = actual_defender_dice_count
        max_attacker_dice = min(3, num_attacking_armies)
        attacker_dice_rolls = sorted([random.randint(1, 6) for _ in range(max_attacker_dice)], reverse=True)
        defender_dice_rolls = sorted([random.randint(1, 6) for _ in range(actual_defender_dice_count)], reverse=True)
        log["attacker_rolls"] = attacker_dice_rolls; log["defender_rolls"] = defender_dice_rolls
        attacker_losses, defender_losses = 0, 0
        for i in range(min(len(attacker_dice_rolls), len(defender_dice_rolls))):
            roll_log = {"attacker_roll": attacker_dice_rolls[i], "defender_roll": defender_dice_rolls[i]}
            if attacker_dice_rolls[i] > defender_dice_rolls[i]:
                defender_losses += 1; roll_log["outcome"] = f"Defender loses 1 army ({defender_territory.name})"
            else:
                attacker_losses += 1; roll_log["outcome"] = f"Attacker loses 1 army ({attacker_territory.name})"
            log["results"].append(roll_log)
        attacker_territory.army_count -= attacker_losses
        defender_territory.army_count -= defender_losses
        log["summary"] = f"Attacker lost {attacker_losses}. Defender lost {defender_losses}."
        if defender_territory.army_count <= 0:
            log["conquered"] = True; log["summary"] += f" {attacker_player.name} conquered {defender_territory.name}!"
            old_owner, new_owner = defender_territory.owner, attacker_player
            if old_owner: old_owner.territories.remove(defender_territory)
            defender_territory.owner = new_owner; new_owner.territories.append(defender_territory)
            gs.requires_post_attack_fortify = True
            min_move = max_attacker_dice
            available_to_move = num_attacking_armies - attacker_losses
            max_move = min(available_to_move, attacker_territory.army_count - 1)
            min_move = min(min_move, max_move)
            min_move = max(1, min_move) if max_move > 0 else 0
            if min_move > max_move: min_move = max_move
            defender_territory.army_count = 0 # To be filled by PAF
            gs.conquest_context = {
                "from_territory_name": attacker_territory_name, "to_territory_name": defender_territory_name,
                "min_movable": min_move, "max_movable": max_move,
                "armies_in_attacking_territory_after_battle": attacker_territory.army_count
            }
            log["post_attack_fortify_required"] = True; log["conquest_context"] = gs.conquest_context
            if not new_owner.has_conquered_territory_this_turn and gs.deck:
                card = gs.deck.pop(0); new_owner.hand.append(card)
                new_owner.has_conquered_territory_this_turn = True; log["card_drawn"] = card.to_dict()
            elif new_owner.has_conquered_territory_this_turn: log["card_skipped_reason"] = "Already received card."
            elif not gs.deck: log["card_skipped_reason"] = "Deck empty."
            eliminated_player_details = None
            if old_owner and not old_owner.is_neutral and not old_owner.territories:
                log["eliminated_player_name"] = old_owner.name; new_owner.hand.extend(old_owner.hand); old_owner.hand.clear()
                log["cards_transferred_count"] = len(new_owner.hand)
                eliminated_player_details = {"player_name": old_owner.name, "cards_transferred_to": new_owner.name, "num_cards": len(new_owner.hand)}
                if len(new_owner.hand) >= 6:
                    gs.elimination_card_trade_player_name = new_owner.name; log["mandatory_card_trade_initiated"] = new_owner.name
            event_data = {"turn": gs.current_turn_number, "type": "ATTACK_RESULT", "attacker": attacker_player.name, "defender": defender_player.name if defender_player else "N/A",
                          "attacking_territory": attacker_territory_name, "defending_territory": defender_territory_name,
                          "attacker_losses": attacker_losses, "defender_losses": defender_losses, "conquered": log["conquered"], "betrayal": log["betrayal"]}
            if log["conquered"]: event_data["card_drawn"] = log.get("card_drawn") is not None
            if eliminated_player_details:
                event_data["elimination"] = eliminated_player_details
                gs.event_history.append({"turn": gs.current_turn_number, "type": "ELIMINATION", "eliminator": new_owner.name, "eliminated_player": old_owner.name, "context": "CONQUEST"})
            gs.event_history.append(event_data)
        else:
            gs.event_history.append({"turn": gs.current_turn_number, "type": "ATTACK_SKIRMISH", "attacker": attacker_player.name, "defender": defender_player.name if defender_player else "N/A",
                                     "attacking_territory": attacker_territory_name, "defending_territory": defender_territory_name,
                                     "attacker_losses": attacker_losses, "defender_losses": defender_losses, "betrayal": log["betrayal"]})
        return log

    def perform_fortify(self, from_territory_name: str, to_territory_name: str, num_armies: int) -> dict:
        log = {"event": "fortify", "success": False, "message": ""}
        from_territory = self.game_state.territories.get(from_territory_name)
        to_territory = self.game_state.territories.get(to_territory_name)
        if not from_territory or not to_territory: log["message"] = "Invalid territory."; return log
        if from_territory.owner != to_territory.owner: log["message"] = "Territories must have same owner."; return log
        if not from_territory.owner: log["message"] = "Territories unowned."; return log
        if not self._are_territories_connected(from_territory, to_territory, from_territory.owner):
            log["message"] = f"{to_territory.name} not connected to {from_territory.name}."; return log
        if num_armies <= 0: log["message"] = "Armies to move must be positive."; return log
        if from_territory.army_count - num_armies < 1:
            log["message"] = f"Cannot move {num_armies} from {from_territory.name}. Must leave 1 army."; return log
        from_territory.army_count -= num_armies; to_territory.army_count += num_armies
        current_player = from_territory.owner
        if current_player: current_player.has_fortified_this_turn = True
        log["success"] = True; log["message"] = f"Moved {num_armies} from {from_territory.name} to {to_territory.name}."
        log["from_territory"] = from_territory.name; log["to_territory"] = to_territory.name; log["num_armies"] = num_armies
        return log

    def perform_post_attack_fortify(self, player: Player, num_armies_to_move: int) -> dict:
        log = {"event": "post_attack_fortify", "player": player.name, "success": False, "message": ""}
        if not self.game_state.requires_post_attack_fortify or not self.game_state.conquest_context:
            log["message"] = "No PAF required or context missing."; return log
        context = self.game_state.conquest_context
        from_t_name, to_t_name = context["from_territory_name"], context["to_territory_name"]
        min_movable, max_movable = context["min_movable"], context["max_movable"]
        from_t = self.game_state.territories.get(from_t_name)
        to_t = self.game_state.territories.get(to_t_name)
        if not from_t or not to_t:
            log["message"] = f"Invalid territories in context: {from_t_name}, {to_t_name}."; self.game_state.requires_post_attack_fortify = False; self.game_state.conquest_context = None; return log
        if to_t.owner != player:
            log["message"] = f"{player.name} does not own conquered territory {to_t_name}."; self.game_state.requires_post_attack_fortify = False; self.game_state.conquest_context = None; return log
        if from_t.owner != player:
            log["message"] = f"{player.name} does not own attacking territory {from_t_name}."; self.game_state.requires_post_attack_fortify = False; self.game_state.conquest_context = None; return log
        if not (min_movable <= num_armies_to_move <= max_movable):
            log["message"] = f"Invalid num_armies: {num_armies_to_move}. Must be {min_movable}-{max_movable}."; return log
        if from_t.army_count - num_armies_to_move < 1:
            log["message"] = f"Cannot move {num_armies_to_move} from {from_t.name}, would leave <1."; return log
        from_t.army_count -= num_armies_to_move
        to_t.army_count += num_armies_to_move
        log["success"] = True; log["message"] = f"{player.name} moved {num_armies_to_move} from {from_t.name} to {to_t.name}."
        log["from_territory_final_armies"] = from_t.army_count; log["to_territory_final_armies"] = to_t.army_count
        self.game_state.requires_post_attack_fortify = False; self.game_state.conquest_context = None
        return log

    def _are_territories_connected(self, start_territory: Territory, end_territory: Territory, player: Player) -> bool:
        if start_territory.owner != player or end_territory.owner != player: return False
        # BFS for connectivity through owned territories for general fortification
        # For strict Risk rule (only adjacent), this check is simpler.
        # The current problem description implies standard Risk rules, so adjacent is enough.
        return end_territory in start_territory.adjacent_territories

    def is_game_over(self) -> Player | None:
        gs = self.game_state
        if not gs.territories: return None

        if gs.is_two_player_game: # Applies to standard 2P and World Map 2P
            initial_setup_phases = ["SETUP_START", "SETUP_DETERMINE_ORDER", "SETUP_2P_DEAL_CARDS", "SETUP_WORLD_MAP_CLAIM"]
            if gs.current_game_phase in initial_setup_phases: return None

            human_players_with_territories = [p for p in gs.players if not p.is_neutral and p.territories]
            if len(human_players_with_territories) == 1:
                return human_players_with_territories[0]
            elif not human_players_with_territories and not gs.current_game_phase.startswith("SETUP_"):
                 print(f"Warning: In 2-player game (phase: {gs.current_game_phase}), no human players found with territories.")
                 return None # Potentially a draw or error if past setup
            return None

        else: # Standard 3-6 player game (or World Map with >2 players)
            active_non_neutral_players = [p for p in gs.players if not p.is_neutral and p.territories]
            if len(active_non_neutral_players) == 1 and not gs.current_game_phase.startswith("SETUP_"):
                return active_non_neutral_players[0] # Elimination win

            # Check for total map conquest (only if not in setup)
            if not gs.current_game_phase.startswith("SETUP_"):
                first_owner = None
                all_territories_owned_by_one_player = True
                for territory in gs.territories.values():
                    if territory.owner is None or territory.owner.is_neutral:
                        all_territories_owned_by_one_player = False; break
                    if first_owner is None: first_owner = territory.owner
                    elif territory.owner != first_owner:
                        all_territories_owned_by_one_player = False; break
                if all_territories_owned_by_one_player and first_owner:
                    return first_owner
            return None

    def next_turn(self):
        gs = self.game_state
        if not gs.players: return

        current_player_obj = gs.get_current_player()
        if current_player_obj:
            current_player_obj.has_fortified_this_turn = False
            current_player_obj.has_conquered_territory_this_turn = False

        # Filter out any truly neutral players (like "WorldPowers" if it wasn't removed, or "Neutral" in 2P)
        # and players with no territories (eliminated).
        eligible_players_for_turn = [p for p in gs.players if not p.is_neutral and p.territories]

        if not eligible_players_for_turn:
            print("Warning: No eligible players with territories for next_turn.")
            # Game over should be caught by is_game_over. This is a fallback state.
            return

        # Find current player's index within the eligible_players list to correctly find next eligible player
        current_eligible_player_idx = -1
        if current_player_obj and current_player_obj in eligible_players_for_turn:
            try:
                current_eligible_player_idx = eligible_players_for_turn.index(current_player_obj)
            except ValueError: # Should not happen if current_player_obj is in eligible_players_for_turn
                pass

        next_eligible_player_idx = (current_eligible_player_idx + 1) % len(eligible_players_for_turn)
        next_player_obj = eligible_players_for_turn[next_eligible_player_idx]

        try:
            gs.current_player_index = gs.players.index(next_player_obj) # Set index in main players list
        except ValueError:
            print(f"CRITICAL ERROR: Next eligible player {next_player_obj.name} not found in main players list.")
            # Fallback: try to find first eligible player in main list
            for i, p in enumerate(gs.players):
                if p in eligible_players_for_turn: gs.current_player_index = i; break
            else: # Should be impossible if eligible_players_for_turn is not empty
                print("CRITICAL ERROR: Cannot find any eligible player in main list.")
                return


        # Determine if it's a new round for turn counting
        # A new round starts when the turn passes to the first player in the original setup order
        # (or the first player in the current list of eligible players if setup order info is lost/complex)
        if gs.first_player_of_game:
            if next_player_obj == gs.first_player_of_game and current_player_obj != gs.first_player_of_game:
                 gs.current_turn_number += 1
        elif eligible_players_for_turn : # Fallback if first_player_of_game is not set
            if next_player_obj == eligible_players_for_turn[0] and current_player_obj != eligible_players_for_turn[0]:
                 gs.current_turn_number += 1

        gs.current_game_phase = "REINFORCE"
        new_current_player_obj = gs.get_current_player()

        if new_current_player_obj and not new_current_player_obj.is_neutral:
            reinforcements, controlled_continents = self.calculate_reinforcements(new_current_player_obj)
            new_current_player_obj.armies_to_deploy = reinforcements
            if controlled_continents:
                gs.event_history.append({
                    "turn": gs.current_turn_number, "type": "CONTINENT_CONTROL_UPDATE",
                    "player": new_current_player_obj.name, "controlled_continents": controlled_continents,
                    "reinforcement_bonus_from_continents": sum(gs.continents[c].bonus_armies for c in controlled_continents if c in gs.continents)
                })
        else:
            print(f"CRITICAL ERROR in next_turn: New current player is {new_current_player_obj.name if new_current_player_obj else 'None'} (Neutral or None).")


    def get_valid_actions(self, player: Player) -> list:
        actions = []
        gs = self.game_state
        phase = gs.current_game_phase

        if gs.elimination_card_trade_player_name == player.name:
            if len(player.hand) <= 4:
                gs.elimination_card_trade_player_name = None
            else:
                valid_card_sets = self.find_valid_card_sets(player)
                if not valid_card_sets:
                    if len(player.hand) >=5 : gs.elimination_card_trade_player_name = None
                else:
                    for card_set in valid_card_sets:
                        card_indices_in_hand = [player.hand.index(c) for c in card_set if c in player.hand]
                        if len(card_indices_in_hand) == 3:
                            actions.append({"type": "TRADE_CARDS", "card_indices": sorted(card_indices_in_hand), "must_trade": True, "reason": "Post-elimination trade"})
                    if actions: return actions
                    else: gs.elimination_card_trade_player_name = None

        if gs.requires_post_attack_fortify and gs.conquest_context:
            context = gs.conquest_context
            if context["max_movable"] >= 0 :
                actions.append({
                    "type": "POST_ATTACK_FORTIFY", "from_territory": context["from_territory_name"],
                    "to_territory": context["to_territory_name"], "min_armies": context["min_movable"],
                    "max_armies": context["max_movable"],
                })
            return actions

        # Handle setup phases
        if gs.is_truthful_world_map_mode:
            if phase == "SETUP_DETERMINE_ORDER": # Only this setup phase for truthful world map
                return [{"type": "AWAIT_SETUP_ORDER"}]
            # No other setup actions for player in truthful_world_map as territories are auto-assigned

        elif gs.is_two_player_game: # Standard 2-player setup
            if phase == "SETUP_2P_DEAL_CARDS":
                return [{"type": "AUTO_SETUP_2P_DEAL_CARDS"}]
            if phase == "SETUP_2P_PLACE_REMAINING":
                if player.is_neutral: return []
                armies_left_pool = player.initial_armies_pool - player.armies_placed_in_setup
                can_place_own = armies_left_pool > 0
                neutral_p = next((p for p in gs.players if p.is_neutral and p.name == "Neutral"), None)
                can_place_neutral = neutral_p and neutral_p.armies_placed_in_setup < neutral_p.initial_armies_pool
                if not can_place_own and not can_place_neutral: return [{"type": "SETUP_2P_DONE_PLACING"}]
                actions.append({
                    "type": "SETUP_2P_PLACE_ARMIES_TURN", "player_can_place_own": can_place_own,
                    "player_armies_to_place_this_turn": min(2, armies_left_pool) if can_place_own else 0,
                    "player_owned_territories": [t.name for t in player.territories],
                    "neutral_can_place": can_place_neutral,
                    "neutral_owned_territories": [t.name for t in neutral_p.territories] if neutral_p else []
                })
                return actions

        else: # Standard 3-6 player setup
            if phase == "SETUP_DETERMINE_ORDER": return [{"type": "AWAIT_SETUP_ORDER"}]
            if phase == "SETUP_CLAIM_TERRITORIES":
                if player.is_neutral: return []
                if gs.unclaimed_territory_names:
                    for terr_name in gs.unclaimed_territory_names:
                         actions.append({"type": "SETUP_CLAIM", "territory": terr_name})
                return actions
            if phase == "SETUP_PLACE_ARMIES":
                if player.is_neutral: return []
                if player.armies_placed_in_setup < player.initial_armies_pool:
                    for territory in player.territories:
                        actions.append({"type": "SETUP_PLACE_ARMY", "territory": territory.name})
                else: actions.append({"type": "SETUP_STANDARD_DONE_PLACING"})
                return actions

        if player.is_neutral: return [] # Regular game phases, neutral players don't act

        if phase == "REINFORCE":
            must_trade = len(player.hand) >= 5
            valid_card_sets = self.find_valid_card_sets(player)
            trade_actions = []
            if valid_card_sets:
                for card_set in valid_card_sets:
                    card_indices_in_hand = [player.hand.index(c) for c in card_set if c in player.hand]
                    if len(card_indices_in_hand) == 3:
                        trade_actions.append({"type": "TRADE_CARDS", "card_indices": sorted(card_indices_in_hand), "must_trade": must_trade})
            if must_trade:
                if trade_actions: actions.extend(trade_actions)
            else:
                if player.armies_to_deploy > 0:
                    for territory in player.territories:
                        actions.append({"type": "DEPLOY", "territory": territory.name, "max_armies": player.armies_to_deploy})
                if trade_actions: actions.extend(trade_actions)
                if player.armies_to_deploy == 0 or any(a["type"] == "DEPLOY" for a in actions):
                    actions.append({"type": "END_REINFORCE_PHASE"})
            if not actions and not (must_trade and trade_actions):
                 actions.append({"type": "END_REINFORCE_PHASE"})
        elif phase == "ATTACK":
            for territory in player.territories:
                if territory.army_count > 1:
                    for neighbor in territory.adjacent_territories:
                        if neighbor.owner != player and not (neighbor.owner and neighbor.owner.is_neutral and gs.is_truthful_world_map_mode and neighbor.owner.name == "WorldPowers"): # Cannot attack WorldPowers
                            diplomatic_key = frozenset({player.name, neighbor.owner.name}) if neighbor.owner else None
                            current_status = gs.diplomacy.get(diplomatic_key) if diplomatic_key else "NEUTRAL" # Treat unowned/unknown as neutral for attack
                            action_type_to_add = "ATTACK"
                            if current_status == "ALLIANCE": action_type_to_add = "BETRAY_ALLY"

                            actions.append({
                                "type": action_type_to_add, "from": territory.name, "to": neighbor.name,
                                "max_armies_for_attack": territory.army_count - 1
                            })
            actions.append({"type": "END_ATTACK_PHASE"})
        elif phase == "FORTIFY":
            if not player.has_fortified_this_turn:
                owned_territories = player.territories
                for i in range(len(owned_territories)):
                    for j in range(len(owned_territories)):
                        if i == j: continue
                        from_t, to_t = owned_territories[i], owned_territories[j]
                        if from_t.army_count > 1 and self._are_territories_connected(from_t, to_t, player):
                            actions.append({"type": "FORTIFY", "from": from_t.name, "to": to_t.name, "max_armies_to_move": from_t.army_count - 1})
            actions.append({"type": "END_TURN"})

        if phase in ["REINFORCE", "ATTACK", "FORTIFY"]:
            actions.append({"type": "GLOBAL_CHAT", "message": "..."})
            for p_target in gs.players:
                if p_target != player and not p_target.is_neutral: # Cannot chat with Neutral or WorldPowers
                    actions.append({"type": "PRIVATE_CHAT", "target_player_name": p_target.name, "initial_message": "..."})
                    diplomatic_key = frozenset({player.name, p_target.name})
                    current_status = gs.diplomacy.get(diplomatic_key)
                    if not current_status or current_status == "NEUTRAL":
                        actions.append({"type": "PROPOSE_ALLIANCE", "target_player_name": p_target.name})
                    proposal_details = gs.active_diplomatic_proposals.get(diplomatic_key)
                    if proposal_details and proposal_details.get('target') == player.name and proposal_details.get('type') == 'ALLIANCE':
                        actions.append({"type": "ACCEPT_ALLIANCE", "proposing_player_name": proposal_details.get('proposer')})
                        actions.append({"type": "REJECT_ALLIANCE", "proposing_player_name": proposal_details.get('proposer')})
                    if current_status == "ALLIANCE":
                        actions.append({"type": "BREAK_ALLIANCE", "target_player_name": p_target.name})
        return actions

if __name__ == '__main__':
    pass
