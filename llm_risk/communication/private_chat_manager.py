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
                          game_rules: str,
                          initiator_goal: str = "Discuss strategy.", # Default goal
                          recipient_goal: str = "Respond to the proposal." # Default goal
                          ) -> tuple[list[dict], dict | None]:
        """
        Manages a private conversation between two agents, aiming for a potential diplomatic agreement.

        Args:
            agent1: The AI agent initiating the conversation.
            agent2: The AI agent receiving the initial message.
            initial_message: The first message from agent1 to agent2.
            game_state: The current GameState object (used to get game_state_json).
            game_rules: Game rules snippet to be passed to agents.
            initiator_goal: Specific goal for agent1 in this conversation.
            recipient_goal: Specific goal for agent2 in this conversation.

        Returns:
            A tuple containing:
                - The final conversation log (list of message dictionaries).
                - A potential diplomatic action (dict) if an agreement is reached, otherwise None.
        """
        if not isinstance(agent1, BaseAIAgent) or not isinstance(agent2, BaseAIAgent):
            print("Error: Both participants in private chat must be BaseAIAgent instances.")
            return ([{"error": "Invalid agent types provided."}], None)

        if agent1 == agent2:
            print(f"Warning: {agent1.player_name} is trying to chat with themselves. Aborting private chat.")
            return ([{"sender": agent1.player_name, "message": initial_message, "timestamp": datetime.utcnow().isoformat(), "note": "Self-chat attempt"}], None)

        conversation_history: list[dict] = []
        negotiated_action: dict | None = None
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

            # Determine the goal for the current speaker
            current_goal = ""
            if current_speaker == agent1: # Initiator or initiator's turn to reply
                # If it's agent1's very first turn to speak after initial message (which is impossible here as loop starts with agent2),
                # or any subsequent turn for agent1.
                current_goal = initiator_goal
            else: # agent2's turn (recipient)
                current_goal = recipient_goal

            system_prompt_addition = (
                f"You are {current_speaker.player_name}. You are in a private negotiation with {recipient_name_for_prompt}. "
                f"The conversation was initiated by {agent1.player_name} with the message: '{initial_message}'. "
                f"Your current goal is: {current_goal} "
                f"Your response should aim to achieve this goal. "
                f"If you wish to make a formal proposal (e.g., ALLIANCE, NON_AGGRESSION_PACT_3_TURNS, JOINT_ATTACK_PLAYER_C_NORTH_AMERICA), "
                f"end your message with the exact phrase: 'PROPOSAL: [details_of_proposal_type_and_terms]'. "
                f"Example: '...PROPOSAL: ALLIANCE'. "
                f"If you wish to accept a proposal made in the last message, end your message with: 'ACCEPT_PROPOSAL'. "
                f"If you wish to reject a proposal, end with: 'REJECT_PROPOSAL'."
            )

            try:
                response_message_full = current_speaker.engage_in_private_chat(
                    history=list(conversation_history), # Pass a copy
                    game_state_json=game_state_json,
                    game_rules=game_rules,
                    recipient_name=recipient_name_for_prompt, # The one they are talking TO
                    system_prompt_addition=system_prompt_addition
                )
            except Exception as e:
                print(f"Error during {current_speaker.player_name}'s turn in private chat: {e}")
                response_message_full = f"(Technical difficulties in responding to {recipient_name_for_prompt})"

            if not response_message_full or not response_message_full.strip():
                response_message_full = "(Says nothing)" # Handle empty responses

            response_message_content = response_message_full
            # Check for special negotiation keywords in the response
            # TODO: Make keyword parsing more robust (e.g., regex, specific JSON format from LLM)
            if "PROPOSAL:" in response_message_full:
                try:
                    # Attempt to parse the proposal part
                    proposal_text = response_message_full.split("PROPOSAL:", 1)[1].strip()
                    response_message_content = response_message_full.split("PROPOSAL:", 1)[0].strip() # Message part
                    # This is a placeholder. The actual parsing of proposal_text into a structured action
                    # needs to be more sophisticated or the LLM needs to return a structured proposal.
                    # For now, let's assume the proposal_text IS the action type if simple, or needs parsing.
                    # Example: "ALLIANCE" -> {'type': 'PROPOSE_ALLIANCE', 'target_player_name': recipient_name_for_prompt}
                    # Example: "JOINT_ATTACK_PLAYER_C_NORTH_AMERICA" -> needs parsing
                    if proposal_text == "ALLIANCE":
                        negotiated_action = {'type': 'PROPOSE_ALLIANCE', 'proposing_player_name': current_speaker.player_name, 'target_player_name': recipient_name_for_prompt}
                        print(f"[Private Chat Negotiation] {current_speaker.player_name} proposed ALLIANCE to {recipient_name_for_prompt}")
                        # Conversation might end here or continue for acceptance/rejection in next turn
                    # Add more proposal types here
                except IndexError:
                    print(f"[Private Chat] Error parsing PROPOSAL from {current_speaker.player_name}")
                    # Keep response_message_content as is, no formal proposal extracted
                    pass


            elif "ACCEPT_PROPOSAL" in response_message_full:
                response_message_content = response_message_full.split("ACCEPT_PROPOSAL", 1)[0].strip()
                # Check if the last message from other_speaker contained a proposal that can be accepted
                # This requires looking at conversation_history[-1] and its potential 'negotiated_action_pending'
                last_exchange = conversation_history[-1] if conversation_history else {}
                pending_proposal = last_exchange.get('pending_proposal_details')

                if pending_proposal and last_exchange.get('sender') == recipient_name_for_prompt: # Proposal was from the other party
                    # Form the acceptance action based on the pending proposal
                    if pending_proposal['type'] == 'PROPOSE_ALLIANCE' and pending_proposal['target_player_name'] == current_speaker.player_name:
                        negotiated_action = {
                            'type': 'ACCEPT_ALLIANCE',
                            'accepting_player_name': current_speaker.player_name,
                            'proposing_player_name': pending_proposal['proposing_player_name']
                        }
                        print(f"[Private Chat Negotiation] {current_speaker.player_name} ACCEPTED ALLIANCE from {pending_proposal['proposing_player_name']}")
                        # Conversation ends with an agreement
                        # Add to conversation history and break
                        timestamp = datetime.utcnow().isoformat()
                        conversation_history.append({
                            "sender": current_speaker.player_name,
                            "message": response_message_content,
                            "negotiation_outcome": "ACCEPT_PROPOSAL",
                            "agreed_action": negotiated_action,
                            "timestamp": timestamp
                        })
                        print(f"[Private Chat] {current_speaker.player_name} to {recipient_name_for_prompt}: {response_message_content} (ACCEPTS PROPOSAL)")
                        break # End conversation on acceptance
                    # Add more acceptance types here
                else:
                    print(f"[Private Chat Negotiation] {current_speaker.player_name} tried to ACCEPT_PROPOSAL, but no valid pending proposal found from {recipient_name_for_prompt}.")
                    # No formal action, just a message

            elif "REJECT_PROPOSAL" in response_message_full:
                response_message_content = response_message_full.split("REJECT_PROPOSAL", 1)[0].strip()
                # Similar logic to ACCEPT_PROPOSAL to see if a rejectable proposal was pending
                last_exchange = conversation_history[-1] if conversation_history else {}
                pending_proposal = last_exchange.get('pending_proposal_details')
                if pending_proposal and last_exchange.get('sender') == recipient_name_for_prompt:
                     print(f"[Private Chat Negotiation] {current_speaker.player_name} REJECTED proposal from {recipient_name_for_prompt}")
                     # Store rejection, conversation might continue or end
                     timestamp = datetime.utcnow().isoformat()
                     conversation_history.append({
                        "sender": current_speaker.player_name,
                        "message": response_message_content,
                        "negotiation_outcome": "REJECT_PROPOSAL",
                        "rejected_proposal_details": pending_proposal,
                        "timestamp": timestamp
                     })
                     print(f"[Private Chat] {current_speaker.player_name} to {recipient_name_for_prompt}: {response_message_content} (REJECTS PROPOSAL)")
                     # Optionally, break here if rejection means end of negotiation. For now, let it continue.
                else:
                    print(f"[Private Chat Negotiation] {current_speaker.player_name} tried to REJECT_PROPOSAL, but no specific proposal was pending from {recipient_name_for_prompt}.")


            timestamp = datetime.utcnow().isoformat()
            msg_entry = {
                "sender": current_speaker.player_name,
                "message": response_message_content,
                "timestamp": timestamp
            }
            if negotiated_action and msg_entry.get("negotiation_outcome") != "ACCEPT_PROPOSAL": # If proposal was made but not yet accepted
                msg_entry["pending_proposal_details"] = negotiated_action
            conversation_history.append(msg_entry)
            print(f"[Private Chat] {current_speaker.player_name} to {recipient_name_for_prompt}: {response_message_content}")


            # Swap speakers
            current_speaker, other_speaker = other_speaker, current_speaker

            # If an agreement was reached (e.g. ACCEPT_PROPOSAL already handled and broke), this loop won't continue for this turn.
            # If a PROPOSAL was made, the conversation continues for the other player to respond.

        # Store the conversation log (optional) in memory
        log_key = f"{agent1.player_name}_vs_{agent2.player_name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        self.conversation_logs[log_key] = list(conversation_history) # Store a copy

        # Log the entire conversation to a file
        if self.log_file:
            try:
                with open(self.log_file, 'a') as f:
                    f.write(f"# Conversation Start: {log_key} | Initiator Goal: {initiator_goal} | Recipient Goal: {recipient_goal}\n")
                    if negotiated_action:
                         f.write(f"# Final Negotiated Action: {json.dumps(negotiated_action)}\n")
                    for entry in conversation_history:
                        f.write(json.dumps(entry) + "\n")
                    f.write(f"# Conversation End: {log_key}\n\n")
            except IOError as e:
                print(f"Error writing to private chat log file {self.log_file}: {e}")

        print(f"[Private Chat] Conversation between {agent1.player_name} and {agent2.player_name} ended. Log key: {log_key}. Agreed action: {negotiated_action}")
        return conversation_history, negotiated_action

    def get_all_conversations(self) -> dict[str, list[dict]]:
        """Returns all stored private conversation logs."""
        return self.conversation_logs

    def get_conversation_log(self, conversation_key: str) -> list[dict] | None:
        """Returns the log for a specific conversation key."""
        return self.conversation_logs.get(conversation_key)

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
