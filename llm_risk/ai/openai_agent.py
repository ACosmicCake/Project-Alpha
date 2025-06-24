from .base_agent import BaseAIAgent, GAME_RULES_SNIPPET
import os
import json
from openai import OpenAI # Would be used in a real environment
import time # For potential retries

class OpenAIAgent(BaseAIAgent):
    def __init__(self, player_name: str, player_color: str, api_key: str = None, model_name: str = "gpt-3.5-turbo"):
        super().__init__(player_name, player_color)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            print(f"Warning: OpenAIAgent for {player_name} initialized without an API key. Live calls will fail.")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key)
        self.model_name = model_name
        self.base_system_prompt = f"You are a strategic AI player in the game of Risk, named {self.player_name}."

    def _get_default_action(self, valid_actions: list) -> dict:
        """Returns a safe default action, prioritizing phase ends or the first valid action."""
        if any(action['type'] == 'END_ATTACK_PHASE' for action in valid_actions):
            return {"type": "END_ATTACK_PHASE"}
        if any(action['type'] == 'END_FORTIFY_PHASE' for action in valid_actions): # Assuming END_FORTIFY_PHASE will be a thing
            return {"type": "END_FORTIFY_PHASE"}
        if any(action['type'] == 'END_REINFORCE_PHASE' for action in valid_actions):
            return {"type": "END_REINFORCE_PHASE"}
        if any(action['type'] == 'END_TURN' for action in valid_actions):
            return {"type": "END_TURN"}
        return valid_actions[0] if valid_actions else {"type": "END_TURN"} # Absolute fallback

    def get_thought_and_action(self, game_state_json: str, valid_actions: list, game_rules: str = GAME_RULES_SNIPPET, system_prompt_addition: str = "", max_retries: int = 1) -> dict:
        default_fallback_action = self._get_default_action(valid_actions)

        if not self.client:
            print(f"OpenAIAgent ({self.player_name}): Client not initialized (API key likely missing). Returning a default valid action.")
            return {"thought": "No client available. Defaulting to a safe action.", "action": default_fallback_action}

        if not valid_actions:
            print(f"OpenAIAgent ({self.player_name}): No valid actions provided. Returning END_TURN.")
            return {"thought": "No valid actions were provided to choose from.", "action": {"type": "END_TURN"}}

        system_prompt = self._construct_system_prompt(self.base_system_prompt, game_rules, system_prompt_addition)
        user_prompt = self._construct_user_prompt_for_action(game_state_json, valid_actions)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        for attempt in range(max_retries + 1):
            try:
                print(f"OpenAIAgent ({self.player_name}) attempt {attempt + 1}: Sending request to API. Model: {self.model_name}")
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    response_format={"type": "json_object"} # For newer models that support JSON mode
                )
                action_data_str = response.choices[0].message.content
                action_data = json.loads(action_data_str)

                if "thought" not in action_data or "action" not in action_data:
                    raise ValueError("Response JSON must contain 'thought' and 'action' keys.")

                # Validate action against valid_actions
                # This is a simple check; more sophisticated validation might be needed
                # (e.g. checking parameters of the action)
                action_type_and_params = {k: v for k, v in action_data["action"].items()}
                is_valid = any(action_type_and_params == {k:v for k,v in va.items()} for va in valid_actions)

                if not is_valid:
                    # More detailed check for common action types to allow flexibility if only type is matched
                    is_type_valid = any(action_data["action"]["type"] == va["type"] for va in valid_actions)
                    if is_type_valid:
                         print(f"OpenAIAgent ({self.player_name}): Action {action_data['action']['type']} is a valid type, but params mismatch or not found in: {valid_actions}. Attempting to use if strategically sound or falling back.")
                         # Potentially allow if type matches and other params are "reasonable" or not security critical
                         # For now, we will be strict.
                         raise ValueError(f"Action {action_data['action']} not found in valid_actions list: {valid_actions}")
                    else:
                        raise ValueError(f"Action type {action_data['action']['type']} not found in valid_actions list: {valid_actions}")


                print(f"OpenAIAgent ({self.player_name}): Successfully received and validated action: {action_data['action']}")
                return action_data

            except json.JSONDecodeError as e:
                error_message = f"JSONDecodeError: {e}. Response: {action_data_str if 'action_data_str' in locals() else 'No response content'}"
                print(f"OpenAIAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return {"thought": f"Error after {max_retries + 1} attempts. {error_message}", "action": default_fallback_action}
            except (AttributeError, IndexError, ValueError, Exception) as e: # Broader OpenAI API errors or custom errors
                error_message = f"API/Validation Error: {e.__class__.__name__}: {e}"
                print(f"OpenAIAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return {"thought": f"Error after {max_retries + 1} attempts. {error_message}", "action": default_fallback_action}

            print(f"OpenAIAgent ({self.player_name}): Retrying in 1 second...")
            time.sleep(1) # Simple backoff

        # Should not be reached if logic is correct, but as a safeguard:
        return {"thought": "Reached end of get_thought_and_action unexpectedly after retries.", "action": default_fallback_action}


    def engage_in_private_chat(self, history: list[dict], game_state_json: str, game_rules: str = GAME_RULES_SNIPPET, recipient_name: str = "", system_prompt_addition: str = "", max_retries: int = 1) -> str:
        default_fallback_message = f"Sorry, I'm having trouble connecting. (OpenAI fallback) - to {recipient_name}"

        if not self.client:
            print(f"OpenAIAgent ({self.player_name}): Client not initialized for chat. Returning default message.")
            return default_fallback_message

        system_prompt_chat = self._construct_system_prompt(
             f"{self.base_system_prompt} You are now in a private chat with {recipient_name}.",
             game_rules,
             system_prompt_addition
        )

        messages = [{"role": "system", "content": system_prompt_chat}]
        for msg in history:
            role = "user" if msg["sender"] == recipient_name else "assistant"
            if msg["sender"] == self.player_name:
                role = "assistant"
            else:
                role = "user"
            messages.append({"role": role, "content": msg["message"]})

        # Add the final user message that prompts the AI for a response
        messages.append({"role": "user", "content": f"You are {self.player_name}. It's your turn to speak to {recipient_name}. Current game state for context:\n{game_state_json}\n\nYour response:"})

        for attempt in range(max_retries + 1):
            try:
                print(f"OpenAIAgent ({self.player_name}) attempt {attempt + 1}: Sending chat request to API. Model: {self.model_name}")
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages
                )
                chat_response_content = response.choices[0].message.content
                if not chat_response_content.strip():
                    raise ValueError("Received empty chat response from API.")
                print(f"OpenAIAgent ({self.player_name}): Successfully received chat response.")
                return chat_response_content

            except (AttributeError, IndexError, ValueError, Exception) as e: # Broader OpenAI API errors
                error_message = f"API/Validation Error in chat: {e.__class__.__name__}: {e}"
                print(f"OpenAIAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return f"Error after {max_retries + 1} attempts in chat. {error_message}. {default_fallback_message}"

            print(f"OpenAIAgent ({self.player_name}): Retrying chat in 1 second...")
            time.sleep(1) # Simple backoff

        return default_fallback_message # Safeguard

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
