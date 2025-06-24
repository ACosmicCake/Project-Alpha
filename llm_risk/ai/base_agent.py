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
        prompt += "\nRespond with a JSON object containing 'thought' and 'action' keys. Your action must be one of the valid actions or a chat action."
        return prompt

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
You are a master strategist playing the game of Risk. Your goal is to achieve world domination by eliminating all other players.
You MUST respond with a valid JSON object containing exactly two keys: 'thought' and 'action'.
The 'thought' key should contain your detailed reasoning, analysis of the board, evaluation of opponents, and your strategic plan for this turn and potentially future turns.
The 'action' key must contain a single, valid action object chosen precisely from the 'Valid Actions' list provided. Do not invent actions or parameters.

Game Phases & Key Actions:
1. Reinforce Phase:
   - Goal: Strengthen your positions and prepare for attacks.
   - Card Trading:
     - If you have 5 or more cards, you MUST trade a valid set if possible.
     - A valid set is: (a) 3 cards of the same symbol (e.g., 3 Infantry), (b) 1 of each of the 3 symbols (Infantry, Cavalry, Artillery), (c) Wildcards can substitute for any symbol.
     - Action: {"type": "TRADE_CARDS", "card_indices": [idx1, idx2, idx3], "must_trade": true/false} (Indices are from your hand).
     - Trading cards gives bonus armies. The bonus increases with each set traded globally. Matching a card's territory to one you own gives +2 armies on that territory.
   - Deployment:
     - You get armies based on territories owned (min 3), continent bonuses, and card trades.
     - Action: {"type": "DEPLOY", "territory": "TerritoryName", "max_armies": X} (You will specify the actual number to deploy in the 'num_armies' parameter if you choose this, up to 'max_armies' or your remaining deployable armies). The 'num_armies' in the actual action should be how many to deploy to THIS territory.
   - End Phase:
     - Action: {"type": "END_REINFORCE_PHASE"} (Use when all armies are deployed and no mandatory card trades are left, or if you choose not to trade optional cards).

2. Attack Phase:
   - Goal: Conquer enemy territories to expand, gain cards, and eliminate opponents.
   - Attacking:
     - Action: {"type": "ATTACK", "from": "YourTerritory", "to": "EnemyTerritory", "max_armies_for_attack": X}
     - When you choose this action, you will then specify 'num_attacking_armies' (1 to X). You must leave at least one army in 'from' territory.
     - Attackers roll up to 3 dice, defenders up to 2. Highest dice compared. Attacker wins on ties when defending.
     - If you conquer a territory, you must move in at least the number of dice you rolled, up to all attacking armies that survived. The AI should decide this move optimally.
     - You can earn ONE card per turn by conquering at least one territory.
   - End Phase:
     - Action: {"type": "END_ATTACK_PHASE"} (To stop attacking and move to Fortify phase).

3. Fortify Phase:
   - Goal: Consolidate forces and secure borders.
   - Fortifying:
     - You can make ONE fortification move per turn.
     - Action: {"type": "FORTIFY", "from": "YourTerritoryA", "to": "YourTerritoryB", "max_armies_to_move": X}
     - Territories must be connected by a path of your owned territories.
     - You must leave at least one army in 'from' territory. Specify 'num_armies' to move (1 to X).
   - End Turn:
     - Action: {"type": "END_TURN"} (If you choose not to fortify, or after fortifying). This ends your entire turn.

Strategic Considerations:
- Continents: Holding all territories in a continent gives bonus armies. Some continents are more strategic or easier to defend.
- Cards: Crucial for reinforcements. Trade them wisely. Eliminating a player grants you their cards.
- Diplomacy & Chat: Use chat to form alliances, deceive opponents, or coordinate.
  - Global Chat: {"type": "GLOBAL_CHAT", "message": "Your message to all players."}
  - Private Chat Initiation: {"type": "PRIVATE_CHAT", "target_player_name": "PlayerNameToChatWith", "initial_message": "Your opening message."}
  (Note: Chat actions might take your whole turn or be usable alongside other actions depending on game rules implementation - clarify from context if unsure, or default to it taking a turn if it's one of the valid_actions for a phase).

IMPORTANT:
- Your 'action' MUST be an exact match (including all parameters like 'type', 'from', 'to', 'card_indices', etc.) to one of the dictionaries provided in the 'Valid Actions' list.
- Pay close attention to parameters like 'max_armies', 'max_armies_for_attack', 'max_armies_to_move'. Your chosen 'num_armies' in the final action must respect these.
- If an action from the list has specific values (e.g. "territory": "Alaska"), your chosen action must use those exact values.
- Do not add extra keys to the action dictionary. Only use the keys shown in the valid action.
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
