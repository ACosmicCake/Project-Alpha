from .game_engine.engine import GameEngine
from .game_engine.data_structures import Player as GamePlayer # To avoid confusion with AI Player concepts
from .ai.base_agent import BaseAIAgent, GAME_RULES_SNIPPET
from .communication.global_chat import GlobalChat
from .communication.private_chat_manager import PrivateChatManager
from .ui.gui import GameGUI # Import for GUI updates later

# Import specific AI agents - for now, we might use placeholders or a factory
from .ai.gemini_agent import GeminiAgent
from .ai.openai_agent import OpenAIAgent
from .ai.claude_agent import ClaudeAgent
from .ai.deepseek_agent import DeepSeekAgent
import threading # For asynchronous AI calls

import json # For loading player configs if any
import time # For potential delays
from datetime import datetime # For logging timestamp
import os # For log directory creation

class GameOrchestrator:
    def __init__(self,
                 map_file: str = "map_config.json",
                 player_configs_override: list | None = None,
                 default_player_setup_file: str = "player_config.json"):
        self.engine = GameEngine(map_file_path=map_file)
        self.global_chat = GlobalChat()
        self.private_chat_manager = PrivateChatManager(max_exchanges_per_conversation=3)

        self.gui = None
        self.setup_gui()

        self.ai_agents: dict[str, BaseAIAgent] = {}
        self.player_map: dict[GamePlayer, BaseAIAgent] = {}

        # Attributes for asynchronous AI calls - INITIALIZE THEM HERE
        self.ai_is_thinking: bool = False
        self.current_ai_thread: threading.Thread | None = None
        self.ai_action_result: dict | None = None
        self.active_ai_player_name: str | None = None
        self.current_ai_context: dict | None = None
        self.has_logged_ai_is_thinking_for_current_action: bool = False
        self.has_logged_current_turn_player_phase: bool = False

        # Load player configurations: either from override or from file
        self._load_player_setup(player_configs_override, default_player_setup_file)

        # Ensure players list is populated before initializing the board
        if not self.engine.game_state.players:
            print("Critical Error: No players were loaded or configured. Cannot initialize board.")
            # Potentially raise an error here or handle more gracefully
            # For now, if _load_player_setup failed to populate, this will be an issue.
            # The _load_player_setup should ideally raise an error if it ends with no players.
            raise ValueError("Player setup resulted in no players.")


        players_data_for_engine = [{"name": p.name, "color": p.color} for p in self.engine.game_state.players]
        self.engine.initialize_board(players_data=players_data_for_engine)

        self._map_game_players_to_ai_agents()

        self.game_rules = GAME_RULES_SNIPPET
        self.turn_action_log = []
        self.max_turns = 200 # Default, could be configurable
        self.game_running_via_gui = False

    def _ai_thread_target(self, agent: BaseAIAgent, game_state_json: str, valid_actions: list, game_rules: str, system_prompt_addition: str):
        """Target function for the AI thinking thread."""
        try:
            self.ai_action_result = agent.get_thought_and_action(
                game_state_json, valid_actions, game_rules, system_prompt_addition
            )
            # It's important to also capture whose thought this was, if applicable for logging/display
            # self.active_ai_player_name is already set before thread start
        except Exception as e:
            print(f"Error in AI thread for {agent.player_name}: {e}")
            self.ai_action_result = {"error": str(e), "thought": f"Error during API call: {e}", "action": None} # Ensure a dict is returned

    def _execute_ai_turn_async(self, agent: BaseAIAgent, game_state_json: str, valid_actions: list, game_rules: str, system_prompt_addition: str):
        """Initiates the AI call in a separate thread."""
        if self.ai_is_thinking:
            print(f"Warning: _execute_ai_turn_async called while AI for {self.active_ai_player_name} is already thinking. Ignoring.")
            return

        self.has_logged_ai_is_thinking_for_current_action = False # Reset logging flag for the new AI action
        self.active_ai_player_name = agent.player_name # Store who is thinking
        self.ai_action_result = None  # Clear previous result
        self.ai_is_thinking = True

        # For simplicity, storing args directly; can be more structured if needed
        self.current_ai_context = {
            "agent": agent,
            "game_state_json": game_state_json,
            "valid_actions": valid_actions,
            "game_rules": game_rules,
            "system_prompt_addition": system_prompt_addition
        }

        self.current_ai_thread = threading.Thread(
            target=self._ai_thread_target,
            args=(agent, game_state_json, valid_actions, game_rules, system_prompt_addition)
        )
        self.current_ai_thread.daemon = True # Allow main program to exit even if threads are running
        self.current_ai_thread.start()
        print(f"Orchestrator: Started AI thinking thread for {agent.player_name}.")
        if self.gui: # Update GUI to show AI is thinking
             self._update_gui_full_state()


    def _load_player_setup(self, player_configs_override: list | None, default_player_setup_file: str):
        final_player_configs = []
        if player_configs_override is not None and isinstance(player_configs_override, list) and player_configs_override:
            print(f"Using player configurations provided by override (e.g., console input). Count: {len(player_configs_override)}")
            final_player_configs = player_configs_override
        else:
            print(f"No valid player override. Attempting to load from default setup file: '{default_player_setup_file}'")
            try:
                with open(default_player_setup_file, 'r') as f:
                    final_player_configs = json.load(f)
                print(f"Successfully loaded player configurations from '{default_player_setup_file}'. Count: {len(final_player_configs)}")
            except FileNotFoundError:
                print(f"Warning: Default player setup file '{default_player_setup_file}' not found. Using hardcoded default AI setup.")
                final_player_configs = [
                    {"name": "PlayerA (Gemini)", "color": "Red", "ai_type": "Gemini"},
                    {"name": "PlayerB (OpenAI)", "color": "Blue", "ai_type": "OpenAI"}
                ] # Simplified default for when file is missing
                # Optionally, try to write this default back to default_player_setup_file
                try:
                    with open(default_player_setup_file, 'w') as f:
                        json.dump(final_player_configs, f, indent=2)
                    print(f"Created default player setup file '{default_player_setup_file}' with 2 players.")
                except IOError:
                    print(f"Could not write default player setup file '{default_player_setup_file}'.")
            except json.JSONDecodeError:
                print(f"Error: Could not decode JSON from '{default_player_setup_file}'. Using hardcoded default.")
                final_player_configs = [ # Fallback if JSON is corrupt
                    {"name": "PlayerX (Gemini)", "color": "Red", "ai_type": "Gemini"},
                    {"name": "PlayerY (OpenAI)", "color": "Blue", "ai_type": "OpenAI"}
                ]


        if not final_player_configs: # Should not happen if defaults are set, but as a safeguard
            print("Critical: No player configurations loaded or defined. Cannot proceed.")
            raise ValueError("Player configurations are empty.")

        # Clear existing players before loading new ones, if any (e.g. re-init)
        self.engine.game_state.players.clear()
        self.ai_agents.clear()

        for config in final_player_configs:
            player_name = config.get("name")
            if not player_name:
                print(f"Warning: Player config missing 'name': {config}. Skipping.")
                continue
            player_color = config.get("color")
            if not player_color:
                print(f"Warning: Player config for '{player_name}' missing 'color': {config}. Assigning default or skipping.")
                # Potentially assign a default color or skip this player
                continue # For now, skip if color is missing

            ai_type = config.get("ai_type", "Gemini") # Default to Gemini if not specified

            # Check for duplicate player names before adding
            if any(p.name == player_name for p in self.engine.game_state.players):
                print(f"Warning: Duplicate player name '{player_name}' found. Skipping this configuration.")
                continue

            game_player_obj = GamePlayer(name=player_name, color=player_color)
            self.engine.game_state.players.append(game_player_obj)

            agent: BaseAIAgent | None = None
            if ai_type == "Gemini": agent = GeminiAgent(player_name, player_color)
            elif ai_type == "OpenAI": agent = OpenAIAgent(player_name, player_color)
            elif ai_type == "Claude": agent = ClaudeAgent(player_name, player_color)
            elif ai_type == "DeepSeek": agent = DeepSeekAgent(player_name, player_color)
            # Add "Human" type here if you have a HumanAgent class
            # elif ai_type == "Human": agent = HumanAgent(player_name, player_color)
            else:
                print(f"Warning: Unknown AI type '{ai_type}' for player {player_name}. Defaulting to Gemini.")
                agent = GeminiAgent(player_name, player_color) # Fallback

            if agent:
                self.ai_agents[player_name] = agent
            else: # Should not happen with current logic unless agent creation fails for other reasons
                print(f"Critical: Could not create agent for {player_name} with type {ai_type}.")


        if len(self.engine.game_state.players) < 2 :
            # This check is important. If after all loading, we don't have enough players.
            print(f"Error: At least two players are required to start the game. Loaded {len(self.engine.game_state.players)} players.")
            # Consider what to do here - raise error, or try to add default players again?
            # For now, raising an error is probably best to indicate a setup problem.
            raise ValueError(f"Insufficient players configured. Need at least 2, got {len(self.engine.game_state.players)}.")

        print(f"Player setup complete. Loaded {len(self.engine.game_state.players)} players.")

    def _map_game_players_to_ai_agents(self):
        self.player_map.clear()
        if not self.engine.game_state.players:
            print("Warning: No players in game_state to map to AI agents.")
            return

        for gp in self.engine.game_state.players:
            if gp.name in self.ai_agents:
                self.player_map[gp] = self.ai_agents[gp.name]
            else:
                # This indicates a mismatch between players defined in game_state and AI agents created.
                # This should ideally not happen if _load_player_setup and subsequent logic is correct.
                print(f"Critical Error: GamePlayer {gp.name} from engine does not have a corresponding AI agent. AI Agents: {list(self.ai_agents.keys())}")
                # Potentially raise an error or try to create a default agent for robustness,
                # but this points to a deeper setup issue.
                # For now, just print error. The game might fail later if an agent is None.
                # raise ValueError(f"Mismatch: GamePlayer {gp.name} has no AI agent.")

    def get_agent_for_current_player(self) -> BaseAIAgent | None:
        current_game_player = self.engine.game_state.get_current_player()
        if current_game_player and current_game_player in self.player_map:
            return self.player_map[current_game_player]
        elif current_game_player:
            print(f"Error: No AI agent mapped for current GamePlayer: {current_game_player.name}")
        else:
            print("Error: No current player in game state.")
        return None

    def _update_gui_full_state(self):
        """Helper to call GUI update with all necessary data."""
        if self.gui:
            self.gui.update(
                game_state=self.engine.game_state,
                global_chat_log=self.global_chat.get_log(),
                private_chat_conversations=self.private_chat_manager.get_all_conversations()
            )

    def run_game(self):
        if not self.player_map:
            print("Critical: Player map not initialized. Attempting to map now.")
            self._map_game_players_to_ai_agents()
            if not self.player_map:
                print("Failed to initialize player_map. Exiting.")
                return
        print("Starting LLM Risk Game!")
        if self.gui:
            self._update_gui_full_state()
            self.game_running_via_gui = True
            self.gui.run()
            if not self.engine.is_game_over() and self.engine.game_state.current_turn_number < self.max_turns :
                 print("\n--- GAME EXITED VIA GUI ---")
                 self.log_turn_info("Game exited via GUI.")
        else:
            self.game_running_via_gui = False
            running = True
            while running:
                running = self.advance_game_turn()
        print("GameOrchestrator.run_game() finished.")

    def advance_game_turn(self) -> bool:
        if self.engine.is_game_over():
            winner = self.engine.is_game_over()
            win_msg = f"\n--- GAME OVER! Winner is {winner.name}! ---"
            print(win_msg)
            self.log_turn_info(win_msg)
            self.global_chat.broadcast("GameSystem", win_msg)
            if self.gui and self.game_running_via_gui: self.gui.show_game_over_screen(winner.name)
            return False
        if self.engine.game_state.current_turn_number >= self.max_turns:
            timeout_msg = f"\n--- GAME OVER! Reached maximum turns ({self.max_turns}). No winner declared by conquest. ---"
            print(timeout_msg)
            self.log_turn_info(timeout_msg)
            self.global_chat.broadcast("GameSystem", timeout_msg)
            if self.gui and self.game_running_via_gui: self.gui.show_game_over_screen("Draw/Timeout")
            return False

        self.turn_action_log.clear()
        current_player_obj = self.engine.game_state.get_current_player()
        if not current_player_obj:
            print("Error: No current player. Ending game logic.")
            return False
        current_player_agent = self.get_agent_for_current_player()
        if not current_player_agent:
            print(f"Error: No AI agent for {current_player_obj.name}. Skipping turn.")
            self.engine.next_turn() # Advance to next player if current has no agent
            if self.gui: self._update_gui_full_state()
            return True # Game continues

        if not self.has_logged_current_turn_player_phase:
            print(f"\n--- Turn {self.engine.game_state.current_turn_number} | Player: {current_player_obj.name} ({current_player_obj.color}) | Phase: {self.engine.game_state.current_game_phase} ---")
            self.has_logged_current_turn_player_phase = True
            # Also log to file/action log only once per new header
            if not self.ai_is_thinking: # Avoid double logging if AI just started thinking this exact moment
                self.log_turn_info(f"Turn {self.engine.game_state.current_turn_number} starting for {current_player_obj.name}.")

        if not self.ai_is_thinking and self.gui: # Ensure GUI is updated if it's not an AI thinking loop
            self._update_gui_full_state() # Update GUI at start of player's turn segment, if not already done by AI start

        # Check if AI is currently thinking
        if self.ai_is_thinking:
            if self.current_ai_thread and self.current_ai_thread.is_alive():
                if not self.has_logged_ai_is_thinking_for_current_action:
                    print(f"Orchestrator: AI ({self.active_ai_player_name}) is still thinking. GUI should be responsive.")
                    self.has_logged_ai_is_thinking_for_current_action = True
                if self.gui: self.gui.update(self.engine.game_state, self.global_chat.get_log(), self.private_chat_manager.get_all_conversations()) # Keep GUI fresh
                return True # AI is busy, game loop continues, UI remains responsive
            else:
                # AI thread has finished
                print(f"Orchestrator: AI ({self.active_ai_player_name}) thread finished.")
                self.ai_is_thinking = False
                self.has_logged_ai_is_thinking_for_current_action = False # Reset for next potential AI action or next AI player
                action_to_process = self.ai_action_result
                # self.ai_action_result = None # Clear it after fetching - or clear before next AI turn

                # Process the action based on the phase stored in current_ai_context or game_state
                # This is where the second half of the refactored phase handlers will be called.
                # For now, placeholder for processing:
                if action_to_process:
                    print(f"Orchestrator: Processing AI action: {action_to_process.get('action')}")
                    self.log_ai_thought(self.active_ai_player_name or "UnknownAI", action_to_process.get('thought', 'N/A'))

                    # Placeholder: This logic will be moved into _process_..._ai_action methods in Step 3
                    # For now, just simulate moving to next phase or turn if action implies end of phase.
                    # This is a very simplified simulation of action processing.
                    processed_action_type = action_to_process.get("action", {}).get("type", "")
                    if self.engine.game_state.current_game_phase == "REINFORCE":
                        # Simulate that the action was processed, and if it was END_REINFORCE_PHASE, engine handles it.
                        # For now, assume _process_reinforce_ai_action would handle advancing phase.
                        # If not end of phase, it would loop within reinforce or prepare for next AI call in reinforce.
                        # This part needs careful integration with Step 3.
                        # For this step, we assume the action is processed and we might be ready for next phase.
                        # The engine's phase might change here by the _process_ method.
                        self._process_reinforce_ai_action(current_player_obj, current_player_agent, action_to_process)

                    elif self.engine.game_state.current_game_phase == "ATTACK":
                        self._process_attack_ai_action(current_player_obj, current_player_agent, action_to_process)

                    elif self.engine.game_state.current_game_phase == "FORTIFY":
                         self._process_fortify_ai_action(current_player_obj, current_player_agent, action_to_process)

                else:
                    print(f"Orchestrator: AI ({self.active_ai_player_name}) action result was None. Problem in thread.")
                    # Decide how to handle this - skip part of turn? End turn?
                    # For now, let's assume it might lead to ending the current phase logic.
                    if self.engine.game_state.current_game_phase == "REINFORCE": self.engine.game_state.current_game_phase = "ATTACK" # Force next
                    elif self.engine.game_state.current_game_phase == "ATTACK": self.engine.game_state.current_game_phase = "FORTIFY"
                    elif self.engine.game_state.current_game_phase == "FORTIFY": self.engine.next_turn()


                self.active_ai_player_name = None # Clear active AI
                self.current_ai_context = None
                self._update_gui_full_state() # Update GUI after processing
                if self.engine.is_game_over(): return self.advance_game_turn() # Recurse to handle game over
                # Fall through to potentially start next phase or next turn if current phase ended by AI action

        # If AI is NOT thinking, then we can initiate AI action for the current phase
        # This will also be refactored in Step 3.
        # The actual calls to _execute_ai_turn_async will be inside _initiate_..._ai_action methods.

        if not self.ai_is_thinking: # Re-check, as processing above might have finished a phase
            if self.engine.game_state.current_game_phase == "REINFORCE":
                # Original: self.handle_reinforce_phase(current_player_obj, current_player_agent)
                self._initiate_reinforce_ai_action(current_player_obj, current_player_agent) # This will set ai_is_thinking
                if self.gui: self._update_gui_full_state()
                if self.engine.is_game_over(): return self.advance_game_turn() # Recurse to handle game over
                if self.ai_is_thinking: return True # AI started, GUI loop continues

            if not self.engine.is_game_over() and self.engine.game_state.current_game_phase == "ATTACK":
                # Original: self.handle_attack_communicate_phase(current_player_obj, current_player_agent)
                self._initiate_attack_ai_action(current_player_obj, current_player_agent)
                if self.gui: self._update_gui_full_state()
                if self.engine.is_game_over(): return self.advance_game_turn()
                if self.ai_is_thinking: return True

            if not self.engine.is_game_over() and self.engine.game_state.current_game_phase == "FORTIFY":
                # Original: self.handle_fortify_phase(current_player_obj, current_player_agent)
                self._initiate_fortify_ai_action(current_player_obj, current_player_agent)
                if self.gui: self._update_gui_full_state()
                if self.engine.is_game_over(): return self.advance_game_turn()
                if self.ai_is_thinking: return True

            # If no AI action was initiated (e.g., phase completed without AI, or human player)
            # and we are here, it means we need to move to the next turn or phase.
            # This will be more cleanly handled when phase handlers are fully refactored.
            # For now, if we fall through all phases and AI is not thinking, advance turn.
            if not self.ai_is_thinking:
                 if self.engine.game_state.current_game_phase == "FORTIFY": # Typically, fortify phase ends the turn.
                    self.engine.next_turn()
                    self.has_logged_current_turn_player_phase = False # Reset for new player/turn
                    print(f"--- End of Turn for {current_player_obj.name}. Next player: {self.engine.game_state.get_current_player().name if self.engine.game_state.get_current_player() else 'N/A'} ---")
                    self._update_gui_full_state()
                 # If not FORTIFY, it implies phases might have auto-advanced or there's a logic gap for this step.
                 # The refactor in Step 3 should make phase transitions explicit after action processing.


        if self.engine.is_game_over(): return False # Final check before returning from advance_game_turn

        return True # Game continues

    def handle_reinforce_phase(self, player: GamePlayer, agent: BaseAIAgent):
        # This method will be split into _initiate_reinforce_ai_action and _process_reinforce_ai_action
        # For now, keeping a simplified version of the original logic for placeholder
        print(f"DEBUG: handle_reinforce_phase called for {player.name} - TO BE REFACTORED")
        if not self.ai_is_thinking:
            self._initiate_reinforce_ai_action(player, agent)
        # Processing will happen when ai_is_thinking is false again after thread completion.

    def _initiate_reinforce_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        print(f"Orchestrator: Initiating REINFORCE AI action for {player.name}")
        # Simplified: Assume one AI call per phase for now for this step's purpose.
        # Real logic will loop within reinforce phase.
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player)
        if not valid_actions:
            self.log_turn_info(f"No valid REINFORCE actions for {player.name}. Auto-ending phase part.");
            # This might mean auto-distribute or move to attack. Engine should handle.
            # For now, just ensure we don't call AI.
            if player.armies_to_deploy > 0: self.auto_distribute_armies(player, player.armies_to_deploy)
            self.engine.game_state.current_game_phase = "ATTACK" # Manually advance for now
            return

        current_reinforcements = player.armies_to_deploy
        current_cards = len(player.hand)
        prompt_details = [f"You have {current_reinforcements} armies to deploy.", f"You currently hold {current_cards} cards."]
        if any(a['type'] == 'TRADE_CARDS' and a.get('must_trade') for a in valid_actions):
            prompt_details.append("You MUST trade cards.")
        system_prompt_addition = "It is your REINFORCE phase. " + " ".join(prompt_details)

        self._execute_ai_turn_async(agent, game_state_json, valid_actions, self.game_rules, system_prompt_addition)

    def _process_reinforce_ai_action(self, player: GamePlayer, agent: BaseAIAgent, ai_response: dict):
        print(f"Orchestrator: Processing REINFORCE AI action for {player.name}")
        action = ai_response.get("action")
        # This is where the original logic from handle_reinforce_phase that processes the action would go.
        # For brevity in this step, I'll just log and simulate phase end.
        # The full logic will be moved in Step 3.
        if not action or "type" not in action:
            self.log_turn_info(f"{player.name} provided malformed REINFORCE action: {action}. Auto-ending phase part.")
            if player.armies_to_deploy > 0: self.auto_distribute_armies(player, player.armies_to_deploy)
            self.engine.game_state.current_game_phase = "ATTACK" # Manually advance
            return

        action_type = action["type"]
        # Simplified processing for now:
        self.log_turn_info(f"{player.name} REINFORCE action: {action_type}")
        if action_type == "END_REINFORCE_PHASE":
            if any(a['type'] == 'TRADE_CARDS' and a.get('must_trade') for a in self.engine.get_valid_actions(player)): # Re-check valid actions
                 self.log_turn_info(f"{player.name} tried END_REINFORCE_PHASE during must_trade. Action ignored for now."); # AI will try again
                 # In a full loop, we'd re-initiate AI call for reinforce. For now, this means AI is not thinking.
                 self.ai_is_thinking = False # Allow re-triggering AI for reinforce
                 return # Stay in reinforce, AI will be called again by advance_game_turn
            if player.armies_to_deploy > 0: self.auto_distribute_armies(player, player.armies_to_deploy)
            player.armies_to_deploy = 0
            self.engine.game_state.current_game_phase = "ATTACK"
        elif action_type == "TRADE_CARDS":
            # Simulate trade, actual logic in engine
            self.log_turn_info(f"{player.name} trades cards (simulated). Reinforcements updated by engine.")
            # In reality, engine.perform_card_trade would be called.
            # After trading, player likely still needs to deploy, so stay in REINFORCE.
            # The AI would need to be called again for deploy/end_reinforce.
            self.ai_is_thinking = False # Allow re-triggering AI for reinforce
        elif action_type == "DEPLOY":
            # Simulate deploy
            self.log_turn_info(f"{player.name} deploys (simulated). Armies updated by engine.")
            # Player might still have armies or need to end phase.
            self.ai_is_thinking = False # Allow re-triggering AI for reinforce
        else: # Unknown action for reinforce
            self.log_turn_info(f"{player.name} unknown REINFORCE action: {action}. Trying again next cycle.")
            self.ai_is_thinking = False # Allow re-triggering

        if self.gui: self._update_gui_full_state()


    def _initiate_attack_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        print(f"Orchestrator: Initiating ATTACK AI action for {player.name}")
        # Placeholder for actual logic to gather state and call _execute_ai_turn_async
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player)
        if not valid_actions or all(a['type'] == "END_ATTACK_PHASE" for a in valid_actions if len(valid_actions) ==1):
            self.log_turn_info(f"No valid ATTACK actions for {player.name} or only END_ATTACK_PHASE. Moving to FORTIFY.");
            self.engine.game_state.current_game_phase = "FORTIFY"
            return
        system_prompt_addition = "It is your ATTACK phase."
        self._execute_ai_turn_async(agent, game_state_json, valid_actions, self.game_rules, system_prompt_addition)

    def _process_attack_ai_action(self, player: GamePlayer, agent: BaseAIAgent, ai_response: dict):
        print(f"Orchestrator: Processing ATTACK AI action for {player.name}")
        action = ai_response.get("action")
        # Placeholder - full logic in Step 3
        if not action or "type" not in action:
            self.log_turn_info(f"{player.name} malformed ATTACK action. Ending phase.")
            self.engine.game_state.current_game_phase = "FORTIFY" # Manually advance
            return

        action_type = action.get("type", "")
        self.log_turn_info(f"{player.name} ATTACK action: {action_type}")

        if self.engine.game_state.requires_post_attack_fortify:
            # If PAF is required, the AI's action should have been PAF.
            # The main loop in advance_game_turn should handle initiating PAF if needed.
            # This spot is for *after* a PAF action or a regular attack action.
            if action_type == "POST_ATTACK_FORTIFY":
                # Simulate PAF processing
                self.log_turn_info(f"{player.name} processes POST_ATTACK_FORTIFY (simulated).")
                self.engine.game_state.requires_post_attack_fortify = False # Assume engine clears this
                self.ai_is_thinking = False # Ready for next attack/end attack
            # else: AI might have chosen another action while PAF was pending - handle as per game rules.
            # For now, assume if PAF was pending, it was handled.
        elif action_type == "ATTACK":
            # Simulate attack
            self.log_turn_info(f"{player.name} attacks (simulated).")
            # Check if PAF is now required by engine after this simulated attack
            # self.engine.game_state.requires_post_attack_fortify = True # Example
            self.ai_is_thinking = False # Ready for next attack / PAF / end attack
        elif action_type == "END_ATTACK_PHASE":
            self.engine.game_state.current_game_phase = "FORTIFY"
        elif action_type in ["GLOBAL_CHAT", "PRIVATE_CHAT"]:
            self.log_turn_info(f"{player.name} chats (simulated). Attack phase continues.")
            self.ai_is_thinking = False # Ready for next attack action
        else: # Unknown
            self.log_turn_info(f"{player.name} unknown ATTACK action. Ending phase.")
            self.engine.game_state.current_game_phase = "FORTIFY"

        if self.gui: self._update_gui_full_state()


    def _initiate_fortify_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        print(f"Orchestrator: Initiating FORTIFY AI action for {player.name}")
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player)
        if not valid_actions: # Should at least have END_TURN
             self.log_turn_info(f"No valid FORTIFY actions for {player.name}. Ending turn.");
             self.engine.next_turn() # End turn
             return
        system_prompt_addition = "It is your FORTIFY phase."
        self._execute_ai_turn_async(agent, game_state_json, valid_actions, self.game_rules, system_prompt_addition)

    def _process_fortify_ai_action(self, player: GamePlayer, agent: BaseAIAgent, ai_response: dict):
        print(f"Orchestrator: Processing FORTIFY AI action for {player.name}")
        action = ai_response.get("action")
        # Placeholder - full logic in Step 3
        if not action or "type" not in action:
            self.log_turn_info(f"{player.name} malformed FORTIFY action. Ending turn.")
        else:
            action_type = action.get("type", "")
            self.log_turn_info(f"{player.name} FORTIFY action: {action_type} (simulated).")

        # Fortify phase always ends the turn after one action (fortify or end_turn)
        # self.engine.next_turn() # This will be called by advance_game_turn after this processing returns
        # No need to set ai_is_thinking = False here, as next_turn will cycle to new player or end game.
        # The check at the start of advance_game_turn will handle this.
        # However, for clarity, if this phase is done, we are no longer waiting for this AI.
        # The main loop will call next_turn().
        if self.gui: self._update_gui_full_state()


    def handle_reinforce_phase(self, player: GamePlayer, agent: BaseAIAgent):
        # This method will be split into _initiate_reinforce_ai_action and _process_reinforce_ai_action
        # For now, keeping a simplified version of the original logic for placeholder
        print(f"DEBUG: handle_reinforce_phase called for {player.name} - TO BE REFACTORED")
        if not self.ai_is_thinking:
            self._initiate_reinforce_ai_action(player, agent)
        # Processing will happen when ai_is_thinking is false again after thread completion.

    def _initiate_reinforce_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        print(f"Orchestrator: Initiating REINFORCE AI action for {player.name}")
        # Simplified: Assume one AI call per phase for now for this step's purpose.
        # Real logic will loop within reinforce phase.
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player)
        if not valid_actions:
            self.log_turn_info(f"No valid REINFORCE actions for {player.name}. Auto-ending phase part.");
            # This might mean auto-distribute or move to attack. Engine should handle.
            # For now, just ensure we don't call AI.
            if player.armies_to_deploy > 0: self.auto_distribute_armies(player, player.armies_to_deploy)
            self.engine.game_state.current_game_phase = "ATTACK" # Manually advance for now
            return

        current_reinforcements = player.armies_to_deploy
        current_cards = len(player.hand)
        prompt_details = [f"You have {current_reinforcements} armies to deploy.", f"You currently hold {current_cards} cards."]
        if any(a['type'] == 'TRADE_CARDS' and a.get('must_trade') for a in valid_actions):
            prompt_details.append("You MUST trade cards.")
        system_prompt_addition = "It is your REINFORCE phase. " + " ".join(prompt_details)

        self._execute_ai_turn_async(agent, game_state_json, valid_actions, self.game_rules, system_prompt_addition)

    def _process_reinforce_ai_action(self, player: GamePlayer, agent: BaseAIAgent, ai_response: dict):
        print(f"Orchestrator: Processing REINFORCE AI action for {player.name}")
        action = ai_response.get("action")
        # This is where the original logic from handle_reinforce_phase that processes the action would go.
        # For brevity in this step, I'll just log and simulate phase end.
        # The full logic will be moved in Step 3.
        if not action or "type" not in action:
            self.log_turn_info(f"{player.name} provided malformed REINFORCE action: {action}. Auto-ending phase part.")
            if player.armies_to_deploy > 0: self.auto_distribute_armies(player, player.armies_to_deploy)
            self.engine.game_state.current_game_phase = "ATTACK" # Manually advance
            return

        action_type = action["type"]
        # Simplified processing for now:
        self.log_turn_info(f"{player.name} REINFORCE action: {action_type}")
        if action_type == "END_REINFORCE_PHASE":
            if any(a['type'] == 'TRADE_CARDS' and a.get('must_trade') for a in self.engine.get_valid_actions(player)): # Re-check valid actions
                 self.log_turn_info(f"{player.name} tried END_REINFORCE_PHASE during must_trade. Action ignored for now."); # AI will try again
                 # In a full loop, we'd re-initiate AI call for reinforce. For now, this means AI is not thinking.
                 self.ai_is_thinking = False # Allow re-triggering AI for reinforce
                 return # Stay in reinforce, AI will be called again by advance_game_turn
            if player.armies_to_deploy > 0: self.auto_distribute_armies(player, player.armies_to_deploy)
            player.armies_to_deploy = 0
            self.engine.game_state.current_game_phase = "ATTACK"
        elif action_type == "TRADE_CARDS":
            # Simulate trade, actual logic in engine
            self.log_turn_info(f"{player.name} trades cards (simulated). Reinforcements updated by engine.")
            # In reality, engine.perform_card_trade would be called.
            # After trading, player likely still needs to deploy, so stay in REINFORCE.
            # The AI would need to be called again for deploy/end_reinforce.
            self.ai_is_thinking = False # Allow re-triggering AI for reinforce
        elif action_type == "DEPLOY":
            # Simulate deploy
            self.log_turn_info(f"{player.name} deploys (simulated). Armies updated by engine.")
            # Player might still have armies or need to end phase.
            self.ai_is_thinking = False # Allow re-triggering AI for reinforce
        else: # Unknown action for reinforce
            self.log_turn_info(f"{player.name} unknown REINFORCE action: {action}. Trying again next cycle.")
            self.ai_is_thinking = False # Allow re-triggering

        if self.gui: self._update_gui_full_state()


    def _initiate_attack_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        print(f"Orchestrator: Initiating ATTACK AI action for {player.name}")
        # Placeholder for actual logic to gather state and call _execute_ai_turn_async
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player)
        if not valid_actions or all(a['type'] == "END_ATTACK_PHASE" for a in valid_actions if len(valid_actions) ==1):
            self.log_turn_info(f"No valid ATTACK actions for {player.name} or only END_ATTACK_PHASE. Moving to FORTIFY.");
            self.engine.game_state.current_game_phase = "FORTIFY"
            return

        # Handle pending Post-Attack Fortification (PAF) first, synchronously if needed, or ensure AI handles it.
        # For async, the PAF itself needs to be an AI decision if not automatic.
        if self.engine.game_state.requires_post_attack_fortify:
            self.log_turn_info(f"{player.name} must complete POST_ATTACK_FORTIFY.")
            paf_actions = [va for va in valid_actions if va['type'] == "POST_ATTACK_FORTIFY"]
            if not paf_actions: # Should not happen if flag is true
                self.log_turn_info(f"ERROR: PAF required but no PAF action for {player.name}. Clearing flag.");
                self.engine.game_state.requires_post_attack_fortify = False; self.engine.game_state.conquest_context = None
            else: # Found PAF action, let AI decide
                paf_detail = paf_actions[0]
                paf_prompt = (f"You conquered {paf_detail['to_territory']}. Move {paf_detail['min_armies']}-{paf_detail['max_armies']} armies "
                              f"from {paf_detail['from_territory']} (has {self.engine.game_state.territories[paf_detail['from_territory']].army_count}) "
                              f"to {paf_detail['to_territory']}.")
                self._execute_ai_turn_async(agent, game_state_json, paf_actions, self.game_rules, paf_prompt)
                return # AI is now thinking about PAF

        # If no PAF pending, proceed with regular attack/chat/end phase options
        system_prompt_addition = "It is your ATTACK phase."
        self._execute_ai_turn_async(agent, game_state_json, valid_actions, self.game_rules, system_prompt_addition)

    def _process_attack_ai_action(self, player: GamePlayer, agent: BaseAIAgent, ai_response: dict):
        print(f"Orchestrator: Processing ATTACK AI action for {player.name}")
        action = ai_response.get("action")

        if not action or "type" not in action:
            self.log_turn_info(f"{player.name} malformed ATTACK action. Ending phase.")
            self.engine.game_state.current_game_phase = "FORTIFY" # Manually advance
            self.ai_is_thinking = False # Reset thinking state
            return

        action_type = action.get("type", "")
        self.log_turn_info(f"{player.name} ATTACK action: {action_type}")

        if action_type == "POST_ATTACK_FORTIFY":
            num_to_move = action.get("num_armies", self.engine.game_state.conquest_context.get('min_movable') if self.engine.game_state.conquest_context else 1)
            fortify_log = self.engine.perform_post_attack_fortify(player, num_to_move)
            self.log_turn_info(f"{player.name} PAF: {fortify_log.get('message', 'Unknown PAF outcome')}")
            # PAF is done, AI might attack again or end phase.
            self.ai_is_thinking = False # Ready for next attack/end attack
        elif action_type == "ATTACK":
            from_t, to_t, num_a = action.get("from"), action.get("to"), action.get("num_armies")
            attack_log = self.engine.perform_attack(from_t, to_t, num_a) # Engine handles details
            self.log_turn_info(f"Battle: {attack_log.get('summary', 'Error in battle')}")
            if "error" not in attack_log:
                if attack_log.get("conquered"):
                    self.log_turn_info(f"{player.name} conquered {to_t}.")
                    if attack_log.get("eliminated_player"):
                         elim_name = attack_log.get("eliminated_player")
                         self.log_turn_info(f"{player.name} ELIMINATED {elim_name}!")
                         self.global_chat.broadcast("GameSystem", f"{player.name} eliminated {elim_name}!")
                         self.handle_player_elimination(elim_name)
                # If conquered, engine.game_state.requires_post_attack_fortify will be true.
                # The next call to _initiate_attack_ai_action will handle PAF.
            self.ai_is_thinking = False # Ready for next attack / PAF / end attack
        elif action_type == "END_ATTACK_PHASE":
            self.engine.game_state.current_game_phase = "FORTIFY"
            self.ai_is_thinking = False # Phase ended
        elif action_type in ["GLOBAL_CHAT", "PRIVATE_CHAT"]:
            # Simulate chat processing for now
            if action_type == "GLOBAL_CHAT": self.global_chat.broadcast(player.name, action.get("message",""))
            else: self.log_turn_info(f"{player.name} starts private chat (simulated).")
            self.log_turn_info(f"{player.name} chats. Attack phase continues.")
            self.ai_is_thinking = False # Ready for next attack action
        else:
            self.log_turn_info(f"{player.name} unknown ATTACK action: {action_type}. Ending phase.")
            self.engine.game_state.current_game_phase = "FORTIFY"
            self.ai_is_thinking = False # Phase ended due to unknown action

        if self.gui: self._update_gui_full_state()


    def _initiate_fortify_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        print(f"Orchestrator: Initiating FORTIFY AI action for {player.name}")
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player)
        if not valid_actions:
             self.log_turn_info(f"No valid FORTIFY actions for {player.name}. Ending turn.");
             # self.engine.next_turn() # Let advance_game_turn handle this transition
             return
        system_prompt_addition = "It is your FORTIFY phase. Make one move or end your turn."
        self._execute_ai_turn_async(agent, game_state_json, valid_actions, self.game_rules, system_prompt_addition)

    def _process_fortify_ai_action(self, player: GamePlayer, agent: BaseAIAgent, ai_response: dict):
        print(f"Orchestrator: Processing FORTIFY AI action for {player.name}")
        action = ai_response.get("action")
        action_processed_successfully = False

        if not action or not isinstance(action, dict) or "type" not in action:
            self.log_turn_info(f"{player.name} malformed/missing FORTIFY action: {action}. Ending turn.")
        else:
            action_type = action.get("type", "")
            self.log_turn_info(f"{player.name} FORTIFY phase, AI action: {action_type} - {action}")

            if action_type == "FORTIFY":
                if player.has_fortified_this_turn:
                    self.log_turn_info(f"{player.name} tried to FORTIFY again (should be prevented by valid_actions). Action ignored.")
                    # This state should ideally not be reached if valid_actions is correct.
                else:
                    from_t_name = action.get("from")
                    to_t_name = action.get("to")
                    num_a = action.get("num_armies")

                    if from_t_name and to_t_name and isinstance(num_a, int):
                        if num_a > 0: # Fortifying with 0 armies is not a move.
                            fortify_result = self.engine.perform_fortify(from_t_name, to_t_name, num_a)
                            self.log_turn_info(f"{player.name} FORTIFY {from_t_name}->{to_t_name} ({num_a}): {fortify_result.get('message')}")
                            action_processed_successfully = fortify_result.get("success", False)
                        else:
                            self.log_turn_info(f"{player.name} tried to FORTIFY with {num_a} armies. Action ignored. Fortification requires >0 armies.")
                            # No actual fortify action taken, player can still choose to end turn or try valid fortify if that was a mistake.
                            # However, current flow processes one action then ends turn.
                    else:
                        self.log_turn_info(f"{player.name} provided incomplete FORTIFY action: from='{from_t_name}', to='{to_t_name}', num_armies='{num_a}'. Action ignored.")
            elif action_type == "END_TURN":
                self.log_turn_info(f"{player.name} chose to END_TURN.")
                action_processed_successfully = True # Ending turn is a successful processing of an action.
            else: # Unknown action
                self.log_turn_info(f"{player.name} unknown action in FORTIFY phase: {action_type}. Ending turn.")

        # Fortify phase is always followed by next_turn() if not game over.
        self.ai_is_thinking = False
        if self.gui: self._update_gui_full_state()


    # Removed original handle_reinforce_phase, handle_attack_communicate_phase, handle_fortify_phase
    # as their logic is now split into _initiate_ and _process_ methods, driven by advance_game_turn.

    def auto_distribute_armies(self, player: GamePlayer, armies_to_distribute: int):
        # For now, keeping a simplified version of the original logic for placeholder
        print(f"DEBUG: handle_reinforce_phase called for {player.name} - TO BE REFACTORED")
        if not self.ai_is_thinking:
            self._initiate_reinforce_ai_action(player, agent)
        # Processing will happen when ai_is_thinking is false again after thread completion.

    def _initiate_reinforce_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        print(f"Orchestrator: Initiating REINFORCE AI action for {player.name}")
        # Simplified: Assume one AI call per phase for now for this step's purpose.
        # Real logic will loop within reinforce phase.
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player)
        if not valid_actions:
            self.log_turn_info(f"No valid REINFORCE actions for {player.name}. Auto-ending phase part.");
            # This might mean auto-distribute or move to attack. Engine should handle.
            # For now, just ensure we don't call AI.
            if player.armies_to_deploy > 0: self.auto_distribute_armies(player, player.armies_to_deploy)
            self.engine.game_state.current_game_phase = "ATTACK" # Manually advance for now
            return

        current_reinforcements = player.armies_to_deploy
        current_cards = len(player.hand)
        prompt_details = [f"You have {current_reinforcements} armies to deploy.", f"You currently hold {current_cards} cards."]
        if any(a['type'] == 'TRADE_CARDS' and a.get('must_trade') for a in valid_actions):
            prompt_details.append("You MUST trade cards.")
        system_prompt_addition = "It is your REINFORCE phase. " + " ".join(prompt_details)

        self._execute_ai_turn_async(agent, game_state_json, valid_actions, self.game_rules, system_prompt_addition)

    def _process_reinforce_ai_action(self, player: GamePlayer, agent: BaseAIAgent, ai_response: dict):
        print(f"Orchestrator: Processing REINFORCE AI action for {player.name}")
        action = ai_response.get("action")
        # This is where the original logic from handle_reinforce_phase that processes the action would go.
        # For brevity in this step, I'll just log and simulate phase end.
        # The full logic will be moved in Step 3.
        if not action or "type" not in action:
            self.log_turn_info(f"{player.name} provided malformed REINFORCE action: {action}. Auto-ending phase part.")
            if player.armies_to_deploy > 0: self.auto_distribute_armies(player, player.armies_to_deploy)
            self.engine.game_state.current_game_phase = "ATTACK" # Manually advance
            return

        action_type = action["type"]
        # Simplified processing for now:
        self.log_turn_info(f"{player.name} REINFORCE action: {action_type}")
        if action_type == "END_REINFORCE_PHASE":
            if any(a['type'] == 'TRADE_CARDS' and a.get('must_trade') for a in self.engine.get_valid_actions(player)): # Re-check valid actions
                 self.log_turn_info(f"{player.name} tried END_REINFORCE_PHASE during must_trade. Action ignored for now."); # AI will try again
                 # In a full loop, we'd re-initiate AI call for reinforce. For now, this means AI is not thinking.
                 self.ai_is_thinking = False # Allow re-triggering AI for reinforce
                 return # Stay in reinforce, AI will be called again by advance_game_turn
            if player.armies_to_deploy > 0: self.auto_distribute_armies(player, player.armies_to_deploy)
            player.armies_to_deploy = 0
            self.engine.game_state.current_game_phase = "ATTACK"
        elif action_type == "TRADE_CARDS":
            # Simulate trade, actual logic in engine
            self.log_turn_info(f"{player.name} trades cards (simulated). Reinforcements updated by engine.")
            # In reality, engine.perform_card_trade would be called.
            # After trading, player likely still needs to deploy, so stay in REINFORCE.
            # The AI would need to be called again for deploy/end_reinforce.
            self.ai_is_thinking = False # Allow re-triggering AI for reinforce
        elif action_type == "DEPLOY":
            # Simulate deploy
            self.log_turn_info(f"{player.name} deploys (simulated). Armies updated by engine.")
            # Player might still have armies or need to end phase.
            self.ai_is_thinking = False # Allow re-triggering AI for reinforce
        else: # Unknown action for reinforce
            self.log_turn_info(f"{player.name} unknown REINFORCE action: {action}. Trying again next cycle.")
            self.ai_is_thinking = False # Allow re-triggering

        if self.gui: self._update_gui_full_state()


    def _initiate_attack_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        print(f"Orchestrator: Initiating ATTACK AI action for {player.name}")
        # Placeholder for actual logic to gather state and call _execute_ai_turn_async
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player)
        if not valid_actions or all(a['type'] == "END_ATTACK_PHASE" for a in valid_actions if len(valid_actions) ==1):
            self.log_turn_info(f"No valid ATTACK actions for {player.name} or only END_ATTACK_PHASE. Moving to FORTIFY.");
            self.engine.game_state.current_game_phase = "FORTIFY"
            return

        # Handle pending Post-Attack Fortification (PAF) first, synchronously if needed, or ensure AI handles it.
        # For async, the PAF itself needs to be an AI decision if not automatic.
        if self.engine.game_state.requires_post_attack_fortify:
            self.log_turn_info(f"{player.name} must complete POST_ATTACK_FORTIFY.")
            paf_actions = [va for va in valid_actions if va['type'] == "POST_ATTACK_FORTIFY"]
            if not paf_actions: # Should not happen if flag is true
                self.log_turn_info(f"ERROR: PAF required but no PAF action for {player.name}. Clearing flag.");
                self.engine.game_state.requires_post_attack_fortify = False; self.engine.game_state.conquest_context = None
            else: # Found PAF action, let AI decide
                paf_detail = paf_actions[0]
                paf_prompt = (f"You conquered {paf_detail['to_territory']}. Move {paf_detail['min_armies']}-{paf_detail['max_armies']} armies "
                              f"from {paf_detail['from_territory']} (has {self.engine.game_state.territories[paf_detail['from_territory']].army_count}) "
                              f"to {paf_detail['to_territory']}.")
                self._execute_ai_turn_async(agent, game_state_json, paf_actions, self.game_rules, paf_prompt)
                return # AI is now thinking about PAF

        # If no PAF pending, proceed with regular attack/chat/end phase options
        system_prompt_addition = "It is your ATTACK phase."
        self._execute_ai_turn_async(agent, game_state_json, valid_actions, self.game_rules, system_prompt_addition)

    def _process_attack_ai_action(self, player: GamePlayer, agent: BaseAIAgent, ai_response: dict):
        print(f"Orchestrator: Processing ATTACK AI action for {player.name}")
        action = ai_response.get("action")

        if not action or "type" not in action:
            self.log_turn_info(f"{player.name} malformed ATTACK action. Ending phase.")
            self.engine.game_state.current_game_phase = "FORTIFY" # Manually advance
            self.ai_is_thinking = False # Reset thinking state
            return

        action_type = action.get("type", "")
        self.log_turn_info(f"{player.name} ATTACK action: {action_type}")

        if action_type == "POST_ATTACK_FORTIFY":
            num_to_move = action.get("num_armies", self.engine.game_state.conquest_context.get('min_movable') if self.engine.game_state.conquest_context else 1)
            fortify_log = self.engine.perform_post_attack_fortify(player, num_to_move)
            self.log_turn_info(f"{player.name} PAF: {fortify_log.get('message', 'Unknown PAF outcome')}")
            # PAF is done, AI might attack again or end phase.
            self.ai_is_thinking = False # Ready for next attack/end attack
        elif action_type == "ATTACK":
            from_t, to_t, num_a = action.get("from"), action.get("to"), action.get("num_armies")
            attack_log = self.engine.perform_attack(from_t, to_t, num_a) # Engine handles details
            self.log_turn_info(f"Battle: {attack_log.get('summary', 'Error in battle')}")
            if "error" not in attack_log:
                if attack_log.get("conquered"):
                    self.log_turn_info(f"{player.name} conquered {to_t}.")
                    if attack_log.get("eliminated_player"):
                         elim_name = attack_log.get("eliminated_player")
                         self.log_turn_info(f"{player.name} ELIMINATED {elim_name}!")
                         self.global_chat.broadcast("GameSystem", f"{player.name} eliminated {elim_name}!")
                         self.handle_player_elimination(elim_name)
                # If conquered, engine.game_state.requires_post_attack_fortify will be true.
                # The next call to _initiate_attack_ai_action will handle PAF.
            self.ai_is_thinking = False # Ready for next attack / PAF / end attack
        elif action_type == "END_ATTACK_PHASE":
            self.engine.game_state.current_game_phase = "FORTIFY"
            self.ai_is_thinking = False # Phase ended
        elif action_type in ["GLOBAL_CHAT", "PRIVATE_CHAT"]:
            # Simulate chat processing for now
            if action_type == "GLOBAL_CHAT": self.global_chat.broadcast(player.name, action.get("message",""))
            else: self.log_turn_info(f"{player.name} starts private chat (simulated).")
            self.log_turn_info(f"{player.name} chats. Attack phase continues.")
            self.ai_is_thinking = False # Ready for next attack action
        else:
            self.log_turn_info(f"{player.name} unknown ATTACK action: {action_type}. Ending phase.")
            self.engine.game_state.current_game_phase = "FORTIFY"
            self.ai_is_thinking = False # Phase ended due to unknown action

        if self.gui: self._update_gui_full_state()


    def _initiate_fortify_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        print(f"Orchestrator: Initiating FORTIFY AI action for {player.name}")
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player)
        if not valid_actions:
             self.log_turn_info(f"No valid FORTIFY actions for {player.name}. Ending turn.");
             # self.engine.next_turn() # Let advance_game_turn handle this transition
             return
        system_prompt_addition = "It is your FORTIFY phase. Make one move or end your turn."
        self._execute_ai_turn_async(agent, game_state_json, valid_actions, self.game_rules, system_prompt_addition)

    def _process_fortify_ai_action(self, player: GamePlayer, agent: BaseAIAgent, ai_response: dict):
        print(f"Orchestrator: Processing FORTIFY AI action for {player.name}")
        action = ai_response.get("action")

        if not action or "type" not in action:
            self.log_turn_info(f"{player.name} malformed FORTIFY action. Ending turn.")
        else:
            action_type = action.get("type", "")
            self.log_turn_info(f"{player.name} FORTIFY action: {action_type} (simulated).")
            if action_type == "FORTIFY":
                # Simulate actual fortify call to engine
                self.engine.perform_fortify(action.get("from"), action.get("to"), action.get("num_armies"))
            # Else, if END_TURN, engine will handle it via next_turn() call in advance_game_turn

        # Fortify phase is always followed by next_turn() if not game over.
        # No need to set self.ai_is_thinking = False here, as the turn will end for this player.
        # The main advance_game_turn loop will call self.engine.next_turn().
        if self.gui: self._update_gui_full_state()

    # Note: Original handle_reinforce_phase, handle_attack_communicate_phase,
    # and handle_fortify_phase methods are now effectively replaced by the combination of
    # advance_game_turn's logic and the _initiate_... and _process_... methods.
    # They can be removed or kept as stubs if desired, but their direct calls from advance_game_turn are gone.

    def _initiate_reinforce_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        """Gathers info and starts the AI thinking for the REINFORCE phase."""
        print(f"Orchestrator: Initiating REINFORCE AI action for {player.name}")
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player)

        if not valid_actions:
            self.log_turn_info(f"No valid REINFORCE actions for {player.name}. Auto-distributing if needed and moving to ATTACK.")
            if player.armies_to_deploy > 0:
                self.auto_distribute_armies(player, player.armies_to_deploy)
            self.engine.game_state.current_game_phase = "ATTACK"
            self.has_logged_current_turn_player_phase = False # Phase changed
            self.ai_is_thinking = False # Ensure not stuck in thinking
            if self.gui: self._update_gui_full_state()
            return

        current_reinforcements = player.armies_to_deploy
        current_cards = len(player.hand)
        prompt_details = [f"You have {current_reinforcements} armies to deploy.", f"You currently hold {current_cards} cards."]
        if any(a['type'] == 'TRADE_CARDS' and a.get('must_trade') for a in valid_actions):
            prompt_details.append("You MUST trade cards as you have 5 or more and a valid set is available.")
        elif any(a['type'] == 'TRADE_CARDS' for a in valid_actions):
            prompt_details.append("You may optionally trade cards if you have a valid set.")
        system_prompt_addition = "It is your REINFORCE phase. " + " ".join(prompt_details)

        self._execute_ai_turn_async(agent, game_state_json, valid_actions, self.game_rules, system_prompt_addition)

    def _process_reinforce_ai_action(self, player: GamePlayer, agent: BaseAIAgent, ai_response: dict):
        """Processes the AI's action for the REINFORCE phase."""
        print(f"Orchestrator: Processing REINFORCE AI action for {player.name}")
        action = ai_response.get("action")

        if not action or not isinstance(action, dict) or "type" not in action:
            self.log_turn_info(f"{player.name} provided malformed or missing REINFORCE action: {action}. AI will be prompted again.")
            self.ai_is_thinking = False # Allow re-triggering AI for next reinforce sub-step.
            if self.gui: self._update_gui_full_state()
            return

        action_type = action["type"]
        self.log_turn_info(f"{player.name} REINFORCE action: {action_type} - Details: {action}")

        if action_type == "TRADE_CARDS":
            card_indices = action.get("card_indices")
            # Validate card_indices (must be a list of integers)
            if not isinstance(card_indices, list) or not all(isinstance(idx, int) for idx in card_indices):
                self.log_turn_info(f"{player.name} selected TRADE_CARDS with invalid indices format: {card_indices}. AI will be prompted again.")
            else:
                trade_result = self.engine.perform_card_trade(player, card_indices)
                log_message = trade_result.get('message', f"Trade attempt by {player.name} with cards {card_indices}.")
                self.log_turn_info(log_message)
                if trade_result.get("success"):
                    self.log_turn_info(f"{player.name} gained {trade_result['armies_gained']} armies. Total to deploy: {player.armies_to_deploy}.")
                    if trade_result.get("territory_bonus"): self.log_turn_info(trade_result["territory_bonus"])
                # else: Card trade failed, message already logged by engine.
            # After any trade attempt, AI needs to make another decision (deploy, trade again if possible, or end).
            self.ai_is_thinking = False

        elif action_type == "DEPLOY":
            terr_name = action.get("territory")
            num_armies_to_deploy = action.get("num_armies")

            # Validate parameters
            if not isinstance(terr_name, str) or not isinstance(num_armies_to_deploy, int):
                self.log_turn_info(f"{player.name} invalid DEPLOY parameters: territory='{terr_name}', num_armies='{num_armies_to_deploy}'. AI will be prompted again.")
            elif num_armies_to_deploy <= 0:
                self.log_turn_info(f"{player.name} attempted DEPLOY with non-positive armies: {num_armies_to_deploy}. AI will be prompted again.")
            elif player.armies_to_deploy == 0:
                 self.log_turn_info(f"{player.name} attempted DEPLOY but has no armies to deploy. AI will be prompted again (may need to END_REINFORCE_PHASE or TRADE_CARDS).")
            else:
                territory_obj = self.engine.game_state.territories.get(terr_name)
                if not territory_obj:
                    self.log_turn_info(f"{player.name} attempted DEPLOY to non-existent territory: {terr_name}. AI will be prompted again.")
                elif territory_obj.owner != player:
                    self.log_turn_info(f"{player.name} attempted DEPLOY to territory '{terr_name}' not owned by them. Owner: {territory_obj.owner.name if territory_obj.owner else 'None'}. AI will be prompted again.")
                else:
                    # Validations passed, proceed with deployment logic directly here
                    actual_armies_to_deploy_on_territory = min(num_armies_to_deploy, player.armies_to_deploy)

                    if actual_armies_to_deploy_on_territory > 0 :
                        territory_obj.army_count += actual_armies_to_deploy_on_territory
                        player.armies_to_deploy -= actual_armies_to_deploy_on_territory
                        self.log_turn_info(f"{player.name} deployed {actual_armies_to_deploy_on_territory} armies to {terr_name} (new total: {territory_obj.army_count}). Armies left to deploy: {player.armies_to_deploy}.")
                    else:
                        # This case implies num_armies_to_deploy from AI was <=0, or player.armies_to_deploy was already 0.
                        # The num_armies_to_deploy <= 0 is already checked above.
                        # So this means player.armies_to_deploy was 0, which is also checked above.
                        # This specific else should ideally not be reached if prior checks are comprehensive.
                        self.log_turn_info(f"{player.name} DEPLOY action for {terr_name} resulted in no armies deployed (requested: {num_armies_to_deploy}, available: {player.armies_to_deploy}). AI will be prompted again.")
            # After deploying (or attempting to), AI needs to make another decision.
            self.ai_is_thinking = False

        elif action_type == "END_REINFORCE_PHASE":
            # Check for must_trade condition before allowing end of phase
            # Re-fetch valid actions as game state might have changed (e.g. after a trade)
            current_valid_actions = self.engine.get_valid_actions(player) # Get fresh valid actions
            if any(a['type'] == 'TRADE_CARDS' and a.get('must_trade') for a in current_valid_actions):
                 self.log_turn_info(f"{player.name} tried END_REINFORCE_PHASE but MUST_TRADE cards. AI will be prompted again.")
                 self.ai_is_thinking = False # AI needs to make a new decision (trade)
            else:
                if player.armies_to_deploy > 0:
                    self.log_turn_info(f"Warning: {player.name} chose END_REINFORCE_PHASE with {player.armies_to_deploy} armies remaining. Auto-distributing.")
                    self.auto_distribute_armies(player, player.armies_to_deploy) # auto_distribute_armies sets player.armies_to_deploy to 0
                else:
                     self.log_turn_info(f"{player.name} ends REINFORCE phase with all armies deployed.")

                player.armies_to_deploy = 0 # Ensure it's zeroed out
                self.engine.game_state.current_game_phase = "ATTACK"
                self.has_logged_current_turn_player_phase = False # So new phase header logs
                self.ai_is_thinking = False # Reinforce phase is over for this player.
                print(f"Orchestrator: {player.name} REINFORCE phase ended. Transitioning to ATTACK.")

        else: # Unknown action type
            self.log_turn_info(f"{player.name} provided an unknown REINFORCE action type: '{action_type}'. AI will be prompted again.")
            self.ai_is_thinking = False # Allow AI to retry its reinforce turn with a valid action.

        if self.gui: self._update_gui_full_state()

    def _initiate_attack_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        """Gathers info and starts the AI thinking for the ATTACK phase (or PAF)."""
        print(f"Orchestrator: Initiating ATTACK/PAF AI action for {player.name}")
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player) # Get current valid actions

        if self.engine.game_state.requires_post_attack_fortify:
            self.log_turn_info(f"{player.name} must complete POST_ATTACK_FORTIFY.")
            paf_actions = [va for va in valid_actions if va['type'] == "POST_ATTACK_FORTIFY"]
            if not paf_actions:
                self.log_turn_info(f"CRITICAL ERROR: PAF required but no PAF action for {player.name}. Clearing flag and ending attack phase for safety.");
                self.engine.game_state.requires_post_attack_fortify = False; self.engine.game_state.conquest_context = None
                self.engine.game_state.current_game_phase = "FORTIFY"
                self.ai_is_thinking = False
                if self.gui: self._update_gui_full_state()
                return
            else:
                paf_detail = paf_actions[0] # Should only be one
                from_terr_obj = self.engine.game_state.territories.get(paf_detail['from_territory'])
                from_army_count = from_terr_obj.army_count if from_terr_obj else "N/A"
                paf_prompt = (f"You conquered {paf_detail['to_territory']}. You MUST move between {paf_detail['min_armies']} and {paf_detail['max_armies']} armies "
                              f"from {paf_detail['from_territory']} (currently has {from_army_count} armies) "
                              f"to the newly conquered {paf_detail['to_territory']}.")
                self._execute_ai_turn_async(agent, game_state_json, paf_actions, self.game_rules, paf_prompt)
                return # AI is now thinking about PAF

        # If no PAF pending, proceed with regular attack/chat/end phase options
        if not valid_actions or all(a['type'] == "END_ATTACK_PHASE" for a in valid_actions if len(valid_actions) ==1):
            self.log_turn_info(f"No more valid attack moves for {player.name} or only END_ATTACK_PHASE available. Moving to FORTIFY.");
            self.engine.game_state.current_game_phase = "FORTIFY"
            self.has_logged_current_turn_player_phase = False # Phase changed
            self.ai_is_thinking = False # Ensure not stuck
            if self.gui: self._update_gui_full_state()
            return

        attacks_this_turn = self.current_ai_context.get("attacks_this_turn", 0) if self.current_ai_context else 0 # Persist across AI calls within same phase
        prompt_elements = [f"It is your attack phase. You have made {attacks_this_turn} attacks this turn.", f"You have {len(player.hand)} cards."]
        other_players_info = []
        for p_other in self.engine.game_state.players:
            if p_other != player: other_players_info.append(f"{p_other.name}({len(p_other.hand)}c, {len(p_other.territories)}t)")
        if other_players_info: prompt_elements.append("Opponents: " + "; ".join(other_players_info))
        system_prompt_addition = " ".join(prompt_elements)

        self._execute_ai_turn_async(agent, game_state_json, valid_actions, self.game_rules, system_prompt_addition)
        if self.current_ai_context: # Store attacks_this_turn for next iteration if AI attacks again
            self.current_ai_context["attacks_this_turn"] = attacks_this_turn


    def _process_attack_ai_action(self, player: GamePlayer, agent: BaseAIAgent, ai_response: dict):
        """Processes the AI's action for the ATTACK phase."""
        print(f"Orchestrator: Processing ATTACK AI action for {player.name}")
        action = ai_response.get("action")

        attacks_this_turn = self.current_ai_context.get("attacks_this_turn", 0) if self.current_ai_context else 0

        if not action or not isinstance(action, dict) or "type" not in action:
            self.log_turn_info(f"{player.name} provided malformed or missing ATTACK action: {action}. AI will be prompted again.")
            self.ai_is_thinking = False # Allow re-triggering AI for next attack sub-step.
            if self.gui: self._update_gui_full_state()
            return

        action_type = action["type"]
        self.log_turn_info(f"{player.name} ATTACK action: {action_type} - Details: {action}")

        if action_type == "POST_ATTACK_FORTIFY":
            # This action is only valid if self.engine.game_state.requires_post_attack_fortify was true
            # when _initiate_attack_ai_action was called.
            num_to_move = action.get("num_armies")
            # Defaulting logic for num_to_move should be robust, using context if available
            conquest_ctx = self.engine.game_state.conquest_context
            min_movable_default = conquest_ctx.get('min_movable', 1) if conquest_ctx else 1 # Default to 1 if context somehow missing

            if not isinstance(num_to_move, int):
                self.log_turn_info(f"{player.name} PAF num_armies invalid: {num_to_move}. Defaulting to min: {min_movable_default}.")
                num_to_move = min_movable_default

            fortify_log = self.engine.perform_post_attack_fortify(player, num_to_move)
            self.log_turn_info(f"{player.name} PAF: {fortify_log.get('message', 'PAF outcome unknown.')}")
            # After PAF, engine automatically clears requires_post_attack_fortify.
            # AI can then make another regular attack or end phase.
            self.ai_is_thinking = False
            if self.engine.is_game_over(): # Check game over after PAF
                 self.ai_is_thinking = False # Ensure AI is not stuck if game ends

        elif action_type == "ATTACK":
            from_territory_name = action.get("from")
            to_territory_name = action.get("to")
            num_armies = action.get("num_armies")

            if not all(isinstance(param, str) for param in [from_territory_name, to_territory_name]) or not isinstance(num_armies, int):
                self.log_turn_info(f"{player.name} invalid ATTACK parameters: from='{from_territory_name}', to='{to_territory_name}', num_armies='{num_armies}'. AI will be prompted again.")
            else:
                attack_log = self.engine.perform_attack(player, from_territory_name, to_territory_name, num_armies)
                self.log_turn_info(f"Battle Log: {attack_log.get('summary', 'Error during battle processing.')}")

                attacks_this_turn +=1
                if self.current_ai_context: self.current_ai_context["attacks_this_turn"] = attacks_this_turn

                if "error" not in attack_log: # Check for engine-level errors first
                    if attack_log.get("conquered"):
                        self.log_turn_info(f"{player.name} conquered {to_territory_name} from {attack_log.get('defender_name', 'N/A')}.")
                        if attack_log.get("card_drawn"):
                            self.log_turn_info(f"{player.name} drew a card for conquering a territory.")
                        if attack_log.get("eliminated_player_name"):
                             elim_name = attack_log.get("eliminated_player_name")
                             self.log_turn_info(f"{player.name} ELIMINATED {elim_name}!")
                             self.global_chat.broadcast("GameSystem", f"{player.name} eliminated {elim_name}!")
                             self.handle_player_elimination(elim_name) # This updates player list, ai_agents, player_map
                             if self.engine.is_game_over():
                                 self.ai_is_thinking = False
                                 if self.gui: self._update_gui_full_state()
                                 # Game over will be handled by advance_game_turn loop.
                                 return
                    # If conquered, engine.game_state.requires_post_attack_fortify will be set to True by perform_attack.
                    # The next call to _initiate_attack_ai_action will detect this and prompt for PAF.
                # else: Error message already logged by engine.perform_attack via summary.
            self.ai_is_thinking = False # AI ready for next decision (could be PAF if conquest, another attack, or end phase).

        elif action_type == "END_ATTACK_PHASE":
            self.log_turn_info(f"{player.name} chose to end ATTACK phase.")
            self.engine.game_state.current_game_phase = "FORTIFY"
            self.has_logged_current_turn_player_phase = False # So new phase header logs
            self.ai_is_thinking = False # Attack phase is over for this player.
            print(f"Orchestrator: {player.name} ATTACK phase ended. Transitioning to FORTIFY.")

        elif action_type == "GLOBAL_CHAT":
            message = action.get("message", "")
            if isinstance(message, str) and message.strip():
                self.global_chat.broadcast(player.name, message)
                self.log_turn_info(f"{player.name} (Global Chat): {message}")
            else:
                self.log_turn_info(f"{player.name} attempted GLOBAL_CHAT with empty or invalid message.")
            self.ai_is_thinking = False # AI can make another attack phase action.

        elif action_type == "PRIVATE_CHAT":
            target_player_name = action.get("target_player_name")
            initial_message = action.get("initial_message")

            if not isinstance(target_player_name, str) or not isinstance(initial_message, str) or not initial_message.strip():
                self.log_turn_info(f"{player.name} invalid PRIVATE_CHAT: missing/invalid target ('{target_player_name}') or message ('{initial_message}').")
            else:
                target_agent = self.ai_agents.get(target_player_name)
                if not target_agent:
                    self.log_turn_info(f"{player.name} invalid PRIVATE_CHAT target: Player '{target_player_name}' not found or not an AI.")
                elif target_agent == agent: # Cannot chat with self
                    self.log_turn_info(f"{player.name} attempted PRIVATE_CHAT with self. Action ignored.")
                else:
                    self.log_turn_info(f"Orchestrator: Initiating private chat between {player.name} and {target_player_name}.")
                    current_game_state_json = self.engine.game_state.to_json() # Fresh state for context
                    # run_conversation is synchronous.
                    conversation_log_entries = self.private_chat_manager.run_conversation(
                        initiating_agent=agent,
                        receiving_agent=target_agent,
                        initial_message=initial_message,
                        game_state_json=current_game_state_json,
                        game_rules=self.game_rules
                    )
                    if conversation_log_entries and self.gui:
                        # Assuming log_private_chat can handle a list of entries or needs adaptation
                        # For now, let's log a summary or the full list if GUI supports it.
                        # This might need a specific format for the GUI to display nicely.
                        summary_msg = f"Private chat between {player.name} and {target_player_name} concluded ({len(conversation_log_entries)} exchanges)."
                        self.gui.log_action(summary_msg) # Generic log for now
                        # If self.private_chat_manager stores conversations, GUI will pick it up with _update_gui_full_state
                    self.log_turn_info(f"Private chat between {player.name} and {target_player_name} concluded.")
            self.ai_is_thinking = False # AI can make another attack phase action after chat.

        else: # Unknown action type
            self.log_turn_info(f"{player.name} provided an unknown ATTACK action type: '{action_type}'. AI will be prompted again.")
            self.ai_is_thinking = False # Allow AI to retry its attack turn with a valid action.

        if self.gui: self._update_gui_full_state()

    def _initiate_fortify_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        """Gathers info and starts the AI thinking for the FORTIFY phase."""
        print(f"Orchestrator: Initiating FORTIFY AI action for {player.name}")
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player) # FORTIFY or END_TURN

        if not valid_actions:
             self.log_turn_info(f"No valid FORTIFY actions for {player.name}. This should not happen (must have END_TURN). Ending turn.");
             self.engine.game_state.current_game_phase = "REINFORCE" # Prepare for next player
             self.engine.next_turn()
             self.has_logged_current_turn_player_phase = False # New turn/player starting
             self.ai_is_thinking = False
             if self.gui: self._update_gui_full_state()
             return

        prompt_add = f"It is your FORTIFY phase. Fortified this turn: {player.has_fortified_this_turn}. "
        if not player.has_fortified_this_turn:
            prompt_add += "Make one fortification move (remember to specify 'num_armies') or choose to end your turn."
        else:
            prompt_add += "You have already fortified. You must end your turn."
        self._execute_ai_turn_async(agent, game_state_json, valid_actions, self.game_rules, system_prompt_addition=prompt_add)

    def _process_fortify_ai_action(self, player: GamePlayer, agent: BaseAIAgent, ai_response: dict):
        """Processes the AI's action for the FORTIFY phase."""
        print(f"Orchestrator: Processing FORTIFY AI action for {player.name}")
        action = ai_response.get("action")

        if not action or not isinstance(action, dict) or "type" not in action:
            self.log_turn_info(f"{player.name} provided malformed or missing FORTIFY action: {action}. Ending turn.")
            # Fall through to end turn logic
        else:
            action_type = action["type"]
            self.log_turn_info(f"{player.name} FORTIFY action: {action_type} - Details: {action}")

            if action_type == "FORTIFY":
                # Player can only fortify once. This should ideally be caught by valid_actions generation.
                if player.has_fortified_this_turn:
                     self.log_turn_info(f"{player.name} attempted to FORTIFY again in the same turn. Action ignored. Ending turn.")
                else:
                    from_territory_name = action.get("from")
                    to_territory_name = action.get("to")
                    num_armies = action.get("num_armies")

                    if not all(isinstance(param, str) for param in [from_territory_name, to_territory_name]) or \
                       not isinstance(num_armies, int) or num_armies < 0: # num_armies can be 0 if AI chooses not to move any from a valid path
                        self.log_turn_info(f"{player.name} invalid FORTIFY parameters: from='{from_territory_name}', to='{to_territory_name}', num_armies='{num_armies}'. Ending turn.")
                        # No actual fortification happens, turn ends.
                    else:
                        # perform_fortify will validate ownership, connectivity, army counts.
                        # The 'player' object is not needed for the engine's perform_fortify method.
                        fortify_result = self.engine.perform_fortify(from_territory_name, to_territory_name, num_armies)
                        log_message = fortify_result.get('message', f"Fortify attempt by {player.name} from {from_territory_name} to {to_territory_name} with {num_armies} armies.")
                        self.log_turn_info(log_message)
                        # player.has_fortified_this_turn is set by the engine if successful and num_armies > 0

            elif action_type == "END_TURN":
                self.log_turn_info(f"{player.name} chose to END_TURN (not fortifying).")

            else: # Unknown action type for fortify phase
                self.log_turn_info(f"{player.name} provided an unknown action type '{action_type}' during FORTIFY phase. Ending turn.")

        # Regardless of the action (FORTIFY, END_TURN, or malformed), the fortify phase ends the player's turn.
        # The main game loop (`advance_game_turn`) will call `self.engine.next_turn()`.
        self.ai_is_thinking = False # Player's turn processing is complete.
        self.has_logged_current_turn_player_phase = False # Reset for next turn's logging.

        # Do not call self.engine.next_turn() here.
        # The advance_game_turn method will see that ai_is_thinking is false
        # and that the phase was FORTIFY, then it will call next_turn().
        # This keeps turn transition logic centralized in advance_game_turn.
        print(f"Orchestrator: {player.name} FORTIFY phase processing complete. Turn will now end.")
        if self.gui: self._update_gui_full_state()

    # Removed original handle_reinforce_phase, handle_attack_communicate_phase, handle_fortify_phase
    # as their logic is now split into _initiate_ and _process_ methods, driven by advance_game_turn.

    def auto_distribute_armies(self, player: GamePlayer, armies_to_distribute: int):
        self.log_turn_info(f"{player.name} starts REINFORCE phase with {player.armies_to_deploy} reinforcements.")
        reinforce_phase_active = True
        max_reinforce_actions = 15
        actions_taken_this_phase = 0
        while reinforce_phase_active and actions_taken_this_phase < max_reinforce_actions:
            actions_taken_this_phase += 1
            game_state_json = self.engine.game_state.to_json()
            valid_actions = self.engine.get_valid_actions(player)
            if not valid_actions:
                err_msg = f"No valid actions for {player.name} during REINFORCE phase. Player might be stuck. Ending phase."
                print(err_msg); self.log_turn_info(err_msg)
                reinforce_phase_active = False; break
            current_reinforcements = player.armies_to_deploy
            current_cards = len(player.hand)
            prompt_details = [f"You have {current_reinforcements} armies to deploy.", f"You currently hold {current_cards} cards."]
            if any(a['type'] == 'TRADE_CARDS' and a.get('must_trade') for a in valid_actions):
                prompt_details.append("You MUST trade cards as you have 5 or more and a valid set is available.")
            elif any(a['type'] == 'TRADE_CARDS' for a in valid_actions):
                prompt_details.append("You may optionally trade cards if you have a valid set.")
            system_prompt_addition = "It is your REINFORCE phase. " + " ".join(prompt_details)
            ai_response = agent.get_thought_and_action(game_state_json, valid_actions, self.game_rules, system_prompt_addition=system_prompt_addition)
            action = ai_response.get("action"); thought = ai_response.get("thought", "(No thought provided)")
            self.log_ai_thought(player.name, thought)
            if not action or "type" not in action:
                err_msg = f"{player.name} provided malformed action: {action}. Ending REINFORCE phase."
                print(err_msg); self.log_turn_info(err_msg)
                reinforce_phase_active = False; break
            action_type = action["type"]
            if action_type == "TRADE_CARDS":
                card_indices = action.get("card_indices")
                if card_indices is None:
                    self.log_turn_info(f"{player.name} selected TRADE_CARDS but no indices. Trying again."); continue
                trade_result = self.engine.perform_card_trade(player, card_indices)
                if trade_result.get("success"):
                    self.log_turn_info(f"{player.name} traded cards for {trade_result['armies_gained']} armies. Now has {player.armies_to_deploy} to deploy.")
                    if trade_result.get("territory_bonus"): self.log_turn_info(trade_result["territory_bonus"])
                    if self.gui: self._update_gui_full_state()
                else:
                    self.log_turn_info(f"{player.name} card trade failed: {trade_result['message']}.")
                    if self.gui: self._update_gui_full_state()
            elif action_type == "DEPLOY":
                terr_name = action.get("territory"); num_armies_to_deploy = action.get("num_armies")
                territory_to_deploy = self.engine.game_state.territories.get(terr_name)
                if not isinstance(num_armies_to_deploy, int) or num_armies_to_deploy <= 0:
                    self.log_turn_info(f"{player.name} invalid DEPLOY num_armies: {num_armies_to_deploy}. Try again."); continue
                if player.armies_to_deploy == 0:
                    self.log_turn_info(f"{player.name} tried DEPLOY with 0 armies. Must_trade?: {any(a['type'] == 'TRADE_CARDS' and a.get('must_trade') for a in valid_actions)}"); continue
                if territory_to_deploy and territory_to_deploy.owner == player:
                    actual_deployed = min(num_armies_to_deploy, player.armies_to_deploy)
                    territory_to_deploy.army_count += actual_deployed
                    player.armies_to_deploy -= actual_deployed
                    self.log_turn_info(f"{player.name} deployed {actual_deployed} to {terr_name} ({territory_to_deploy.army_count}). Left: {player.armies_to_deploy}.")
                    if self.gui: self._update_gui_full_state()
                else:
                    self.log_turn_info(f"{player.name} invalid DEPLOY: {action}. Armies: {player.armies_to_deploy}.")
                    if self.gui: self._update_gui_full_state()
            elif action_type == "END_REINFORCE_PHASE":
                if any(a['type'] == 'TRADE_CARDS' and a.get('must_trade') for a in valid_actions):
                    self.log_turn_info(f"{player.name} tried END_REINFORCE_PHASE during must_trade. Ignoring."); continue
                self.log_turn_info(f"{player.name} ends REINFORCE phase.")
                if player.armies_to_deploy > 0:
                    self.log_turn_info(f"Warning: {player.name} ended with {player.armies_to_deploy} armies. Auto-distributing.")
                    self.auto_distribute_armies(player, player.armies_to_deploy)
                player.armies_to_deploy = 0; reinforce_phase_active = False
                if self.gui: self._update_gui_full_state()
            else:
                self.log_turn_info(f"{player.name} unknown REINFORCE action: {action}. Trying again.")
                if self.gui: self._update_gui_full_state()
        if actions_taken_this_phase >= max_reinforce_actions:
            self.log_turn_info(f"{player.name} max REINFORCE actions. Auto-distributing {player.armies_to_deploy} armies.")
            if player.armies_to_deploy > 0: self.auto_distribute_armies(player, player.armies_to_deploy)
        player.armies_to_deploy = 0
        self.log_turn_info(f"{player.name} REINFORCE phase ended.")

    def auto_distribute_armies(self, player: GamePlayer, armies_to_distribute: int):
        if not player.territories: return
        idx = 0
        while armies_to_distribute > 0:
            territory = player.territories[idx % len(player.territories)]
            territory.army_count += 1; armies_to_distribute -= 1
            self.log_turn_info(f"Auto-distributed 1 army to {territory.name} for {player.name}.")
            idx += 1
        if self.gui: self._update_gui_full_state()

    def handle_attack_communicate_phase(self, player: GamePlayer, agent: BaseAIAgent):
        attack_action_limit = 10; attacks_this_turn = 0
        while attacks_this_turn < attack_action_limit:
            if self.engine.game_state.requires_post_attack_fortify: # Check if PAF is pending
                self.log_turn_info(f"{player.name} must complete POST_ATTACK_FORTIFY.")
                paf_actions = self.engine.get_valid_actions(player)
                if not paf_actions or paf_actions[0]['type'] != "POST_ATTACK_FORTIFY":
                    self.log_turn_info(f"ERROR: Expected POST_ATTACK_FORTIFY for {player.name}, got {paf_actions}. Clearing flag.");
                    self.engine.game_state.requires_post_attack_fortify = False; self.engine.game_state.conquest_context = None
                    self._update_gui_full_state(); continue

                paf_detail = paf_actions[0]
                paf_prompt = (f"You conquered {paf_detail['to_territory']}. Move {paf_detail['min_armies']}-{paf_detail['max_armies']} armies "
                              f"from {paf_detail['from_territory']} (has {self.engine.game_state.territories[paf_detail['from_territory']].army_count}) "
                              f"to {paf_detail['to_territory']} (has 0).")
                paf_response = agent.get_thought_and_action(self.engine.game_state.to_json(), paf_actions, self.game_rules, system_prompt_addition=paf_prompt)
                paf_action = paf_response.get("action")
                self.log_ai_thought(player.name, f"PAF Thought: {paf_response.get('thought', 'N/A')}")

                num_to_move = paf_detail['min_armies'] # Default to min
                if paf_action and paf_action.get("type") == "POST_ATTACK_FORTIFY" and paf_action.get("num_armies") is not None:
                    num_to_move = paf_action.get("num_armies")
                else:
                     self.log_turn_info(f"AI invalid/missing PAF action, using min {num_to_move} armies.")

                fortify_log = self.engine.perform_post_attack_fortify(player, num_to_move)
                self.log_turn_info(f"{player.name} PAF: {fortify_log.get('message', 'Unknown PAF outcome')}")
                self._update_gui_full_state()
                if self.engine.is_game_over(): break # Check again after PAF
                # PAF is done, loop continues for regular attack phase actions.

            game_state_json = self.engine.game_state.to_json()
            valid_actions = self.engine.get_valid_actions(player)
            if not valid_actions or all(a['type'] == "END_ATTACK_PHASE" for a in valid_actions if len(valid_actions) ==1): # Only END_ATTACK_PHASE left or no actions
                 if not any(a['type'] == 'ATTACK' for a in valid_actions): # Double check no attack actions
                    print(f"{player.name} has no more valid attack moves or only END_ATTACK_PHASE. Ending attack phase.")
                    break

            prompt_elements = [f"It is your attack phase. You have made {attacks_this_turn} attacks this turn.", f"You have {len(player.hand)} cards."]
            # ... (rest of prompt element generation for opponents, continents - kept for brevity) ...
            other_players_info = []
            for p_other in self.engine.game_state.players:
                if p_other != player: other_players_info.append(f"{p_other.name}({len(p_other.hand)}c, {len(p_other.territories)}t)")
            if other_players_info: prompt_elements.append("Opps: " + "; ".join(other_players_info))
            system_prompt_addition = " ".join(prompt_elements)
            ai_response = agent.get_thought_and_action(game_state_json, valid_actions, self.game_rules, system_prompt_addition=system_prompt_addition)
            action = ai_response.get("action"); thought = ai_response.get("thought", "(No thought provided)")
            self.log_ai_thought(player.name, thought)

            if not action or not action.get("type"): self.log_turn_info(f"{player.name} invalid action: {action}. Ending attack phase."); break
            action_type = action.get("type")

            if action_type == "ATTACK":
                from_t, to_t, num_a = action.get("from"), action.get("to"), action.get("num_armies")
                self.log_turn_info(f"{player.name} ATTACK {from_t}->{to_t} with {num_a}")
                attack_log = self.engine.perform_attack(from_t, to_t, num_a)
                self.log_turn_info(f"Battle: {attack_log.get('summary', 'Error in battle')}")
                if "error" not in attack_log:
                    if attack_log.get("conquered"):
                        self.log_turn_info(f"{player.name} conquered {to_t} from {attack_log.get('defender', 'PrevOwner')}.")
                        if attack_log.get("card_drawn"): self.log_turn_info(f"{player.name} drew a card.")
                        if attack_log.get("eliminated_player"):
                            elim_name = attack_log.get("eliminated_player")
                            self.log_turn_info(f"{player.name} ELIMINATED {elim_name}!")
                            self.global_chat.broadcast("GameSystem", f"{player.name} eliminated {elim_name}!")
                            self.handle_player_elimination(elim_name)
                            self._update_gui_full_state()
                            if self.engine.is_game_over(): break
                        # Post-attack fortify is now handled at the start of the loop if flag is set.
                    self._update_gui_full_state()
                else: # Attack error
                     self._update_gui_full_state()

                attacks_this_turn += 1
                if self.engine.is_game_over(): break
                continue # Continue attack loop
            elif action_type == "GLOBAL_CHAT":
                msg = action.get("message", "")
                if msg: self.global_chat.broadcast(player.name, msg); self.log_turn_info(f"{player.name} (Global): {msg}")
                else: self.log_turn_info(f"{player.name} empty GLOBAL_CHAT.")
                self._update_gui_full_state(); continue
            elif action_type == "PRIVATE_CHAT":
                target_n, init_msg = action.get("target_player_name"), action.get("initial_message")
                if not target_n or not init_msg: self.log_turn_info(f"{player.name} invalid PRIVATE_CHAT: missing target/msg."); continue
                target_agent = self.ai_agents.get(target_n)
                if not target_agent or target_agent == agent: self.log_turn_info(f"{player.name} invalid PRIVATE_CHAT target."); continue
                self.log_turn_info(f"{player.name} private chat with {target_n}.")
                convo_log = self.private_chat_manager.run_conversation(agent, target_agent, init_msg, game_state_json, self.game_rules)
                if convo_log and self.gui: self.gui.log_private_chat(convo_log, player.name, target_n) # GUI specific log
                self.log_turn_info(f"Private chat ended {player.name}-{target_n} ({len(convo_log) if convo_log else 0} msgs).")
                self._update_gui_full_state(); continue
            elif action_type == "END_ATTACK_PHASE":
                self.log_turn_info(f"{player.name} ends ATTACK phase."); break
            else: self.log_turn_info(f"{player.name} unknown ATTACK action: {action_type}. Ending phase."); break
        if attacks_this_turn >= attack_action_limit: self.log_turn_info(f"{player.name} reached attack limit.")

    def handle_fortify_phase(self, player: GamePlayer, agent: BaseAIAgent):
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player)
        fortify_actions = [a for a in valid_actions if a['type'] == 'FORTIFY' or a['type'] == 'END_TURN']
        if not fortify_actions: self.log_turn_info(f"{player.name} no fortify options. Ending turn."); return

        prompt_add = f"It's your FORTIFY phase. Fortified this turn: {player.has_fortified_this_turn}. "
        prompt_add += "Make one move or end turn." if not player.has_fortified_this_turn else "Must end turn."
        ai_response = agent.get_thought_and_action(game_state_json, fortify_actions, self.game_rules, system_prompt_addition=prompt_add)
        action = ai_response.get("action"); thought = ai_response.get("thought", "(No thought for fortify)")
        self.log_ai_thought(player.name, thought)

        if not action or not action.get("type"):
            self.log_turn_info(f"{player.name} invalid FORTIFY action: {action}. Ending turn."); return
        action_type = action.get("type")
        if action_type == "FORTIFY":
            if player.has_fortified_this_turn: # Should be prevented by get_valid_actions
                self.log_turn_info(f"{player.name} tried to FORTIFY again. Ending turn."); return
            from_t, to_t, num_a = action.get("from"), action.get("to"), action.get("num_armies")
            fortify_result = self.engine.perform_fortify(from_t, to_t, num_a)
            self.log_turn_info(f"{player.name} FORTIFY {from_t}->{to_t} ({num_a}): {fortify_result.get('message')}")
            if self.gui: self._update_gui_full_state()
        elif action_type == "END_TURN":
            self.log_turn_info(f"{player.name} chose to END_TURN.")
            if self.gui: self._update_gui_full_state()
        else:
            self.log_turn_info(f"{player.name} unknown FORTIFY action: {action_type}. Ending turn.")
            if self.gui: self._update_gui_full_state()

    def handle_player_elimination(self, eliminated_player_name: str):
        player_to_remove_engine = None
        original_index = -1
        for i, p_obj in enumerate(self.engine.game_state.players):
            if p_obj.name == eliminated_player_name:
                player_to_remove_engine = p_obj
                original_index = i
                break
        if player_to_remove_engine:
            self.engine.game_state.players.pop(original_index) # Use pop with index
            print(f"Removed {eliminated_player_name} from engine player list at index {original_index}.")
            if original_index <= self.engine.game_state.current_player_index and self.engine.game_state.current_player_index > 0:
                self.engine.game_state.current_player_index -= 1
                print(f"Adjusted current_player_index to {self.engine.game_state.current_player_index}.")
        else:
            print(f"Warning: Could not find {eliminated_player_name} in engine player list to remove.")
        if eliminated_player_name in self.ai_agents:
            del self.ai_agents[eliminated_player_name]
        key_to_remove_map = None
        for gp_key, ai_val in self.player_map.items():
            if gp_key.name == eliminated_player_name: # Compare by name as gp_key might be stale if player list changed
                key_to_remove_map = gp_key; break
        if key_to_remove_map: del self.player_map[key_to_remove_map]
        print(f"Player {eliminated_player_name} fully processed for elimination.")

    def log_ai_thought(self, player_name: str, thought: str):
        print(f"--- {player_name}'s Thought --- \n{thought[:300]}...\n--------------------")
        if self.gui: self.gui.update_thought_panel(player_name, thought)
        # ... (file logging remains same) ...

    def log_turn_info(self, message: str):
        if self.gui: self.gui.log_action(message)
        # ... (file logging remains same) ...

    def setup_gui(self):
        if not self.gui:
            self.gui = GameGUI(self.engine, self)
            print("GUI setup complete. GUI is active.")
        else:
            print("GUI already setup.")

if __name__ == '__main__':
    print("Setting up Game Orchestrator for a test run...")
    dummy_player_config = [
        {"name": "Alice (Gemini)", "color": "Red", "ai_type": "Gemini"},
        {"name": "Bob (OpenAI)", "color": "Blue", "ai_type": "OpenAI"}
    ]
    config_path = "player_config.json"
    try:
        with open(config_path, 'w') as f: json.dump(dummy_player_config, f, indent=2)
        print(f"Created dummy {config_path} for testing.")
    except IOError: print(f"Could not create dummy {config_path}.")
    orchestrator = GameOrchestrator(default_player_setup_file=config_path) # Using new parameter name
    print("Starting game run...")
    orchestrator.run_game()
    print("\nGame run finished.")
    # ... (final log print remains same) ...
