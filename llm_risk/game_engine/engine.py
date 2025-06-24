from .data_structures import GameState, Player, Territory, Continent, Card
import json
import random

class GameEngine:
    def __init__(self, map_file_path: str = "map_config.json"):
        self.game_state = GameState()
        self.map_file_path = map_file_path
        self.card_trade_bonus_index = 0 # For escalating card bonuses
        self.card_trade_bonuses = [4, 6, 8, 10, 12, 15] # Standard escalation

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
        # Card trade-in reinforcements are handled by `perform_card_trade` now.

        # player.armies_to_deploy += reinforcements # This is done by the caller
        return reinforcements

    def _get_card_trade_bonus(self) -> int:
        """Gets the current bonus for trading cards, and escalates for next time."""
        if self.card_trade_bonus_index < len(self.card_trade_bonuses):
            bonus = self.card_trade_bonuses[self.card_trade_bonus_index]
        else:
            # After the defined list, bonus increases by 5 each time
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
        if current_player:
            # Reset turn-specific flags for the player whose turn is ending
            current_player.has_fortified_this_turn = False
            current_player.has_conquered_territory_this_turn = False
            # armies_to_deploy is reset when new reinforcements are calculated for the next player

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

        # Check for mandatory post-attack fortification first, as this takes precedence.
        if self.game_state.requires_post_attack_fortify and self.game_state.conquest_context:
            context = self.game_state.conquest_context
            # Only POST_ATTACK_FORTIFY actions are allowed at this point.
            # The AI needs to decide how many armies to move, from min_movable to max_movable.
            # The action should allow specifying any number in this range.
            if context["max_movable"] > 0 : # Only if there are armies that *can* be moved
                actions.append({
                    "type": "POST_ATTACK_FORTIFY",
                    "from_territory": context["from_territory_name"], # Attacking territory
                    "to_territory": context["to_territory_name"],     # Newly conquered territory
                    "min_armies": context["min_movable"],
                    "max_armies": context["max_movable"],
                    # The AI will select "num_armies" in its chosen action.
                })
            else: # No armies can be moved (e.g. attacking territory has only 1 after battle, or all attackers died but somehow still won)
                  # This case implies something might be off, or it's an edge case where 0 armies are moved.
                  # The perform_post_attack_fortify will still be called (with 0 armies if AI chooses that).
                  # Or we can force it to "complete" by providing a "skip" or "confirm_zero_move" type action.
                  # For now, if max_movable is 0, min_movable will also be 0.
                  # The AI should choose to move 0 armies.
                actions.append({
                    "type": "POST_ATTACK_FORTIFY",
                    "from_territory": context["from_territory_name"],
                    "to_territory": context["to_territory_name"],
                    "min_armies": 0,
                    "max_armies": 0,
                })

            # If no valid POST_ATTACK_FORTIFY actions could be generated (e.g. max_movable is 0 and we didn't add the above)
            # OR if the only option is to move 0, the game should proceed.
            # The current logic will provide an action for 0 move. The orchestrator will call perform_post_attack_fortify.
            # That method will then clear requires_post_attack_fortify.
            return actions # Return immediately, no other actions are valid.

        if phase == "REINFORCE":
            # Valid deploy actions: (territory_name, num_armies)
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
