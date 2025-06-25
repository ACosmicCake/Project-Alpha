from .base_agent import BaseAIAgent, GAME_RULES_SNIPPET
import os
import json
from google import genai # Would be used in a real environment
import time
from pydantic import BaseModel

# Define the Pydantic model for the expected response structure
class AgentResponse(BaseModel):
    thought: str
    action: dict

class GeminiAgent(BaseAIAgent):
    def __init__(self, player_name: str, player_color: str, api_key: str = None, model_name: str = "gemini-2.5-flash"): # Using flash for speed
        super().__init__(player_name, player_color)
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            print(f"Warning: GeminiAgent for {player_name} initialized without an API key. Live calls will fail.")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)
            # System instructions can be passed to GenerativeModel for some models/versions
            # Or included directly in the prompt. For action generation, explicit JSON instruction is key.
           
        self.model_name = model_name
        # Base system prompt will be part of the full prompt sent to generate_content
        self.base_system_prompt = f"You are a strategic AI player in the game of Risk, named {self.player_name} ({self.player_color}). Your goal is to win. You must respond with a valid JSON object containing 'thought' and 'action' keys, according to the provided schema."
        # self.generation_config_json is no longer needed here as schema will be passed directly
        self.generation_config_text = genai.types.GenerationConfig(
            response_mime_type="text/plain"
        )


    def _get_default_action(self, valid_actions: list) -> dict:
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

        if not self.client:
            print(f"GeminiAgent ({self.player_name}): Client not initialized (API key likely missing).")
            return {"thought": "No client available. Defaulting to a safe action.", "action": default_fallback_action}

        if not valid_actions:
            print(f"GeminiAgent ({self.player_name}): No valid actions provided.")
            return {"thought": "No valid actions were provided to choose from.", "action": {"type": "END_TURN"}}

        # Construct the full prompt including system instructions, game rules, state, and valid actions.
        # Gemini's `system_instruction` in `GenerativeModel` is one way, but for complex prompts,
        # including it as part of the user's turn content is often more reliable, especially for JSON.
        system_part = self._construct_system_prompt(self.base_system_prompt, game_rules, system_prompt_addition)
        user_part = self._construct_user_prompt_for_action(game_state_json, valid_actions)

        # Gemini prefers a list of Parts or strings. We'll combine system and user for a single prompt.
        # Ensure the instruction for JSON is very clear.
        full_prompt = f"{system_part}\n\n{user_part}\n\nYou MUST provide your response as a single, valid JSON object with exactly two keys: 'thought' (your detailed reasoning) and 'action' (selected from the valid actions list)."

        for attempt in range(max_retries + 1):
            try:
                print(f"GeminiAgent ({self.player_name}) attempt {attempt + 1}: Sending request to API. Model: {self.model_name}")
                response = self.client.models.generate_content(
                    model= self.model_name,
                    contents= full_prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": AgentResponse,
                    }
                )

                # Parse the response using the Pydantic model
                # The API should return a JSON string that pydantic can parse if response_schema is honored.
                # If the model directly returns the parsed object (depends on SDK version/behavior):
                # parsed_response = response.candidates[0].content.parts[0].data # or similar, needs checking
                # For now, assume response.text is the JSON string as per example, then parse if needed
                # Or directly use response.parse() if available and does what we want

                # The example shows `response.parse()`, let's use that.
                # If `response.parse()` is not available or doesn't work as expected with `response_schema`,
                # we might need to fall back to `AgentResponse.model_validate_json(response.text)`.
                try:
                    parsed_response: AgentResponse = response.parse()
                except AttributeError: # If .parse() is not a method of response
                    print(f"GeminiAgent ({self.player_name}): response.parse() not available, trying AgentResponse.model_validate_json(response.text)")
                    parsed_response = AgentResponse.model_validate_json(response.text)
                except Exception as e_parse: # Catch other potential parsing issues
                    print(f"GeminiAgent ({self.player_name}): Error during response.parse() or model_validate_json: {e_parse}. Response text: {response.text if hasattr(response, 'text') else 'N/A'}")
                    raise # Re-raise to be caught by the outer try-except

                # Pydantic model validation handles the presence of 'thought' and 'action' keys.
                action_to_validate = parsed_response.action
                action_type_and_params = {k: v for k, v in action_to_validate.items()}
                is_valid = any(action_type_and_params == {k:v for k,v in va.items()} for va in valid_actions)

                if not is_valid:
                    is_type_valid = any(action_to_validate["type"] == va["type"] for va in valid_actions)
                    if is_type_valid:
                        print(f"GeminiAgent ({self.player_name}): Action {action_to_validate['type']} is a valid type, but params mismatch: {action_to_validate}. Valid: {valid_actions}. Falling back.")
                        raise ValueError(f"Action {action_to_validate} params mismatch or not found in valid_actions list.")
                    else:
                        raise ValueError(f"Action type {action_to_validate['type']} not found in valid_actions list.")

                print(f"GeminiAgent ({self.player_name}): Successfully received and validated action: {parsed_response.action}")
                # Return the dictionary structure expected by the game engine
                return {"thought": parsed_response.thought, "action": parsed_response.action}

            # Removed json.JSONDecodeError as Pydantic handles JSON validation.
            # ValueError can still be raised by Pydantic or our custom checks. # Fixed: The line below originally caused error
            except (AttributeError, IndexError, ValueError) as e:
                # Added IncompleteIterationError for cases where the model stops but schema isn't met
                error_message = f"API/Validation Error: {e.__class__.__name__}: {e}"
                # Check if response text is available for logging
                response_text_for_log = "No response text available"
                if 'response' in locals() and hasattr(response, 'text'):
                    response_text_for_log = response.text
                elif 'response' in locals() and hasattr(response, 'candidates') and response.candidates:
                    try:
                        response_text_for_log = str(response.candidates[0].content.parts)
                    except:
                        pass # Keep default if extraction fails

                print(f"GeminiAgent ({self.player_name}): {error_message}. Response content/text (if available): '{response_text_for_log}'")
                if 'response' in locals() and hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                     print(f"GeminiAgent ({self.player_name}): Prompt blocked, reason: {response.prompt_feedback.block_reason}")
                if attempt >= max_retries:
                    return {"thought": f"Error after {max_retries + 1} attempts. {error_message}", "action": default_fallback_action}
            except Exception as e: # Catch any other unexpected errors
                error_message = f"Unexpected Error: {e.__class__.__name__}: {e}"
                print(f"GeminiAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return {"thought": f"Error after {max_retries + 1} attempts. {error_message}", "action": default_fallback_action}

            print(f"GeminiAgent ({self.player_name}): Retrying in 1 second...")
            time.sleep(1)

        return {"thought": "Reached end of get_thought_and_action unexpectedly after retries.", "action": default_fallback_action}

    def engage_in_private_chat(self, history: list[dict], game_state_json: str, game_rules: str = GAME_RULES_SNIPPET, recipient_name: str = "", system_prompt_addition: str = "", max_retries: int = 1) -> str:
        default_fallback_message = f"My apologies, {recipient_name}, I am currently unable to formulate a response. (Gemini fallback)"
        if not self.client:
            print(f"GeminiAgent ({self.player_name}): Client not initialized for chat.")
            return default_fallback_message

        # Construct chat prompt for Gemini. It's usually a sequence of user/model turns.
        # The system prompt can be part of the initial message or set on the model.
        # We'll build a single prompt string for simplicity here.

        # System prompt for chat (does not ask for JSON here)
        chat_system_prompt = self._construct_system_prompt(
             f"You are {self.player_name} ({self.player_color}), a strategic AI player in Risk. You are now in a private chat with {recipient_name}.",
             game_rules, # Game rules snippet for context
             system_prompt_addition
        )

        # Build the chat history into a string format Gemini can understand
        chat_history_str = ""
        for msg in history:
            speaker = "You" if msg["sender"] == self.player_name else msg["sender"]
            chat_history_str += f"{speaker}: {msg['message']}\n"

        # The final part of the prompt is your turn to speak, including game state context
        full_chat_prompt = (
            f"{chat_system_prompt}\n\n"
            f"Current game state for your reference:\n{game_state_json}\n\n"
            f"Conversation History with {recipient_name}:\n{chat_history_str}\n"
            f"It is now your turn, {self.player_name}. What do you say to {recipient_name}?"
        )

        for attempt in range(max_retries + 1):
            try:
                print(f"GeminiAgent ({self.player_name}) attempt {attempt + 1}: Sending chat request to API. Model: {self.model_name}")
                response = self.client.generate_content(
                    full_chat_prompt,
                    generation_config=self.generation_config_text # Expecting plain text for chat
                )

                chat_response_content = response.text
                if not chat_response_content.strip():
                    # Check for blocking if content is empty
                    if response.prompt_feedback.block_reason:
                        raise genai.types.BlockedPromptException(f"Prompt blocked for chat, reason: {response.prompt_feedback.block_reason}")
                    raise ValueError("Received empty chat response from API.")

                print(f"GeminiAgent ({self.player_name}): Successfully received chat response.")
                return chat_response_content

            except (genai.types.BlockedPromptException, genai.types.generation_types.StopCandidateException, ValueError) as e:
                error_message = f"API/Validation Error in chat: {e.__class__.__name__}: {e}"
                print(f"GeminiAgent ({self.player_name}): {error_message}")
                if 'response' in locals() and hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                     print(f"GeminiAgent ({self.player_name}): Chat prompt blocked, reason: {response.prompt_feedback.block_reason}")
                if attempt >= max_retries:
                    return f"Error after {max_retries + 1} attempts in chat. {error_message}. {default_fallback_message}"
            except Exception as e: # Catch any other unexpected errors
                error_message = f"Unexpected Error in chat: {e.__class__.__name__}: {e}"
                print(f"GeminiAgent ({self.player_name}): {error_message}")
                if attempt >= max_retries:
                    return f"Error after {max_retries + 1} attempts in chat. {error_message}. {default_fallback_message}"

            print(f"GeminiAgent ({self.player_name}): Retrying chat in 1 second...")
            time.sleep(1)

        return default_fallback_message

if __name__ == '__main__':
    # from dotenv import load_dotenv
    # load_dotenv() # Make sure .env is in the root of the project if you run this directly
    agent = GeminiAgent(player_name="GeminiBot", player_color="Blue")
    dummy_game_state = {"territories": {"Brazil": {"owner": "GeminiBot", "army_count": 5}}, "current_player": "GeminiBot"}
    dummy_valid_actions = [{"type": "DEPLOY", "territory": "Brazil", "armies": 3}, {"type": "END_REINFORCE_PHASE"}]

    if agent.api_key:
        print("GeminiAgent: API calls would be made here if client was live.")
        # result = agent.get_thought_and_action(json.dumps(dummy_game_state), dummy_valid_actions)
        # print("Action result (placeholder):", result)
        # chat_history = [{"sender": "OtherPlayer", "message": "Care for an alliance?"}]
        # chat_response = agent.engage_in_private_chat(chat_history, json.dumps(dummy_game_state), recipient_name="OtherPlayer")
        # print("Chat response (placeholder):", chat_response)
    else:
        print("GeminiAgent: GOOGLE_API_KEY not found. Skipping live call examples.")
        result = agent.get_thought_and_action(json.dumps(dummy_game_state), dummy_valid_actions)
        print("Action result (placeholder):", result)
        chat_history = [{"sender": "OtherPlayer", "message": "Care for an alliance?"}]
        chat_response = agent.engage_in_private_chat(chat_history, json.dumps(dummy_game_state), recipient_name="OtherPlayer")
        print("Chat response (placeholder):", chat_response)
