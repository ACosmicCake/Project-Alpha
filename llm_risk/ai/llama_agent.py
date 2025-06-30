from .base_agent import BaseAIAgent, GAME_RULES_SNIPPET
import os
import json
import requests # Would be used in a real environment
import time # For potential retries
import ast # For safely evaluating string literals

class LlamaAgent(BaseAIAgent):
    def __init__(self, player_name: str, player_color: str, api_key: str = None, model_name: str = "mminimax/minimax-m1:extended"): # Or specific model version
        super().__init__(player_name, player_color)
        # Updated for OpenRouter API
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            print(f"Warning: LlamaAgent (via OpenRouter) for {player_name} initialized without an OPENROUTER_API_KEY. Live calls will fail.")
        self.model_name = model_name
        self.api_base_url = "https://openrouter.ai/api/v1" # OpenRouter endpoint

        # Llama API (via OpenRouter, assuming similar compatibility to OpenAI for JSON)
        self.base_system_prompt = (
            f"You are an exceptionally intelligent AI player in the game of Risk, known as {self.player_name}. "
            f"You are playing with the {self.player_color} pieces. Your goal is world conquest. "
            f"Think step-by-step and make bold, calculated moves. "
            f"You MUST respond with a single valid JSON object. This JSON object must contain exactly two keys: "
            f"'thought' (a string detailing your reasoning) and 'action' (a JSON object representing one of the provided valid actions)."
        )
        # Optional headers for OpenRouter analytics
        self.http_referer = os.getenv("YOUR_SITE_URL", "http://localhost:8000") # Example URL
        self.x_title = os.getenv("YOUR_SITE_NAME", "LLM Risk Game") # Example Title

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

    def get_thought_and_action(self, game_state_json: str, valid_actions: list, game_rules: str = GAME_RULES_SNIPPET, system_prompt_addition: str = "", max_retries: int = 4) -> dict:
        default_fallback_action = self._get_default_action(valid_actions)

        if not self.api_key:
            print(f"LlamaAgent ({self.player_name}): API key missing. Returning a default valid action.")
            return {"thought": "No API key. Defaulting to a safe action.", "action": default_fallback_action}

        if not valid_actions:
            print(f"LlamaAgent ({self.player_name}): No valid actions provided. Returning END_TURN.")
            return {"thought": "No valid actions were provided to choose from.", "action": {"type": "END_TURN"}}

        system_prompt = self._construct_system_prompt(self.base_system_prompt, game_rules, system_prompt_addition)
        # The base_system_prompt already includes the detailed JSON instruction.
        # We can add a reinforcement here if system_prompt_addition somehow overwrites it, though unlikely with _construct_system_prompt.
        if "You MUST respond with a single valid JSON object" not in system_prompt: # Check for the more specific instruction
             system_prompt += " Remember, your entire response must be a single JSON object, and the 'action' key within that JSON must also contain a JSON object representing your chosen action."

        user_prompt = self._construct_user_prompt_for_action(game_state_json, valid_actions)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Optional headers for OpenRouter analytics
            "HTTP-Referer": self.http_referer,
            "X-Title": self.x_title
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            # Assuming Llama via OpenRouter supports response_format for JSON like OpenAI
            "response_format": {"type": "json_object"}
            # "temperature": 0.7, # Optional: Adjust creativity
            # "max_tokens": 1000, # Optional: Limit response length
        }

        for attempt in range(max_retries + 1):
            try:
                print(f"LlamaAgent ({self.player_name}) attempt {attempt + 1}: Sending request to API. Model: {self.model_name}")
                response = requests.post(f"{self.api_base_url}/chat/completions", headers=headers, data=json.dumps(payload), timeout=30)
                response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

                response_data = response.json()
                action_data_str = response_data["choices"][0]["message"]["content"].strip()

                if not action_data_str: # Handle empty string response
                    raise ValueError("Received empty content from LLM.")

                action_data = None
                try:
                    # Attempt to parse the entire response string as JSON first
                    action_data = json.loads(action_data_str)
                except json.JSONDecodeError as e_json:
                    print(f"LlamaAgent ({self.player_name}): json.loads failed for initial response. Trying ast.literal_eval. Error: {e_json}")
                    try:
                        # Sanitize Python bools/None to JSON true/false/null for ast.literal_eval compatibility
                        # and general robustness if ast.literal_eval were to expect more JSON-like structures
                        # for some edge cases, though it primarily handles Python literals.
                        sanitized_str = action_data_str.replace("True", "true").replace("False", "false").replace("None", "null")

                        # ast.literal_eval can handle Python dicts with single quotes.
                        action_data = ast.literal_eval(sanitized_str)
                        if not isinstance(action_data, dict):
                            raise ValueError(f"ast.literal_eval on main response produced type {type(action_data).__name__}, not a dictionary. Content: '{action_data_str}'")
                        print(f"LlamaAgent ({self.player_name}): Successfully parsed initial response with ast.literal_eval after sanitization.")
                    except (ValueError, SyntaxError) as e_ast:
                        print(f"LlamaAgent ({self.player_name}): ast.literal_eval also failed for initial response. Error: {e_ast}. Content: '{action_data_str}'")
                        raise e_json # Re-raise the original JSONDecodeError to be caught by the retry loop's handler

                if action_data is None:
                    raise ValueError(f"Failed to parse LLM response content into a dictionary using any method. Content: '{action_data_str}'")

                if "thought" not in action_data or "action" not in action_data:
                    raise ValueError(f"Response JSON must contain 'thought' and 'action' keys. Received: {action_data}")

                # --- ROBUST PARSING for 'action' field (value of the "action" key) ---
                action_field = action_data["action"]
                action_dict_from_llm = None
                if isinstance(action_field, str):
                    try:
                        action_dict_from_llm = json.loads(action_field)
                    except json.JSONDecodeError:
                        try:
                            # Sanitize Python bools/None within the action string as well
                            sanitized_action_str = action_field.replace("True", "true").replace("False", "false").replace("None", "null")
                            action_dict_from_llm = ast.literal_eval(sanitized_action_str)
                            if not isinstance(action_dict_from_llm, dict):
                                raise ValueError(f"ast.literal_eval on 'action' field produced type {type(action_dict_from_llm).__name__}, not a dictionary. Action field content: '{action_field}'")
                        except (ValueError, SyntaxError) as e_ast:
                            raise ValueError(f"The 'action' field string could not be parsed as JSON or Python dict. Error: {e_ast}. Action field content: '{action_field}'")
                elif isinstance(action_field, dict):
                    action_dict_from_llm = action_field
                else:
                    raise ValueError(f"The 'action' field is not a valid dictionary or a parseable string. Received type: {type(action_field).__name__}, value: '{action_field}'")
                # --- END ROBUST PARSING ---

                # Use the validation method from BaseAIAgent
                if not self._validate_chosen_action(action_dict_from_llm, valid_actions):
                    # _validate_chosen_action already prints detailed error
                    raise ValueError(f"Action validation failed for {action_dict_from_llm}.")

                print(f"LlamaAgent ({self.player_name}): Successfully received and validated action: {action_dict_from_llm}")
                return {"thought": action_data["thought"], "action": action_dict_from_llm}

            except requests.exceptions.Timeout:
                error_message = "Request timed out."
                print(f"LlamaAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return {"thought": f"Error after {max_retries + 1} attempts. {error_message}", "action": default_fallback_action}
            except requests.exceptions.RequestException as e:
                error_message = f"HTTP Request Error: {e}"
                print(f"LlamaAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return {"thought": f"Error after {max_retries + 1} attempts. {error_message}", "action": default_fallback_action}
            except json.JSONDecodeError as e:
                error_message = f"JSONDecodeError: {e}. Response: {action_data_str if 'action_data_str' in locals() else (response.text if 'response' in locals() else 'No response content')}"
                print(f"LlamaAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return {"thought": f"Error after {max_retries + 1} attempts. {error_message}", "action": default_fallback_action}
            except (KeyError, IndexError, ValueError) as e: # For issues with response structure or custom validation
                error_message = f"API Response/Validation Error: {e.__class__.__name__}: {e}"
                print(f"LlamaAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return {"thought": f"Error after {max_retries + 1} attempts. {error_message}", "action": default_fallback_action}

            print(f"LlamaAgent ({self.player_name}): Retrying in 1 second...")
            time.sleep(1)

        return {"thought": "Reached end of get_thought_and_action unexpectedly after retries.", "action": default_fallback_action}


    def engage_in_private_chat(self, history: list[dict], game_state_json: str, game_rules: str = GAME_RULES_SNIPPET, recipient_name: str = "", system_prompt_addition: str = "", max_retries: int = 4) -> str:
        default_fallback_message = f"My apologies to {recipient_name}, I seem to be having technical difficulties. (Llama fallback)"
        if not self.api_key:
            print(f"LlamaAgent ({self.player_name}): API key missing for chat. Returning default message.")
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
            "Content-Type": "application/json",
            "HTTP-Referer": self.http_referer,
            "X-Title": self.x_title
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            # "temperature": 0.8, # Chat can be more creative
            # "max_tokens": 500,
        }

        for attempt in range(max_retries + 1):
            try:
                print(f"LlamaAgent ({self.player_name}) attempt {attempt + 1}: Sending chat request to API. Model: {self.model_name}")
                response = requests.post(f"{self.api_base_url}/chat/completions", headers=headers, data=json.dumps(payload), timeout=20)
                response.raise_for_status()

                response_data = response.json()
                chat_response_content = response_data["choices"][0]["message"]["content"]

                if not chat_response_content.strip():
                    raise ValueError("Received empty chat response from API.")
                print(f"LlamaAgent ({self.player_name}): Successfully received chat response.")
                return chat_response_content

            except requests.exceptions.Timeout:
                error_message = "Chat request timed out."
                print(f"LlamaAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return f"Error after {max_retries + 1} attempts in chat. {error_message}. {default_fallback_message}"
            except requests.exceptions.RequestException as e:
                error_message = f"Chat HTTP Request Error: {e}"
                print(f"LlamaAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return f"Error after {max_retries + 1} attempts in chat. {error_message}. {default_fallback_message}"
            except (KeyError, IndexError, ValueError) as e: # For issues with response structure or validation
                error_message = f"Chat API Response/Validation Error: {e.__class__.__name__}: {e}"
                print(f"LlamaAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return f"Error after {max_retries + 1} attempts in chat. {error_message}. {default_fallback_message}"

            print(f"LlamaAgent ({self.player_name}): Retrying chat in 1 second...")
            time.sleep(1)

        return default_fallback_message

if __name__ == '__main__':
    # from dotenv import load_dotenv
    # load_dotenv() # Load .env file for OPENROUTER_API_KEY

    # Note: The requests library is not available in this environment, so live calls will fail.
    # The code is structured as if it were.
    agent = LlamaAgent(player_name="LlamaBot", player_color="Purple") # Example color
    dummy_game_state = {"territories": {"Brazil": {"owner": "LlamaBot", "army_count": 10}}, "current_player": "LlamaBot"}
    dummy_valid_actions = [{"type": "ATTACK", "from": "Brazil", "to": "Peru", "max_armies_for_attack": 9}, {"type": "END_ATTACK_PHASE"}]

    if agent.api_key:
        print("LlamaAgent: API key found. Placeholder API calls will be simulated.")
        # Actual calls would require 'requests' and a live API.
    else:
        print("LlamaAgent: OPENROUTER_API_KEY not found in environment. Using full placeholders.")

    result = agent.get_thought_and_action(json.dumps(dummy_game_state), dummy_valid_actions)
    print("Action result (placeholder):", result)

    chat_history = [{"sender": "PlayerX", "message": "I propose an alliance against PlayerY."}]
    chat_response = agent.engage_in_private_chat(chat_history, json.dumps(dummy_game_state), recipient_name="PlayerX")
    print("Chat response (placeholder):", chat_response)
