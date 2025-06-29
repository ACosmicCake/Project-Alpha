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
from .game_orchestrator_diplomacy_helper import _process_diplomatic_action # Import the helper
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
        except Exception as e:
            print(f"Error in AI thread for {agent.player_name}: {e}")
            self.ai_action_result = {"error": str(e), "thought": f"Error during API call: {e}", "action": None}

    def _execute_ai_turn_async(self, agent: BaseAIAgent, game_state_json: str, valid_actions: list, game_rules: str, system_prompt_addition: str):
        """Initiates the AI call in a separate thread."""
        if self.ai_is_thinking:
            print(f"Warning: _execute_ai_turn_async called while AI for {self.active_ai_player_name} is already thinking. Ignoring.")
            return

        self.has_logged_ai_is_thinking_for_current_action = False
        self.active_ai_player_name = agent.player_name
        self.ai_action_result = None
        self.ai_is_thinking = True
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
        self.current_ai_thread.daemon = True
        self.current_ai_thread.start()
        print(f"Orchestrator: Started AI thinking thread for {agent.player_name}.")
        if self.gui:
             self._update_gui_full_state()

    def _load_player_setup(self, player_configs_override: list | None, default_player_setup_file: str) -> list[GamePlayer]:
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

        self.ai_agents.clear()
        human_game_players_for_engine = []

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
            player_name = config.get("name", f"Player{i+1}")
            player_color = config.get("color")
            if not player_color or player_color.lower() in used_colors:
                found_color = False
                for c in default_colors:
                    if c.lower() not in used_colors:
                        player_color = c
                        found_color = True
                        break
                if not found_color:
                    player_color = f"{default_colors[i % len(default_colors)]}{i // len(default_colors) + 1}"
                print(f"Assigned color '{player_color}' to player '{player_name}'.")
            used_colors.add(player_color.lower())
            ai_type = config.get("ai_type", "Gemini")
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
        self.player_map.clear()
        if not self.engine.game_state.players:
            print("Warning: No players in game_state to map to AI agents (called from _map_game_players_to_ai_agents).")
            return
        for gp in self.engine.game_state.players:
            if gp.is_neutral: continue
            if gp.name in self.ai_agents:
                self.player_map[gp] = self.ai_agents[gp.name]
            else:
                raise ValueError(f"Mismatch: GamePlayer {gp.name} has no AI agent.")
        print(f"Mapped {len(self.player_map)} GamePlayer objects to AI agents.")

    def get_agent_for_player(self, player_obj: GamePlayer) -> BaseAIAgent | None:
        if player_obj is None or player_obj.is_neutral:
            return None
        return self.player_map.get(player_obj)

    def get_agent_for_current_player(self) -> BaseAIAgent | None:
        gs = self.engine.game_state
        current_phase = gs.current_game_phase
        acting_player_obj: GamePlayer | None = None
        if current_phase in ["SETUP_CLAIM_TERRITORIES", "SETUP_PLACE_ARMIES"] and not gs.is_two_player_game:
            current_player_obj_temp: GamePlayer | None = None
            if not gs.player_setup_order or \
               gs.current_setup_player_index < 0 or \
               gs.current_setup_player_index >= len(gs.player_setup_order):
                current_player_obj_temp = None
            else:
                current_player_obj_temp = gs.player_setup_order[gs.current_setup_player_index]
            acting_player_obj = current_player_obj_temp
        elif current_phase == "SETUP_2P_PLACE_REMAINING" and gs.is_two_player_game:
            current_player_obj_temp: GamePlayer | None = None
            if not gs.player_setup_order or \
               gs.current_setup_player_index < 0 or \
               gs.current_setup_player_index >= len(gs.player_setup_order):
                current_player_obj_temp = None
            else:
                current_player_obj_temp = gs.player_setup_order[gs.current_setup_player_index]
            acting_player_obj = current_player_obj_temp
        elif current_phase not in ["SETUP_START", "SETUP_DETERMINE_ORDER", "SETUP_2P_DEAL_CARDS"]:
            acting_player_obj = gs.get_current_player()
        if acting_player_obj:
            return self.get_agent_for_player(acting_player_obj)
        return None

    def _update_gui_full_state(self):
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

    def _handle_setup_determine_order(self) -> bool:
        gs = self.engine.game_state
        self.log_turn_info("Phase: SETUP_DETERMINE_ORDER")
        if gs.is_two_player_game:
            self.log_turn_info("Error: SETUP_DETERMINE_ORDER called in 2-player mode. Advancing to 2P card dealing.")
            gs.current_game_phase = "SETUP_2P_DEAL_CARDS"
            return True
        human_players = [p for p in gs.players if not p.is_neutral]
        if not human_players:
            self.log_turn_info("No human players to determine order for. Error.")
            return False
        ordered_player_names = [p.name for p in human_players]
        first_placer_name = human_players[0].name
        success = self.engine.set_player_setup_order(ordered_player_names, first_placer_name)
        if not success:
            self.log_turn_info("Failed to set player setup order in engine. Halting.")
            return False
        self.log_turn_info(f"Player setup order determined: {ordered_player_names}. First placer & first turn: {first_placer_name}.")
        self.has_logged_current_turn_player_phase = False
        return True

    def _get_current_setup_player_and_agent(self) -> tuple[GamePlayer | None, BaseAIAgent | None]:
        gs = self.engine.game_state
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
            self.log_turn_info(f"Error: No AI agent for current setup player {current_setup_player_obj.name}. Skipping their setup turn.")
            return current_setup_player_obj, None
        return current_setup_player_obj, current_setup_agent

    def _handle_setup_claim_territories(self) -> bool:
        gs = self.engine.game_state
        if gs.is_two_player_game:
            gs.current_game_phase = "SETUP_2P_DEAL_CARDS"; return True
        if not gs.unclaimed_territory_names:
            self.log_turn_info("All territories claimed, but phase is still SETUP_CLAIM_TERRITORIES. Engine should have transitioned.")
            gs.current_game_phase = "SETUP_PLACE_ARMIES"
            self.engine.game_state.current_setup_player_index = 0
            return True
        if self.ai_is_thinking:
            if self.current_ai_thread and self.current_ai_thread.is_alive():
                return True
            if self.active_ai_player_name:
                self.log_turn_info(f"Orchestrator: AI ({self.active_ai_player_name}) thread finished (detected in _handle_setup_claim_territories).")
            else:
                self.log_turn_info(f"Orchestrator: AI thread finished (detected in _handle_setup_claim_territories, no active_ai_player_name).")
            self.ai_is_thinking = False
        if self.ai_action_result:
            action_to_process = self.ai_action_result
            player_name_who_acted = self.active_ai_player_name
            self.ai_action_result = None
            self.active_ai_player_name = None
            self.current_ai_context = None
            if not player_name_who_acted:
                self.log_turn_info("Error: AI action result found, but no active_ai_player_name. Cannot process claim.")
                return True
            action = action_to_process.get("action")
            if action and action.get("type") == "SETUP_CLAIM":
                territory_name = action.get("territory")
                log = self.engine.player_claims_territory(player_name_who_acted, territory_name)
                self.log_turn_info(f"{player_name_who_acted} claims {territory_name}: {log['message']}")
                if not log["success"]:
                    self.log_turn_info(f"Claim by {player_name_who_acted} for {territory_name} failed. AI may need to retry if phase hasn't changed.")
            else:
                self.log_turn_info(f"Invalid action from {player_name_who_acted} during SETUP_CLAIM: {action}. Will re-prompt.")
            self._update_gui_full_state()
            self.has_logged_current_turn_player_phase = False
            return True
        current_setup_player_obj, current_setup_agent = self._get_current_setup_player_and_agent()
        if not current_setup_player_obj or not current_setup_agent:
             self.log_turn_info("No current setup player/agent for claiming. Game might stall.")
             return False
        if not self.has_logged_current_turn_player_phase:
            self.log_turn_info(f"Phase: SETUP_CLAIM_TERRITORIES - {current_setup_player_obj.name}'s turn to claim.")
            self.has_logged_current_turn_player_phase = True
        valid_actions = self.engine.get_valid_actions(current_setup_player_obj)
        if not valid_actions:
            self.log_turn_info(f"No valid claim actions for {current_setup_player_obj.name}, but territories remain. Engine state: {gs.unclaimed_territory_names}")
            if not gs.unclaimed_territory_names: gs.current_game_phase = "SETUP_PLACE_ARMIES"; self.engine.game_state.current_setup_player_index = 0
            return True
        prompt_add = f"It's your turn to claim a territory. Choose one from the list."
        self._execute_ai_turn_async(current_setup_agent, gs.to_json_with_history(), valid_actions, self.game_rules, prompt_add)
        return True

    def _handle_setup_place_armies(self) -> bool:
        gs = self.engine.game_state
        if gs.is_two_player_game:
            gs.current_game_phase = "SETUP_2P_DEAL_CARDS"; return True
        if self.engine._all_initial_armies_placed():
            gs.current_game_phase = "REINFORCE"
            self.log_turn_info("All initial armies placed, but phase is still SETUP_PLACE_ARMIES. Engine should have transitioned.")
            if gs.first_player_of_game:
                 try: gs.current_player_index = gs.players.index(gs.first_player_of_game)
                 except ValueError: gs.current_player_index = 0
                 first_game_player = gs.get_current_player()
                 if first_game_player: first_game_player.armies_to_deploy = self.engine.calculate_reinforcements(first_game_player)
            return True
        if self.ai_is_thinking:
            if self.current_ai_thread and self.current_ai_thread.is_alive():
                return True
            if self.active_ai_player_name:
                self.log_turn_info(f"Orchestrator: AI ({self.active_ai_player_name}) thread finished (detected in _handle_setup_place_armies).")
            else:
                self.log_turn_info(f"Orchestrator: AI thread finished (detected in _handle_setup_place_armies, no active_ai_player_name).")
            self.ai_is_thinking = False
        if self.ai_action_result:
            action_to_process = self.ai_action_result
            player_name_who_acted = self.active_ai_player_name
            self.ai_action_result = None
            self.active_ai_player_name = None
            self.current_ai_context = None
            if not player_name_who_acted:
                self.log_turn_info("Error: AI action result found (SETUP_PLACE_ARMIES), but no active_ai_player_name.")
                return True
            action = action_to_process.get("action")
            if action and action.get("type") == "SETUP_PLACE_ARMY":
                territory_name = action.get("territory")
                log = self.engine.player_places_initial_army(player_name_who_acted, territory_name)
                self.log_turn_info(f"{player_name_who_acted} places army on {territory_name}: {log['message']}")
            elif action and action.get("type") == "SETUP_STANDARD_DONE_PLACING":
                self.log_turn_info(f"{player_name_who_acted} is done placing initial armies (or has no more to place).")
            else:
                self.log_turn_info(f"Invalid action from {player_name_who_acted} during SETUP_PLACE_ARMIES: {action}")
            self._update_gui_full_state()
            self.has_logged_current_turn_player_phase = False
            return True
        current_setup_player_obj, current_setup_agent = self._get_current_setup_player_and_agent()
        if not current_setup_player_obj :
             self.log_turn_info("No current setup player for placing armies. Game might stall if not all armies placed.")
             return False if not self.engine._all_initial_armies_placed() else True
        if current_setup_player_obj.armies_placed_in_setup >= current_setup_player_obj.initial_armies_pool:
            self.log_turn_info(f"{current_setup_player_obj.name} has placed all initial armies. Orchestrator cycling.")
            self.has_logged_current_turn_player_phase = False
            return True
        if not current_setup_agent:
            self.log_turn_info(f"Player {current_setup_player_obj.name} has no AI agent. Cannot place armies. Game will stall.")
            return False
        if not self.has_logged_current_turn_player_phase:
            self.log_turn_info(f"Phase: SETUP_PLACE_ARMIES - {current_setup_player_obj.name}'s turn to place. ({current_setup_player_obj.initial_armies_pool - current_setup_player_obj.armies_placed_in_setup} left)")
            self.has_logged_current_turn_player_phase = True
        valid_actions = self.engine.get_valid_actions(current_setup_player_obj)
        if not valid_actions and current_setup_player_obj.armies_placed_in_setup < current_setup_player_obj.initial_armies_pool :
            self.log_turn_info(f"No valid place_army actions for {current_setup_player_obj.name} but has armies left. Owned: {[t.name for t in current_setup_player_obj.territories]}")
            return True
        elif not valid_actions :
             return True
        prompt_add = f"Place one army on a territory you own. You have {current_setup_player_obj.initial_armies_pool - current_setup_player_obj.armies_placed_in_setup} left to place in total."
        self._execute_ai_turn_async(current_setup_agent, gs.to_json_with_history(), valid_actions, self.game_rules, prompt_add)
        return True

    def _handle_setup_2p_deal_cards(self) -> bool:
        gs = self.engine.game_state
        self.log_turn_info("Phase: SETUP_2P_DEAL_CARDS (Automatic)")
        log = self.engine.setup_two_player_initial_territory_assignment()
        self.log_turn_info(log["message"])
        if not log["success"]: return False
        self._update_gui_full_state()
        self.has_logged_current_turn_player_phase = False
        return True

    def _handle_setup_2p_place_remaining(self) -> bool:
        gs = self.engine.game_state
        all_human_done = True
        for p_human in gs.player_setup_order:
            if p_human.armies_placed_in_setup < p_human.initial_armies_pool:
                all_human_done = False; break
        if all_human_done:
            if gs.current_game_phase == "SETUP_2P_PLACE_REMAINING":
                 self.log_turn_info("All 2P human armies placed, but phase not transitioned by engine. Forcing.")
            return True
        if self.ai_is_thinking:
            if self.current_ai_thread and self.current_ai_thread.is_alive():
                return True
            if self.active_ai_player_name:
                self.log_turn_info(f"Orchestrator: AI ({self.active_ai_player_name}) thread finished (detected in _handle_setup_2p_place_remaining).")
            else:
                self.log_turn_info(f"Orchestrator: AI thread finished (detected in _handle_setup_2p_place_remaining, no active_ai_player_name).")
            self.ai_is_thinking = False
        if self.ai_action_result:
            action_to_process = self.ai_action_result
            player_name_who_acted = self.active_ai_player_name
            self.ai_action_result = None
            self.active_ai_player_name = None
            self.current_ai_context = None
            if not player_name_who_acted:
                self.log_turn_info("Error: AI action result found (SETUP_2P_PLACE_REMAINING), but no active_ai_player_name.")
                return True
            action_data = action_to_process.get("action")
            if action_data and action_data.get("type") == "SETUP_2P_PLACE_ARMIES_TURN":
                own_placements = action_data.get("own_army_placements")
                neutral_placement = action_data.get("neutral_army_placement")
                if own_placements is not None :
                    log = self.engine.player_places_initial_armies_2p(player_name_who_acted, own_placements, neutral_placement)
                    self.log_turn_info(f"{player_name_who_acted} (2P Setup Place): {log['message']}")
                else:
                    self.log_turn_info(f"Invalid/missing own_army_placements from {player_name_who_acted} for 2P setup: {action_data}")
            elif action_data and action_data.get("type") == "SETUP_2P_DONE_PLACING":
                 self.log_turn_info(f"{player_name_who_acted} is done with 2P setup placing.")
            else:
                self.log_turn_info(f"Invalid action from {player_name_who_acted} during SETUP_2P_PLACE_REMAINING: {action_data}")
            self._update_gui_full_state()
            self.has_logged_current_turn_player_phase = False
            return True
        current_setup_player_obj, current_setup_agent = self._get_current_setup_player_and_agent()
        if not current_setup_player_obj or not current_setup_agent:
            self.log_turn_info("No current setup player/agent for 2P placing. Game might stall.")
            return False
        if not self.has_logged_current_turn_player_phase:
            self.log_turn_info(f"Phase: SETUP_2P_PLACE_REMAINING - {current_setup_player_obj.name}'s turn.")
            self.has_logged_current_turn_player_phase = True
        valid_actions = self.engine.get_valid_actions(current_setup_player_obj)
        if not valid_actions or valid_actions[0].get("type") != "SETUP_2P_PLACE_ARMIES_TURN":
            if valid_actions and valid_actions[0].get("type") == "SETUP_2P_DONE_PLACING":
                self.log_turn_info(f"{current_setup_player_obj.name} has no more armies for 2P setup. Will cycle.")
                self.has_logged_current_turn_player_phase = False
                return True
            self.log_turn_info(f"Unexpected valid actions for {current_setup_player_obj.name} in 2P place remaining: {valid_actions}. Game might stall.")
            return True
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
        gs = self.engine.game_state
        self.log_turn_info(f"Player {player_to_trade.name} must trade cards due to elimination (hand size: {len(player_to_trade.hand)}).")
        trade_attempt_limit = 5
        attempts = 0
        while gs.elimination_card_trade_player_name == player_to_trade.name and attempts < trade_attempt_limit:
            attempts += 1
            self.log_turn_info(f"Elimination trade attempt {attempts} for {player_to_trade.name}. Hand: {len(player_to_trade.hand)}")
            valid_actions = self.engine.get_valid_actions(player_to_trade)
            if gs.elimination_card_trade_player_name != player_to_trade.name:
                self.log_turn_info(f"{player_to_trade.name} no longer needs to trade for elimination (hand <= 4 or no sets).")
                break
            trade_actions = [va for va in valid_actions if va.get("type") == "TRADE_CARDS" and va.get("must_trade")]
            if not trade_actions:
                self.log_turn_info(f"No valid 'must_trade' actions for {player_to_trade.name} despite pending elimination trade. Hand: {len(player_to_trade.hand)}. Clearing flag.")
                gs.elimination_card_trade_player_name = None
                break
            prompt_add = "You MUST trade cards to reduce your hand size below 5 due to player elimination."
            ai_response = agent_to_trade.get_thought_and_action(gs.to_json_with_history(), trade_actions, self.game_rules, prompt_add)
            self.log_ai_thought(player_to_trade.name, ai_response.get("thought", "N/A (elimination trade)"))
            chosen_action = ai_response.get("action")
            if chosen_action and chosen_action.get("type") == "TRADE_CARDS":
                card_indices = chosen_action.get("card_indices")
                trade_result = self.engine.perform_card_trade(player_to_trade, card_indices)
                self.log_turn_info(f"{player_to_trade.name} mandatory trade: {trade_result.get('message')}")
                self._update_gui_full_state()
                if not trade_result.get("success"):
                    self.log_turn_info(f"Mandatory trade by {player_to_trade.name} failed. This may stall the game if not resolved.")
            else:
                self.log_turn_info(f"{player_to_trade.name} failed to provide a valid TRADE_CARDS action during mandatory elimination trade. Action: {chosen_action}")
                gs.elimination_card_trade_player_name = None
                break
        if attempts >= trade_attempt_limit:
            self.log_turn_info(f"Reached trade attempt limit for {player_to_trade.name} during elimination card trade. Clearing flag.")
            gs.elimination_card_trade_player_name = None
        self.log_turn_info(f"Finished elimination card trade loop for {player_to_trade.name}. Hand size: {len(player_to_trade.hand)}")
        return True

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
        if current_phase == "SETUP_START":
            self.log_turn_info("Error: Game in SETUP_START. Initialization might be incomplete.")
            if self.is_two_player_mode: gs.current_game_phase = "SETUP_2P_DEAL_CARDS"
            else: gs.current_game_phase = "SETUP_DETERMINE_ORDER"
            return True
        elif current_phase == "SETUP_DETERMINE_ORDER": return self._handle_setup_determine_order()
        elif current_phase == "SETUP_CLAIM_TERRITORIES": return self._handle_setup_claim_territories()
        elif current_phase == "SETUP_PLACE_ARMIES": return self._handle_setup_place_armies()
        elif current_phase == "SETUP_2P_DEAL_CARDS": return self._handle_setup_2p_deal_cards()
        elif current_phase == "SETUP_2P_PLACE_REMAINING": return self._handle_setup_2p_place_remaining()
        self.turn_action_log.clear()
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
            current_game_phase = self.engine.game_state.current_game_phase
            if phase_when_action_was_initiated == "FORTIFY" and action_processed_in_current_tick:
                if not self.engine.is_game_over():
                    self.engine.next_turn()
                    self.has_logged_current_turn_player_phase = False
                    new_player = self.engine.game_state.get_current_player()
                    print(f"--- End of Turn for {current_player_obj.name}. Next player: {new_player.name if new_player else 'N/A'} ---")
                    self._update_gui_full_state()
                if self.engine.is_game_over(): return self.advance_game_turn()
                return True
            max_phase_transitions_per_tick = 3
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
                else: break
                if self.ai_is_thinking: break
                if self.engine.game_state.current_game_phase == current_phase_before_initiation: break
            if transitions_this_tick >= max_phase_transitions_per_tick:
                self.log_turn_info(f"Orchestrator: Exceeded max phase transitions ({max_phase_transitions_per_tick}) in a single tick for player {current_player_obj.name}. This might indicate a problem.")
            if self.gui: self._update_gui_full_state()
            if self.engine.is_game_over(): return self.advance_game_turn()
            if self.ai_is_thinking: return True
            if not self.ai_is_thinking and self.engine.game_state.current_game_phase == "FORTIFY":
                if not self.engine.is_game_over():
                    self.log_turn_info(f"Orchestrator: Fallback - Fortify phase, AI not thinking after initiation attempt. Ending turn for {current_player_obj.name}.")
                    self.engine.next_turn()
                    self.has_logged_current_turn_player_phase = False
                    new_player = self.engine.game_state.get_current_player()
                    print(f"--- End of Turn for {current_player_obj.name} (fallback after fortify init). Next player: {new_player.name if new_player else 'N/A'} ---")
                    self._update_gui_full_state()
                if self.engine.is_game_over(): return self.advance_game_turn()
                return True
        if self.engine.is_game_over(): return False
        return True

    def _initiate_reinforce_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        """Gathers info and starts the AI thinking for the REINFORCE phase."""
        self.log_turn_info(f"Orchestrator: Initiating REINFORCE AI action for {player.name}") # Corrected: Using log_turn_info
        game_state_json = self.engine.game_state.to_json_with_history() # Corrected: Using to_json_with_history
        valid_actions = self.engine.get_valid_actions(player)

        if not valid_actions:
            self.log_turn_info(f"No valid REINFORCE actions for {player.name}. Auto-distributing if needed and moving to ATTACK.")
            if player.armies_to_deploy > 0:
                self.auto_distribute_armies(player, player.armies_to_deploy)
            self.engine.game_state.current_game_phase = "ATTACK"
            self.has_logged_current_turn_player_phase = False
            self.ai_is_thinking = False
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
        self.log_turn_info(f"Orchestrator: Processing REINFORCE AI action for {player.name}")
        action = ai_response.get("action")

        if not action or not isinstance(action, dict) or "type" not in action:
            self.log_turn_info(f"{player.name} provided malformed or missing REINFORCE action: {action}. AI will be prompted again.")
            self.ai_is_thinking = False
            if self.gui: self._update_gui_full_state()
            return

        action_type = action["type"]
        self.log_turn_info(f"{player.name} REINFORCE action: {action_type} - Details: {action}")

        if self._process_diplomatic_action(player, action):
            self.ai_is_thinking = False
            if self.gui: self._update_gui_full_state()
            return

        current_valid_actions = self.engine.get_valid_actions(player) # Get fresh valid actions for must_trade check
        must_trade_currently = any(a['type'] == 'TRADE_CARDS' and a.get('must_trade') for a in current_valid_actions)
        ai_failed_must_trade = False

        if must_trade_currently:
            if action_type != "TRADE_CARDS":
                self.log_turn_info(f"{player.name} provided action '{action_type}' but MUST_TRADE cards.")
                ai_failed_must_trade = True
            elif action_type == "TRADE_CARDS": # AI attempted to trade
                card_indices = action.get("card_indices")
                if not isinstance(card_indices, list) or not all(isinstance(idx, int) for idx in card_indices) or len(set(card_indices)) != 3:
                    self.log_turn_info(f"{player.name} selected TRADE_CARDS with invalid indices format: {card_indices}. Must be 3 unique integers.")
                    ai_failed_must_trade = True # Considered a failure to trade correctly
                else:
                    trade_result = self.engine.perform_card_trade(player, card_indices)
                    log_message = trade_result.get('message', f"Trade attempt by {player.name} with cards {card_indices}.")
                    self.log_turn_info(log_message)
                    if not trade_result.get("success"):
                        self.log_turn_info(f"{player.name}'s chosen card trade failed during must_trade.")
                        ai_failed_must_trade = True
                    else:
                        # Successful trade by AI during must_trade
                        self.log_turn_info(f"{player.name} gained {trade_result['armies_gained']} armies. Total to deploy: {player.armies_to_deploy}.")
                        if trade_result.get("territory_bonus"): self.log_turn_info(trade_result["territory_bonus"])
                        self.engine.game_state.event_history.append({
                            "turn": self.engine.game_state.current_turn_number, "type": "CARD_TRADE", "player": player.name,
                            "cards_traded_symbols": trade_result.get("traded_card_symbols", []),
                            "armies_gained": trade_result.get("armies_gained", 0),
                            "territory_bonus_info": trade_result.get("territory_bonus")
                        })
                        self.ai_is_thinking = False # AI can now deploy or end
                        if self.gui: self._update_gui_full_state()
                        return # Successfully handled AI's must_trade

        if ai_failed_must_trade:
            self.log_turn_info(f"Orchestrator forcing trade for {player.name} due to AI non-compliance during must_trade.")
            possible_sets = self.engine.find_valid_card_sets(player)
            if possible_sets:
                first_set_cards = possible_sets[0]
                first_set_indices = []
                # Find indices of these cards in the player's current hand
                # This assumes card objects returned by find_valid_card_sets are the same instances as in player.hand
                for card_in_set in first_set_cards:
                    try:
                        idx = player.hand.index(card_in_set)
                        if idx not in first_set_indices:
                             first_set_indices.append(idx)
                    except ValueError:
                        self.log_turn_info(f"Error: Could not find card {card_in_set.to_dict()} in player's hand for forced trade. This is unexpected if find_valid_card_sets is correct.")
                        # This indicates a deeper issue if find_valid_card_sets returns cards not in hand.
                        # Forcing a re-prompt for AI.
                        self.ai_is_thinking = False
                        if self.gui: self._update_gui_full_state()
                        return

                if len(first_set_indices) == 3:
                    self.log_turn_info(f"Orchestrator forcing trade for {player.name} with card indices: {sorted(first_set_indices)}.")
                    trade_result = self.engine.perform_card_trade(player, sorted(first_set_indices))
                    self.log_turn_info(f"Forced trade result for {player.name}: {trade_result.get('message')}")
                    if trade_result.get("success"):
                         self.log_turn_info(f"{player.name} gained {trade_result['armies_gained']} armies from forced trade. Total to deploy: {player.armies_to_deploy}.")
                         if trade_result.get("territory_bonus"): self.log_turn_info(trade_result["territory_bonus"])
                else:
                    self.log_turn_info(f"Error: Failed to form a unique set of 3 indices for forced trade for {player.name} from cards: {[c.to_dict() for c in first_set_cards]}. Indices found: {first_set_indices}. AI prompted again.")
            else:
                self.log_turn_info(f"CRITICAL Error: {player.name} must_trade but no valid sets found by engine's find_valid_card_sets for forced trade. AI prompted again.")

            self.ai_is_thinking = False # After forced attempt or error, let AI decide next
            if self.gui: self._update_gui_full_state()
            return

        # --- Continue with normal processing if not a must_trade failure handled above ---
        if action_type == "TRADE_CARDS":
            # This path is now only for:
            # 1. Optional trades (must_trade_currently was false).
            # 2. AI-initiated trades when must_trade was true AND its trade was successful (already returned).
            # So, if we reach here with action_type == "TRADE_CARDS", it implies an optional trade attempt.
            if not must_trade_currently: # Redundant check given the logic flow, but safe.
                card_indices = action.get("card_indices") # Already validated if it was a must_trade success.
                if not isinstance(card_indices, list) or not all(isinstance(idx, int) for idx in card_indices) or len(set(card_indices)) != 3:
                     self.log_turn_info(f"{player.name} selected optional TRADE_CARDS with invalid indices format: {card_indices}. AI will be prompted again.")
                else:
                    trade_result = self.engine.perform_card_trade(player, card_indices)
                    log_message = trade_result.get('message', f"Optional trade attempt by {player.name} with cards {card_indices}.")
                    self.log_turn_info(log_message)
                    if trade_result.get("success"):
                        self.log_turn_info(f"{player.name} gained {trade_result['armies_gained']} armies. Total to deploy: {player.armies_to_deploy}.")
                        if trade_result.get("territory_bonus"): self.log_turn_info(trade_result["territory_bonus"])
                        self.engine.game_state.event_history.append({
                            "turn": self.engine.game_state.current_turn_number, "type": "CARD_TRADE", "player": player.name,
                            "cards_traded_symbols": trade_result.get("traded_card_symbols", []),
                            "armies_gained": trade_result.get("armies_gained", 0),
                            "territory_bonus_info": trade_result.get("territory_bonus")
                        })
            self.ai_is_thinking = False

        elif action_type == "DEPLOY":
            terr_name = action.get("territory")
            num_armies_to_deploy = action.get("num_armies")
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
                    actual_armies_to_deploy_on_territory = min(num_armies_to_deploy, player.armies_to_deploy)
                    if actual_armies_to_deploy_on_territory > 0 :
                        territory_obj.army_count += actual_armies_to_deploy_on_territory
                        player.armies_to_deploy -= actual_armies_to_deploy_on_territory
                        self.log_turn_info(f"{player.name} deployed {actual_armies_to_deploy_on_territory} armies to {terr_name} (new total: {territory_obj.army_count}). Armies left to deploy: {player.armies_to_deploy}.")
                    else:
                        self.log_turn_info(f"{player.name} DEPLOY action for {terr_name} resulted in no armies deployed (requested: {num_armies_to_deploy}, available: {player.armies_to_deploy}). AI will be prompted again.")
            self.ai_is_thinking = False
        elif action_type == "END_REINFORCE_PHASE":
            current_valid_actions = self.engine.get_valid_actions(player)
            if any(a['type'] == 'TRADE_CARDS' and a.get('must_trade') for a in current_valid_actions):
                 self.log_turn_info(f"{player.name} tried END_REINFORCE_PHASE but MUST_TRADE cards. AI will be prompted again.")
                 self.ai_is_thinking = False
            else:
                if player.armies_to_deploy > 0:
                    self.log_turn_info(f"Warning: {player.name} chose END_REINFORCE_PHASE with {player.armies_to_deploy} armies remaining. Auto-distributing.")
                    self.auto_distribute_armies(player, player.armies_to_deploy)
                else:
                     self.log_turn_info(f"{player.name} ends REINFORCE phase with all armies deployed.")
                player.armies_to_deploy = 0
                self.engine.game_state.current_game_phase = "ATTACK"
                self.has_logged_current_turn_player_phase = False
                self.ai_is_thinking = False
                self.log_turn_info(f"Orchestrator: {player.name} REINFORCE phase ended. Transitioning to ATTACK.") # Corrected: Using log_turn_info
        else:
            self.log_turn_info(f"{player.name} provided an unknown REINFORCE action type: '{action_type}'. AI will be prompted again.")
            self.ai_is_thinking = False
        if self.gui: self._update_gui_full_state()

    def _initiate_attack_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        """Gathers info and starts the AI thinking for the ATTACK phase (or PAF)."""
        self.log_turn_info(f"Orchestrator: Initiating ATTACK/PAF AI action for {player.name}.")
        game_state_json = self.engine.game_state.to_json_with_history() # Corrected: Using to_json_with_history
        paf_required = self.engine.game_state.requires_post_attack_fortify
        self.log_turn_info(f"Orchestrator: _initiate_attack_ai_action for {player.name}. PAF required: {paf_required}.")
        if paf_required:
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
                return
        valid_actions = self.engine.get_valid_actions(player)
        self.log_turn_info(f"Orchestrator: Regular ATTACK phase for {player.name}. Valid actions from engine: {valid_actions}")
        if not valid_actions or (len(valid_actions) == 1 and valid_actions[0]['type'] == "END_ATTACK_PHASE"):
            self.log_turn_info(f"Orchestrator: No actual attack options (or only END_ATTACK_PHASE) for {player.name}. Transitioning phase to FORTIFY directly in _initiate_attack_ai_action.")
            self.engine.game_state.current_game_phase = "FORTIFY"
            self.has_logged_current_turn_player_phase = False
            self.ai_is_thinking = False
            if self.gui: self._update_gui_full_state()
            return
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
        attacks_this_turn = 0
        if self.current_ai_context and isinstance(self.current_ai_context.get("attacks_this_turn"), int):
            attacks_this_turn = self.current_ai_context["attacks_this_turn"]
        if not action or not isinstance(action, dict) or "type" not in action:
            self.log_turn_info(f"Orchestrator: Player {player.name} provided malformed or missing ATTACK action: {action}. AI will be prompted again for ATTACK phase.")
            self.ai_is_thinking = False
            if self.gui: self._update_gui_full_state()
            return
        action_type = action["type"]
        self.log_turn_info(f"Orchestrator: Player {player.name} ATTACK action type: '{action_type}'. Details: {action}")
        if action_type in ["ACCEPT_ALLIANCE", "REJECT_ALLIANCE"]:
            if self._process_diplomatic_action(player, action):
                self.ai_is_thinking = False
                if self.gui: self._update_gui_full_state()
                return
        if action_type == "POST_ATTACK_FORTIFY":
            num_to_move = action.get("num_armies")
            conquest_ctx = self.engine.game_state.conquest_context
            min_movable_default = conquest_ctx.get('min_movable', 1) if conquest_ctx else 1
            if not isinstance(num_to_move, int):
                self.log_turn_info(f"Orchestrator: {player.name} PAF num_armies invalid type: {num_to_move}. Defaulting to min: {min_movable_default}.")
                num_to_move = min_movable_default
            fortify_log = self.engine.perform_post_attack_fortify(player, num_to_move)
            self.log_turn_info(f"Orchestrator: {player.name} PAF engine call result: {fortify_log.get('message', 'PAF outcome unknown.')}")
            self.log_turn_info(f"Orchestrator: PAF for {player.name} complete. PAF required is now: {self.engine.game_state.requires_post_attack_fortify}")
            self.ai_is_thinking = False
            if self.engine.is_game_over():
                 self.ai_is_thinking = False
        elif action_type == "ATTACK":
            from_territory_name = action.get("from")
            to_territory_name = action.get("to")
            num_armies = action.get("num_armies")
            if not all(isinstance(param, str) for param in [from_territory_name, to_territory_name]) or \
               not isinstance(num_armies, int) or num_armies <= 0:
                self.log_turn_info(f"Orchestrator: {player.name} invalid ATTACK parameters: from='{from_territory_name}', to='{to_territory_name}', num_armies='{num_armies}'. AI will be prompted again.")
                self.ai_is_thinking = False
                if self.gui: self._update_gui_full_state()
                return
            defender_territory_obj = self.engine.game_state.territories.get(to_territory_name)
            explicit_defense_dice = None
            if self.is_two_player_mode and defender_territory_obj and \
               defender_territory_obj.owner and defender_territory_obj.owner.is_neutral:
                other_human_player = None
                for p_obj in self.engine.game_state.players:
                    if not p_obj.is_neutral and p_obj.name != player.name:
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
                            def_prompt = (f"Player {player.name} is attacking neutral territory {to_territory_name} "
                                          f"(armies: {defender_territory_obj.army_count}). "
                                          f"You ({other_human_player.name}) must choose how many dice Neutral will defend with.")
                            def_rules = "Choose one action from the list: {'type': 'CHOOSE_DEFENSE_DICE', 'num_dice': 1_or_2}"
                            original_active_ai_name = self.active_ai_player_name
                            self.active_ai_player_name = other_human_agent.player_name
                            defense_choice_response = other_human_agent.get_thought_and_action(
                                self.engine.game_state.to_json_with_history(), defense_dice_options, def_rules, def_prompt
                            )
                            self.log_ai_thought(other_human_agent.player_name, defense_choice_response.get("thought", "N/A (defense dice choice)"))
                            self.active_ai_player_name = original_active_ai_name
                            defense_action = defense_choice_response.get("action")
                            if defense_action and defense_action.get("type") == "CHOOSE_DEFENSE_DICE":
                                explicit_defense_dice = defense_action.get("num_dice")
                                if not (explicit_defense_dice == 1 or (explicit_defense_dice == 2 and defender_territory_obj.army_count >=2)):
                                    self.log_turn_info(f"Warning: Invalid defense dice choice {explicit_defense_dice} from {other_human_player.name}. Defaulting to 1 die.")
                                    explicit_defense_dice = 1 if defender_territory_obj.army_count >=1 else 0
                            else:
                                self.log_turn_info(f"Warning: {other_human_player.name} failed to choose defense dice. Defaulting to 1 die.")
                                explicit_defense_dice = 1 if defender_territory_obj.army_count >=1 else 0
                        else: explicit_defense_dice = 0
                    else:
                        self.log_turn_info(f"Warning: No AI agent for other human player {other_human_player.name} to choose neutral defense. Defaulting dice.")
                        explicit_defense_dice = 1 if defender_territory_obj.army_count >=1 else 0
                else:
                    self.log_turn_info("Warning: Could not find other human player in 2P mode for neutral defense. Defaulting dice.")
                    explicit_defense_dice = 1 if defender_territory_obj.army_count >=1 else 0
            attack_log = self.engine.perform_attack(from_territory_name, to_territory_name, num_armies, explicit_defense_dice)
            self.log_turn_info(f"Orchestrator: Engine perform_attack log for {player.name}: {attack_log}")
            if "error" not in attack_log:
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
                                 self.ai_is_thinking = False
                                 if self.gui: self._update_gui_full_state()
                                 return
            self.ai_is_thinking = False
        elif action_type == "END_ATTACK_PHASE":
            self.log_turn_info(f"Orchestrator: {player.name} chose to end ATTACK phase. Transitioning to FORTIFY.")
            self.engine.game_state.current_game_phase = "FORTIFY"
            self.has_logged_current_turn_player_phase = False
            self.ai_is_thinking = False
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
                if not target_agent:
                    self.log_turn_info(f"Orchestrator: {player.name} invalid PRIVATE_CHAT target: Player '{target_player_name}' not found, is neutral, or not an AI.")
                elif target_agent == agent:
                    self.log_turn_info(f"Orchestrator: {player.name} attempted PRIVATE_CHAT with self. Action ignored.")
                else:
                    self.log_turn_info(f"Orchestrator: Initiating private chat between {player.name} and {target_player_name}.")
                    initiator_goal = f"Your goal is to negotiate a favorable outcome with {target_player_name}. Consider proposing an ALLIANCE, a non-aggression pact, or a joint attack."
                    recipient_goal = f"Your goal is to evaluate {player.name}'s proposal and negotiate the best terms for yourself. You can accept, reject, or make a counter-offer."
                    conversation_log_entries, negotiated_action = self.private_chat_manager.run_conversation(
                        agent1=agent, agent2=target_agent, initial_message=initial_message,
                        game_state=self.engine.game_state, game_rules=self.game_rules,
                        initiator_goal=initiator_goal, recipient_goal=recipient_goal
                    )
                    summary_msg = f"Private chat between {player.name} and {target_player_name} concluded ({len(conversation_log_entries)} messages)."
                    if self.gui: self.gui.log_action(summary_msg)
                    self.log_turn_info(f"Orchestrator: {summary_msg}")
                    if negotiated_action:
                        self.log_turn_info(f"Orchestrator: Private chat resulted in a negotiated action: {negotiated_action}")
                        if negotiated_action.get("type") == "PROPOSE_ALLIANCE":
                            proposer = negotiated_action.get("proposing_player_name")
                            target = negotiated_action.get("target_player_name")
                            if proposer and target:
                                diplomatic_key = frozenset({proposer, target})
                                self.engine.game_state.diplomacy[diplomatic_key] = "PROPOSED_ALLIANCE"
                                self.engine.game_state.active_diplomatic_proposals[diplomatic_key] = {
                                    'proposer': proposer, 'target': target, 'type': 'ALLIANCE',
                                    'turn_proposed': self.engine.game_state.current_turn_number
                                }
                                self.log_turn_info(f"Diplomacy: {proposer} proposed ALLIANCE to {target}. Proposal recorded.")
                                self.global_chat.broadcast("GameSystem", f"{proposer} has proposed an alliance to {target} via private channels.")
                                self.engine.game_state.event_history.append({
                                    "turn": self.engine.game_state.current_turn_number, "type": "DIPLOMACY_PROPOSAL",
                                    "subtype": "ALLIANCE_PROPOSED", "proposer": proposer, "target": target
                                })
                        elif negotiated_action.get("type") == "ACCEPT_ALLIANCE":
                            accepter = negotiated_action.get("accepting_player_name")
                            proposer = negotiated_action.get("proposing_player_name")
                            if accepter and proposer:
                                diplomatic_key = frozenset({accepter, proposer})
                                self.engine.game_state.diplomacy[diplomatic_key] = "ALLIANCE"
                                self.log_turn_info(f"Diplomacy: {accepter} ACCEPTED ALLIANCE with {proposer}. Status set to ALLIANCE.")
                                self.global_chat.broadcast("GameSystem", f"{accepter} and {proposer} have formed an ALLIANCE!")
                                self.engine.game_state.event_history.append({
                                    "turn": self.engine.game_state.current_turn_number, "type": "DIPLOMACY_CHANGE",
                                    "subtype": "ALLIANCE_FORMED", "players": sorted([accepter, proposer])
                                })
                        self._update_gui_full_state()
                    else:
                        self.log_turn_info(f"Orchestrator: Private chat between {player.name} and {target_player_name} did not result in a formal agreement.")
            self.ai_is_thinking = False
        elif action_type == "BREAK_ALLIANCE":
            target_player_name = action.get("target_player_name")
            if player and target_player_name:
                diplomatic_key = frozenset({player.name, target_player_name})
                if self.engine.game_state.diplomacy.get(diplomatic_key) == "ALLIANCE":
                    self.engine.game_state.diplomacy[diplomatic_key] = "NEUTRAL"
                    self.log_turn_info(f"Diplomacy: {player.name} BROKE ALLIANCE with {target_player_name}. Status set to NEUTRAL.")
                    self.global_chat.broadcast("GameSystem", f"{player.name} has broken their alliance with {target_player_name}!")
                    self.engine.game_state.event_history.append({
                        "turn": self.engine.game_state.current_turn_number, "type": "DIPLOMACY_CHANGE",
                        "subtype": "ALLIANCE_BROKEN", "breaker": player.name, "target": target_player_name, "new_status": "NEUTRAL"
                    })
                    self._update_gui_full_state()
                else:
                    self.log_turn_info(f"Orchestrator: {player.name} tried to BREAK_ALLIANCE with {target_player_name}, but no alliance existed.")
            else:
                self.log_turn_info(f"Orchestrator: {player.name} tried BREAK_ALLIANCE with invalid parameters: {action}")
            self.ai_is_thinking = False
        else:
            self.log_turn_info(f"Orchestrator: Player {player.name} provided an unknown ATTACK action type: '{action_type}'. AI will be prompted again.")
            self.ai_is_thinking = False
        self.log_turn_info(f"Orchestrator: End of _process_attack_ai_action for {player.name}. ai_is_thinking: {self.ai_is_thinking}, current_phase: {self.engine.game_state.current_game_phase}")
        if self.gui: self._update_gui_full_state()

    def _initiate_fortify_ai_action(self, player: GamePlayer, agent: BaseAIAgent):
        """Gathers info and starts the AI thinking for the FORTIFY phase."""
        self.log_turn_info(f"Orchestrator: Initiating FORTIFY AI action for {player.name}. Player has_fortified_this_turn: {player.has_fortified_this_turn}")
        game_state_json = self.engine.game_state.to_json_with_history() # Corrected: Using to_json_with_history
        valid_actions = self.engine.get_valid_actions(player)
        self.log_turn_info(f"Orchestrator: Valid actions for {player.name} in FORTIFY: {valid_actions}")
        if not valid_actions:
             self.log_turn_info(f"CRITICAL: No valid FORTIFY actions for {player.name} (should always have END_TURN). Ending turn to prevent issues.");
             self.engine.game_state.current_game_phase = "REINFORCE"
             self.engine.next_turn()
             self.has_logged_current_turn_player_phase = False
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
        else:
            action_type = action["type"]
            self.log_turn_info(f"{player.name} chose FORTIFY action: {action_type} - Full Details: {action}")
            if action_type in ["ACCEPT_ALLIANCE", "REJECT_ALLIANCE"]:
                if self._process_diplomatic_action(player, action):
                    pass
            elif action_type == "FORTIFY":
                if player.has_fortified_this_turn:
                     self.log_turn_info(f"{player.name} attempted to FORTIFY again in the same turn (has_fortified_this_turn was True). Action ignored. Turn will end.")
                else:
                    from_territory_name = action.get("from")
                    to_territory_name = action.get("to")
                    num_armies = action.get("num_armies")
                    if not all(isinstance(param, str) for param in [from_territory_name, to_territory_name]) or \
                       not isinstance(num_armies, int) or num_armies < 0: # Allow 0 for "skip"
                        self.log_turn_info(f"{player.name} provided invalid FORTIFY parameters: from='{from_territory_name}', to='{to_territory_name}', num_armies='{num_armies}'. No fortification performed. Turn will end.")
                    else:
                        fortify_result = self.engine.perform_fortify(from_territory_name, to_territory_name, num_armies)
                        log_message = fortify_result.get('message', f"Fortify attempt by {player.name} from {from_territory_name} to {to_territory_name} with {num_armies} armies.")
                        self.log_turn_info(f"Engine fortify result for {player.name}: {log_message}. Success: {fortify_result.get('success', False)}")
            elif action_type == "END_TURN":
                self.log_turn_info(f"{player.name} explicitly chose to END_TURN during fortify phase.")
            else:
                self.log_turn_info(f"{player.name} provided an unknown action type '{action_type}' during FORTIFY phase. Turn will end.")
        self.log_turn_info(f"Orchestrator: Player {player.name} status after processing fortify action: has_fortified_this_turn = {player.has_fortified_this_turn}")
        self.ai_is_thinking = False
        self.log_turn_info(f"Orchestrator: {player.name} FORTIFY phase AI processing complete. Turn will now end via main loop.")
        if self.gui: self._update_gui_full_state()

    def auto_distribute_armies(self, player: GamePlayer, armies_to_distribute: int):
        """Simple iterative distribution of armies to player's territories."""
        if not player.territories:
            self.log_turn_info(f"Warning: {player.name} has no territories to auto-distribute {armies_to_distribute} armies.")
            player.armies_to_deploy = 0 # Clear remaining armies
            return

        idx = 0
        while armies_to_distribute > 0:
            territory_to_reinforce = player.territories[idx % len(player.territories)]
            territory_to_reinforce.army_count += 1
            armies_to_distribute -= 1
            self.log_turn_info(f"Auto-distributed 1 army to {territory_to_reinforce.name} for {player.name} (new total: {territory_to_reinforce.army_count}).")
            idx += 1
        player.armies_to_deploy = 0 # Ensure it's zeroed out
        if self.gui: self._update_gui_full_state()

    def handle_player_elimination(self, eliminated_player_name: str):
        gs = self.engine.game_state
        player_to_remove_engine: GamePlayer | None = None
        original_index = -1

        # Find the player in the engine's main player list
        for i, p_obj in enumerate(gs.players):
            if p_obj.name == eliminated_player_name:
                player_to_remove_engine = p_obj
                original_index = i
                break

        if player_to_remove_engine:
            # Cards are handled by the engine in perform_attack when elimination occurs.
            # Remove player from game state lists
            gs.players.pop(original_index)
            self.log_turn_info(f"Removed {eliminated_player_name} from engine player list at index {original_index}.")

            # Adjust current_player_index if the removed player was before or at the current index
            if original_index <= gs.current_player_index and gs.current_player_index > 0:
                gs.current_player_index -= 1
                self.log_turn_info(f"Adjusted current_player_index to {gs.current_player_index} due to elimination.")

            # Remove from player_setup_order if present (relevant during setup phases)
            if gs.player_setup_order:
                new_setup_order = [p for p in gs.player_setup_order if p.name != eliminated_player_name]
                if len(new_setup_order) < len(gs.player_setup_order):
                    self.log_turn_info(f"Removed {eliminated_player_name} from player_setup_order.")
                    # Adjust current_setup_player_index carefully
                    # This part is complex as the index might need to wrap or shift.
                    # For simplicity, if current setup player was eliminated, orchestrator might need to re-evaluate.
                    # A common approach is to let the turn advance; if the current_setup_player_index becomes invalid,
                    # _get_current_setup_player_and_agent will handle it or next turn logic will pick next valid.
                    # However, if the removed player was *before* the current_setup_player_index in the original list,
                    # and current_setup_player_index was based on the old list, it needs adjustment.
                    # This requires knowing the index of the eliminated player *within player_setup_order*.
                    try:
                        eliminated_player_setup_idx = next(i for i, p_setup in enumerate(gs.player_setup_order) if p_setup.name == eliminated_player_name)
                        gs.player_setup_order = new_setup_order # Update the list
                        if eliminated_player_setup_idx < gs.current_setup_player_index:
                             gs.current_setup_player_index -=1
                             self.log_turn_info(f"Adjusted current_setup_player_index to {gs.current_setup_player_index}.")
                        # If eliminated player *was* the current setup player, the orchestrator loop will pick next valid one from new list.
                    except StopIteration:
                        # Player was not in setup order, no adjustment needed for this list.
                        gs.player_setup_order = new_setup_order # Still update the list

        else:
            self.log_turn_info(f"Warning: Could not find {eliminated_player_name} in engine player list to remove.")

        # Remove from orchestrator's AI agent tracking
        if eliminated_player_name in self.ai_agents:
            del self.ai_agents[eliminated_player_name]
            self.log_turn_info(f"Removed {eliminated_player_name} from AI agents dictionary.")

        # Remove from player_map (mapping GamePlayer object to AI agent)
        # Need to find the GamePlayer object by name as the object reference might be stale if list was modified
        key_to_remove_map = None
        for gp_key in list(self.player_map.keys()): # Iterate over a copy for safe deletion
            if gp_key.name == eliminated_player_name:
                key_to_remove_map = gp_key
                break
        if key_to_remove_map and key_to_remove_map in self.player_map: # Check if key still exists before deleting
            del self.player_map[key_to_remove_map]
            self.log_turn_info(f"Removed {eliminated_player_name} from player_map.")

        self.log_turn_info(f"Player {eliminated_player_name} fully processed for elimination.")
        if self.gui: self._update_gui_full_state()


    def log_ai_thought(self, player_name: str, thought: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] --- {player_name}'s Thought --- \n{thought}\n--------------------"
        print(log_entry) # Keep console log for immediate feedback
        if self.gui: self.gui.update_thought_panel(player_name, thought)

        log_dir = "game_logs"
        os.makedirs(log_dir, exist_ok=True)
        game_log_file = os.path.join(log_dir, "game_thoughts_log.txt")
        try:
            with open(game_log_file, "a") as f:
                f.write(log_entry + "\n")
        except IOError:
            print(f"Error: Could not write thought to {game_log_file}")

    def log_turn_info(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        print(log_entry) # Keep console log for immediate feedback
        if self.gui: self.gui.log_action(message)

        log_dir = "game_logs"
        os.makedirs(log_dir, exist_ok=True)
        game_log_file = os.path.join(log_dir, "game_events_log.txt")
        try:
            with open(game_log_file, "a") as f:
                f.write(log_entry + "\n")
        except IOError:
            print(f"Error: Could not write event to {game_log_file}")

    def setup_gui(self):
        if not self.gui: # Ensure GUI is initialized only once
            self.gui = GameGUI(self.engine, self) # Pass self (orchestrator) to GUI
            print("GUI setup complete. GUI is active.")
        else:
            print("GUI already setup.")

if __name__ == '__main__':
    print("Setting up Game Orchestrator for a test run...")
    # Default to 2-player if no config is provided or is invalid
    dummy_player_config = [
        {"name": "Player1-Gemini", "color": "Red", "ai_type": "Gemini"},
        {"name": "Player2-OpenAI", "color": "Blue", "ai_type": "OpenAI"}
    ]

    config_file_path = "player_config.json"

    # Try to load existing config, if not, create a default one
    try:
        with open(config_file_path, 'r') as f:
            loaded_config = json.load(f)
            # Basic validation: check if it's a list of dicts
            if isinstance(loaded_config, list) and all(isinstance(item, dict) for item in loaded_config) and loaded_config:
                print(f"Successfully loaded player configurations from '{config_file_path}'.")
                dummy_player_config = loaded_config # Use loaded config
            else:
                print(f"Warning: '{config_file_path}' has invalid format. Using default 2-player setup.")
                # Re-write with default if format is bad
                with open(config_file_path, 'w') as f_write:
                    json.dump(dummy_player_config, f_write, indent=2)
                print(f"Created/Reverted to default player setup in '{config_file_path}'.")

    except FileNotFoundError:
        print(f"Player config file '{config_file_path}' not found. Creating with default 2-player setup.")
        try:
            with open(config_file_path, 'w') as f:
                json.dump(dummy_player_config, f, indent=2)
            print(f"Created default player setup file '{config_file_path}'.")
        except IOError:
            print(f"Could not create default player setup file '{config_file_path}'. Check permissions.")
    except json.JSONDecodeError:
        print(f"Error decoding JSON from '{config_file_path}'. Creating with default 2-player setup.")
        try:
            with open(config_file_path, 'w') as f:
                json.dump(dummy_player_config, f, indent=2)
            print(f"Reverted to default player setup in '{config_file_path}'.")
        except IOError:
            print(f"Could not create default player setup file '{config_file_path}' after JSON error. Check permissions.")

    # Orchestrator will use the config file specified by default_player_setup_file
    orchestrator = GameOrchestrator(default_player_setup_file=config_file_path)

    print("Starting game run...")
    orchestrator.run_game()
    print("\nGame run finished.")

    # Log final game state or summary if desired
    final_log_dir = "game_logs"
    os.makedirs(final_log_dir, exist_ok=True)
    final_state_file = os.path.join(final_log_dir, "final_game_state.json")
    try:
        with open(final_state_file, "w") as f:
            # We need a way to serialize the full GameState, to_json might not be enough
            # For now, just a simple message or basic serialization
            # A more complete serialization would involve iterating through players, territories etc.
            # and building a dict. For now, using the existing to_json() for a snapshot.
            f.write(orchestrator.engine.game_state.to_json_with_history(include_map=True)) # Include map for full context
        print(f"Final game state snapshot saved to {final_state_file}")
    except Exception as e:
        print(f"Could not save final game state: {e}")
