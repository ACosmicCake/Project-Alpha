from .base_agent import BaseAIAgent, GAME_RULES_SNIPPET
import os
import json
# import requests # Would be used in a real environment

class DeepSeekAgent(BaseAIAgent):
    def __init__(self, player_name: str, player_color: str, api_key: str = None, model_name: str = "deepseek-chat"): # Or specific model version
        super().__init__(player_name, player_color)
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            print(f"Warning: DeepSeekAgent for {player_name} initialized without an API key.")
        self.model_name = model_name
        self.api_base_url = "https://api.deepseek.com/v1" # Verify correct endpoint

        self.base_system_prompt = f"You are an exceptionally intelligent AI player in the game of Risk, known as {self.player_name}. You are playing with the {self.player_color} pieces. Your goal is world conquest. Think step-by-step and make bold, calculated moves."

    def _make_api_request(self, messages: list, stream: bool = False) -> dict | str :
        if not self.api_key:
            # This case is handled by the calling methods to return placeholder actions/chat
            raise ValueError("DeepSeek API key not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": stream # Stream might not be ideal for structured JSON, but API supports it
            # Add other parameters like temperature, max_tokens as needed
        }

        # In a real scenario:
        # response = requests.post(f"{self.api_base_url}/chat/completions", headers=headers, json=payload)
        # response.raise_for_status() # Raise an exception for HTTP errors
        # return response.json() # If not streaming
        # If streaming, response handling would be different.

        # Placeholder for when requests library is not available
        print(f"DeepSeekAgent ({self.player_name}) would make HTTP POST to {self.api_base_url}/chat/completions with payload: {json.dumps(payload, indent=2)[:500]}...")

        # Simulate a successful response structure for get_thought_and_action
        if not stream: # Assuming get_thought_and_action does not stream
            action_to_return = {"type": "END_ATTACK_PHASE"} # Default fallback
            # Try to find a valid action from the user prompt to make the placeholder more realistic
            # This is a bit of a hack since we don't have the valid_actions list here
            # The calling methods (get_thought_and_action, engage_in_private_chat) will provide better placeholders

            # For get_thought_and_action, it expects a JSON with 'thought' and 'action'
            simulated_llm_response_content = json.dumps({
                "thought": f"DeepSeekAgent ({self.player_name}) placeholder: Considering options...",
                "action": action_to_return # This will be overridden by the calling method's placeholder logic
            })
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": simulated_llm_response_content
                    }
                }]
            }
        else: # For engage_in_private_chat, if it were to stream (it doesn't in current design)
            return f"DeepSeek placeholder stream response part 1 for {self.player_name}"


    def get_thought_and_action(self, game_state_json: str, valid_actions: list, game_rules: str = GAME_RULES_SNIPPET, system_prompt_addition: str = "") -> dict:
        if not self.api_key:
            print(f"DeepSeekAgent ({self.player_name}): API key missing. Returning a default valid action.")
            action_to_return = valid_actions[0] if valid_actions else {"type": "END_TURN"}
            return {"thought": "No API key. Defaulting to first valid action or END_TURN.", "action": action_to_return}

        system_prompt = self._construct_system_prompt(self.base_system_prompt, game_rules, system_prompt_addition)
        user_prompt = self._construct_user_prompt_for_action(game_state_json, valid_actions)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            # response_data = self._make_api_request(messages) # Real call
            # # Parse response_data - structure depends on DeepSeek's API
            # # Example assumes a similar structure to OpenAI for choices[0].message.content
            # content_str = response_data["choices"][0]["message"]["content"]
            # action_data = json.loads(content_str)
            # return action_data

            # Placeholder logic since _make_api_request is stubbed:
            print(f"DeepSeekAgent ({self.player_name}) get_thought_and_action: Using placeholder response.")
            action_to_return = valid_actions[0] if valid_actions else {"type": "END_ATTACK_PHASE"}
            if any(action['type'] == 'END_ATTACK_PHASE' for action in valid_actions):
                action_to_return = {"type": "END_ATTACK_PHASE"}
            elif any(action['type'] == 'END_REINFORCE_PHASE' for action in valid_actions):
                action_to_return = {"type": "END_REINFORCE_PHASE"}
            elif any(action['type'] == 'END_TURN' for action in valid_actions):
                action_to_return = {"type": "END_TURN"}

            return {"thought": f"DeepSeekAgent ({self.player_name}) placeholder: Choosing first valid action or phase end.", "action": action_to_return}

        except Exception as e: # Catch requests.exceptions.RequestException, json.JSONDecodeError, KeyError etc.
            print(f"DeepSeekAgent ({self.player_name}) error during API call or processing: {e}")
            action_to_return = valid_actions[0] if valid_actions else {"type": "END_TURN"}
            return {"thought": f"Error processing LLM response: {e}", "action": action_to_return}


    def engage_in_private_chat(self, history: list[dict], game_state_json: str, game_rules: str = GAME_RULES_SNIPPET, recipient_name: str = "", system_prompt_addition: str = "") -> str:
        if not self.api_key:
            print(f"DeepSeekAgent ({self.player_name}): API key missing for chat. Returning default message.")
            return "Hello. (DeepSeek placeholder due to no API key)"

        system_prompt_chat = self._construct_system_prompt(
             f"{self.base_system_prompt} You are in a private dialogue with {recipient_name}.",
             game_rules,
             system_prompt_addition
        )

        messages = [{"role": "system", "content": system_prompt_chat}]
        for msg in history:
            role = "user" if msg["sender"] == recipient_name else "assistant"
            if msg["sender"] == self.player_name: role = "assistant"
            else: role = "user"
            messages.append({"role": role, "content": msg["message"]})

        # Add the final user message that prompts the LLM for its turn in the conversation.
        # This includes context like the game state.
        final_user_message_content = f"Current game state for your information:\n{game_state_json}\n\nIt's your turn to speak to {recipient_name}. What do you say?"
        messages.append({"role": "user", "content": final_user_message_content})

        try:
            # response_data = self._make_api_request(messages) # Real call
            # # Parse response_data - structure depends on DeepSeek's API
            # # Example assumes a similar structure to OpenAI for choices[0].message.content
            # chat_response = response_data["choices"][0]["message"]["content"]
            # return chat_response

            # Placeholder logic:
            print(f"DeepSeekAgent ({self.player_name}) engage_in_private_chat: Using placeholder response.")
            return f"Indeed, {recipient_name}. Your proposition is intriguing. (DeepSeek placeholder response)"

        except Exception as e: # Catch requests.exceptions.RequestException, KeyError etc.
            print(f"DeepSeekAgent ({self.player_name}) error during chat API call or processing: {e}")
            return f"My apologies, {recipient_name}, I encountered a momentary lapse in communication. (DeepSeek error placeholder)"


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
