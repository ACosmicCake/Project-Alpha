from .base_agent import BaseAIAgent, GAME_RULES_SNIPPET
import os
import json
import requests # Would be used in a real environment
import time # For potential retries

class DeepSeekAgent(BaseAIAgent):
    def __init__(self, player_name: str, player_color: str, api_key: str = None, model_name: str = "deepseek-chat"): # Or specific model version like deepseek-coder
        super().__init__(player_name, player_color)
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            print(f"Warning: DeepSeekAgent for {player_name} initialized without an API key. Live calls will fail.")
        self.model_name = model_name
        self.api_base_url = "https://api.deepseek.com/v1" # Standard endpoint

        # Deepseek API is OpenAI compatible, so system prompt should ask for JSON.
        self.base_system_prompt = f"You are an exceptionally intelligent AI player in the game of Risk, known as {self.player_name}. You are playing with the {self.player_color} pieces. Your goal is world conquest. Think step-by-step and make bold, calculated moves. Respond in JSON format with 'thought' and 'action' keys."

    def _get_default_action(self, valid_actions: list) -> dict:
        """Returns a safe default action, prioritizing phase ends or the first valid action."""
        if any(action['type'] == 'END_ATTACK_PHASE' for action in valid_actions):
            return {"type": "END_ATTACK_PHASE"}
        if any(action['type'] == 'END_FORTIFY_PHASE' for action in valid_actions):
            return {"type": "END_FORTIFY_PHASE"}
        if any(action['type'] == 'END_REINFORCE_PHASE' for action in valid_actions):
            return {"type": "END_REINFORCE_PHASE"}
        if any(action['type'] == 'END_TURN' for action in valid_actions):
            return {"type": "END_TURN"}
        return valid_actions[0] if valid_actions else {"type": "END_TURN"}

    def get_thought_and_action(self, game_state_json: str, valid_actions: list, game_rules: str = GAME_RULES_SNIPPET, system_prompt_addition: str = "", max_retries: int = 1) -> dict:
        default_fallback_action = self._get_default_action(valid_actions)

        if not self.api_key:
            print(f"DeepSeekAgent ({self.player_name}): API key missing. Returning a default valid action.")
            return {"thought": "No API key. Defaulting to a safe action.", "action": default_fallback_action}

        if not valid_actions:
            print(f"DeepSeekAgent ({self.player_name}): No valid actions provided. Returning END_TURN.")
            return {"thought": "No valid actions were provided to choose from.", "action": {"type": "END_TURN"}}

        system_prompt = self._construct_system_prompt(self.base_system_prompt, game_rules, system_prompt_addition)
        if "Respond in JSON format" not in system_prompt: # Ensure JSON instruction
             system_prompt += " You MUST respond with a single valid JSON object containing two keys: 'thought' (your reasoning) and 'action' (one of the provided valid actions)."

        user_prompt = self._construct_user_prompt_for_action(game_state_json, valid_actions)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            # Deepseek supports response_format for JSON like OpenAI
            "response_format": {"type": "json_object"}
            # "temperature": 0.7, # Optional: Adjust creativity
            # "max_tokens": 1000, # Optional: Limit response length
        }

        for attempt in range(max_retries + 1):
            try:
                print(f"DeepSeekAgent ({self.player_name}) attempt {attempt + 1}: Sending request to API. Model: {self.model_name}")
                response = requests.post(f"{self.api_base_url}/chat/completions", headers=headers, json=payload, timeout=30)
                response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

                response_data = response.json()
                action_data_str = response_data["choices"][0]["message"]["content"]
                action_data = json.loads(action_data_str)

                if "thought" not in action_data or "action" not in action_data:
                    raise ValueError("Response JSON must contain 'thought' and 'action' keys.")

                action_type_and_params = {k: v for k, v in action_data["action"].items()}
                is_valid = any(action_type_and_params == {k:v for k,v in va.items()} for va in valid_actions)

                if not is_valid:
                    is_type_valid = any(action_data["action"]["type"] == va["type"] for va in valid_actions)
                    if is_type_valid:
                        print(f"DeepSeekAgent ({self.player_name}): Action {action_data['action']['type']} is a valid type, but params mismatch or not found in: {valid_actions}. Falling back.")
                        raise ValueError(f"Action {action_data['action']} params mismatch or not found in valid_actions list: {valid_actions}")
                    else:
                        raise ValueError(f"Action type {action_data['action']['type']} not found in valid_actions list: {valid_actions}")

                print(f"DeepSeekAgent ({self.player_name}): Successfully received and validated action: {action_data['action']}")
                return action_data

            except requests.exceptions.Timeout:
                error_message = "Request timed out."
                print(f"DeepSeekAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return {"thought": f"Error after {max_retries + 1} attempts. {error_message}", "action": default_fallback_action}
            except requests.exceptions.RequestException as e:
                error_message = f"HTTP Request Error: {e}"
                print(f"DeepSeekAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return {"thought": f"Error after {max_retries + 1} attempts. {error_message}", "action": default_fallback_action}
            except json.JSONDecodeError as e:
                error_message = f"JSONDecodeError: {e}. Response: {action_data_str if 'action_data_str' in locals() else (response.text if 'response' in locals() else 'No response content')}"
                print(f"DeepSeekAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return {"thought": f"Error after {max_retries + 1} attempts. {error_message}", "action": default_fallback_action}
            except (KeyError, IndexError, ValueError) as e: # For issues with response structure or validation
                error_message = f"API Response/Validation Error: {e.__class__.__name__}: {e}"
                print(f"DeepSeekAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return {"thought": f"Error after {max_retries + 1} attempts. {error_message}", "action": default_fallback_action}

            print(f"DeepSeekAgent ({self.player_name}): Retrying in 1 second...")
            time.sleep(1)

        return {"thought": "Reached end of get_thought_and_action unexpectedly after retries.", "action": default_fallback_action}


    def engage_in_private_chat(self, history: list[dict], game_state_json: str, game_rules: str = GAME_RULES_SNIPPET, recipient_name: str = "", system_prompt_addition: str = "", max_retries: int = 1) -> str:
        default_fallback_message = f"My apologies to {recipient_name}, I seem to be having technical difficulties. (DeepSeek fallback)"
        if not self.api_key:
            print(f"DeepSeekAgent ({self.player_name}): API key missing for chat. Returning default message.")
            return default_fallback_message

        system_prompt_chat = self._construct_system_prompt(
             f"{self.base_system_prompt.split(' Respond in JSON format')[0]} You are in a private dialogue with {recipient_name}. Current game state is provided for context.", # Remove JSON part for chat
             game_rules,
             system_prompt_addition
        )

        messages = [{"role": "system", "content": system_prompt_chat}]
        for msg in history:
            role = "user" if msg["sender"] == recipient_name else "assistant"
            content = msg["message"] if msg["message"] and msg["message"].strip() else "(empty message)"
            messages.append({"role": role, "content": content})

        final_user_message_content = f"Current game state for your information:\n{game_state_json}\n\nIt's your turn to speak to {recipient_name}. What do you say?"
        messages.append({"role": "user", "content": final_user_message_content})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            # "temperature": 0.8, # Chat can be more creative
            # "max_tokens": 500,
        }

        for attempt in range(max_retries + 1):
            try:
                print(f"DeepSeekAgent ({self.player_name}) attempt {attempt + 1}: Sending chat request to API. Model: {self.model_name}")
                response = requests.post(f"{self.api_base_url}/chat/completions", headers=headers, json=payload, timeout=20)
                response.raise_for_status()

                response_data = response.json()
                chat_response_content = response_data["choices"][0]["message"]["content"]

                if not chat_response_content.strip():
                    raise ValueError("Received empty chat response from API.")
                print(f"DeepSeekAgent ({self.player_name}): Successfully received chat response.")
                return chat_response_content

            except requests.exceptions.Timeout:
                error_message = "Chat request timed out."
                print(f"DeepSeekAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return f"Error after {max_retries + 1} attempts in chat. {error_message}. {default_fallback_message}"
            except requests.exceptions.RequestException as e:
                error_message = f"Chat HTTP Request Error: {e}"
                print(f"DeepSeekAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return f"Error after {max_retries + 1} attempts in chat. {error_message}. {default_fallback_message}"
            except (KeyError, IndexError, ValueError) as e: # For issues with response structure or validation
                error_message = f"Chat API Response/Validation Error: {e.__class__.__name__}: {e}"
                print(f"DeepSeekAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return f"Error after {max_retries + 1} attempts in chat. {error_message}. {default_fallback_message}"

            print(f"DeepSeekAgent ({self.player_name}): Retrying chat in 1 second...")
            time.sleep(1)

        return default_fallback_message

if __name__ == '__main__':
    # from dotenv import load_dotenv
    # load_dotenv() # Load .env file for DEEPSEEK_API_KEY

    # Note: The requests library is not available in this environment, so live calls will fail.
    # The code is structured as if it were.
    agent = DeepSeekAgent(player_name="DeepSeekBot", player_color="Black")
    dummy_game_state = {"territories": {"Brazil": {"owner": "DeepSeekBot", "army_count": 10}}, "current_player": "DeepSeekBot"}
    dummy_valid_actions = [{"type": "ATTACK", "from": "Brazil", "to": "Peru", "max_armies_for_attack": 9}, {"type": "END_ATTACK_PHASE"}]

    if agent.api_key:
        print("DeepSeekAgent: API key found. Placeholder API calls will be simulated.")
        # Actual calls would require 'requests' and a live API.
    else:
        print("DeepSeekAgent: DEEPSEEK_API_KEY not found in environment. Using full placeholders.")

    result = agent.get_thought_and_action(json.dumps(dummy_game_state), dummy_valid_actions)
    print("Action result (placeholder):", result)

    chat_history = [{"sender": "PlayerX", "message": "I propose an alliance against PlayerY."}]
    chat_response = agent.engage_in_private_chat(chat_history, json.dumps(dummy_game_state), recipient_name="PlayerX")
    print("Chat response (placeholder):", chat_response)
