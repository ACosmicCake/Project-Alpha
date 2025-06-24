from ..ai.base_agent import BaseAIAgent
from ..game_engine.data_structures import GameState
from datetime import datetime
import json
import os

LOG_DIR = "logs" # Defined in global_chat.py, ensure consistency or pass around

class PrivateChatManager:
    def __init__(self, max_exchanges_per_conversation: int = 3, log_file_name: str = "private_chats.jsonl"):
        """
        Manages private conversations between two AI agents.

        Args:
            max_exchanges_per_conversation: The maximum number of message exchanges (one message from each agent is one exchange)
                                            allowed in a single private conversation session.
        """
        self.max_exchanges = max_exchanges_per_conversation
        self.conversation_logs: dict[str, list[dict]] = {} # Stores logs, key could be "PlayerA_PlayerB_timestamp"
        self.log_file = None
        if log_file_name:
            if not os.path.exists(LOG_DIR):
                os.makedirs(LOG_DIR)
            self.log_file = os.path.join(LOG_DIR, log_file_name)


    def run_conversation(self,
                         agent1: BaseAIAgent,
                         agent2: BaseAIAgent,
                         initial_message: str,
                         game_state: GameState, # Pass the whole GameState object
                         game_rules: str) -> list[dict]:
        """
        Manages a private conversation between two agents.

        Args:
            agent1: The AI agent initiating the conversation.
            agent2: The AI agent receiving the initial message.
            initial_message: The first message from agent1 to agent2.
            game_state: The current GameState object (used to get game_state_json).
            game_rules: Game rules snippet to be passed to agents.

        Returns:
            The final conversation log (list of message dictionaries).
        """
        if not isinstance(agent1, BaseAIAgent) or not isinstance(agent2, BaseAIAgent):
            print("Error: Both participants in private chat must be BaseAIAgent instances.")
            return [{"error": "Invalid agent types provided."}]

        if agent1 == agent2:
            print(f"Warning: {agent1.player_name} is trying to chat with themselves. Aborting private chat.")
            return [{"sender": agent1.player_name, "message": initial_message, "timestamp": datetime.utcnow().isoformat(), "note": "Self-chat attempt"}]


        conversation_history: list[dict] = []
        timestamp = datetime.utcnow().isoformat()

        # Add initial message from agent1
        conversation_history.append({
            "sender": agent1.player_name,
            "message": initial_message,
            "timestamp": timestamp
        })
        print(f"[Private Chat] {agent1.player_name} to {agent2.player_name}: {initial_message}")

        current_speaker = agent2
        other_speaker = agent1
        game_state_json = game_state.to_json() # Serialize once

        for exchange_turn in range(self.max_exchanges * 2 -1): # Max (N*2 -1) messages after initial one
            # If current_speaker is agent2, recipient_name is agent1.player_name for the prompt
            # If current_speaker is agent1, recipient_name is agent2.player_name for the prompt
            recipient_name_for_prompt = other_speaker.player_name

            try:
                # System prompt addition can be used to give specific instructions for this chat turn if needed
                # e.g., "Try to negotiate a ceasefire."
                system_prompt_addition = f"You are {current_speaker.player_name}. You are in a private conversation with {recipient_name_for_prompt}. The conversation was initiated by {agent1.player_name}."
                if current_speaker == agent1: # agent1 is replying
                     system_prompt_addition = f"You are {current_speaker.player_name}. Continue your private conversation with {recipient_name_for_prompt}."


                response_message = current_speaker.engage_in_private_chat(
                    history=list(conversation_history), # Pass a copy
                    game_state_json=game_state_json,
                    game_rules=game_rules,
                    recipient_name=recipient_name_for_prompt, # The one they are talking TO
                    system_prompt_addition=system_prompt_addition
                )
            except Exception as e:
                print(f"Error during {current_speaker.player_name}'s turn in private chat: {e}")
                response_message = f"(Technical difficulties in responding to {recipient_name_for_prompt})"

            if not response_message or not response_message.strip():
                response_message = "(Says nothing)" # Handle empty responses

            timestamp = datetime.utcnow().isoformat()
            conversation_history.append({
                "sender": current_speaker.player_name,
                "message": response_message,
                "timestamp": timestamp
            })
            print(f"[Private Chat] {current_speaker.player_name} to {recipient_name_for_prompt}: {response_message}")

            # Swap speakers
            current_speaker, other_speaker = other_speaker, current_speaker

            # Check if it's the end of an exchange and if we've hit max_exchanges
            # An exchange completes after agent2 has replied to agent1's message.
            # Initial message (agent1) -> exchange 1 reply (agent2) -> exchange 1 reply (agent1) -> exchange 2 reply (agent2) ...
            # Number of messages = initial + (max_exchanges -1)*2 responses + 1 final response from agent2
            # Total messages = 1 (initial) + (exchanges_done * 2)
            # We iterate `self.max_exchanges * 2 - 1` times for replies after the initial message.
            # So, total messages will be `1 + (self.max_exchanges * 2 - 1)` if it goes full term, or `self.max_exchanges * 2`.
            # The loop runs for (max_exchanges * 2 - 1) iterations.
            # Example: max_exchanges = 3.
            # A1: msg1 (initial)
            # Loop iter 0: A2 replies to A1 (msg2)
            # Loop iter 1: A1 replies to A2 (msg3)
            # Loop iter 2: A2 replies to A1 (msg4)
            # Loop iter 3: A1 replies to A2 (msg5)
            # Loop iter 4: A2 replies to A1 (msg6)
            # Total messages: 1 (initial) + 5 (replies) = 6 messages = 3 exchanges.
            # The loop should run (max_exchanges * 2 - 1) times.

        # Store the conversation log (optional) in memory
        log_key = f"{agent1.player_name}_vs_{agent2.player_name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        self.conversation_logs[log_key] = list(conversation_history) # Store a copy

        # Log the entire conversation to a file
        if self.log_file:
            try:
                with open(self.log_file, 'a') as f:
                    # Log a header for the conversation for readability in the file
                    f.write(f"# Conversation Start: {log_key}\n")
                    for entry in conversation_history:
                        f.write(json.dumps(entry) + "\n")
                    f.write(f"# Conversation End: {log_key}\n\n")
            except IOError as e:
                print(f"Error writing to private chat log file {self.log_file}: {e}")

        print(f"[Private Chat] Conversation between {agent1.player_name} and {agent2.player_name} ended. Log key: {log_key}")
        return conversation_history

if __name__ == '__main__':
    # For testing, we need mock AI agents and a GameState
    from ..ai.base_agent import BaseAIAgent, GAME_RULES_SNIPPET # Adjusted import path for testing
    from ..game_engine.data_structures import GameState as MockGameState # Adjusted import path

    class MockAgent(BaseAIAgent):
        def __init__(self, player_name: str, player_color: str, responses: list[str]):
            super().__init__(player_name, player_color)
            self.responses = responses
            self.response_idx = 0

        def get_thought_and_action(self, game_state_json: str, valid_actions: list, game_rules: str = GAME_RULES_SNIPPET, system_prompt_addition: str = "") -> dict:
            return {"thought": "Thinking...", "action": {"type": "PASS"}}

        def engage_in_private_chat(self, history: list[dict], game_state_json: str, game_rules: str = GAME_RULES_SNIPPET, recipient_name: str = "", system_prompt_addition: str = "") -> str:
            response = f"Hello {recipient_name}, this is {self.player_name}. "
            if self.response_idx < len(self.responses):
                response += self.responses[self.response_idx]
                self.response_idx += 1
            else:
                response += "I have nothing more to say."
            # Simulate thinking based on history
            if history:
                response += f" (I see you last said: '{history[-1]['message']}')"
            return response

    # Setup
    agent_a_responses = ["How about an alliance?", "Okay, deal for 2 turns.", "Sounds good."]
    agent_b_responses = ["An alliance, you say? Interesting.", "What are the terms?", "Agreed."]

    agent_A = MockAgent("PlayerAlpha", "Red", agent_a_responses)
    agent_B = MockAgent("PlayerBeta", "Blue", agent_b_responses)

    mock_game_state = MockGameState() # Create a simple GameState
    # Add some dummy players to game_state if needed by to_json() or AI
    # from ..game_engine.data_structures import Player as MockPlayer
    # pA_ds = MockPlayer(agent_A.player_name, agent_A.player_color)
    # pB_ds = MockPlayer(agent_B.player_name, agent_B.player_color)
    # mock_game_state.players = [pA_ds, pB_ds]


    manager = PrivateChatManager(max_exchanges_per_conversation=2) # 2 exchanges = A1, B1, A2, B2 (4 messages total)

    print("--- Test Case 1: Normal Conversation (2 exchanges) ---")
    initial_msg = "Greetings PlayerBeta, I have a proposal."
    conversation1 = manager.run_conversation(agent_A, agent_B, initial_msg, mock_game_state, GAME_RULES_SNIPPET)

    print("\nFinal Conversation Log (Test Case 1):")
    for msg in conversation1:
        print(f"- ({msg['timestamp']}) {msg['sender']}: {msg['message']}")

    # Reset response indices for next test
    agent_A.response_idx = 0
    agent_B.response_idx = 0
    # agent_A.responses = ["Let's attack Gamma together!"] # Change responses for another test
    # agent_B.responses = ["Hmm, Gamma is strong. What's in it for me?"]

    print("\n--- Test Case 2: Agent runs out of unique things to say (max_exchanges = 1) ---")
    agent_A_short_resp = ["My only offer."]
    agent_B_short_resp = ["I see."]
    agent_A_short = MockAgent("PlayerShortA", "Green", agent_A_short_resp)
    agent_B_short = MockAgent("PlayerShortB", "Yellow", agent_B_short_resp)
    manager_short = PrivateChatManager(max_exchanges_per_conversation=1) # 1 exchange = A1, B1 (2 messages total)

    initial_msg_short = "Short proposal."
    conversation2 = manager_short.run_conversation(agent_A_short, agent_B_short, initial_msg_short, mock_game_state, GAME_RULES_SNIPPET)
    print("\nFinal Conversation Log (Test Case 2):")
    for msg in conversation2:
        print(f"- ({msg['timestamp']}) {msg['sender']}: {msg['message']}")

    print("\n--- Test Case 3: Self Chat ---")
    conversation3 = manager.run_conversation(agent_A, agent_A, "Talking to myself", mock_game_state, GAME_RULES_SNIPPET)
    print("\nFinal Conversation Log (Test Case 3):")
    for msg in conversation3:
        print(f"- ({msg['timestamp']}) {msg['sender']}: {msg['message']}")

    print("\nStored Conversation Logs in Manager:")
    for key, log_entries in manager.conversation_logs.items():
        print(f"Log Key: {key}")
        #for entry in log_entries:
        #    print(f"  - {entry['sender']}: {entry['message']}")
    if not manager.conversation_logs:
        print("No logs stored (as expected if only self-chat occurred or no successful multi-message chats).")

    # Note: The mock agents are very simple. Real LLM agents would have richer interactions.
    # The GAME_RULES_SNIPPET and game_state_json are passed to the agents.
    # The `system_prompt_addition` in `engage_in_private_chat` is used to give context.

    # Verify max_exchanges behavior
    # max_exchanges = 1 means: A1 (initial), B1 (reply). Total 2 messages.
    # max_exchanges = 2 means: A1 (initial), B1 (reply), A1 (reply), B1 (reply). Total 4 messages.
    # The loop runs `max_exchanges * 2 - 1` times.
    # Initial message is sent before loop.
    # Exchange 1:
    #   - Agent2 replies (1st loop iteration, current_speaker=agent2)
    # Exchange 2 (if max_exchanges >= 2):
    #   - Agent1 replies (2nd loop iteration, current_speaker=agent1)
    #   - Agent2 replies (3rd loop iteration, current_speaker=agent2)
    # ... and so on.
    # Number of replies in loop = (max_exchanges * 2) - 1.
    # Total messages = 1 (initial) + (max_exchanges * 2 - 1) = max_exchanges * 2.
    # Test case 1: max_exchanges = 2. Expected messages = 4.
    # Initial: PlayerAlpha
    # Reply 1: PlayerBeta (Loop 0)
    # Reply 2: PlayerAlpha (Loop 1)
    # Reply 3: PlayerBeta (Loop 2) -> Loop runs for (2*2-1) = 3 iterations. Correct.
    assert len(conversation1) == 4, f"Test Case 1 Expected 4 messages, got {len(conversation1)}"

    # Test case 2: max_exchanges = 1. Expected messages = 2.
    # Initial: PlayerShortA
    # Reply 1: PlayerShortB (Loop 0) -> Loop runs for (1*2-1) = 1 iteration. Correct.
    assert len(conversation2) == 2, f"Test Case 2 Expected 2 messages, got {len(conversation2)}"
