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
You must respond with a JSON object containing two keys: 'thought' and 'action'.
The 'thought' key should contain your reasoning, your analysis of the board, and your strategy for the current turn.
The 'action' key must contain a valid action object.

Game Phases:
1. Reinforce: Deploy armies based on territories owned, continent bonuses, and card trade-ins.
   - Action: {"type": "DEPLOY", "territory": "TerritoryName", "num_armies": X}
   - Action: {"type": "TRADE_CARDS", "cards": [{"territory_name": "Name", "symbol": "Symbol"}, ...]} (if available)
   - Action: {"type": "END_REINFORCE_PHASE"} (if all armies deployed or no cards to trade)
2. Attack: Attack adjacent enemy territories.
   - Action: {"type": "ATTACK", "from": "YourTerritory", "to": "EnemyTerritory", "num_armies": X} (X is number of armies joining attack, 1 to 3 dice typically)
   - Action: {"type": "END_ATTACK_PHASE"} (to stop attacking and move to Fortify)
3. Fortify: Move armies between two of your connected territories once per turn.
   - Action: {"type": "FORTIFY", "from": "YourTerritoryA", "to": "YourTerritoryB", "num_armies": X}
   - Action: {"type": "END_TURN"} (or SKIP_FORTIFY)

Communication Actions (can often be used instead of a phase-specific action, especially during Attack phase):
- Global Chat: {"type": "GLOBAL_CHAT", "message": "Your message to all players."}
- Private Chat: {"type": "PRIVATE_CHAT", "target_player_name": "PlayerNameToChatWith", "initial_message": "Your opening message."}

Consider the board state, your opponent's strengths, and potential alliances. Be strategic!
The 'action' you choose MUST be from the list of 'Valid Actions' provided, or a correctly formatted chat action.
If you choose an action like ATTACK or FORTIFY, ensure 'num_armies' is appropriate and valid based on the game state and rules.
For ATTACK, 'num_armies' is the number of armies you are sending into battle (not the total in the territory). You must leave at least one army behind.
For DEPLOY, 'num_armies' is the number of armies you are placing on that specific territory.
"""

# This GAME_RULES_SNIPPET will be passed to the agents.
# It needs to be refined as the action schema becomes more concrete.
# For example, how 'num_armies' for an attack action is interpreted (total dice vs. total moving).
# The valid_actions list provided to the agent will be the ultimate source of truth for what specific parameters are needed for each action.
"""

This base class includes:
- Constructor with `player_name` and `player_color`.
- Abstract methods `get_thought_and_action` and `engage_in_private_chat`.
- Helper methods `_construct_system_prompt`, `_construct_user_prompt_for_action`, and `_construct_user_prompt_for_private_chat` to standardize prompt creation.
- A `GAME_RULES_SNIPPET` constant that provides a basic overview of the game and expected JSON format. This will be refined.

Next, I will create the concrete implementations for each LLM. I'll start with a dummy/placeholder implementation for each, which can be filled in later with actual API calls. This helps to quickly establish the structure.

I'll create `gemini_agent.py`, `openai_agent.py`, `claude_agent.py`, and `deepseek_agent.py` in the `llm_risk/ai/` directory.
Due to the limitations of not being able to install new packages or use API keys in this environment, these will be structural placeholders.
