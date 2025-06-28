from abc import ABC, abstractmethod

class BaseAIAgent(ABC):
    def __init__(self, player_name: str, player_color: str):
        """
        Initialize the base AI agent.
        player_name: The name of the player this agent represents.
        player_color: The color assigned to this player.
        """
        self.player_name = player_name
        self.player_color = player_color
        # API-specific setup will be handled in concrete implementations

    @abstractmethod
    def get_thought_and_action(self, game_state_json: str, valid_actions: list, game_rules: str, system_prompt_addition: str = "") -> dict:
        """
        The core method. Takes the game state, valid actions, game rules, and an optional addition to the system prompt,
        and returns a structured action.

        Args:
            game_state_json: A JSON string representing the current game state.
            valid_actions: A list of valid action dictionaries the AI can choose from.
            game_rules: A string describing the rules of the game and expected JSON output format.
            system_prompt_addition: Optional string to append to the core system prompt for this specific call.

        Returns:
            A dictionary like:
            {
                "thought": "My reasoning process...",
                "action": {"type": "ATTACK", "from": "Ukraine", "to": "Southern Europe", "num_armies": 3}
            }
            The action must be one of the actions provided in `valid_actions` or a correctly formatted chat action.
        """
        pass

    @abstractmethod
    def engage_in_private_chat(self, history: list[dict], game_state_json: str, game_rules: str, recipient_name: str, system_prompt_addition: str = "") -> str:
        """
        Handles a 1-on-1 conversation turn.

        Args:
            history: A list of message dictionaries representing the conversation so far.
                     Each dict: {"sender": "PlayerName", "message": "text"}
            game_state_json: A JSON string representing the current game state.
            game_rules: A string describing the rules of the game and context.
            recipient_name: The name of the player this agent is chatting with.
            system_prompt_addition: Optional string to append to the core system prompt for this specific call.


        Returns:
            A string containing the agent's response message.
        """
        pass

    def _construct_system_prompt(self, base_prompt: str, game_rules: str, additional_text: str = "") -> str:
        """
        Helper method to construct the full system prompt.
        """
        prompt = f"{base_prompt}\n\nYou are {self.player_name}, playing as the {self.player_color} pieces.\n\n{game_rules}"
        if additional_text:
            prompt += f"\n\n{additional_text}"
        return prompt

    def _construct_user_prompt_for_action(self, game_state_json: str, valid_actions: list, turn_chat_log: list = None) -> str:
        """
        Helper method to construct the user prompt for get_thought_and_action.
        """
        prompt = f"Current Game State:\n{game_state_json}\n\n"
        if turn_chat_log:
            prompt += "Recent Global Chat Messages (last 10):\n"
            for chat_msg in turn_chat_log[-10:]:
                 prompt += f"- {chat_msg['sender']}: {chat_msg['message']}\n"
            prompt += "\n"

        prompt += "Valid Actions (choose one, or a chat action):\n"
        # Prettify valid actions for the prompt
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
        """
        Validates the LLM's chosen action_dict against the list of valid_actions templates.
        - Checks if the action type is valid.
        - For complex actions (DEPLOY, ATTACK, FORTIFY), verifies that non-numeric parameters
          (like territory, from, to) match an existing template in valid_actions.
        - Numeric parameters chosen by the LLM (e.g., num_armies) are not validated here for range,
          as that's the engine's responsibility, but their presence might be implied by the template.
        """
        if not action_dict or not isinstance(action_dict, dict) or "type" not in action_dict:
            print(f"Validation Error: Action dictionary is malformed or missing 'type'. Action: {action_dict}")
            return False

        llm_action_type = action_dict.get("type")
        matching_type_actions = [va for va in valid_actions if va.get("type") == llm_action_type]

        if not matching_type_actions:
            print(f"Validation Error: Action type '{llm_action_type}' not found in valid_actions. Action: {action_dict}")
            return False

        # --- Start of Aggressively Refactored Validation Logic ---

        # Handle SETUP_2P_PLACE_ARMIES_TURN with highest priority
        if llm_action_type == "SETUP_2P_PLACE_ARMIES_TURN":
            # print(f"[DEBUG _validate_action] Prioritized Check: SETUP_2P_PLACE_ARMIES_TURN. Action: {action_dict}")

            own_placements = action_dict.get("own_army_placements")
            if not isinstance(own_placements, list):
                print(f"Validation Error (SETUP_2P_PLACE_ARMIES_TURN): 'own_army_placements' must be a list. Got: {type(own_placements)}. Action: {action_dict}")
                return False
            if not own_placements: # Must have at least one placement if player_armies_to_place_this_turn > 0 (engine validates sum)
                 print(f"Validation Error (SETUP_2P_PLACE_ARMIES_TURN): 'own_army_placements' list cannot be empty if armies are to be placed. Action: {action_dict}")
                 # Allowing empty list if player_armies_to_place_this_turn is 0 (handled by engine)
                 # This validation primarily checks structure if placements are provided.
                 # If player_armies_to_place_this_turn is 0, this field might be an empty list from AI.

            for i, item in enumerate(own_placements):
                if not (isinstance(item, list) and len(item) == 2 and isinstance(item[0], str) and isinstance(item[1], int) and item[1] > 0): # Armies must be positive
                    print(f"Validation Error (SETUP_2P_PLACE_ARMIES_TURN): Invalid item #{i} in 'own_army_placements': {item}. Must be [String, positive Integer]. Action: {action_dict}")
                    return False

            neutral_placement = action_dict.get("neutral_army_placement")
            if neutral_placement is not None:
                if not (isinstance(neutral_placement, list) and len(neutral_placement) == 2 and isinstance(neutral_placement[0], str) and isinstance(neutral_placement[1], int) and neutral_placement[1] == 1): # Neutral must be 1
                    print(f"Validation Error (SETUP_2P_PLACE_ARMIES_TURN): Invalid 'neutral_army_placement': {neutral_placement}. Must be null or [String, 1]. Action: {action_dict}")
                    return False

            # print(f"[DEBUG _validate_action] SETUP_2P_PLACE_ARMIES_TURN action passed specific structural validation.")
            return True # This action type is now fully validated (structurally).

        # --- Generic Validation for other action types ---
        # Check if the action type is simple (e.g., END_TURN)
        is_simple_action_type = all(len(va_template) == 1 and "type" in va_template for va_template in matching_type_actions)

        if is_simple_action_type:
            if action_dict in matching_type_actions:
                return True
            elif len(action_dict) == 1 and "type" in action_dict:
                 return True
            else:
                print(f"Validation Error (Simple Action): Action {action_dict} for simple type '{llm_action_type}' does not match templates {matching_type_actions} and is not just a type field.")
                return False

        # For other complex actions (not SETUP_2P_PLACE_ARMIES_TURN, and not simple)
        for template in matching_type_actions:
            params_match = True
            for key, template_value in template.items():
                if not isinstance(template_value, (int, float, bool)):
                    if key not in action_dict or action_dict[key] != template_value:
                        params_match = False
                        break
            if not params_match: continue

            for key, action_value in action_dict.items():
                if key not in template:
                    if not isinstance(action_value, (int, float, bool)):
                        params_match = False
                        break
            if not params_match: continue

            action_valid_for_type = True
            # Type-specific required field and basic value checks
            if llm_action_type == "ATTACK":
                if not isinstance(action_dict.get("num_armies"), int) or action_dict.get("num_armies", 0) <= 0:
                    print(f"Validation Error (ATTACK): Missing or invalid 'num_armies' (must be >0). Action: {action_dict}")
                    action_valid_for_type = False
            elif llm_action_type == "DEPLOY":
                if not isinstance(action_dict.get("num_armies"), int) or action_dict.get("num_armies", 0) <= 0:
                    print(f"Validation Error (DEPLOY): Missing or invalid 'num_armies' (must be >0). Action: {action_dict}")
                    action_valid_for_type = False
            elif llm_action_type == "FORTIFY": # num_armies must be present, engine checks if >0
                if "num_armies" not in action_dict or not isinstance(action_dict.get("num_armies"), int):
                    print(f"Validation Error (FORTIFY): Missing or non-integer 'num_armies'. Action: {action_dict}")
                    action_valid_for_type = False
            elif llm_action_type == "POST_ATTACK_FORTIFY": # num_armies must be present, engine checks range
                if "num_armies" not in action_dict or not isinstance(action_dict.get("num_armies"), int):
                    print(f"Validation Error (POST_ATTACK_FORTIFY): Missing or non-integer 'num_armies'. Action: {action_dict}")
                    action_valid_for_type = False

            if action_valid_for_type:
                return True

        print(f"Validation Error (Fallback): Action {action_dict} (type: {llm_action_type}) did not conform to any valid action templates in {matching_type_actions} or failed its type-specific field validation.")
        return False


    def _construct_user_prompt_for_private_chat(self, history: list[dict], game_state_json: str, recipient_name: str) -> str:
        """
        Helper method to construct the user prompt for engage_in_private_chat.
        """
        prompt = f"You are in a private conversation with {recipient_name}.\n"
        prompt += f"Current Game State:\n{game_state_json}\n\nConversation History:\n"
        for msg in history:
            prompt += f"- {msg['sender']}: {msg['message']}\n"
        prompt += "\nYour response:"
        return prompt

GAME_RULES_SNIPPET = """\
You are a master strategist playing the game of Risk. Your goal is to achieve world domination by eliminating all other players (or your direct opponent in a 2-player game).
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
