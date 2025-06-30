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
from .ai.llama_agent import LlamaAgent
from .ai.qwen_agent import QwenAgent
from .ai.mistral_agent import MistralAgent
from .game_orchestrator_diplomacy_helper import _process_diplomatic_action # Import the helper
import threading # For asynchronous AI calls

import json # For loading player configs if any
import time # For potential delays
from datetime import datetime # For logging timestamp
import os # For log directory creation

class GameOrchestrator:
    def __init__(self,
                 player_configs_override: list | None = None,
                 default_player_setup_file: str = "player_config.json",
                 game_mode: str = "standard",
                 geojson_data_str: str | None = None): # Added geojson_data_str

        self.game_mode = game_mode
        print(f"DEBUG: GameOrchestrator.__init__ - Received game_mode: {self.game_mode}")

        map_file_to_load = "map_config.json" # Default for standard
        self.map_display_config_to_load = "map_display_config.json" # Default for standard

        if self.game_mode == "world_map":
            if not geojson_data_str:
                # This case should ideally be caught by main.py if world_map is chosen without data.
                print("ERROR: GameOrchestrator - GeoJSON data string MUST be provided for 'world_map' mode but was None. Attempting to load default.")
                # Fallback to try and load the default polygon file directly if main.py somehow missed it.
                # This is a safeguard, main.py should prevent this.
                default_geojson_path = "map_display_config_polygons.json"
                if os.path.exists(default_geojson_path):
                    try:
                        with open(default_geojson_path, 'r', encoding='utf-8') as f:
                            geojson_data_str = f.read()
                        print(f"DEBUG: GameOrchestrator - Fallback: Loaded GeoJSON from {default_geojson_path}")
                    except Exception as e:
                        raise ValueError(f"Fallback load of {default_geojson_path} failed: {e}")
                else:
                    raise ValueError(f"GeoJSON data string must be provided for 'world_map' mode and default '{default_geojson_path}' not found.")


            # Define paths for generated config files
            generated_map_dir = "generated_maps"
            os.makedirs(generated_map_dir, exist_ok=True) # Ensure directory exists
            map_file_to_load = os.path.join(generated_map_dir, "world_map_config.json")
            self.map_display_config_to_load = os.path.join(generated_map_dir, "world_map_display_config.json")
            print(f"DEBUG: GameOrchestrator.__init__ - world_map mode: map_file_to_load set to '{map_file_to_load}', map_display_config_to_load set to '{self.map_display_config_to_load}'")

            print(f"Initializing World Map game mode. Processing GeoJSON...")
            try:
                geojson_data = json.loads(geojson_data_str)
                from .utils.map_processor import MapProcessor # Import here
                # Assuming GUI dimensions are known or can be accessed (e.g., from gui.py constants)
                # For now, using constants that might be defined in gui.py or here.
                # These should ideally come from a shared config or GUI constants.
                MAP_AREA_WIDTH_FOR_PROCESSING = 900
                MAP_AREA_HEIGHT_FOR_PROCESSING = 720
                processor = MapProcessor(geojson_data, MAP_AREA_WIDTH_FOR_PROCESSING, MAP_AREA_HEIGHT_FOR_PROCESSING)
                processor.save_configs(map_file_to_load, self.map_display_config_to_load)
                print(f"World map configurations generated: {map_file_to_load}, {self.map_display_config_to_load}")
                # DEBUG: Inspect content of the generated display config
                try:
                    with open(self.map_display_config_to_load, 'r') as f_inspect:
                        # Attempt to load it as JSON to check structure
                        f_inspect.seek(0)
                        loaded_json_for_debug = json.load(f_inspect)
                        if isinstance(loaded_json_for_debug, dict):
                            print(f"DEBUG: GameOrchestrator - Generated display config keys: {list(loaded_json_for_debug.keys())}")
                            if "territory_polygons" in loaded_json_for_debug:
                                print(f"DEBUG: GameOrchestrator - 'territory_polygons' has {len(loaded_json_for_debug['territory_polygons'])} entries.")
                            if "territory_centroids" in loaded_json_for_debug:
                                print(f"DEBUG: GameOrchestrator - 'territory_centroids' has {len(loaded_json_for_debug['territory_centroids'])} entries.")
                        else:
                            print(f"DEBUG: GameOrchestrator - Generated display config is not a dictionary. Type: {type(loaded_json_for_debug)}")

                except Exception as e_inspect:
                    print(f"DEBUG: GameOrchestrator - Error inspecting generated display config: {e_inspect}")

            except json.JSONDecodeError:
                raise ValueError("Invalid GeoJSON data string provided.")
            except ImportError:
                raise ImportError("MapProcessor utility not found. Ensure llm_risk/utils/map_processor.py exists.")
            except Exception as e:
                raise RuntimeError(f"Error processing GeoJSON for world map: {e}")
        else: # Standard mode
            print(f"Initializing Standard game mode. Map file: {map_file_to_load}")

        self.engine = GameEngine(map_file_path=map_file_to_load)
        self.global_chat = GlobalChat()
        self.private_chat_manager = PrivateChatManager(max_exchanges_per_conversation=3)

        # Attributes for asynchronous AI calls - INITIALIZE THEM HERE
        self.ai_is_thinking: bool = False
        self.current_ai_thread: threading.Thread | None = None
        self.ai_action_result: dict | None = None
        self.active_ai_player_name: str | None = None # Name of the player whose AI is thinking
        self.current_ai_context: dict | None = None # Context for the current AI call
        self.has_logged_ai_is_thinking_for_current_action: bool = False
        self.has_logged_current_turn_player_phase: bool = False # For logging headers
        # self.gui is initialized after engine and player setup
        self.gui = None

        # AI agents and player_map are initialized after players are loaded by _load_player_setup
        self.ai_agents: dict[str, BaseAIAgent] = {}
        self.player_map: dict[GamePlayer, BaseAIAgent] = {}
        self.is_two_player_mode: bool = False # Will be set in _load_player_setup


        # Load player configurations: this will populate self.engine.game_state.players
        # and also determine self.is_two_player_mode
        human_player_configs = self._load_player_setup(player_configs_override, default_player_setup_file)

        if not human_player_configs: # _load_player_setup should raise error if this happens
             raise ValueError("Player setup resulted in no human player configurations.")

        # Initialize the game board in the engine
        # The engine will internally create a Neutral player if is_two_player_mode is True.
        # For world_map mode, it will also perform special territory initialization.
        self.engine.initialize_game_from_map(
            players_data=[{"name": p.name, "color": p.color} for p in human_player_configs], # Pass only human player data
            is_two_player_game=self.is_two_player_mode,
            game_mode=self.game_mode # Pass game_mode to engine
        )

        # After engine initializes players (including Neutral if 2P), map all to AI agents
        # The Neutral player won't have an AI agent in self.ai_agents, so player_map will skip it.
        self._map_game_players_to_ai_agents()

        # Initialize GUI now that engine and players are fully set up
        self.setup_gui() # Moved the single call here

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
            elif ai_type == "Llama": agent = LlamaAgent(player_name, player_color)
            elif ai_type == "Qwen": agent = QwenAgent(player_name, player_color)
            elif ai_type == "Mistral": agent = MistralAgent(player_name, player_color)
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

        # Check if an AI action is currently being awaited
        if self.ai_is_thinking:
            if self.current_ai_thread and self.current_ai_thread.is_alive():
                # AI is still thinking. Log if needed (already done by GUI loop implicitly).
                # print(f"Orchestrator: AI for {self.active_ai_player_name} is still thinking (SETUP_CLAIM_TERRITORIES).")
                return True # Still busy, orchestrator will call this handler again via advance_game_turn

            # If self.ai_is_thinking was true, but thread is NOT alive, it means thread just finished.
            # So, action_result should be available. We must set ai_is_thinking to False.
            if self.active_ai_player_name: # Check if there was an active AI
                self.log_turn_info(f"Orchestrator: AI ({self.active_ai_player_name}) thread finished (detected in _handle_setup_claim_territories).")
            else:
                self.log_turn_info(f"Orchestrator: AI thread finished (detected in _handle_setup_claim_territories, no active_ai_player_name).")
            self.ai_is_thinking = False
            # Fall through to process self.ai_action_result below.
            # No 'return True' here, because we want to process the result in this same call to the handler.

        # If AI has finished (either detected above, or ai_is_thinking was already false and result is pending from a previous tick)
        if self.ai_action_result:
            action_to_process = self.ai_action_result
            player_name_who_acted = self.active_ai_player_name # Should have been set when AI call was made

            # Clear context related to the completed AI action
            self.ai_action_result = None
            self.active_ai_player_name = None
            self.current_ai_context = None # Clear the context as well

            if not player_name_who_acted:
                self.log_turn_info("Error: AI action result found, but no active_ai_player_name. Cannot process claim.")
                # This is an inconsistent state. Might need to decide how to recover or if game should stall.
                # For now, returning True will cause this handler to be called again, hopefully state resolves or next player is initiated.
                return True

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
        # Use to_json_with_history() for AI context
        self._execute_ai_turn_async(current_setup_agent, gs.to_json_with_history(), valid_actions, self.game_rules, prompt_add)
        return True # AI is now thinking

    def _handle_setup_place_armies(self) -> bool:
        """Handles logic for SETUP_PLACE_ARMIES phase (standard game)."""
        gs = self.engine.game_state
        if gs.is_two_player_game: # Should not be in this phase for 2-player mode
            gs.current_game_phase = "SETUP_2P_DEAL_CARDS"
            return True

        # Check if the phase is complete before doing anything else
        if self.engine._all_initial_armies_placed():
            if gs.current_game_phase == "SETUP_PLACE_ARMIES":
                self.log_turn_info("All initial armies have been placed. Transitioning to first game turn.")
                # The engine should have already handled the phase transition, but this is a safeguard.
                gs.current_game_phase = "REINFORCE"
                gs.current_player_index = gs.players.index(gs.first_player_of_game)
                first_player = gs.get_current_player()
                if first_player:
                    first_player.armies_to_deploy, _ = self.engine.calculate_reinforcements(first_player)
            return True # Proceed to the new REINFORCE phase

        # Check if an AI action is currently being awaited
        if self.ai_is_thinking:
            if self.current_ai_thread and self.current_ai_thread.is_alive():
                return True # Still busy

            if self.active_ai_player_name:
                self.log_turn_info(f"Orchestrator: AI ({self.active_ai_player_name}) thread finished (in _handle_setup_place_armies).")
            self.ai_is_thinking = False
            # Fall through to process self.ai_action_result

        # If AI has finished, process its action
        if self.ai_action_result:
            action_to_process = self.ai_action_result
            player_name_who_acted = self.active_ai_player_name

            # Clear context for the next AI action
            self.ai_action_result = None
            self.active_ai_player_name = None
            self.current_ai_context = None

            if not player_name_who_acted:
                self.log_turn_info("Error: AI action result found, but no active_ai_player_name. Cycling.")
                return True

            action = action_to_process.get("action")
            
            # ** FIX: This block now correctly handles both action types by calling the engine,
            # which ensures the setup turn index is always advanced, preventing the loop. **
            if action and action.get("type") == "SETUP_PLACE_ARMY":
                territory_name = action.get("territory")
                log = self.engine.player_places_initial_army(player_name_who_acted, territory_name)
                self.log_turn_info(f"{player_name_who_acted} places army on {territory_name}: {log.get('message', 'No message from engine.')}")
            
            elif action and action.get("type") == "SETUP_STANDARD_DONE_PLACING":
                self.log_turn_info(f"{player_name_who_acted} is done placing armies. Notifying engine to advance turn.")
                # We still call the engine. Its internal logic will see the player has no armies
                # left to place and will correctly advance to the next player without changing army counts.
                log = self.engine.player_places_initial_army(player_name_who_acted, "") # Pass dummy territory name
                if not log.get('success'):
                    self.log_turn_info(f"Error when notifying engine that {player_name_who_acted} is done placing.")
            
            else:
                self.log_turn_info(f"Invalid action from {player_name_who_acted} during SETUP_PLACE_ARMIES: {action}. Re-prompting.")

            self._update_gui_full_state()
            self.has_logged_current_turn_player_phase = False
            return True

        # If AI is not thinking, initiate the action for the current setup player
        current_setup_player_obj, current_setup_agent = self._get_current_setup_player_and_agent()
        
        if not current_setup_player_obj or not current_setup_agent:
             self.log_turn_info("No current setup player/agent for placing armies. Game might stall.")
             return False

        if not self.has_logged_current_turn_player_phase:
            armies_left = current_setup_player_obj.initial_armies_pool - current_setup_player_obj.armies_placed_in_setup
            self.log_turn_info(f"Phase: SETUP_PLACE_ARMIES - {current_setup_player_obj.name}'s turn to place. ({armies_left} left)")
            self.has_logged_current_turn_player_phase = True

        valid_actions = self.engine.get_valid_actions(current_setup_player_obj)
        
        if not valid_actions:
            self.log_turn_info(f"No valid SETUP_PLACE_ARMY actions for {current_setup_player_obj.name}. This may indicate an issue.")
            # Let the loop continue, it may resolve if the engine transitions the phase on the next tick.
            return True

        prompt_add = f"Place one army on a territory you own. You have {current_setup_player_obj.initial_armies_pool - current_setup_player_obj.armies_placed_in_setup} left to place in total."
        self._execute_ai_turn_async(current_setup_agent, gs.to_json_with_history(), valid_actions, self.game_rules, prompt_add)
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

        # Check if an AI action is currently being awaited
        if self.ai_is_thinking:
            if self.current_ai_thread and self.current_ai_thread.is_alive():
                return True # Still busy

            if self.active_ai_player_name:
                self.log_turn_info(f"Orchestrator: AI ({self.active_ai_player_name}) thread finished (detected in _handle_setup_2p_place_remaining).")
            else:
                self.log_turn_info(f"Orchestrator: AI thread finished (detected in _handle_setup_2p_place_remaining, no active_ai_player_name).")
            self.ai_is_thinking = False
            # Fall through to process self.ai_action_result

        if self.ai_action_result:
            action_to_process = self.ai_action_result
            player_name_who_acted = self.active_ai_player_name

            self.ai_action_result = None
            self.active_ai_player_name = None
            self.current_ai_context = None # Clear context

            if not player_name_who_acted:
                self.log_turn_info("Error: AI action result found (SETUP_2P_PLACE_REMAINING), but no active_ai_player_name.")
                return True

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
                      "Provide action as: {'type': 'SETUP_2P_PLACE_ARMIES_TURN', 'own_army_placements': [['T1', count1], ['T2', count2], ...], 'neutral_army_placement': ['NT1', 1] or null}. "
                      "Ensure placements are lists of two elements (e.g., [\"TerritoryName\", number_of_armies]).")
        self._execute_ai_turn_async(current_setup_agent, gs.to_json_with_history(), valid_actions, self.game_rules, prompt_add)
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
            ai_response = agent_to_trade.get_thought_and_action(gs.to_json_with_history(), trade_actions, self.game_rules, prompt_add)
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
        # self.log_turn_info(f"Orchestrator: Advancing turn. Current phase: {current_phase}")

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

        current_player_obj = gs.get_current_player()
        if not current_player_obj or current_player_obj.is_neutral:
            self.log_turn_info(f"Error: No valid current human player for phase {current_phase}. Current player from engine: {current_player_obj.name if current_player_obj else 'None'}. Halting.")
            return False

        current_player_agent = self.get_agent_for_player(current_player_obj)
        if not current_player_agent:
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

        if gs.elimination_card_trade_player_name == current_player_obj.name:
            self.log_turn_info(f"Player {current_player_obj.name} has pending elimination card trades.")
            trade_loop_continue = self._handle_elimination_card_trade_loop(current_player_obj, current_player_agent)
            if not trade_loop_continue:
                 self.log_turn_info(f"Problem during elimination card trade for {current_player_obj.name}. Game may be unstable.")
            self.has_logged_current_turn_player_phase = False
            self._update_gui_full_state()

        action_processed_in_current_tick = False
        phase_when_action_was_initiated = None

        if self.ai_is_thinking:
            if self.current_ai_thread and self.current_ai_thread.is_alive():
                if not self.has_logged_ai_is_thinking_for_current_action:
                    print(f"Orchestrator: AI ({self.active_ai_player_name}) is still thinking. GUI should be responsive.")
                    self.has_logged_ai_is_thinking_for_current_action = True
                if self.gui: self.gui.update(self.engine.game_state, self.global_chat.get_log(), self.private_chat_manager.get_all_conversations())
                return True
            else:
                # AI thread has finished
                print(f"Orchestrator: AI ({self.active_ai_player_name}) thread finished.")
                self.ai_is_thinking = False
                self.has_logged_ai_is_thinking_for_current_action = False
                action_to_process = self.ai_action_result

                if action_to_process:
                    print(f"Orchestrator: Processing AI action: {action_to_process.get('action')}")
                    self.log_ai_thought(self.active_ai_player_name or "UnknownAI", action_to_process.get('thought', 'N/A'))
                    phase_when_action_was_initiated = self.engine.game_state.current_game_phase

                    if phase_when_action_was_initiated == "REINFORCE":
                        self._process_reinforce_ai_action(current_player_obj, current_player_agent, action_to_process)
                    elif phase_when_action_was_initiated == "ATTACK":
                        self._process_attack_ai_action(current_player_obj, current_player_agent, action_to_process)
                    elif phase_when_action_was_initiated == "FORTIFY":
                        self._process_fortify_ai_action(current_player_obj, current_player_agent, action_to_process)
                    action_processed_in_current_tick = True
                else:
                    print(f"Orchestrator: AI ({self.active_ai_player_name}) action result was None. Problem in thread.")
                    if self.engine.game_state.current_game_phase == "FORTIFY":
                        action_processed_in_current_tick = True
                self.ai_action_result = None
                self.active_ai_player_name = None
                self.current_ai_context = None
                self._update_gui_full_state()
                if self.engine.is_game_over(): return self.advance_game_turn()

        if not self.ai_is_thinking:
            # FIX: This is the critical block to fix the freeze. After a FORTIFY action is
            # processed, the turn must end. This logic ensures `next_turn()` is called.
            if phase_when_action_was_initiated == "FORTIFY" and action_processed_in_current_tick:
                if not self.engine.is_game_over():
                    self.engine.next_turn()
                    self.has_logged_current_turn_player_phase = False
                    new_player = self.engine.game_state.get_current_player()
                    self.log_turn_info(f"--- End of Turn for {current_player_obj.name}. Next is Turn {self.engine.game_state.current_turn_number}, Player: {new_player.name if new_player else 'N/A'} ---")
                    self._update_gui_full_state()
                if self.engine.is_game_over(): return self.advance_game_turn()
                return True

            max_phase_transitions_per_tick = 5
            transitions_this_tick = 0
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
                    break
                if self.ai_is_thinking:
                    break
                if self.engine.game_state.current_game_phase == current_phase_before_initiation:
                    break

            if transitions_this_tick >= max_phase_transitions_per_tick:
                self.log_turn_info(f"Orchestrator: Exceeded max phase transitions ({max_phase_transitions_per_tick}) in a single tick for player {current_player_obj.name}. This might indicate a problem.")

            if self.gui: self._update_gui_full_state()
            if self.engine.is_game_over(): return self.advance_game_turn()
            if self.ai_is_thinking: return True

            # Fallback for Fortify phase if AI initiation fails to start thinking
            if not self.ai_is_thinking and self.engine.game_state.current_game_phase == "FORTIFY":
                if not self.engine.is_game_over():
                    self.log_turn_info(f"Orchestrator: Fallback - Fortify phase, AI not thinking after initiation attempt. Ending turn for {current_player_obj.name}.")
                    self.engine.next_turn()
                    self.has_logged_current_turn_player_phase = False
                    new_player = self.engine.game_state.get_current_player()
                    self.log_turn_info(f"--- End of Turn for {current_player_obj.name} (fallback after fortify init). Next player: {new_player.name if new_player else 'N/A'} ---")
                    self._update_gui_full_state()
                if self.engine.is_game_over(): return self.advance_game_turn()
                return True

        if self.engine.is_game_over(): return False

        return True

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

        self._execute_ai_turn_async(agent, self.engine.game_state.to_json_with_history(), valid_actions, self.game_rules, system_prompt_addition)

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

        # Handle diplomatic actions first if chosen
        if _process_diplomatic_action(self, player, action):
            self.ai_is_thinking = False # Diplomatic action taken, AI can make another move in Reinforce
            if self.gui: self._update_gui_full_state()
            return

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
                    # Log card trade event
                    self.engine.game_state.event_history.append({
                        "turn": self.engine.game_state.current_turn_number,
                        "type": "CARD_TRADE",
                        "player": player.name,
                        "cards_traded_symbols": trade_result.get("traded_card_symbols", []), # From engine log
                        "armies_gained": trade_result.get("armies_gained", 0),
                        "territory_bonus_info": trade_result.get("territory_bonus") # Will be None or a string message
                    })
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
                self._execute_ai_turn_async(agent, self.engine.game_state.to_json_with_history(), paf_actions, self.game_rules, paf_prompt)
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
        self._execute_ai_turn_async(agent, self.engine.game_state.to_json_with_history(), valid_actions, self.game_rules, system_prompt_addition)
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

        # Handle diplomatic actions first if chosen (e.g. ACCEPT/REJECT if proposed via chat earlier)
        # or BREAK_ALLIANCE if chosen as a formal action.
        # The `_process_diplomatic_action` method is designed for ACCEPT/REJECT.
        # BREAK_ALLIANCE is already handled further down.
        # We need to make sure that if a diplomatic action (ACCEPT/REJECT) is taken,
        # the player can still perform another attack phase action.
        if action_type in ["ACCEPT_ALLIANCE", "REJECT_ALLIANCE"]:
            if self._process_diplomatic_action(self, player, action):
                self.ai_is_thinking = False # Diplomatic action processed, AI can make another move in Attack phase
                if self.gui: self._update_gui_full_state()
                return # Return to allow re-initiation of AI for attack phase

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
                                self.engine.game_state.to_json_with_history(), defense_dice_options, def_rules, def_prompt
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
                target_game_player_obj = next((p for p in self.engine.game_state.players if p.name == target_player_name), None)
                target_agent = self.get_agent_for_player(target_game_player_obj) if target_game_player_obj else None

                if not target_agent: # Covers target_game_player_obj being None or Neutral
                    self.log_turn_info(f"Orchestrator: {player.name} invalid PRIVATE_CHAT target: Player '{target_player_name}' not found, is neutral, or not an AI.")
                elif target_agent == agent:
                    self.log_turn_info(f"Orchestrator: {player.name} attempted PRIVATE_CHAT with self. Action ignored.")
                else:
                    self.log_turn_info(f"Orchestrator: Initiating private chat between {player.name} and {target_player_name}.")
                    # Define goals for the negotiation based on game context or default
                    # Example: initiator wants an alliance, recipient wants to evaluate
                    initiator_goal = f"Your goal is to negotiate a favorable outcome with {target_player_name}. Consider proposing an ALLIANCE, a non-aggression pact, or a joint attack."
                    recipient_goal = f"Your goal is to evaluate {player.name}'s proposal and negotiate the best terms for yourself. You can accept, reject, or make a counter-offer."

                    conversation_log_entries, negotiated_action = self.private_chat_manager.run_conversation(
                        agent1=agent, agent2=target_agent,
                        initial_message=initial_message,
                        game_state=self.engine.game_state, # Pass full GameState object
                        game_rules=self.game_rules,
                        initiator_goal=initiator_goal,
                        recipient_goal=recipient_goal
                    )
                    summary_msg = f"Private chat between {player.name} and {target_player_name} concluded ({len(conversation_log_entries)} messages)."
                    if self.gui: self.gui.log_action(summary_msg) # Simple log for now
                    self.log_turn_info(f"Orchestrator: {summary_msg}")

                    if negotiated_action:
                        self.log_turn_info(f"Orchestrator: Private chat resulted in a negotiated action: {negotiated_action}")
                        # Process the negotiated_action
                        # This is a critical step. The orchestrator needs to validate and apply this action.
                        # Example: If PROPOSE_ALLIANCE, update GameState.diplomacy to "PROPOSED_ALLIANCE"
                        #          and set up for target_player to accept/reject on their turn.
                        # If ACCEPT_ALLIANCE, update GameState.diplomacy to "ALLIANCE".
                        if negotiated_action.get("type") == "PROPOSE_ALLIANCE":
                            proposer = negotiated_action.get("proposing_player_name")
                            target = negotiated_action.get("target_player_name")
                            if proposer and target:
                                diplomatic_key = frozenset({proposer, target})
                                # Store proposal detail (who proposed to whom) for later acceptance check
                                # This might need a new structure in GameState, e.g., gs.pending_proposals
                                self.engine.game_state.diplomacy[diplomatic_key] = "PROPOSED_ALLIANCE"
                                # Add details to a new structure like:
                                self.engine.game_state.diplomacy[diplomatic_key] = "PROPOSED_ALLIANCE" # General status
                                self.engine.game_state.active_diplomatic_proposals[diplomatic_key] = {
                                    'proposer': proposer,
                                    'target': target,
                                    'type': 'ALLIANCE', # Could be other types like NON_AGGRESSION
                                    'turn_proposed': self.engine.game_state.current_turn_number
                                }
                                self.log_turn_info(f"Diplomacy: {proposer} proposed ALLIANCE to {target}. Proposal recorded.")
                                self.global_chat.broadcast("GameSystem", f"{proposer} has proposed an alliance to {target} via private channels.")
                                # Log event
                                self.engine.game_state.event_history.append({
                                    "turn": self.engine.game_state.current_turn_number,
                                    "type": "DIPLOMACY_PROPOSAL",
                                    "subtype": "ALLIANCE_PROPOSED",
                                    "proposer": proposer,
                                    "target": target
                                })
                        elif negotiated_action.get("type") == "ACCEPT_ALLIANCE":
                            accepter = negotiated_action.get("accepting_player_name")
                            proposer = negotiated_action.get("proposing_player_name")
                            if accepter and proposer:
                                diplomatic_key = frozenset({accepter, proposer})
                                # TODO: Add verification against a pending proposal structure if implemented
                                self.engine.game_state.diplomacy[diplomatic_key] = "ALLIANCE"
                                self.log_turn_info(f"Diplomacy: {accepter} ACCEPTED ALLIANCE with {proposer}. Status set to ALLIANCE.")
                                self.global_chat.broadcast("GameSystem", f"{accepter} and {proposer} have formed an ALLIANCE!")
                                # Log event
                                self.engine.game_state.event_history.append({
                                    "turn": self.engine.game_state.current_turn_number,
                                    "type": "DIPLOMACY_CHANGE",
                                    "subtype": "ALLIANCE_FORMED",
                                    "players": sorted([accepter, proposer])
                                })
                        # Add more processing for other negotiated_action types (BREAK_ALLIANCE, etc.)
                        self._update_gui_full_state() # Update GUI with new diplomatic status
                    else:
                        self.log_turn_info(f"Orchestrator: Private chat between {player.name} and {target_player_name} did not result in a formal agreement.")

            self.ai_is_thinking = False

        elif action_type == "BREAK_ALLIANCE":
            target_player_name = action.get("target_player_name")
            if player and target_player_name:
                diplomatic_key = frozenset({player.name, target_player_name})
                if self.engine.game_state.diplomacy.get(diplomatic_key) == "ALLIANCE":
                    self.engine.game_state.diplomacy[diplomatic_key] = "NEUTRAL" # Or WAR, depending on desired outcome
                    self.log_turn_info(f"Diplomacy: {player.name} BROKE ALLIANCE with {target_player_name}. Status set to NEUTRAL.")
                    self.global_chat.broadcast("GameSystem", f"{player.name} has broken their alliance with {target_player_name}!")
                    # Log event
                    self.engine.game_state.event_history.append({
                        "turn": self.engine.game_state.current_turn_number,
                        "type": "DIPLOMACY_CHANGE",
                        "subtype": "ALLIANCE_BROKEN",
                        "breaker": player.name,
                        "target": target_player_name,
                        "new_status": "NEUTRAL"
                    })
                    self._update_gui_full_state()
                else:
                    self.log_turn_info(f"Orchestrator: {player.name} tried to BREAK_ALLIANCE with {target_player_name}, but no alliance existed.")
            else:
                self.log_turn_info(f"Orchestrator: {player.name} tried BREAK_ALLIANCE with invalid parameters: {action}")
            self.ai_is_thinking = False # Player can make another move in attack phase


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
        self._execute_ai_turn_async(agent, self.engine.game_state.to_json_with_history(), valid_actions, self.game_rules, system_prompt_addition=prompt_add)

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

            # Handle diplomatic actions first if chosen
            if action_type in ["ACCEPT_ALLIANCE", "REJECT_ALLIANCE"]:
                if self._process_diplomatic_action(self, player, action):
                    # Unlike other phases, a diplomatic action in Fortify phase might still end the turn,
                    # or allow one actual fortification move.
                    # For now, let's assume it consumes the "action" for the fortify phase, and then the turn ends.
                    # The current _process_diplomatic_action doesn't set ai_is_thinking.
                    # The fortify phase naturally ends after one action (fortify or end_turn).
                    # So, if a diplomatic action is taken, it's the action for this phase.
                    pass # Diplomatic action processed, turn will end as usual after this.
                # Fall through to end turn logic in advance_game_turn

            elif action_type == "FORTIFY":
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

            else: # Unknown action type
                self.log_turn_info(f"{player.name} provided an unknown action type '{action_type}' during FORTIFY phase. Turn will end.")

        # Log status after processing
        self.log_turn_info(f"Orchestrator: Player {player.name} status after processing fortify action: has_fortified_this_turn = {player.has_fortified_this_turn}")
        self.ai_is_thinking = False
        self.log_turn_info(f"Orchestrator: {player.name} FORTIFY phase AI processing complete. Turn will now end via main loop.")
        if self.gui: self._update_gui_full_state()

    def auto_distribute_armies(self, player: GamePlayer, armies_to_distribute: int):
        if not player.territories: return
        idx = 0
        while armies_to_distribute > 0:
            territory = player.territories[idx % len(player.territories)]
            territory.army_count += 1; armies_to_distribute -= 1
            self.log_turn_info(f"Auto-distributed 1 army to {territory.name} for {player.name}.")
            idx += 1
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
            if gp_key.name == eliminated_player_name: # Compare by name as gp_key might be a stale object
                key_to_remove_map = gp_key; break
        if key_to_remove_map: del self.player_map[key_to_remove_map]
        print(f"Player {eliminated_player_name} fully processed for elimination.")

    def log_ai_thought(self, player_name: str, thought: str):
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        print(f"--- {player_name}'s Thought --- \n{thought[:300]}...\n--------------------")
        if self.gui:
            self.gui.update_thought_panel(player_name, thought)
        try:
            with open(os.path.join(log_dir, "ai_thoughts.jsonl"), 'a') as f:
                log_entry = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "player": player_name,
                    "thought": thought
                }
                f.write(json.dumps(log_entry) + "\n")
        except IOError as e:
            print(f"Error writing to AI thought log: {e}")

    def log_turn_info(self, message: str):
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        if self.gui:
            self.gui.log_action(message)
        try:
            with open(os.path.join(log_dir, "game_log.txt"), 'a') as f:
                f.write(f"[{datetime.utcnow().isoformat()}] {message}\n")
        except IOError as e:
            print(f"Error writing to game log: {e}")

    def setup_gui(self):
        try:
            if not self.gui:
                # Ensure self.map_display_config_to_load is determined before this call
                print(f"DEBUG: GameOrchestrator.setup_gui - Initializing GameGUI with map_display_config_file: '{self.map_display_config_to_load}' and game_mode: '{self.game_mode}'")
                self.gui = GameGUI(engine=self.engine, orchestrator=self, map_display_config_file=self.map_display_config_to_load, game_mode=self.game_mode)
                print("GUI setup complete. GUI is active.")
        except Exception as e:
            print(f"Failed to initialize GUI, will run in headless mode. Error: {e}")
            self.gui = None

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
    orchestrator = GameOrchestrator(default_player_setup_file=config_path, game_mode="standard") # Assuming test runs standard
    print("Starting game run...")
    orchestrator.run_game()
    print("\nGame run finished.")
    if os.path.exists("logs/game_log.txt"):
        with open("logs/game_log.txt", 'r') as f:
            print("\n--- Final Game Log ---")
            print(f.read())