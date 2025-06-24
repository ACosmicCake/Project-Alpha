from .base_agent import BaseAIAgent, GAME_RULES_SNIPPET
import os
import json
# from openai import OpenAI # Would be used in a real environment

class OpenAIAgent(BaseAIAgent):
    def __init__(self, player_name: str, player_color: str, api_key: str = None, model_name: str = "gpt-3.5-turbo"):
        super().__init__(player_name, player_color)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            print(f"Warning: OpenAIAgent for {player_name} initialized without an API key.")
        # self.client = OpenAI(api_key=self.api_key) # Real setup
        self.client = None # Placeholder
        self.model_name = model_name
        self.base_system_prompt = f"You are a strategic AI player in the game of Risk, named {self.player_name}."

    def get_thought_and_action(self, game_state_json: str, valid_actions: list, game_rules: str = GAME_RULES_SNIPPET, system_prompt_addition: str = "") -> dict:
        if not self.client:
            print(f"OpenAIAgent ({self.player_name}): Client not initialized (API key likely missing). Returning a default valid action.")
            action_to_return = valid_actions[0] if valid_actions else {"type": "END_TURN"} # Fallback
            return {"thought": "No client available. Defaulting to first valid action or END_TURN.", "action": action_to_return}

        system_prompt = self._construct_system_prompt(self.base_system_prompt, game_rules, system_prompt_addition)
        user_prompt = self._construct_user_prompt_for_action(game_state_json, valid_actions)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # In a real scenario:
        # response = self.client.chat.completions.create(
        #     model=self.model_name,
        #     messages=messages,
        #     response_format={"type": "json_object"} # For newer models that support JSON mode
        # )
        # try:
        #     # Assuming the response is directly a JSON string in choice.message.content
        #     action_data_str = response.choices[0].message.content
        #     action_data = json.loads(action_data_str)
        # except (json.JSONDecodeError, AttributeError, IndexError) as e:
        #     print(f"OpenAIAgent ({self.player_name}) error decoding JSON: {e}\nResponse was: {action_data_str if 'action_data_str' in locals() else 'No response content'}")
        #     # Fallback or error handling strategy
        #     return {"thought": f"Error processing LLM response: {action_data_str if 'action_data_str' in locals() else 'No response content'}", "action": valid_actions[0] if valid_actions else {"type": "END_TURN"}}
        # return action_data

        print(f"OpenAIAgent ({self.player_name}) would send to API: \nMESSAGES: {messages}\n") # Log mock call
        action_to_return = valid_actions[0] if valid_actions else {"type": "END_ATTACK_PHASE"}
        if any(action['type'] == 'END_ATTACK_PHASE' for action in valid_actions):
            action_to_return = {"type": "END_ATTACK_PHASE"}
        elif any(action['type'] == 'END_REINFORCE_PHASE' for action in valid_actions):
            action_to_return = {"type": "END_REINFORCE_PHASE"}
        elif any(action['type'] == 'END_TURN' for action in valid_actions):
            action_to_return = {"type": "END_TURN"}

        return {"thought": f"OpenAIAgent ({self.player_name}) placeholder: Choosing first valid action or a phase end.", "action": action_to_return}

    def engage_in_private_chat(self, history: list[dict], game_state_json: str, game_rules: str = GAME_RULES_SNIPPET, recipient_name: str = "", system_prompt_addition: str = "") -> str:
        if not self.client:
            print(f"OpenAIAgent ({self.player_name}): Client not initialized for chat. Returning default message.")
            return "Hello! (OpenAI placeholder due to no client)"

        system_prompt_chat = self._construct_system_prompt(
             f"{self.base_system_prompt} You are now in a private chat with {recipient_name}.",
             game_rules,
             system_prompt_addition
        )

        messages = [{"role": "system", "content": system_prompt_chat}]
        for msg in history:
            # Ensure correct role mapping if history has 'sender'/'self' etc.
            role = "user" if msg["sender"] == recipient_name else "assistant"
            if msg["sender"] == self.player_name: # Our own messages are 'assistant' in OpenAI terms for history
                role = "assistant"
            else: # Messages from the other person are 'user'
                role = "user"
            messages.append({"role": role, "content": msg["message"]})

        # The last user prompt for the current turn of chat
        # This is slightly different from _construct_user_prompt_for_private_chat as it's integrated into messages
        # For OpenAI, the prompt is the last message from the "user" (the other chatter)
        # If we are initiating or speaking next, the "user" prompt is more of a context setter.
        # The actual prompt for the LLM to respond to is the history itself.
        # Let's add a final instruction.
        messages.append({"role": "user", "content": f"You are {self.player_name}. It's your turn to speak to {recipient_name}. Current game state for context:\n{game_state_json}\n\nYour response:"})


        # In a real scenario:
        # response = self.client.chat.completions.create(
        #     model=self.model_name,
        #     messages=messages
        # )
        # return response.choices[0].message.content

        print(f"OpenAIAgent ({self.player_name}) would send to API for chat: \nMESSAGES: {messages}\n") # Log mock call
        return f"Interesting point, {recipient_name}. (OpenAI placeholder response)"

if __name__ == '__main__':
    # from dotenv import load_dotenv
    # load_dotenv()
    agent = OpenAIAgent(player_name="OpenAIBot", player_color="Green")
    dummy_game_state = {"territories": {"Alaska": {"owner": "OpenAIBot", "army_count": 3}}, "current_player": "OpenAIBot"}
    dummy_valid_actions = [{"type": "FORTIFY", "from": "Alaska", "to": "Alberta", "max_armies_to_move": 2}, {"type": "END_TURN"}]

    if agent.api_key:
        print("OpenAIAgent: API calls would be made here if client was live.")
    else:
        print("OpenAIAgent: API_KEY not found. Skipping live call examples.")
        result = agent.get_thought_and_action(json.dumps(dummy_game_state), dummy_valid_actions)
        print("Action result (placeholder):", result)
        chat_history = [{"sender": "OtherPlayer", "message": "Shall we discuss strategy?"}]
        chat_response = agent.engage_in_private_chat(chat_history, json.dumps(dummy_game_state), recipient_name="OtherPlayer")
        print("Chat response (placeholder):", chat_response)
