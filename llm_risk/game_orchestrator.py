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
        self.player_map: dict[GamePlayer, BaseAIAgent] = {} # Maps GamePlayer objects to their AI agents
        self.is_two_player_mode: bool = False # Will be set in _load_player_setup

        # Attributes for asynchronous AI calls - INITIALIZE THEM HERE
        self.ai_is_thinking: bool = False
        self.current_ai_thread: threading.Thread | None = None
        self.ai_action_result: dict | None = None
        self.active_ai_player_name: str | None = None # Name of the player whose AI is thinking
        self.current_ai_context: dict | None = None # Context for the current AI call
        self.has_logged_ai_is_thinking_for_current_action: bool = False
        self.has_logged_current_turn_player_phase: bool = False # For logging headers

        # Load player configurations: this will populate self.engine.game_state.players
        # and also determine self.is_two_player_mode
        human_player_configs = self._load_player_setup(player_configs_override, default_player_setup_file)

        if not human_player_configs: # _load_player_setup should raise error if this happens
             raise ValueError("Player setup resulted in no human player configurations.")

        # Initialize the game board in the engine
        # The engine will internally create a Neutral player if is_two_player_mode is True.
        self.engine.initialize_game_from_map(
            players_data=[{"name": p.name, "color": p.color} for p in human_player_configs], # Pass only human player data
            is_two_player_game=self.is_two_player_mode
        )

        # After engine initializes players (including Neutral if 2P), map all to AI agents
        # The Neutral player won't have an AI agent in self.ai_agents, so player_map will skip it.
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


    def _load_player_setup(self, player_configs_override: list | None, default_player_setup_file: str) -> list[GamePlayer]:
        """
        Loads player configurations, creates AI agents, and determines game mode (2-player or standard).
        Returns a list of human GamePlayer objects created.
        The actual Player objects in self.engine.game_state (including Neutral for 2P)
        will be created by self.engine.initialize_game_from_map().
        """
        loaded_player_configs = []
        if player_configs_override is not None and isinstance(player_configs_override, list) and player_configs_override:
            print(f"Using player configurations provided by override. Count: {len(player_configs_override)}")
            loaded_player_configs = player_configs_override
        else:
            print(f"No valid player override. Attempting to load from default setup file: '{default_player_setup_file}'")
            try:
                with open(default_player_setup_file, 'r') as f:
                    loaded_player_configs = json.load(f)
                print(f"Successfully loaded player configurations from '{default_player_setup_file}'. Count: {len(loaded_player_configs)}")
            except FileNotFoundError:
                print(f"Warning: Default player setup file '{default_player_setup_file}' not found. Using 2-player default AI setup.")
                loaded_player_configs = [
                    {"name": "P1-Gemini", "color": "Red", "ai_type": "Gemini"},
                    {"name": "P2-OpenAI", "color": "Blue", "ai_type": "OpenAI"}
                ]
                try:
                    with open(default_player_setup_file, 'w') as f: json.dump(loaded_player_configs, f, indent=2)
                    print(f"Created default player setup file '{default_player_setup_file}' with 2 players.")
                except IOError: print(f"Could not write default player setup file '{default_player_setup_file}'.")
            except json.JSONDecodeError:
                print(f"Error: Could not decode JSON from '{default_player_setup_file}'. Using 2-player hardcoded default.")
                loaded_player_configs = [
                    {"name": "PX-Gemini", "color": "Red", "ai_type": "Gemini"},
                    {"name": "PY-OpenAI", "color": "Blue", "ai_type": "OpenAI"}
                ]

        if not loaded_player_configs:
            raise ValueError("Player configurations are empty after attempting to load.")

        self.ai_agents.clear() # Clear any previous agents
        human_game_players_for_engine = [] # Store GamePlayer stubs for engine init

        # Determine game mode based on number of human player configs
        if len(loaded_player_configs) == 2:
            self.is_two_player_mode = True
            print("2-Player mode detected based on configuration.")
        elif len(loaded_player_configs) >= 3 and len(loaded_player_configs) <= 6:
            self.is_two_player_mode = False
            print(f"{len(loaded_player_configs)}-Player standard mode detected.")
        else:
            raise ValueError(f"Invalid number of player configurations: {len(loaded_player_configs)}. Must be 2 (for 2-player mode) or 3-6 (for standard mode).")

        default_colors = ["Red", "Blue", "Green", "Yellow", "Purple", "Orange"]
        used_colors = set()

        for i, config in enumerate(loaded_player_configs):
            player_name = config.get("name", f"Player{i+1}") # Use configured name or generate

            player_color = config.get("color")
            if not player_color or player_color.lower() in used_colors:
                # Find next available default color
                found_color = False
                for c in default_colors:
                    if c.lower() not in used_colors:
                        player_color = c
                        found_color = True
                        break
                if not found_color: # All defaults used, cycle with numbers
                    player_color = f"{default_colors[i % len(default_colors)]}{i // len(default_colors) + 1}"
                print(f"Assigned color '{player_color}' to player '{player_name}'.")
            used_colors.add(player_color.lower())

            ai_type = config.get("ai_type", "Gemini")

            # Create GamePlayer stub for engine (engine creates the actual objects)
            # This list `human_game_players_for_engine` will only contain human players.
            # The engine will add the Neutral player itself in 2P mode.
            human_game_players_for_engine.append(GamePlayer(name=player_name, color=player_color))

            agent: BaseAIAgent | None = None
            if ai_type == "Gemini": agent = GeminiAgent(player_name, player_color)
            elif ai_type == "OpenAI": agent = OpenAIAgent(player_name, player_color)
            elif ai_type == "Claude": agent = ClaudeAgent(player_name, player_color)
            elif ai_type == "DeepSeek": agent = DeepSeekAgent(player_name, player_color)
            else:
                print(f"Warning: Unknown AI type '{ai_type}' for player {player_name}. Defaulting to Gemini.")
                agent = GeminiAgent(player_name, player_color)

            if agent:
                self.ai_agents[player_name] = agent
            else:
                raise ValueError(f"Could not create AI agent for {player_name} with type {ai_type}.")

        print(f"Player setup complete. Loaded {len(human_game_players_for_engine)} human players. Two player mode: {self.is_two_player_mode}")
        return human_game_players_for_engine


    def _map_game_players_to_ai_agents(self):
        """Maps GamePlayer objects (created by engine) to their corresponding AI agents."""
        self.player_map.clear()
        if not self.engine.game_state.players:
            print("Warning: No players in game_state to map to AI agents (called from _map_game_players_to_ai_agents).")
            return

        for gp in self.engine.game_state.players:
            if gp.is_neutral: # Neutral player does not have an AI agent
                continue
            if gp.name in self.ai_agents:
                self.player_map[gp] = self.ai_agents[gp.name]
            else:
                print(f"Critical Error: Human GamePlayer {gp.name} from engine does not have a corresponding AI agent. AI Agents: {list(self.ai_agents.keys())}")
                # This implies a mismatch between player names in configs and those used by engine, or an issue in agent creation.
                # Raise error as this will break gameplay.
                raise ValueError(f"Mismatch: GamePlayer {gp.name} has no AI agent.")
        print(f"Mapped {len(self.player_map)} GamePlayer objects to AI agents.")


    def get_agent_for_player(self, player_obj: GamePlayer) -> BaseAIAgent | None:
        """Gets the AI agent for a given GamePlayer object."""
        if player_obj is None or player_obj.is_neutral:
            return None
        return self.player_map.get(player_obj)


    def get_agent_for_current_player(self) -> BaseAIAgent | None:
        # This method now needs to handle setup phases where current player might be from player_setup_order
        gs = self.engine.game_state
        current_phase = gs.current_game_phase

        acting_player_obj: GamePlayer | None = None

        if current_phase in ["SETUP_CLAIM_TERRITORIES", "SETUP_PLACE_ARMIES"] and not gs.is_two_player_game:
            # acting_player_obj = gs.get_current_setup_player() # Replaced due to AttributeError
            current_player_obj_temp: GamePlayer | None = None
            if not gs.player_setup_order or \
               gs.current_setup_player_index < 0 or \
               gs.current_setup_player_index >= len(gs.player_setup_order):
                current_player_obj_temp = None
            else:
                current_player_obj_temp = gs.player_setup_order[gs.current_setup_player_index]
            acting_player_obj = current_player_obj_temp
        elif current_phase == "SETUP_2P_PLACE_REMAINING" and gs.is_two_player_game:
            # acting_player_obj = gs.get_current_setup_player() # Replaced due to AttributeError
            current_player_obj_temp: GamePlayer | None = None
            if not gs.player_setup_order or \
               gs.current_setup_player_index < 0 or \
               gs.current_setup_player_index >= len(gs.player_setup_order):
                current_player_obj_temp = None
            else:
                current_player_obj_temp = gs.player_setup_order[gs.current_setup_player_index]
            acting_player_obj = current_player_obj_temp # This will be one of the two human players
        elif current_phase not in ["SETUP_START", "SETUP_DETERMINE_ORDER", "SETUP_2P_DEAL_CARDS"]: # Regular game turn
            acting_player_obj = gs.get_current_player()

        if acting_player_obj:
            return self.get_agent_for_player(acting_player_obj)

        # If in a phase without a current acting player (e.g., SETUP_START) or error
        # print(f"get_agent_for_current_player: No specific acting player in phase {current_phase} or acting_player_obj is None.")
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


    # --- Setup Phase Handlers ---
    def _handle_setup_determine_order(self) -> bool:
        """Handles logic for SETUP_DETERMINE_ORDER phase (standard game)."""
        gs = self.engine.game_state
        self.log_turn_info("Phase: SETUP_DETERMINE_ORDER")
        if gs.is_two_player_game: # Should not be in this phase for 2P
            self.log_turn_info("Error: SETUP_DETERMINE_ORDER called in 2-player mode. Advancing to 2P card dealing.")
            gs.current_game_phase = "SETUP_2P_DEAL_CARDS"
            return True # Continue to next state processing

        # Simulate dice rolls to determine order (TODO: Involve AI if players were human and rolled)
        # For now, use current player list order, P0 is first.
        human_players = [p for p in gs.players if not p.is_neutral]
        if not human_players:
            self.log_turn_info("No human players to determine order for. Error.")
            return False # Stop game

        # Simple order: current order of human_players in gs.players
        ordered_player_names = [p.name for p in human_players]
        first_placer_name = human_players[0].name # First player in list places first army & gets first game turn

        success = self.engine.set_player_setup_order(ordered_player_names, first_placer_name)
        if not success:
            self.log_turn_info("Failed to set player setup order in engine. Halting.")
            return False

        self.log_turn_info(f"Player setup order determined: {ordered_player_names}. First placer & first turn: {first_placer_name}.")
        self.has_logged_current_turn_player_phase = False # Allow new phase header
        return True # Phase changed, continue processing

    def _get_current_setup_player_and_agent(self) -> tuple[GamePlayer | None, BaseAIAgent | None]:
        gs = self.engine.game_state
        # current_setup_player_obj = gs.get_current_setup_player() # Replaced due to AttributeError

        current_setup_player_obj: GamePlayer | None = None
        if not gs.player_setup_order or \
           gs.current_setup_player_index < 0 or \
           gs.current_setup_player_index >= len(gs.player_setup_order):
            current_setup_player_obj = None
        else:
            current_setup_player_obj = gs.player_setup_order[gs.current_setup_player_index]

        if not current_setup_player_obj:
            self.log_turn_info(f"Error: No current setup player identified in phase {gs.current_game_phase} using player_setup_order and current_setup_player_index.")
            return None, None

        current_setup_agent = self.get_agent_for_player(current_setup_player_obj)
        if not current_setup_agent:
            # This could happen if a human player is configured without a valid AI type
            # Or if a neutral player somehow becomes the setup player (should be prevented)
            self.log_turn_info(f"Error: No AI agent for current setup player {current_setup_player_obj.name}. Skipping their setup turn.")
            # To prevent game from stalling, advance setup player index in engine directly (if possible)
            # This is a hack; proper error handling or player skipping logic is needed in engine or here.
            # For now, just log and the game might stall if AI is expected.
            return current_setup_player_obj, None
        return current_setup_player_obj, current_setup_agent

    def _handle_setup_claim_territories(self) -> bool:
        """Handles logic for SETUP_CLAIM_TERRITORIES phase (standard game)."""
        gs = self.engine.game_state
        if gs.is_two_player_game: # Should not be here
            gs.current_game_phase = "SETUP_2P_DEAL_CARDS"; return True

        if not gs.unclaimed_territory_names: # Should have been caught by engine transitioning phase
            self.log_turn_info("All territories claimed, but phase is still SETUP_CLAIM_TERRITORIES. Engine should have transitioned.")
            gs.current_game_phase = "SETUP_PLACE_ARMIES" # Force transition
            self.engine.game_state.current_setup_player_index = 0 # Reset for next phase
            return True

        if self.ai_is_thinking: return True # AI is busy for this phase

        # If AI has finished, process its action
        if self.ai_action_result:
            action_to_process = self.ai_action_result
            self.ai_action_result = None # Clear it
            player_name_who_acted = self.active_ai_player_name
            self.active_ai_player_name = None # Clear active AI

            action = action_to_process.get("action")
            if action and action.get("type") == "SETUP_CLAIM":
                territory_name = action.get("territory")
                log = self.engine.player_claims_territory(player_name_who_acted, territory_name)
                self.log_turn_info(f"{player_name_who_acted} claims {territory_name}: {log['message']}")
                if not log["success"]:
                    self.log_turn_info(f"Claim by {player_name_who_acted} for {territory_name} failed. AI may need to retry if phase hasn't changed.")
                    # AI will be re-prompted if phase is still SETUP_CLAIM_TERRITORIES
            else:
                self.log_turn_info(f"Invalid action from {player_name_who_acted} during SETUP_CLAIM: {action}. Will re-prompt.")

            self._update_gui_full_state()
            self.has_logged_current_turn_player_phase = False # Allow new phase header if phase changed
            return True # Continue processing, potentially re-prompting or moving to next phase

        # If AI is not thinking and no result to process, initiate AI action
        current_setup_player_obj, current_setup_agent = self._get_current_setup_player_and_agent()
        if not current_setup_player_obj or not current_setup_agent:
             self.log_turn_info("No current setup player/agent for claiming. Game might stall.")
             return False # Stall or error

        if not self.has_logged_current_turn_player_phase: # Log only once per actual player's turn part
            self.log_turn_info(f"Phase: SETUP_CLAIM_TERRITORIES - {current_setup_player_obj.name}'s turn to claim.")
            self.has_logged_current_turn_player_phase = True

        valid_actions = self.engine.get_valid_actions(current_setup_player_obj)
        if not valid_actions: # Should not happen if territories are still unclaimed
            self.log_turn_info(f"No valid claim actions for {current_setup_player_obj.name}, but territories remain. Engine state: {gs.unclaimed_territory_names}")
            # This might mean engine correctly moved to next phase if all claimed by others before this player's turn in a loop
            if not gs.unclaimed_territory_names: gs.current_game_phase = "SETUP_PLACE_ARMIES"; self.engine.game_state.current_setup_player_index = 0
            return True

        prompt_add = f"It's your turn to claim a territory. Choose one from the list."
        self._execute_ai_turn_async(current_setup_agent, gs.to_json(), valid_actions, self.game_rules, prompt_add)
        return True # AI is now thinking

    def _handle_setup_place_armies(self) -> bool:
        """Handles logic for SETUP_PLACE_ARMIES phase (standard game)."""
        gs = self.engine.game_state
        if gs.is_two_player_game: # Should not be here
            gs.current_game_phase = "SETUP_2P_DEAL_CARDS"; return True

        if self.engine._all_initial_armies_placed(): # Should have been caught by engine
            gs.current_game_phase = "REINFORCE" # Should be set by engine
            self.log_turn_info("All initial armies placed, but phase is still SETUP_PLACE_ARMIES. Engine should have transitioned.")
            # Ensure first player is set for REINFORCE
            if gs.first_player_of_game:
                 try: gs.current_player_index = gs.players.index(gs.first_player_of_game)
                 except ValueError: gs.current_player_index = 0 # Fallback
                 # Calculate initial reinforcements for the actual first player
                 first_game_player = gs.get_current_player()
                 if first_game_player: first_game_player.armies_to_deploy = self.engine.calculate_reinforcements(first_game_player)
            return True

        if self.ai_is_thinking: return True

        if self.ai_action_result:
            action_to_process = self.ai_action_result
            self.ai_action_result = None
            player_name_who_acted = self.active_ai_player_name
            self.active_ai_player_name = None

            action = action_to_process.get("action")
            if action and action.get("type") == "SETUP_PLACE_ARMY":
                territory_name = action.get("territory")
                log = self.engine.player_places_initial_army(player_name_who_acted, territory_name)
                self.log_turn_info(f"{player_name_who_acted} places army on {territory_name}: {log['message']}")
            elif action and action.get("type") == "SETUP_STANDARD_DONE_PLACING":
                self.log_turn_info(f"{player_name_who_acted} is done placing initial armies (or has no more to place).")
                # Engine will advance current_setup_player_index when player_places_initial_army is called,
                # even if player had no armies left. Orchestrator just needs to keep calling for next player.
            else:
                self.log_turn_info(f"Invalid action from {player_name_who_acted} during SETUP_PLACE_ARMIES: {action}")

            self._update_gui_full_state()
            self.has_logged_current_turn_player_phase = False
            return True

        current_setup_player_obj, current_setup_agent = self._get_current_setup_player_and_agent()
        if not current_setup_player_obj : # Agent can be none if we decide to auto-place for some.
             self.log_turn_info("No current setup player for placing armies. Game might stall if not all armies placed.")
             return False if not self.engine._all_initial_armies_placed() else True # If all placed, allow phase change.

        if current_setup_player_obj.armies_placed_in_setup >= current_setup_player_obj.initial_armies_pool:
            # This player is done, engine will advance. We just need to re-trigger the loop for the next player.
            self.log_turn_info(f"{current_setup_player_obj.name} has placed all initial armies. Orchestrator cycling.")
            # Manually advance engine's setup player index if engine didn't for a "done" player.
            # The engine's player_places_initial_army does advance if success is true, even if no armies placed.
            # So, just need to ensure the loop continues.
            self.has_logged_current_turn_player_phase = False # Log for next player
            # No AI call needed for this player, just continue the orchestrator loop.
            return True # Loop again in advance_game_turn for the next setup player.

        if not current_setup_agent: # Human player with no agent
            self.log_turn_info(f"Player {current_setup_player_obj.name} has no AI agent. Cannot place armies. Game will stall.")
            return False


        if not self.has_logged_current_turn_player_phase:
            self.log_turn_info(f"Phase: SETUP_PLACE_ARMIES - {current_setup_player_obj.name}'s turn to place. ({current_setup_player_obj.initial_armies_pool - current_setup_player_obj.armies_placed_in_setup} left)")
            self.has_logged_current_turn_player_phase = True

        valid_actions = self.engine.get_valid_actions(current_setup_player_obj)
        if not valid_actions and current_setup_player_obj.armies_placed_in_setup < current_setup_player_obj.initial_armies_pool :
            self.log_turn_info(f"No valid place_army actions for {current_setup_player_obj.name} but has armies left. Owned: {[t.name for t in current_setup_player_obj.territories]}")
            return True # Let it loop, maybe state will resolve or engine handles phase end.
        elif not valid_actions : # No actions and no armies left
             return True # Player is done, loop for next.

        prompt_add = f"Place one army on a territory you own. You have {current_setup_player_obj.initial_armies_pool - current_setup_player_obj.armies_placed_in_setup} left to place in total."
        self._execute_ai_turn_async(current_setup_agent, gs.to_json(), valid_actions, self.game_rules, prompt_add)
        return True

    def _handle_setup_2p_deal_cards(self) -> bool:
        """Handles SETUP_2P_DEAL_CARDS phase (automatic engine step)."""
        gs = self.engine.game_state
        self.log_turn_info("Phase: SETUP_2P_DEAL_CARDS (Automatic)")
        log = self.engine.setup_two_player_initial_territory_assignment()
        self.log_turn_info(log["message"])
        if not log["success"]: return False # Error in engine step
        self._update_gui_full_state()
        self.has_logged_current_turn_player_phase = False
        return True # Phase changed, continue processing

    def _handle_setup_2p_place_remaining(self) -> bool:
        """Handles SETUP_2P_PLACE_REMAINING phase."""
        gs = self.engine.game_state

        # Check if all human players have placed their armies
        all_human_done = True
        for p_human in gs.player_setup_order: # Should be the two human players
            if p_human.armies_placed_in_setup < p_human.initial_armies_pool:
                all_human_done = False; break

        if all_human_done: # Engine should transition phase when last army placed by player_places_initial_armies_2p
            if gs.current_game_phase == "SETUP_2P_PLACE_REMAINING": # If engine hasn't transitioned
                 self.log_turn_info("All 2P human armies placed, but phase not transitioned by engine. Forcing.")
                 # This part is complex as engine's player_places_initial_armies_2p should handle final transition
                 # For now, assume engine handles it. If orchestrator finds itself here and all done, it's a sync issue.
            return True # Let main loop pick up new REINFORCE phase.

        if self.ai_is_thinking: return True

        if self.ai_action_result:
            action_to_process = self.ai_action_result
            self.ai_action_result = None
            player_name_who_acted = self.active_ai_player_name
            self.active_ai_player_name = None

            action_data = action_to_process.get("action")
            # AI's action for "SETUP_2P_PLACE_ARMIES_TURN" should be a dict containing
            # "own_army_placements": list[tuple[str, int]] and "neutral_army_placement": tuple[str, int] | None
            if action_data and action_data.get("type") == "SETUP_2P_PLACE_ARMIES_TURN":
                own_placements = action_data.get("own_army_placements")
                neutral_placement = action_data.get("neutral_army_placement")
                if own_placements is not None : # Check presence, engine will validate content
                    log = self.engine.player_places_initial_armies_2p(player_name_who_acted, own_placements, neutral_placement)
                    self.log_turn_info(f"{player_name_who_acted} (2P Setup Place): {log['message']}")
                else:
                    self.log_turn_info(f"Invalid/missing own_army_placements from {player_name_who_acted} for 2P setup: {action_data}")
            elif action_data and action_data.get("type") == "SETUP_2P_DONE_PLACING":
                 self.log_turn_info(f"{player_name_who_acted} is done with 2P setup placing.")
                 # Engine will advance player turn.
            else:
                self.log_turn_info(f"Invalid action from {player_name_who_acted} during SETUP_2P_PLACE_REMAINING: {action_data}")

            self._update_gui_full_state()
            self.has_logged_current_turn_player_phase = False
            return True

        current_setup_player_obj, current_setup_agent = self._get_current_setup_player_and_agent()
        if not current_setup_player_obj or not current_setup_agent:
            self.log_turn_info("No current setup player/agent for 2P placing. Game might stall.")
            return False # Stall

        if not self.has_logged_current_turn_player_phase:
            self.log_turn_info(f"Phase: SETUP_2P_PLACE_REMAINING - {current_setup_player_obj.name}'s turn.")
            self.has_logged_current_turn_player_phase = True

        valid_actions = self.engine.get_valid_actions(current_setup_player_obj) # Should be one composite action
        if not valid_actions or valid_actions[0].get("type") != "SETUP_2P_PLACE_ARMIES_TURN":
            if valid_actions and valid_actions[0].get("type") == "SETUP_2P_DONE_PLACING":
                # Player has no more armies, this is fine, orchestrator will cycle.
                self.log_turn_info(f"{current_setup_player_obj.name} has no more armies for 2P setup. Will cycle.")
                # We need to advance the engine's current_setup_player_index here if engine doesn't.
                # player_places_initial_armies_2p advances it.
                # If player is truly done, they should not be asked for action.
                # This indicates the main loop should cycle.
                self.has_logged_current_turn_player_phase = False # So next player logs correctly
                return True # Allow main loop to cycle player via engine's turn advancement in player_places_initial_armies_2p

            self.log_turn_info(f"Unexpected valid actions for {current_setup_player_obj.name} in 2P place remaining: {valid_actions}. Game might stall.")
            return True # Let it try again, maybe state resolves.

        # Prompt for the composite action
        action_template = valid_actions[0]
        prompt_add = (f"Place {action_template['player_armies_to_place_this_turn']} of your armies on your territories "
                      f"({action_template['player_owned_territories']}). "
                      f"Also, if neutral can place ({action_template['neutral_can_place']}), "
                      f"place 1 neutral army on a neutral territory ({action_template['neutral_owned_territories']}). "
                      "Provide action as: {'type': 'SETUP_2P_PLACE_ARMIES_TURN', 'own_army_placements': [('T1', count1), ...], 'neutral_army_placement': ('NT1', 1) or null}")
        self._execute_ai_turn_async(current_setup_agent, gs.to_json(), valid_actions, self.game_rules, prompt_add)
        return True

    def _handle_elimination_card_trade_loop(self, player_to_trade: GamePlayer, agent_to_trade: BaseAIAgent) -> bool:
        """Handles the mandatory card trading loop after a player elimination."""
        gs = self.engine.game_state
        self.log_turn_info(f"Player {player_to_trade.name} must trade cards due to elimination (hand size: {len(player_to_trade.hand)}).")

        trade_attempt_limit = 5 # Prevent infinite loops
        attempts = 0
        original_phase_before_trade_loop = gs.current_game_phase # Store to potentially restore or manage state

        while gs.elimination_card_trade_player_name == player_to_trade.name and attempts < trade_attempt_limit:
            attempts += 1
            self.log_turn_info(f"Elimination trade attempt {attempts} for {player_to_trade.name}. Hand: {len(player_to_trade.hand)}")

            # Check if condition is met (engine's get_valid_actions clears the flag if met)
            valid_actions = self.engine.get_valid_actions(player_to_trade) # This will update the flag if needed
            if gs.elimination_card_trade_player_name != player_to_trade.name:
                self.log_turn_info(f"{player_to_trade.name} no longer needs to trade for elimination (hand <= 4 or no sets).")
                break # Requirement met or impossible

            trade_actions = [va for va in valid_actions if va.get("type") == "TRADE_CARDS" and va.get("must_trade")]
            if not trade_actions:
                self.log_turn_info(f"No valid 'must_trade' actions for {player_to_trade.name} despite pending elimination trade. Hand: {len(player_to_trade.hand)}. Clearing flag.")
                gs.elimination_card_trade_player_name = None # Cannot proceed
                break

            # Get AI action for trading (synchronous for this sub-loop for simplicity now)
            # TODO: Could make this async like other actions if needed, but it's a sequence.
            prompt_add = "You MUST trade cards to reduce your hand size below 5 due to player elimination."
            ai_response = agent_to_trade.get_thought_and_action(gs.to_json(), trade_actions, self.game_rules, prompt_add)
            self.log_ai_thought(player_to_trade.name, ai_response.get("thought", "N/A (elimination trade)"))

            chosen_action = ai_response.get("action")
            if chosen_action and chosen_action.get("type") == "TRADE_CARDS":
                card_indices = chosen_action.get("card_indices")
                trade_result = self.engine.perform_card_trade(player_to_trade, card_indices)
                self.log_turn_info(f"{player_to_trade.name} mandatory trade: {trade_result.get('message')}")
                self._update_gui_full_state() # Update after each trade
                if not trade_result.get("success"):
                    self.log_turn_info(f"Mandatory trade by {player_to_trade.name} failed. This may stall the game if not resolved.")
                    # Potentially break or try to get another action. For now, let loop continue.
            else:
                self.log_turn_info(f"{player_to_trade.name} failed to provide a valid TRADE_CARDS action during mandatory elimination trade. Action: {chosen_action}")
                # This is an AI error. Break loop to avoid getting stuck. Orchestrator might need to handle this.
                gs.elimination_card_trade_player_name = None # Clear flag to prevent stall
                break

        if attempts >= trade_attempt_limit:
            self.log_turn_info(f"Reached trade attempt limit for {player_to_trade.name} during elimination card trade. Clearing flag.")
            gs.elimination_card_trade_player_name = None

        self.log_turn_info(f"Finished elimination card trade loop for {player_to_trade.name}. Hand size: {len(player_to_trade.hand)}")
        # The game should now proceed with any pending post-attack fortification or next phase actions.
        # The main advance_game_turn loop will call get_valid_actions again, which will now not be overridden by this.
        return True # Indicate trade loop finished, main loop can re-evaluate.


    def advance_game_turn(self) -> bool:
        gs = self.engine.game_state

        if self.engine.is_game_over():
            winner = self.engine.is_game_over()
            win_msg = f"\n--- GAME OVER! Winner is {winner.name if winner else 'Unknown'}! ---"
            self.log_turn_info(win_msg); print(win_msg)
            self.global_chat.broadcast("GameSystem", win_msg)
            if self.gui and self.game_running_via_gui: self.gui.show_game_over_screen(winner.name if winner else "N/A")
            return False
        if gs.current_turn_number >= self.max_turns and not gs.current_game_phase.startswith("SETUP_"):
            timeout_msg = f"\n--- GAME OVER! Reached max turns ({self.max_turns}). ---"
            self.log_turn_info(timeout_msg); print(timeout_msg)
            self.global_chat.broadcast("GameSystem", timeout_msg)
            if self.gui and self.game_running_via_gui: self.gui.show_game_over_screen("Draw/Timeout")
            return False

        current_phase = gs.current_game_phase
        self.log_turn_info(f"Orchestrator: Advancing turn. Current phase: {current_phase}")

        # --- Setup Phase Handling ---
        if current_phase == "SETUP_START": # Should be handled by initial call to initialize_game_from_map
            self.log_turn_info("Error: Game in SETUP_START. Initialization might be incomplete.")
            # Attempt to move to next logical step if possible
            if self.is_two_player_mode: gs.current_game_phase = "SETUP_2P_DEAL_CARDS"
            else: gs.current_game_phase = "SETUP_DETERMINE_ORDER"
            return True
        elif current_phase == "SETUP_DETERMINE_ORDER":
            return self._handle_setup_determine_order()
        elif current_phase == "SETUP_CLAIM_TERRITORIES":
            return self._handle_setup_claim_territories()
        elif current_phase == "SETUP_PLACE_ARMIES":
            return self._handle_setup_place_armies()
        elif current_phase == "SETUP_2P_DEAL_CARDS":
            return self._handle_setup_2p_deal_cards()
        elif current_phase == "SETUP_2P_PLACE_REMAINING":
            return self._handle_setup_2p_place_remaining()

        # --- Regular Game Turn Logic (Post-Setup) ---
        self.turn_action_log.clear() # Clear log for the new turn/main phase part

        # Determine current player and agent for regular turns
        # Note: get_current_player() in engine is for regular turns, skips neutral.
        # get_current_setup_player() is for setup turns.
        current_player_obj = gs.get_current_player()
        if not current_player_obj or current_player_obj.is_neutral: # Should always be a human player here
            self.log_turn_info(f"Error: No valid current human player for phase {current_phase}. Current player from engine: {current_player_obj.name if current_player_obj else 'None'}. Halting.")
            return False

        current_player_agent = self.get_agent_for_player(current_player_obj)
        if not current_player_agent: # Should not happen if player is human
            self.log_turn_info(f"Error: No AI agent for current player {current_player_obj.name} in phase {current_phase}. Skipping turn.")
            self.engine.next_turn()
            self.has_logged_current_turn_player_phase = False
            if self.gui: self._update_gui_full_state()
            return True

        if not self.has_logged_current_turn_player_phase:
            header = f"\n--- Turn {gs.current_turn_number} | Player: {current_player_obj.name} ({current_player_obj.color}) | Phase: {current_phase} ---"
            self.log_turn_info(header); print(header)
            self.has_logged_current_turn_player_phase = True

        if not self.ai_is_thinking and self.gui: self._update_gui_full_state()

        # --- Mandatory Elimination Card Trade Check ---
        # This needs to happen before Post Attack Fortify or other actions if flag is set for current player.
        if gs.elimination_card_trade_player_name == current_player_obj.name:
            self.log_turn_info(f"Player {current_player_obj.name} has pending elimination card trades.")
            # The loop will be managed here, AI calls made, until flag is cleared or attempts exhausted.
            # This needs to be integrated with the async AI call mechanism if we want spinner for these trades.
            # For now, let's assume _handle_elimination_card_trade_loop is synchronous for simplicity of this step.
            trade_loop_continue = self._handle_elimination_card_trade_loop(current_player_obj, current_player_agent)
            if not trade_loop_continue: # Problem in trade loop
                 self.log_turn_info(f"Problem during elimination card trade for {current_player_obj.name}. Game may be unstable.")
                 # Fall through, next get_valid_actions will reflect if flag is cleared.
            # After trade loop, re-fetch valid actions as game state (and flag) might have changed.
            # The main phase logic below will then pick up.
            # No immediate 'return True' here, let the main phase logic proceed with updated state.
            self.has_logged_current_turn_player_phase = False # Re-log phase info if needed
            self._update_gui_full_state() # Update GUI after trades.


        # --- AI Thinking & Action Processing Logic (copied and adapted from before) ---
        # This section handles the asynchronous AI thinking and subsequent action processing.

        action_processed_in_current_tick = False
        phase_when_action_was_initiated = None # Store phase context for processing

        if self.ai_is_thinking:
            if self.current_ai_thread and self.current_ai_thread.is_alive():
                # AI is still thinking
                if not self.has_logged_ai_is_thinking_for_current_action:
                    print(f"Orchestrator: AI ({self.active_ai_player_name}) is still thinking. GUI should be responsive.")
                    self.has_logged_ai_is_thinking_for_current_action = True
                if self.gui: self.gui.update(self.engine.game_state, self.global_chat.get_log(), self.private_chat_manager.get_all_conversations())
                return True  # AI is busy, game loop continues
            else:
                # AI thread has finished
                print(f"Orchestrator: AI ({self.active_ai_player_name}) thread finished.")
                self.ai_is_thinking = False
                self.has_logged_ai_is_thinking_for_current_action = False
                action_to_process = self.ai_action_result

                if action_to_process:
                    print(f"Orchestrator: Processing AI action: {action_to_process.get('action')}")
                    self.log_ai_thought(self.active_ai_player_name or "UnknownAI", action_to_process.get('thought', 'N/A'))

                    # Store the phase in which the AI action was *initiated* or is being processed for.
                    # self.current_ai_context might hold the phase if it was set during _execute_ai_turn_async
                    # However, relying on self.engine.game_state.current_game_phase is also an option if context is complex.
                    # For robustness, let's assume the current game phase is the context for the action.
                    phase_when_action_was_initiated = self.engine.game_state.current_game_phase # Capture phase before processing

                    if phase_when_action_was_initiated == "REINFORCE":
                        self._process_reinforce_ai_action(current_player_obj, current_player_agent, action_to_process)
                    elif phase_when_action_was_initiated == "ATTACK":
                        self._process_attack_ai_action(current_player_obj, current_player_agent, action_to_process)
                    elif phase_when_action_was_initiated == "FORTIFY":
                        self._process_fortify_ai_action(current_player_obj, current_player_agent, action_to_process)
                        # After processing a fortify action, the turn should end.
                        # The logic below will handle calling next_turn().
                    action_processed_in_current_tick = True
                else:
                    print(f"Orchestrator: AI ({self.active_ai_player_name}) action result was None. Problem in thread.")
                    # Handling this might involve ending the current phase prematurely or turn.
                    # For now, if it's FORTIFY, it will proceed to next_turn. Others might need specific error handling.
                    if self.engine.game_state.current_game_phase == "FORTIFY":
                        action_processed_in_current_tick = True # Treat as if processed to allow turn end

                self.ai_action_result = None # Clear after processing
                self.active_ai_player_name = None
                self.current_ai_context = None # Clear context after processing
                self._update_gui_full_state() # Update GUI after processing AI action
                if self.engine.is_game_over(): return self.advance_game_turn() # Handle game over immediately

        # --- Phase Logic: Initiate AI Action or Advance Turn/Phase ---
        # This section runs if AI is not currently thinking (either finished or never started for this phase part)

        if not self.ai_is_thinking:
            current_game_phase = self.engine.game_state.current_game_phase

            # If a FORTIFY action was just processed (either a FORTIFY move or END_TURN),
            # or if an AI error occurred during FORTIFY, the turn must end.
            # We use phase_when_action_was_initiated to know if _process_fortify_ai_action was just called.
            if phase_when_action_was_initiated == "FORTIFY" and action_processed_in_current_tick:
                if not self.engine.is_game_over(): # Ensure game isn't over before ending turn
                    self.engine.next_turn()
                    self.has_logged_current_turn_player_phase = False
                    new_player = self.engine.game_state.get_current_player()
                    print(f"--- End of Turn for {current_player_obj.name}. Next player: {new_player.name if new_player else 'N/A'} ---")
                    self._update_gui_full_state()
                if self.engine.is_game_over(): return self.advance_game_turn() # Check again after next_turn
                return True # Turn ended, game continues with next player or new turn

            # If not ending turn due to FORTIFY completion, proceed with normal phase initiation.

            max_phase_transitions_per_tick = 3 # Safety break for chained phase changes without AI action
            transitions_this_tick = 0

            # Loop to handle phase transitions that occur without AI thinking (e.g., ATTACK -> FORTIFY if no attacks)
            while transitions_this_tick < max_phase_transitions_per_tick and not self.ai_is_thinking:
                transitions_this_tick += 1
                current_phase_before_initiation = self.engine.game_state.current_game_phase

                if current_phase_before_initiation == "REINFORCE":
                    self._initiate_reinforce_ai_action(current_player_obj, current_player_agent)
                elif not self.engine.is_game_over() and current_phase_before_initiation == "ATTACK":
                    self._initiate_attack_ai_action(current_player_obj, current_player_agent)
                elif not self.engine.is_game_over() and current_phase_before_initiation == "FORTIFY":
                    self._initiate_fortify_ai_action(current_player_obj, current_player_agent)
                else:
                    # Unknown phase or game is over and wasn't caught earlier
                    break # Exit loop if phase is not one of the known ones or game over

                # If AI started thinking as a result of the initiation, break the loop.
                if self.ai_is_thinking:
                    break

                # If the phase changed during initiation (e.g. ATTACK immediately went to FORTIFY)
                # and AI is still not thinking, loop again to initiate the new phase.
                if self.engine.game_state.current_game_phase == current_phase_before_initiation:
                    # Phase did not change, and AI is not thinking, so break (something else is wrong or phase is done)
                    break

            if transitions_this_tick >= max_phase_transitions_per_tick:
                self.log_turn_info(f"Orchestrator: Exceeded max phase transitions ({max_phase_transitions_per_tick}) in a single tick for player {current_player_obj.name}. This might indicate a problem.")

            if self.gui: self._update_gui_full_state()
            if self.engine.is_game_over(): return self.advance_game_turn() # Check game over after potential phase changes/initiations
            if self.ai_is_thinking: return True # AI action was successfully initiated

            # Fallback: If AI is still not thinking, and current phase is FORTIFY, then end the turn.
            # This handles cases where FORTIFY phase was reached, _initiate_fortify_ai_action was called,
            # but for some reason (e.g., AI error or unexpected empty valid_actions for fortify) AI didn't start.
            if not self.ai_is_thinking and self.engine.game_state.current_game_phase == "FORTIFY":
                if not self.engine.is_game_over(): # Ensure game isn't over before trying to end turn
                    self.log_turn_info(f"Orchestrator: Fallback - Fortify phase, AI not thinking after initiation attempt. Ending turn for {current_player_obj.name}.")
                    self.engine.next_turn()
                    self.has_logged_current_turn_player_phase = False
                    new_player = self.engine.game_state.get_current_player()
                    print(f"--- End of Turn for {current_player_obj.name} (fallback after fortify init). Next player: {new_player.name if new_player else 'N/A'} ---")
                    self._update_gui_full_state()
                if self.engine.is_game_over(): return self.advance_game_turn() # Check again
                return True # Game continues with next player


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
        self.log_turn_info(f"Orchestrator: Initiating ATTACK/PAF AI action for {player.name}.") # Changed print to log_turn_info
        game_state_json = self.engine.game_state.to_json()

        paf_required = self.engine.game_state.requires_post_attack_fortify
        self.log_turn_info(f"Orchestrator: _initiate_attack_ai_action for {player.name}. PAF required: {paf_required}.")

        if paf_required:
            # Valid actions should primarily be PAF if required.
            valid_actions = self.engine.get_valid_actions(player)
            self.log_turn_info(f"Orchestrator: PAF is required for {player.name}. Valid actions from engine: {valid_actions}")
            paf_actions = [va for va in valid_actions if va['type'] == "POST_ATTACK_FORTIFY"]

            if not paf_actions:
                self.log_turn_info(f"CRITICAL ERROR: PAF required for {player.name} but no PAF action generated. Conquest context: {self.engine.game_state.conquest_context}. Clearing flag and moving to FORTIFY for safety.");
                self.engine.game_state.requires_post_attack_fortify = False
                self.engine.game_state.conquest_context = None
                self.engine.game_state.current_game_phase = "FORTIFY"
                self.has_logged_current_turn_player_phase = False
                self.ai_is_thinking = False
                if self.gui: self._update_gui_full_state()
                # Return here because we are not initiating an AI action for ATTACK or PAF.
                # The main loop in advance_game_turn will pick up the new FORTIFY phase.
                return
            else:
                paf_detail = paf_actions[0]
                from_terr_obj = self.engine.game_state.territories.get(paf_detail['from_territory'])
                from_army_count = from_terr_obj.army_count if from_terr_obj else "N/A"
                paf_prompt = (f"You conquered {paf_detail['to_territory']}. You MUST move between {paf_detail['min_armies']} and {paf_detail['max_armies']} armies "
                              f"from {paf_detail['from_territory']} (currently has {from_army_count} armies) "
                              f"to the newly conquered {paf_detail['to_territory']}.")
                self.log_turn_info(f"Orchestrator: Prompting {player.name} for PAF with actions: {paf_actions}. Prompt: {paf_prompt}")
                self._execute_ai_turn_async(agent, game_state_json, paf_actions, self.game_rules, paf_prompt)
                self.log_turn_info(f"Orchestrator: PAF AI action initiated for {player.name}. ai_is_thinking is now: {self.ai_is_thinking}")
                return # AI is now thinking about PAF, advance_game_turn will detect ai_is_thinking.

        # If no PAF pending, proceed with regular attack options
        valid_actions = self.engine.get_valid_actions(player)
        self.log_turn_info(f"Orchestrator: Regular ATTACK phase for {player.name}. Valid actions from engine: {valid_actions}")

        if not valid_actions or (len(valid_actions) == 1 and valid_actions[0]['type'] == "END_ATTACK_PHASE"):
            self.log_turn_info(f"Orchestrator: No actual attack options (or only END_ATTACK_PHASE) for {player.name}. Transitioning phase to FORTIFY directly in _initiate_attack_ai_action.")
            self.engine.game_state.current_game_phase = "FORTIFY"
            self.has_logged_current_turn_player_phase = False
            self.ai_is_thinking = False # Ensure AI is not marked as thinking for ATTACK phase
            if self.gui: self._update_gui_full_state()
            # No AI action is initiated for ATTACK in this case.
            # The while loop in advance_game_turn needs to re-evaluate for the new FORTIFY phase.
            # We return here because this function's job (initiating an ATTACK AI action) is done (it decided not to).
            return

        # Proceed to ask AI for an attack action
        attacks_this_turn = self.current_ai_context.get("attacks_this_turn", 0) if self.current_ai_context else 0
        prompt_elements = [f"It is your attack phase. You have made {attacks_this_turn} attacks this turn.", f"You have {len(player.hand)} cards."]
        other_players_info = []
        for p_other in self.engine.game_state.players:
            if p_other != player: other_players_info.append(f"{p_other.name}({len(p_other.hand)}c, {len(p_other.territories)}t)")
        if other_players_info: prompt_elements.append("Opponents: " + "; ".join(other_players_info))
        system_prompt_addition = " ".join(prompt_elements)

        self.log_turn_info(f"Orchestrator: Prompting {player.name} for regular ATTACK action with {len(valid_actions)} options. System prompt addition: {system_prompt_addition}")
        self._execute_ai_turn_async(agent, game_state_json, valid_actions, self.game_rules, system_prompt_addition)
        self.log_turn_info(f"Orchestrator: Regular ATTACK AI action initiated for {player.name}. ai_is_thinking is now: {self.ai_is_thinking}")

        if self.current_ai_context:
            self.current_ai_context["attacks_this_turn"] = attacks_this_turn


    def _process_attack_ai_action(self, player: GamePlayer, agent: BaseAIAgent, ai_response: dict):
        """Processes the AI's action for the ATTACK phase."""
        self.log_turn_info(f"Orchestrator: Processing ATTACK AI action for {player.name}. AI Response: {ai_response}")
        action = ai_response.get("action")

        # Retrieve attacks_this_turn from context if available, default to 0
        attacks_this_turn = 0
        if self.current_ai_context and isinstance(self.current_ai_context.get("attacks_this_turn"), int):
            attacks_this_turn = self.current_ai_context["attacks_this_turn"]

        if not action or not isinstance(action, dict) or "type" not in action:
            self.log_turn_info(f"Orchestrator: Player {player.name} provided malformed or missing ATTACK action: {action}. AI will be prompted again for ATTACK phase.")
            self.ai_is_thinking = False # Allow re-triggering AI for next attack sub-step.
            if self.gui: self._update_gui_full_state()
            return

        action_type = action["type"]
        self.log_turn_info(f"Orchestrator: Player {player.name} ATTACK action type: '{action_type}'. Details: {action}")

        if action_type == "POST_ATTACK_FORTIFY":
            num_to_move = action.get("num_armies")
            conquest_ctx = self.engine.game_state.conquest_context
            min_movable_default = conquest_ctx.get('min_movable', 1) if conquest_ctx else 1

            if not isinstance(num_to_move, int): # Basic type check
                self.log_turn_info(f"Orchestrator: {player.name} PAF num_armies invalid type: {num_to_move}. Defaulting to min: {min_movable_default}.")
                num_to_move = min_movable_default

            # perform_post_attack_fortify will validate min/max bounds based on conquest_context
            fortify_log = self.engine.perform_post_attack_fortify(player, num_to_move)
            self.log_turn_info(f"Orchestrator: {player.name} PAF engine call result: {fortify_log.get('message', 'PAF outcome unknown.')}")
            self.log_turn_info(f"Orchestrator: PAF for {player.name} complete. PAF required is now: {self.engine.game_state.requires_post_attack_fortify}")

            self.ai_is_thinking = False # Ready for next attack or end phase.
            if self.engine.is_game_over():
                 self.ai_is_thinking = False # Ensure AI is not stuck if game ends. Fall through to GUI update.

        elif action_type == "ATTACK":
            from_territory_name = action.get("from")
            to_territory_name = action.get("to")
            num_armies = action.get("num_armies")

            if not all(isinstance(param, str) for param in [from_territory_name, to_territory_name]) or \
               not isinstance(num_armies, int) or num_armies <= 0:
                self.log_turn_info(f"Orchestrator: {player.name} invalid ATTACK parameters: from='{from_territory_name}', to='{to_territory_name}', num_armies='{num_armies}'. AI will be prompted again.")
                # No actual attack performed, AI needs to retry.
                self.ai_is_thinking = False # Allow re-triggering for ATTACK phase
                if self.gui: self._update_gui_full_state()
                return # Return to main loop to re-initiate AI for attack phase.

            # Check if defender is Neutral in a 2-player game
            defender_territory_obj = self.engine.game_state.territories.get(to_territory_name)
            explicit_defense_dice = None
            if self.is_two_player_mode and defender_territory_obj and \
               defender_territory_obj.owner and defender_territory_obj.owner.is_neutral:

                other_human_player = None
                for p_obj in self.engine.game_state.players:
                    if not p_obj.is_neutral and p_obj.name != player.name: # player is the attacker
                        other_human_player = p_obj
                        break

                if other_human_player:
                    other_human_agent = self.get_agent_for_player(other_human_player)
                    if other_human_agent:
                        self.log_turn_info(f"Neutral territory {to_territory_name} attacked by {player.name}. Prompting {other_human_player.name} for defense dice.")

                        defense_dice_options = []
                        if defender_territory_obj.army_count >= 1: defense_dice_options.append({"type": "CHOOSE_DEFENSE_DICE", "num_dice": 1})
                        if defender_territory_obj.army_count >= 2: defense_dice_options.append({"type": "CHOOSE_DEFENSE_DICE", "num_dice": 2})

                        if defense_dice_options:
                            # This is a nested, synchronous AI call for simplicity here.
                            # TODO: Could be made async if this causes noticeable delays.
                            def_prompt = (f"Player {player.name} is attacking neutral territory {to_territory_name} "
                                          f"(armies: {defender_territory_obj.army_count}). "
                                          f"You ({other_human_player.name}) must choose how many dice Neutral will defend with.")
                            # Use a simplified game_rules for this specific choice.
                            def_rules = "Choose one action from the list: {'type': 'CHOOSE_DEFENSE_DICE', 'num_dice': 1_or_2}"

                            # Temporarily set active AI for this sub-call for logging purposes
                            original_active_ai_name = self.active_ai_player_name
                            self.active_ai_player_name = other_human_agent.player_name

                            defense_choice_response = other_human_agent.get_thought_and_action(
                                self.engine.game_state.to_json(), defense_dice_options, def_rules, def_prompt
                            )
                            self.log_ai_thought(other_human_agent.player_name, defense_choice_response.get("thought", "N/A (defense dice choice)"))
                            self.active_ai_player_name = original_active_ai_name # Restore

                            defense_action = defense_choice_response.get("action")
                            if defense_action and defense_action.get("type") == "CHOOSE_DEFENSE_DICE":
                                explicit_defense_dice = defense_action.get("num_dice")
                                if not (explicit_defense_dice == 1 or (explicit_defense_dice == 2 and defender_territory_obj.army_count >=2)):
                                    self.log_turn_info(f"Warning: Invalid defense dice choice {explicit_defense_dice} from {other_human_player.name}. Defaulting to 1 die.")
                                    explicit_defense_dice = 1 if defender_territory_obj.army_count >=1 else 0
                            else: # AI failed to choose or malformed action
                                self.log_turn_info(f"Warning: {other_human_player.name} failed to choose defense dice. Defaulting to 1 die.")
                                explicit_defense_dice = 1 if defender_territory_obj.army_count >=1 else 0
                        else: # Neutral territory has 0 armies
                            explicit_defense_dice = 0
                    else: # No agent for other human player
                        self.log_turn_info(f"Warning: No AI agent for other human player {other_human_player.name} to choose neutral defense. Defaulting dice.")
                        explicit_defense_dice = 1 if defender_territory_obj.army_count >=1 else 0 # Or some other default
                else: # Should not happen in 2P mode
                    self.log_turn_info("Warning: Could not find other human player in 2P mode for neutral defense. Defaulting dice.")
                    explicit_defense_dice = 1 if defender_territory_obj.army_count >=1 else 0

            # Call engine's perform_attack
            attack_log = self.engine.perform_attack(from_territory_name, to_territory_name, num_armies, explicit_defense_dice)
            self.log_turn_info(f"Orchestrator: Engine perform_attack log for {player.name}: {attack_log}")

            if "error" not in attack_log: # Only increment if attack was valid and processed
                attacks_this_turn += 1
                if self.current_ai_context: self.current_ai_context["attacks_this_turn"] = attacks_this_turn
                self.log_turn_info(f"Orchestrator: {player.name} attacks_this_turn incremented to: {attacks_this_turn}")

                if "error" not in attack_log:
                    if attack_log.get("conquered"):
                        self.log_turn_info(f"Orchestrator: {player.name} conquered {to_territory_name}. PAF required: {self.engine.game_state.requires_post_attack_fortify}. Card drawn: {attack_log.get('card_drawn') is not None}.")
                        if attack_log.get("eliminated_player_name"):
                             elim_name = attack_log.get("eliminated_player_name")
                             self.log_turn_info(f"Orchestrator: {player.name} ELIMINATED {elim_name}!")
                             self.global_chat.broadcast("GameSystem", f"{player.name} eliminated {elim_name}!")
                             self.handle_player_elimination(elim_name)
                             if self.engine.is_game_over():
                                 self.ai_is_thinking = False # Ensure AI not stuck
                                 # Game over will be handled by advance_game_turn loop.
                                 # Update GUI and return to let advance_game_turn handle game over.
                                 if self.gui: self._update_gui_full_state()
                                 return
                # else: Error already logged by engine or in attack_log.
            self.ai_is_thinking = False # AI ready for next decision (PAF, another attack, or end phase).

        elif action_type == "END_ATTACK_PHASE":
            self.log_turn_info(f"Orchestrator: {player.name} chose to end ATTACK phase. Transitioning to FORTIFY.")
            self.engine.game_state.current_game_phase = "FORTIFY"
            self.has_logged_current_turn_player_phase = False
            self.ai_is_thinking = False
            # print(f"Orchestrator: {player.name} ATTACK phase ended. Transitioning to FORTIFY.") # Replaced by log

        elif action_type == "GLOBAL_CHAT":
            message = action.get("message", "")
            if isinstance(message, str) and message.strip():
                self.global_chat.broadcast(player.name, message)
                self.log_turn_info(f"Orchestrator: {player.name} (Global Chat): {message}")
            else:
                self.log_turn_info(f"Orchestrator: {player.name} attempted GLOBAL_CHAT with empty or invalid message.")
            self.ai_is_thinking = False

        elif action_type == "PRIVATE_CHAT":
            target_player_name = action.get("target_player_name")
            initial_message = action.get("initial_message")

            if not isinstance(target_player_name, str) or not isinstance(initial_message, str) or not initial_message.strip():
                self.log_turn_info(f"Orchestrator: {player.name} invalid PRIVATE_CHAT parameters: target='{target_player_name}', message_empty='{not initial_message.strip() if isinstance(initial_message, str) else True}'.")
            else:
                target_agent = self.ai_agents.get(target_player_name)
                if not target_agent:
                    self.log_turn_info(f"Orchestrator: {player.name} invalid PRIVATE_CHAT target: Player '{target_player_name}' not found or not an AI.")
                elif target_agent == agent:
                    self.log_turn_info(f"Orchestrator: {player.name} attempted PRIVATE_CHAT with self. Action ignored.")
                else:
                    self.log_turn_info(f"Orchestrator: Initiating private chat between {player.name} and {target_player_name}.")
                    current_game_state_json = self.engine.game_state.to_json()
                    conversation_log_entries = self.private_chat_manager.run_conversation(
                        initiating_agent=agent, receiving_agent=target_agent,
                        initial_message=initial_message, game_state_json=current_game_state_json,
                        game_rules=self.game_rules
                    )
                    summary_msg = f"Private chat between {player.name} and {target_player_name} concluded ({len(conversation_log_entries)} exchanges)."
                    if self.gui: self.gui.log_action(summary_msg)
                    self.log_turn_info(f"Orchestrator: {summary_msg}")
            self.ai_is_thinking = False

        else:
            self.log_turn_info(f"Orchestrator: Player {player.name} provided an unknown ATTACK action type: '{action_type}'. AI will be prompted again.")
            self.ai_is_thinking = False

        self.log_turn_info(f"Orchestrator: End of _process_attack_ai_action for {player.name}. ai_is_thinking: {self.ai_is_thinking}, current_phase: {self.engine.game_state.current_game_phase}")
        if self.gui: self._update_gui_full_state()

    def _initiate_fortify_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        """Gathers info and starts the AI thinking for the FORTIFY phase."""
        self.log_turn_info(f"Orchestrator: Initiating FORTIFY AI action for {player.name}. Player has_fortified_this_turn: {player.has_fortified_this_turn}")
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player) # FORTIFY or END_TURN
        self.log_turn_info(f"Orchestrator: Valid actions for {player.name} in FORTIFY: {valid_actions}")

        if not valid_actions:
             self.log_turn_info(f"CRITICAL: No valid FORTIFY actions for {player.name} (should always have END_TURN). Ending turn to prevent issues.");
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
        self.log_turn_info(f"Orchestrator: Fortify prompt addition for {player.name}: {prompt_add}")
        self._execute_ai_turn_async(agent, game_state_json, valid_actions, self.game_rules, system_prompt_addition=prompt_add)

    def _process_fortify_ai_action(self, player: GamePlayer, agent: BaseAIAgent, ai_response: dict):
        """Processes the AI's action for the FORTIFY phase."""
        self.log_turn_info(f"Orchestrator: Processing FORTIFY AI action for {player.name}. AI Response: {ai_response}")
        action = ai_response.get("action")
        self.log_turn_info(f"Orchestrator: Player {player.name} status before processing fortify action: has_fortified_this_turn = {player.has_fortified_this_turn}")

        if not action or not isinstance(action, dict) or "type" not in action:
            self.log_turn_info(f"{player.name} provided malformed or missing FORTIFY action: {action}. Ending turn as per rules.")
            # Fall through to end turn logic, has_fortified_this_turn remains unchanged by this path.
        else:
            action_type = action["type"]
            self.log_turn_info(f"{player.name} chose FORTIFY action: {action_type} - Full Details: {action}")

            if action_type == "FORTIFY":
                if player.has_fortified_this_turn:
                     self.log_turn_info(f"{player.name} attempted to FORTIFY again in the same turn (has_fortified_this_turn was True). Action ignored. Turn will end.")
                else:
                    from_territory_name = action.get("from")
                    to_territory_name = action.get("to")
                    num_armies = action.get("num_armies")

                    if not all(isinstance(param, str) for param in [from_territory_name, to_territory_name]) or \
                       not isinstance(num_armies, int) or num_armies < 0:
                        self.log_turn_info(f"{player.name} provided invalid FORTIFY parameters: from='{from_territory_name}', to='{to_territory_name}', num_armies='{num_armies}'. No fortification performed. Turn will end.")
                    else:
                        # Perform the fortification. Engine will set has_fortified_this_turn if successful & num_armies > 0.
                        fortify_result = self.engine.perform_fortify(from_territory_name, to_territory_name, num_armies)
                        log_message = fortify_result.get('message', f"Fortify attempt by {player.name} from {from_territory_name} to {to_territory_name} with {num_armies} armies.")
                        self.log_turn_info(f"Engine fortify result for {player.name}: {log_message}. Success: {fortify_result.get('success', False)}")
                        # player.has_fortified_this_turn is updated by the engine.

            elif action_type == "END_TURN":
                self.log_turn_info(f"{player.name} explicitly chose to END_TURN during fortify phase.")
                # player.has_fortified_this_turn remains as it was (e.g., false if they didn't fortify).

            else: # Unknown action type for fortify phase
                self.log_turn_info(f"{player.name} provided an unknown action type '{action_type}' during FORTIFY phase. Turn will end.")

        # Log status after processing
        self.log_turn_info(f"Orchestrator: Player {player.name} status after processing fortify action: has_fortified_this_turn = {player.has_fortified_this_turn}")

        # Regardless of the action (FORTIFY, END_TURN, or malformed), the fortify phase processing for this AI action is complete.
        # The main game loop (`advance_game_turn`) will call `self.engine.next_turn()` due to the logic implemented in the previous step.
        self.ai_is_thinking = False # Player's AI is no longer thinking for this specific action.
        # self.has_logged_current_turn_player_phase = False # This is reset by advance_game_turn when next_turn() is actually called.

        self.log_turn_info(f"Orchestrator: {player.name} FORTIFY phase AI processing complete. Turn will now end via main loop.")
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
