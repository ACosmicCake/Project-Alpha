from .base_agent import BaseAIAgent, GAME_RULES_SNIPPET
import os
import json
# import anthropic # Would be used in a real environment

class ClaudeAgent(BaseAIAgent):
    def __init__(self, player_name: str, player_color: str, api_key: str = None, model_name: str = "claude-3-opus-20240229"): # Or claude-3-sonnet, claude-2.1 etc.
        super().__init__(player_name, player_color)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            print(f"Warning: ClaudeAgent for {player_name} initialized without an API key.")
        # self.client = anthropic.Anthropic(api_key=self.api_key) # Real setup
        self.client = None # Placeholder
        self.model_name = model_name
        self.base_system_prompt = f"You are a masterful and cunning AI player in the game of Risk, known as {self.player_name} ({self.player_color}). Your objective is total domination. You are highly analytical and articulate your thoughts clearly before deciding on an action."

    def get_thought_and_action(self, game_state_json: str, valid_actions: list, game_rules: str = GAME_RULES_SNIPPET, system_prompt_addition: str = "") -> dict:
        if not self.client:
            print(f"ClaudeAgent ({self.player_name}): Client not initialized (API key likely missing). Returning a default valid action.")
            action_to_return = valid_actions[0] if valid_actions else {"type": "END_TURN"}
            return {"thought": "No client available. Defaulting to first valid action or END_TURN.", "action": action_to_return}

        system_p = self._construct_system_prompt(self.base_system_prompt, game_rules, system_prompt_addition)
        user_p = self._construct_user_prompt_for_action(game_state_json, valid_actions)

        # Anthropic API uses a slightly different format for messages (system prompt + list of user/assistant turns)
        # For a single turn action, it's simpler:

        # In a real scenario:
        # response = self.client.messages.create(
        #     model=self.model_name,
        #     max_tokens=1024,
        #     system=system_p, # System prompt
        #     messages=[
        #         {"role": "user", "content": user_p}
        #     ]
        # )
        # try:
        #     # Claude's response is typically in response.content[0].text
        #     # It's expected to be a JSON string.
        #     action_data_str = response.content[0].text
        #     action_data = json.loads(action_data_str)
        # except (json.JSONDecodeError, AttributeError, IndexError) as e:
        #     print(f"ClaudeAgent ({self.player_name}) error decoding JSON: {e}\nResponse was: {action_data_str if 'action_data_str' in locals() else 'No response content'}")
        #     return {"thought": f"Error processing LLM response: {action_data_str if 'action_data_str' in locals() else 'No response content'}", "action": valid_actions[0] if valid_actions else {"type": "END_TURN"}}
        # return action_data

        print(f"ClaudeAgent ({self.player_name}) would send to API: \nSYSTEM: {system_p}\nUSER_PROMPT (messages format): {user_p[:500]}...\n")
        action_to_return = valid_actions[0] if valid_actions else {"type": "END_ATTACK_PHASE"}
        if any(action['type'] == 'END_ATTACK_PHASE' for action in valid_actions):
            action_to_return = {"type": "END_ATTACK_PHASE"}
        elif any(action['type'] == 'END_REINFORCE_PHASE' for action in valid_actions):
            action_to_return = {"type": "END_REINFORCE_PHASE"}
        elif any(action['type'] == 'END_TURN' for action in valid_actions):
            action_to_return = {"type": "END_TURN"}

        return {"thought": f"ClaudeAgent ({self.player_name}) placeholder: Choosing first valid action or phase end.", "action": action_to_return}

    def engage_in_private_chat(self, history: list[dict], game_state_json: str, game_rules: str = GAME_RULES_SNIPPET, recipient_name: str = "", system_prompt_addition: str = "") -> str:
        if not self.client:
            print(f"ClaudeAgent ({self.player_name}): Client not initialized for chat. Returning default message.")
            return "Greetings. (Claude placeholder due to no client)"

        system_p = self._construct_system_prompt(
            f"{self.base_system_prompt} You are in a private text-based negotiation with {recipient_name}.",
            game_rules,
            system_prompt_addition
        )

        # Construct messages list for Anthropic API
        anthropic_messages = []
        for msg in history:
            # Convert sender/recipient to user/assistant roles
            # 'user' is the one who is NOT us (the LLM). 'assistant' IS us.
            role = "user" if msg["sender"] == recipient_name else "assistant"
            anthropic_messages.append({"role": role, "content": msg["message"]})

        # Add the current context and prompt for a response. This is the latest "user" turn.
        # Effectively, we are asking Claude to respond to the last message in history, or initiate if history is empty.
        # The _construct_user_prompt_for_private_chat is not directly used here due to message list format.
        # We can append a final user message that tells Claude it's its turn.
        # If history's last message was from us (assistant), we might not need to add another user message before calling API.
        # However, it's usually a user message that prompts an assistant response.
        # Let's assume the history leads up to Claude needing to speak.

        # The prompt to Claude is essentially the history. We can add context.
        # For Claude, the prompt for its response is the last message in the `messages` list, which should be from the "user" (the other player).
        # If we need to add context like game_state, it can be part of the last user message or system prompt.
        # The _construct_user_prompt_for_private_chat can be adapted.

        # For simplicity, let's ensure the last message is from the "user" perspective to prompt Claude.
        # If the history is empty or the last message was from us, we craft a "user" message.
        # For Claude, the conversation history IS the prompt.
        # The user_prompt from helper is for the content of the last "user" message.

        # Here, we'll just pass the history. The last message in history is what Claude responds to.
        # If history is empty, Claude should generate an opening based on the system prompt.
        # The prompt is implicitly: "Based on this history and your persona, what do you say next?"

        # We can add a final "user" message to guide the response if needed:
        # anthropic_messages.append({"role": "user", "content": f"Game state for context: {game_state_json}. Your turn, {self.player_name}."})


        # In a real scenario:
        # response = self.client.messages.create(
        #     model=self.model_name,
        #     max_tokens=500,
        #     system=system_p,
        #     messages=anthropic_messages # history is already in the correct format
        # )
        # return response.content[0].text

        # For placeholder:
        chat_context_for_claude = f"Game state for context: {game_state_json[:200]}...\nConversation with {recipient_name} so far:\n"
        for msg in history:
            chat_context_for_claude += f"- {msg['sender']}: {msg['message']}\n"
        chat_context_for_claude += f"\nYour response as {self.player_name}:"


        print(f"ClaudeAgent ({self.player_name}) would send to API for chat: \nSYSTEM: {system_p}\nMESSAGES (history): {anthropic_messages}\n(Implicitly asking for next message based on history and system prompt)\n")
        return f"A fascinating proposal, {recipient_name}. Let me consider... (Claude placeholder response)"

if __name__ == '__main__':
    # from dotenv import load_dotenv
    # load_dotenv()
    agent = ClaudeAgent(player_name="ClaudeBot", player_color="Purple")
    dummy_game_state = {"territories": {"Egypt": {"owner": "ClaudeBot", "army_count": 7}}, "current_player": "ClaudeBot"}
    dummy_valid_actions = [{"type": "END_TURN"}]

    if agent.api_key:
        print("ClaudeAgent: API calls would be made here if client was live.")
    else:
        print("ClaudeAgent: API_KEY not found. Skipping live call examples.")
        result = agent.get_thought_and_action(json.dumps(dummy_game_state), dummy_valid_actions)
        print("Action result (placeholder):", result)
        chat_history = [{"sender": "HumanPlayer", "message": "Care for a non-aggression pact for 3 turns?"}]
        chat_response = agent.engage_in_private_chat(chat_history, json.dumps(dummy_game_state), recipient_name="HumanPlayer")
        print("Chat response (placeholder):", chat_response)
