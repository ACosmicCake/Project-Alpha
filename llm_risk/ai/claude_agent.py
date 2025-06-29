from .base_agent import BaseAIAgent, GAME_RULES_SNIPPET
import os
import json
import anthropic # Would be used in a real environment
import time # For potential retries

class ClaudeAgent(BaseAIAgent):
    def __init__(self, player_name: str, player_color: str, api_key: str = None, model_name: str = "claude-3-haiku-20240307"): # Using Haiku for speed/cost effectiveness
        super().__init__(player_name, player_color)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            print(f"Warning: ClaudeAgent for {player_name} initialized without an API key. Live calls will fail.")
            self.client = None
        else:
            self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model_name = model_name
        self.base_system_prompt = f"You are a masterful and cunning AI player in the game of Risk, known as {self.player_name} ({self.player_color}). Your objective is total domination. You are highly analytical and articulate your thoughts clearly before deciding on an action. Respond in JSON format with 'thought' and 'action' keys."

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
        return valid_actions[0] if valid_actions else {"type": "END_TURN"} # Absolute fallback

    def get_thought_and_action(self, game_state_json: str, valid_actions: list, game_rules: str = GAME_RULES_SNIPPET, system_prompt_addition: str = "", max_retries: int = 4) -> dict:
        default_fallback_action = self._get_default_action(valid_actions)

        if not self.client:
            print(f"ClaudeAgent ({self.player_name}): Client not initialized (API key likely missing). Returning a default valid action.")
            return {"thought": "No client available. Defaulting to a safe action.", "action": default_fallback_action}

        if not valid_actions:
            print(f"ClaudeAgent ({self.player_name}): No valid actions provided. Returning END_TURN.")
            return {"thought": "No valid actions were provided to choose from.", "action": {"type": "END_TURN"}}

        # Ensure the system prompt explicitly asks for JSON.
        system_p = self._construct_system_prompt(self.base_system_prompt, game_rules, system_prompt_addition)
        if "Respond in JSON format" not in system_p: # Double check
             system_p += " You MUST respond with a single valid JSON object containing two keys: 'thought' (your reasoning) and 'action' (one of the provided valid actions)."

        user_p = self._construct_user_prompt_for_action(game_state_json, valid_actions)
        # Anthropic expects the last message to be 'user' to generate an 'assistant' response.
        # The user_p already contains the request for action.

        for attempt in range(max_retries + 1):
            try:
                print(f"ClaudeAgent ({self.player_name}) attempt {attempt + 1}: Sending request to API. Model: {self.model_name}")
                response = self.client.messages.create(
                    model=self.model_name,
                    max_tokens=1024, # Adjust as needed
                    system=system_p,
                    messages=[
                        {"role": "user", "content": user_p}
                    ]
                )

                # Ensure response.content is a list and has at least one item
                if not response.content or not isinstance(response.content, list) or not hasattr(response.content[0], 'text'):
                    raise ValueError("Invalid response structure from Claude API.")

                action_data_str = response.content[0].text
                # Claude might sometimes wrap JSON in ```json ... ```, try to strip it
                if action_data_str.strip().startswith("```json"):
                    action_data_str = action_data_str.strip()[7:-3].strip()
                elif action_data_str.strip().startswith("```"): # More generic ``` stripping
                    action_data_str = action_data_str.strip()[3:-3].strip()

                action_data = json.loads(action_data_str) # This should be a dict with 'thought' and 'action'

                if "thought" not in action_data or "action" not in action_data:
                    raise ValueError("Response JSON must contain 'thought' and 'action' keys.")

                # --- FIX: Handle 'action' being either a string or a dict ---
                action_field = action_data["action"]
                action_dict_from_llm = None
                if isinstance(action_field, str):
                    try:
                        action_dict_from_llm = json.loads(action_field)
                    except json.JSONDecodeError:
                        raise ValueError(f"The 'action' field was a string but not valid JSON. Received: {action_field}")
                elif isinstance(action_field, dict):
                    action_dict_from_llm = action_field # It's already a dict
                else:
                    raise ValueError(f"The 'action' field is not a valid dictionary or JSON string. Received: {action_field}")
                # --- END FIX ---

                # Use the validation method from BaseAIAgent
                if not self._validate_chosen_action(action_dict_from_llm, valid_actions):
                    # _validate_chosen_action already prints detailed error
                    raise ValueError(f"Action validation failed for {action_dict_from_llm}.")

                print(f"ClaudeAgent ({self.player_name}): Successfully received and validated action: {action_dict_from_llm}")
                return {"thought": action_data["thought"], "action": action_dict_from_llm}

            except json.JSONDecodeError as e:
                error_message = f"JSONDecodeError: {e}. Response: '{action_data_str if 'action_data_str' in locals() else 'No response content yet'}'"
                print(f"ClaudeAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return {"thought": f"Error after {max_retries + 1} attempts. {error_message}", "action": default_fallback_action}
            except (anthropic.APIError, ValueError, AttributeError, IndexError) as e: # Catch Anthropic specific and other validation/parsing errors
                error_message = f"API/Validation Error: {e.__class__.__name__}: {e}"
                print(f"ClaudeAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return {"thought": f"Error after {max_retries + 1} attempts. {error_message}", "action": default_fallback_action}

            print(f"ClaudeAgent ({self.player_name}): Retrying in 1 second...")
            time.sleep(1)

        return {"thought": "Reached end of get_thought_and_action unexpectedly after retries.", "action": default_fallback_action}


    def engage_in_private_chat(self, history: list[dict], game_state_json: str, game_rules: str = GAME_RULES_SNIPPET, recipient_name: str = "", system_prompt_addition: str = "", max_retries: int = 4) -> str:
        default_fallback_message = f"My apologies, I am currently unable to respond. (Claude fallback) - to {recipient_name}"
        if not self.client:
            print(f"ClaudeAgent ({self.player_name}): Client not initialized for chat. Returning default message.")
            return default_fallback_message

        system_p = self._construct_system_prompt(
            f"{self.base_system_prompt} You are in a private text-based negotiation with {recipient_name}. Be strategic and try to achieve your goals. The game state is provided for context.",
            game_rules, # Game rules might be less relevant for chat, but can be included
            system_prompt_addition
        )

        anthropic_messages = []
        for msg in history:
            role = "user" if msg["sender"] == recipient_name else "assistant"
            # Ensure no empty content messages, as Claude API might reject them.
            content = msg["message"] if msg["message"] and msg["message"].strip() else "(empty message)"
            anthropic_messages.append({"role": role, "content": content})

        # Add a final "user" message to prompt Claude for its response in the conversation.
        # This message should make it clear it's Claude's turn to speak.
        # We include game_state_json here as part of the context for the current turn.
        final_user_prompt = f"Current game state for context:\n{game_state_json}\n\nIt's your turn to speak to {recipient_name}. What do you say?"
        anthropic_messages.append({"role": "user", "content": final_user_prompt})

        for attempt in range(max_retries + 1):
            try:
                print(f"ClaudeAgent ({self.player_name}) attempt {attempt + 1}: Sending chat request to API. Model: {self.model_name}")
                response = self.client.messages.create(
                    model=self.model_name,
                    max_tokens=1000, # Max tokens for chat
                    system=system_p,
                    messages=anthropic_messages
                )
                if not response.content or not isinstance(response.content, list) or not hasattr(response.content[0], 'text'):
                    raise ValueError("Invalid response structure from Claude API for chat.")

                chat_response_content = response.content[0].text
                if not chat_response_content.strip():
                    raise ValueError("Received empty chat response from API.")
                print(f"ClaudeAgent ({self.player_name}): Successfully received chat response.")
                return chat_response_content

            except (anthropic.APIError, ValueError, AttributeError, IndexError) as e:
                error_message = f"API/Validation Error in chat: {e.__class__.__name__}: {e}"
                print(f"ClaudeAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return f"Error after {max_retries + 1} attempts in chat. {error_message}. {default_fallback_message}"

            print(f"ClaudeAgent ({self.player_name}): Retrying chat in 1 second...")
            time.sleep(1)

        return default_fallback_message

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
