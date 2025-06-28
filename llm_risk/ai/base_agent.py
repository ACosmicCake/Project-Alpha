from abc import ABC, abstractmethod
import json # Added for potential use if action is a string that needs parsing, though Gemini part handles it.

class BaseAIAgent(ABC):
    DEBUG_VALIDATION = False # Class-level toggle for validation debug messages

    def __init__(self, player_name: str, player_color: str):
        self.player_name = player_name
        self.player_color = player_color

    @abstractmethod
    def get_thought_and_action(self, game_state_json: str, valid_actions: list, game_rules: str, system_prompt_addition: str = "") -> dict:
        pass

    @abstractmethod
    def engage_in_private_chat(self, history: list[dict], game_state_json: str, game_rules: str, recipient_name: str, system_prompt_addition: str = "") -> str:
        pass

    def _construct_system_prompt(self, base_prompt: str, game_rules: str, additional_text: str = "") -> str:
        prompt = f"{base_prompt}\n\nYou are {self.player_name}, playing as the {self.player_color} pieces.\n\n{game_rules}"
        if additional_text:
            prompt += f"\n\n{additional_text}"
        return prompt

    def _construct_user_prompt_for_action(self, game_state_json: str, valid_actions: list, turn_chat_log: list = None) -> str:
        prompt = f"Current Game State:\n{game_state_json}\n\n"
        if turn_chat_log:
            prompt += "Recent Global Chat Messages (last 10):\n"
            for chat_msg in turn_chat_log[-10:]:
                 prompt += f"- {chat_msg['sender']}: {chat_msg['message']}\n"
            prompt += "\n"

        # Attempt to parse game_state_json to extract event_history for summary
        try:
            game_state_data = json.loads(game_state_json)
            event_history = game_state_data.get("event_history") # This key might not be in the default to_json
            # We need to ensure game_state_json passed here includes event_history.
            # For now, assume it might be missing or needs to be fetched/passed differently.
            # If GameState.to_json() doesn't include it, this will be None.
            # The Orchestrator will need to pass a version of game_state_json that has event_history.
            # For now, we'll proceed assuming it *could* be there.

            if event_history and isinstance(event_history, list):
                # Create a summarized intelligence briefing (last 3-5 turns or N events)
                # This is a simplified summary. More sophisticated summarization could be done by an LLM.
                briefing = "\n--- Intelligence Briefing (Recent Events) ---\n"
                recent_events_to_show = 5 # Show last 5 events

                # Filter for key event types and summarize
                relevant_event_count = 0
                for event in reversed(event_history):
                    if relevant_event_count >= recent_events_to_show:
                        break

                    event_type = event.get("type")
                    turn = event.get("turn", "N/A")
                    summary_line = None

                    if event_type == "ATTACK_RESULT" or event_type == "ATTACK_SKIRMISH":
                        summary_line = (f"Turn {turn}: {event.get('attacker')} attacked {event.get('defender')} "
                                        f"at {event.get('defending_territory')} (from {event.get('attacking_territory')}). "
                                        f"Losses: A-{event.get('attacker_losses',0)} D-{event.get('defender_losses',0)}. ")
                        if event.get('conquered'):
                            summary_line += f"Conquered. "
                        if event.get('betrayal'):
                            summary_line += f"BETRAYAL! "
                    elif event_type == "DIPLOMACY_CHANGE":
                        summary_line = (f"Turn {turn}: Diplomacy - {event.get('subtype')} involving {event.get('players') or [event.get('breaker'), event.get('target')]}. "
                                        f"New status: {event.get('new_status', event.get('status', 'N/A'))}.")
                    elif event_type == "CARD_TRADE":
                        summary_line = f"Turn {turn}: {event.get('player')} traded cards for {event.get('armies_gained')} armies."
                    elif event_type == "CONTINENT_CONTROL_UPDATE":
                         summary_line = f"Turn {turn}: {event.get('player')} controls continents: {', '.join(event.get('controlled_continents',[]))} (bonus: {event.get('reinforcement_bonus_from_continents',0)})."
                    elif event_type == "ELIMINATION": # Assuming this event type will be added
                        summary_line = f"Turn {turn}: {event.get('eliminator')} eliminated {event.get('eliminated_player')}."

                    if summary_line:
                        briefing += f"- {summary_line}\n"
                        relevant_event_count += 1

                if relevant_event_count == 0:
                    briefing += "- No significant recent actions by players.\n"
                briefing += "--- End of Briefing ---\n\n"
                prompt += briefing
            else:
                # This case will be hit if game_state_json does not contain 'event_history'
                # or if it's not a list.
                prompt += "\n--- Intelligence Briefing ---\n- Event history not available in this summary.\n--- End of Briefing ---\n\n"
        except (json.JSONDecodeError, AttributeError):
            prompt += "\n--- Intelligence Briefing ---\n- Could not parse event history from game state.\n--- End of Briefing ---\n\n"


        prompt += "Valid Actions (choose one, or a chat action):\n"
        for i, action in enumerate(valid_actions):
            prompt += f"{i+1}. {action}\n"
        prompt += "\nIf you want to chat globally, use action: {'type': 'GLOBAL_CHAT', 'message': 'your message here'}\n"
        prompt += "If you want to initiate a private chat, use action: {'type': 'PRIVATE_CHAT', 'target_player_name': 'PlayerName', 'initial_message': 'your message here'}\n"
        prompt += "\nCRITICAL INSTRUCTIONS FOR ACTION SELECTION:\n"
        prompt += "1. Your primary task is to select ONE action object EXACTLY AS IT APPEARS in the 'Valid Actions' list below or construct a chat action.\n"
        prompt += "2. For actions like 'DEPLOY', 'ATTACK', or 'FORTIFY', the 'Valid Actions' list provides templates. You MUST choose one of these templates.\n"
        prompt += "   - The `territory`, `from`, `to` fields in these templates are FIXED. DO NOT change them or choose territories not listed in these templates for the respective action type.\n"
        prompt += "   - Your role is to decide numerical values like `num_armies`, `num_attacking_armies`, or `num_armies_to_move`, respecting any 'max_armies' or similar constraints provided in the chosen template.\n"
        prompt += "3. The 'action' key in your JSON response MUST be a JSON STRING representation of your chosen action object (copied from 'Valid Actions' and with numerical values filled in where appropriate).\n"
        prompt += "   Example: If a valid DEPLOY action is `{'type': 'DEPLOY', 'territory': 'Alaska', 'max_armies': 5}` and you decide to deploy 3 armies, your action string would be `'{\"type\": \"DEPLOY\", \"territory\": \"Alaska\", \"num_armies\": 3}'`. Notice 'Alaska' was copied directly.\n"
        prompt += "\nRespond with a JSON object containing 'thought' and 'action' keys. "
        return prompt

    def _validate_chosen_action(self, action_dict: dict, valid_actions: list) -> bool:
        if BaseAIAgent.DEBUG_VALIDATION:
            print(f"[VALIDATE_ACTION_DEBUG] _validate_chosen_action: Start validation for action_dict: {action_dict}")
            print(f"[VALIDATE_ACTION_DEBUG] _validate_chosen_action: valid_actions provided: {valid_actions}")

        if not action_dict or not isinstance(action_dict, dict) or "type" not in action_dict:
            if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL: Action dictionary is malformed or missing 'type'. Action: {action_dict}")
            return False

        llm_action_type = action_dict.get("type")
        if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] llm_action_type: {llm_action_type}")

        matching_type_actions = [va for va in valid_actions if va.get("type") == llm_action_type]
        if not matching_type_actions:
            if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL: Action type '{llm_action_type}' not found in any template in valid_actions. Action: {action_dict}")
            return False
        if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] Found {len(matching_type_actions)} matching template(s) for type '{llm_action_type}'.")

        # Prioritized handler for SETUP_2P_PLACE_ARMIES_TURN
        if llm_action_type == "SETUP_2P_PLACE_ARMIES_TURN":
            if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] Entered specific validator for SETUP_2P_PLACE_ARMIES_TURN.")

            own_placements = action_dict.get("own_army_placements")
            if not isinstance(own_placements, list):
                if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL (SETUP_2P): 'own_army_placements' is NOT A LIST. Actual type: {type(own_placements)}. Action: {action_dict}")
                return False
            if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] (SETUP_2P): 'own_army_placements' is a list. Length: {len(own_placements)}.")

            for i, item in enumerate(own_placements):
                if not (isinstance(item, list) and len(item) == 2):
                    if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL (SETUP_2P): Item #{i} in 'own_army_placements' ({item}) is NOT A LIST OF LENGTH 2. Action: {action_dict}")
                    return False
                if not isinstance(item[0], str):
                    if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL (SETUP_2P): Territory name in 'own_army_placements' item #{i} ('{item[0]}') is NOT A STRING. Type: {type(item[0])}. Action: {action_dict}")
                    return False
                if not isinstance(item[1], int):
                    if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL (SETUP_2P): Army count in 'own_army_placements' item #{i} ('{item[1]}') is NOT AN INTEGER. Type: {type(item[1])}. Action: {action_dict}")
                    return False
                if item[1] <= 0:
                    if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL (SETUP_2P): Army count in 'own_army_placements' item #{i} ({item[1]}) must be POSITIVE. Action: {action_dict}")
                    return False
            if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] (SETUP_2P): 'own_army_placements' items structure is OK.")

            neutral_placement = action_dict.get("neutral_army_placement")
            if neutral_placement is not None:
                if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] (SETUP_2P): Validating 'neutral_army_placement': {neutral_placement}")
                if not (isinstance(neutral_placement, list) and len(neutral_placement) == 2):
                    if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL (SETUP_2P): 'neutral_army_placement' ({neutral_placement}) is NOT A LIST OF LENGTH 2 (if not null). Action: {action_dict}")
                    return False
                if not isinstance(neutral_placement[0], str):
                    if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL (SETUP_2P): Territory name in 'neutral_army_placement' ('{neutral_placement[0]}') is NOT A STRING. Type: {type(neutral_placement[0])}. Action: {action_dict}")
                    return False
                if not isinstance(neutral_placement[1], int):
                    if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL (SETUP_2P): Army count in 'neutral_army_placement' ('{neutral_placement[1]}') is NOT AN INTEGER. Type: {type(neutral_placement[1])}. Action: {action_dict}")
                    return False
                if neutral_placement[1] != 1:
                    if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL (SETUP_2P): 'neutral_army_placement' ({neutral_placement}) armies must be EXACTLY 1 if specified. Got: {neutral_placement[1]}. Action: {action_dict}")
                    return False
            # else:
                # if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] (SETUP_2P): 'neutral_army_placement' is null, which is acceptable.")

            if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] SUCCESS (SETUP_2P_PLACE_ARMIES_TURN): Action structure is VALID. Action: {action_dict}")
            return True

        # --- Generic Validation for other action types ---
        if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] Action type '{llm_action_type}' is not SETUP_2P_PLACE_ARMIES_TURN. Proceeding to generic validation.")

        # Try to find an exact match in valid_actions (useful for simple actions like END_TURN)
        # This is the primary validation for actions that are not SETUP_2P_PLACE_ARMIES_TURN and are expected to match a template.
        if action_dict in matching_type_actions: # matching_type_actions contains templates of the same type
            if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] SUCCESS (Generic - Exact Match): Action {action_dict} found in valid_actions_templates.")
            return True

        # Fallback for complex actions where LLM might add numeric fields (e.g. num_armies)
        # to a template that didn't explicitly list them but implied them.
        for template in matching_type_actions:
            if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] (Generic) Comparing action {action_dict} with template {template}")

            # Check if action_dict contains all keys from template and non-numeric/non-bool values match
            params_match = True
            for key, template_value in template.items():
                if key not in action_dict:
                    if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] (Generic) Key '{key}' from template missing in action.")
                    params_match = False
                    break
                # For non-fillable fields (not numbers/booleans that AI would set, but strings like territory names)
                if not isinstance(template_value, (int, float, bool)):
                    if action_dict[key] != template_value:
                        if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] (Generic) Value mismatch for key '{key}'. Template: '{template_value}', Action: '{action_dict[key]}'.")
                        params_match = False
                        break
            if not params_match:
                if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] (Generic) Template non-fillable fields mismatch. Trying next template.")
                continue

            # Check if action_dict has extra keys not in template (ignoring numeric/bool keys AI might add)
            # This is to prevent AI from adding arbitrary non-expected string keys, for example.
            extra_keys_invalid = False
            for key, action_value in action_dict.items():
                if key not in template: # If a key is in action_dict but not in template
                    # AI is allowed to add numeric/boolean fields (like 'num_armies' or a flag)
                    if not isinstance(action_value, (int, float, bool)):
                        if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] (Generic) Action has extra non-numeric/bool key '{key}' not in template '{template}'.")
                        extra_keys_invalid = True
                        break
            if extra_keys_invalid:
                if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] (Generic) Action has unexpected extra non-numeric/bool keys. Trying next template.")
                continue

            # If template fields match and no unexpected extra fields, check type-specific required numeric fields
            type_specific_checks_pass = True
            if llm_action_type == "ATTACK":
                if not (isinstance(action_dict.get("num_armies"), int) and action_dict.get("num_armies", 0) > 0):
                    if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL (Generic - ATTACK): 'num_armies' missing, not int, or not >0. Value: {action_dict.get('num_armies')}")
                    type_specific_checks_pass = False
            elif llm_action_type == "DEPLOY":
                if not (isinstance(action_dict.get("num_armies"), int) and action_dict.get("num_armies", 0) > 0):
                    if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL (Generic - DEPLOY): 'num_armies' missing, not int, or not >0. Value: {action_dict.get('num_armies')}")
                    type_specific_checks_pass = False
            elif llm_action_type == "FORTIFY":
                if not ("num_armies" in action_dict and isinstance(action_dict.get("num_armies"), int) and action_dict.get("num_armies", -1) >= 0): # Allow 0
                    if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL (Generic - FORTIFY): 'num_armies' missing, not int, or <0. Value: {action_dict.get('num_armies')}")
                    type_specific_checks_pass = False
            elif llm_action_type == "POST_ATTACK_FORTIFY":
                 if not ("num_armies" in action_dict and isinstance(action_dict.get("num_armies"), int) and action_dict.get("num_armies", -1) >= 0):
                    if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL (Generic - POST_ATTACK_FORTIFY): 'num_armies' missing, not int or <0. Value: {action_dict.get('num_armies')}")
                    type_specific_checks_pass = False

            if type_specific_checks_pass:
                if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] SUCCESS (Generic - Complex Match): Action {action_dict} conforms to template {template} with type checks.")
                return True
            else:
                if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] (Generic) Action {action_dict} matched template {template} on fixed fields, but failed type-specific checks (e.g. num_armies).")
                # This means this template was the right one, but the AI filled something incorrectly.
                # We should return False here as it matched the template type but failed specific content.
                return False


        if BaseAIAgent.DEBUG_VALIDATION: print(f"[VALIDATE_ACTION_DEBUG] FAIL (Fallback): Action {action_dict} (type: {llm_action_type}) did not conform to any valid action templates in {matching_type_actions} or failed its type-specific checks.")
        return False

    def _construct_user_prompt_for_private_chat(self, history: list[dict], game_state_json: str, recipient_name: str) -> str:
        prompt = f"You are in a private conversation with {recipient_name}.\n"
        prompt += f"Current Game State:\n{game_state_json}\n\nConversation History:\n"
        for msg in history:
            prompt += f"- {msg['sender']}: {msg['message']}\n"
        prompt += "\nYour response:"
        return prompt

GAME_RULES_SNIPPET = """\
You are a master strategist and a ruthless player in the game of Risk. Your goal is to achieve world domination by eliminating all other players (or your direct opponent in a 2-player game) . Your only goal is to win, and you will do whatever it takes to achieve victory. You are not bound by loyalty or fairness unless it serves your ultimate goal of winning.
You MUST respond with a valid JSON object containing exactly two keys: 'thought' and 'action'.
The 'thought' key should contain your detailed reasoning, analysis of the board, evaluation of opponents, and your strategic plan for this turn and potentially future turns.
The 'action' key must contain a single, valid action object chosen precisely from the 'Valid Actions' list provided. Do not invent actions or parameters not shown in the valid action template you choose.

Core Game Objective: Conquer the world by occupying every territory (standard game) or by eliminating your human opponent (2-player game).

Initial Game Setup (Standard 3-6 Player Game):
1.  Determine Order: Player order for setup is determined (e.g., by dice rolls managed by the game master). The player who places the first army also takes the first game turn.
2.  Claim Territories (Phase: SETUP_CLAIM_TERRITORIES):
    -   In turn order, each player chooses an UNCLAIMED territory and places 1 army on it.
    -   Action: {"type": "SETUP_CLAIM", "territory": "TerritoryName"}
    -   This continues until all 42 territories are claimed.
3.  Place Remaining Armies (Phase: SETUP_PLACE_ARMIES):
    -   In the same turn order, players take turns placing ONE additional army onto any territory THEY OWN.
    -   Action: {"type": "SETUP_PLACE_ARMY", "territory": "YourOwnedTerritoryName"}
    -   This continues until all players have placed their initial pool of armies (e.g., 35 for 3 players, 30 for 4, 25 for 5, 20 for 6).

Initial Game Setup (2-Player Game - You are P1 or P2, vs one other Human and a Neutral player):
1.  Initial Territories (Phase: SETUP_2P_DEAL_CARDS - Automatic): 14 territories are automatically assigned to you, 14 to your human opponent, and 14 to a "Neutral" player. Each of these territories starts with 1 army.
2.  Place Remaining Armies (Phase: SETUP_2P_PLACE_REMAINING):
    -   You and your human opponent take turns. In your turn, you will place some of your remaining armies AND some of the Neutral player's armies.
    -   You start with 40 armies. 14 are placed automatically. You have 26 left to place. The Neutral player also has 26 armies to be placed by you and your opponent.
    -   Action: {"type": "SETUP_2P_PLACE_ARMIES_TURN", "player_can_place_own": true/false, "player_armies_to_place_this_turn": X, "player_owned_territories": ["T1", "T2"...], "neutral_can_place": true/false, "neutral_owned_territories": ["N1", "N2"...]}
        -   From this, you will construct a specific action detailing your chosen placements. For example:
            `{"type": "SETUP_2P_PLACE_ARMIES_TURN", "own_army_placements": [("YourTerritoryA", 1), ("YourTerritoryB", 1)], "neutral_army_placement": ("NeutralTerritoryX", 1)}`
            (The sum of your own placements must be `player_armies_to_place_this_turn`, usually 2, unless you have fewer left).
    -   This continues until you and your opponent have placed all your initial 40 armies. Wild cards are then added to the deck.

Main Game Phases (after setup):
1. Reinforce Phase (Phase: REINFORCE):
   - Goal: Strengthen your positions and prepare for attacks.
   - Army Calculation:
     - Territories: (Number of territories you own / 3), rounded down. Minimum of 3 armies.
     - Continents: Bonus armies for controlling entire continents:
       - North America: 5, South America: 2, Europe: 5, Africa: 3, Asia: 7, Australia: 2.
   - Card Trading:
     - If you have 5 or more cards at the START of your turn, you MUST trade a valid set if possible.
     - If you have fewer than 5 cards, you MAY trade a valid set.
     - Valid Sets: (a) 3 cards of the same design (Infantry, Cavalry, or Artillery), (b) 1 of each of the 3 designs, (c) Any 2 cards plus a "Wild" card.
     - Action: {"type": "TRADE_CARDS", "card_indices": [idx1, idx2, idx3], "must_trade": true/false, "reason": "..."} (Indices are 0-based from your hand).
     - Card Trade Bonus Armies (Global Count): 1st set=4, 2nd=6, 3rd=8, 4th=10, 5th=12, 6th=15. Each subsequent set is worth 5 more armies than the previous (e.g., 7th=20).
     - Occupied Territory Bonus: If any of the 3 cards you trade shows a territory you occupy, you get +2 extra armies placed directly onto THAT territory. Max one such +2 bonus per trade.
     - Elimination Card Trade: If you eliminate another player and receive their cards, and your hand size becomes 6 or more, you MUST immediately perform `TRADE_CARDS` actions (these will be marked with `must_trade: true`) until your hand is 4 or fewer cards. These trades happen before any other pending actions like post-attack fortification.
   - Deployment:
     - Place all armies received from territories, continents, and card trades.
     - Action: {"type": "DEPLOY", "territory": "YourOwnedTerritoryName", "max_armies": X} (You will specify 'num_armies' up to 'max_armies' or your remaining deployable armies for THIS territory).
   - End Phase:
     - Action: {"type": "END_REINFORCE_PHASE"} (Use when all armies are deployed and no mandatory card trades are left).

2. Attack Phase (Phase: ATTACK):
   - Goal: Conquer enemy territories.
   - Rules:
     - Attack only adjacent territories. Must have at least 2 armies in your attacking territory.
     - Attacker rolls 1, 2, or 3 dice (must have more armies in territory than dice rolled).
     - Defender rolls 1 or 2 dice (needs >=2 armies to roll 2 dice). Defender wins ties.
     - In a 2-Player game, if you attack a NEUTRAL territory, your HUMAN OPPONENT decides how many dice (1 or 2) the Neutral territory will defend with.
   - Action: {"type": "ATTACK", "from": "YourTerritory", "to": "EnemyTerritory", "max_armies_for_attack": X}
     - You MUST include 'num_armies' in your chosen action: e.g., `{"type": "ATTACK", "from": "Alpha", "to": "Beta", "num_armies": Y}` where Y is 1 to X.
   - Capturing Territory:
     - If you defeat all armies, you capture it.
     - Post-Attack Fortification (Mandatory): You MUST move armies into the newly conquered territory.
       - Action Template: {"type": "POST_ATTACK_FORTIFY", "from_territory": "AttackingTerritory", "to_territory": "ConqueredTerritory", "min_armies": M, "max_armies": N}
       - Your chosen action: `{"type": "POST_ATTACK_FORTIFY", ..., "num_armies": Z}` (Z is between M and N, inclusive). This happens before other attacks.
     - Earn Card: If you capture at least one territory on your turn, you get ONE Risk card at the end of your attack phase.
   - End Phase: Action: {"type": "END_ATTACK_PHASE"}.

3. Fortify Phase (Phase: FORTIFY):
   - Goal: Consolidate forces.
   - Rules: Make ONE move of armies from one of your territories to ONE ADJACENT territory you own. Must leave at least 1 army behind.
   - Action: {"type": "FORTIFY", "from": "YourTerritoryA", "to": "YourTerritoryB", "max_armies_to_move": X}
     - You MUST include 'num_armies': e.g., `{"type": "FORTIFY", ..., "num_armies": Y}` (Y is 1 to X).
   - End Turn: Action: {"type": "END_TURN"} (Ends your turn, whether you fortified or not). This is the only way to end your turn in this phase.

Winning the Game:
- Standard Game: Eliminate all opponents by capturing all 42 territories.
- 2-Player Game: Eliminate your human opponent by capturing all of their territories. Neutral territories do not need to be captured to win.

Diplomacy & Chat:
- Global Chat: {"type": "GLOBAL_CHAT", "message": "Your message to all players."}
- Private Chat Initiation: {"type": "PRIVATE_CHAT", "target_player_name": "PlayerNameToChatWith", "initial_message": "Your opening message."}
  (Chat actions generally do not consume your main phase action, but check context.)

CRITICAL - Action Selection:
- Your 'action' in the JSON response MUST be a JSON STRING representation of your chosen action object.
- Choose ONE action object EXACTLY AS IT APPEARS in the 'Valid Actions' list, or construct a chat action.
- For actions like 'DEPLOY', 'ATTACK', 'FORTIFY', 'SETUP_PLACE_ARMY', 'POST_ATTACK_FORTIFY':
    - The 'Valid Actions' list provides templates with fixed 'territory', 'from', 'to' names. DO NOT change these.
    - Your role is to decide numerical values like 'num_armies', respecting 'max_armies' or 'min_armies' constraints.
    - Example: If valid is `{'type': 'DEPLOY', 'territory': 'Alaska', 'max_armies': 5}` and you deploy 3, your action string is `'{\"type\": \"DEPLOY\", \"territory\": \"Alaska\", \"num_armies\": 3}'`.
- Pay close attention to all parameters in the chosen valid action template.
- Do not add extra keys to the action dictionary not present in the template you selected (unless it's a numerical value like 'num_armies' that you are filling in).
"""

# This GAME_RULES_SNIPPET will be passed to the agents.
# It needs to be refined as the action schema becomes more concrete.
# For example, how 'num_armies' for an attack action is interpreted (total dice vs. total moving).
# The valid_actions list provided to the agent will be the ultimate source of truth for what specific parameters are needed for each action.

# This base class includes:
# - Constructor with `player_name` and `player_color`.
# - Abstract methods `get_thought_and_action` and `engage_in_private_chat`.
# - Helper methods `_construct_system_prompt`, `_construct_user_prompt_for_action`, and `_construct_user_prompt_for_private_chat` to standardize prompt creation.
# - A `GAME_RULES_SNIPPET` constant that provides a basic overview of the game and expected JSON format. This will be refined.

# Next, I will create the concrete implementations for each LLM. I'll start with a dummy/placeholder implementation for each,
# which can be filled in later with actual API calls. This helps to quickly establish the structure.

# I'll create `gemini_agent.py`, `openai_agent.py`, `claude_agent.py`, and `deepseek_agent.py` in the `llm_risk/ai/` directory.
# Due to the limitations of not being able to install new packages or use API keys in this environment, these will be structural placeholders.
