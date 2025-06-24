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

import json # For loading player configs if any
import time # For potential delays
from datetime import datetime # For logging timestamp
import os # For log directory creation

class GameOrchestrator:
    def __init__(self, map_file: str = "map_config.json", player_setup_file: str = "player_config.json"):
        self.engine = GameEngine(map_file_path=map_file)
        self.global_chat = GlobalChat()
        self.private_chat_manager = PrivateChatManager(max_exchanges_per_conversation=3) # Default 3 exchanges

        self.gui = None # Initialize GUI later if used: self.gui = GameGUI(self.engine)
        self.setup_gui() # Call setup_gui here

        self.ai_agents: dict[str, BaseAIAgent] = {} # Maps player name to AI agent instance
        self.player_map: dict[GamePlayer, BaseAIAgent] = {} # Maps GamePlayer object to AI agent

        self._load_player_setup(player_setup_file) # Loads AI agents and player info

        # Initialize board after loading players, as initialize_board now takes player data
        players_data_for_engine = [{"name": p.name, "color": p.color} for p in self.engine.game_state.players]
        self.engine.initialize_board(players_data=players_data_for_engine)

        self._map_game_players_to_ai_agents()

        self.game_rules = GAME_RULES_SNIPPET # Central place for game rules text for AIs
        self.turn_action_log = [] # Log actions for GUI or review

    def _load_player_setup(self, player_setup_file: str):
        """
        Loads player configurations and initializes AI agents.
        The game engine's players list will be populated here.
        """
        try:
            with open(player_setup_file, 'r') as f:
                player_configs = json.load(f)
        except FileNotFoundError:
            print(f"Warning: Player setup file '{player_setup_file}' not found. Using default AI setup.")
            # Define a default setup if file not found
            player_configs = [
                {"name": "PlayerA (Gemini)", "color": "Red", "ai_type": "Gemini"},
                {"name": "PlayerB (OpenAI)", "color": "Blue", "ai_type": "OpenAI"},
                {"name": "PlayerC (Claude)", "color": "Green", "ai_type": "Claude"},
                {"name": "PlayerD (DeepSeek)", "color": "Yellow", "ai_type": "DeepSeek"}
            ]
            # Create the default file for next time
            try:
                with open(player_setup_file, 'w') as f:
                    json.dump(player_configs, f, indent=2)
                print(f"Created default player_config.json.")
            except IOError:
                print(f"Could not write default player_config.json.")


        for config in player_configs:
            player_name = config["name"]
            player_color = config["color"]
            ai_type = config.get("ai_type", "Gemini") # Default to Gemini if not specified

            # Create GamePlayer for the engine's list of players
            # This ensures the engine knows about the players before initialize_board fully populates them
            game_player_obj = GamePlayer(name=player_name, color=player_color)
            self.engine.game_state.players.append(game_player_obj)

            agent: BaseAIAgent | None = None
            if ai_type == "Gemini":
                agent = GeminiAgent(player_name, player_color)
            elif ai_type == "OpenAI":
                agent = OpenAIAgent(player_name, player_color)
            elif ai_type == "Claude":
                agent = ClaudeAgent(player_name, player_color)
            elif ai_type == "DeepSeek":
                agent = DeepSeekAgent(player_name, player_color)
            # Add more AI types here
            else:
                print(f"Warning: Unknown AI type '{ai_type}' for player {player_name}. Defaulting to Gemini.")
                agent = GeminiAgent(player_name, player_color)

            if agent:
                self.ai_agents[player_name] = agent

        if len(self.engine.game_state.players) < 2 :
            print("Error: At least two players are required to start the game.")
            raise ValueError("Insufficient players configured.")


    def _map_game_players_to_ai_agents(self):
        """
        Maps the GamePlayer objects (from engine.game_state.players which are now fully set up
        after initialize_board) to their corresponding AI agent controllers.
        This is crucial because territory ownership etc. in engine uses GamePlayer objects.
        """
        self.player_map.clear()
        for gp in self.engine.game_state.players: # gp is a GamePlayer object
            if gp.name in self.ai_agents:
                self.player_map[gp] = self.ai_agents[gp.name]
            else:
                print(f"Critical Error: GamePlayer {gp.name} from engine does not have a corresponding AI agent.")
                # This should not happen if _load_player_setup and initialize_board work correctly.

    def get_agent_for_current_player(self) -> BaseAIAgent | None:
        current_game_player = self.engine.game_state.get_current_player()
        if current_game_player and current_game_player in self.player_map:
            return self.player_map[current_game_player]
        elif current_game_player:
            print(f"Error: No AI agent mapped for current GamePlayer: {current_game_player.name}")
        else:
            print("Error: No current player in game state.")
        return None

    def run_game(self):
        """
        The main game loop.
        """
        if not self.player_map: # Ensure mapping is done
            print("Critical: Player map not initialized. Attempting to map now.")
            self._map_game_players_to_ai_agents()
            if not self.player_map:
                 print("Failed to initialize player_map. Exiting.")
                 return

        print("Starting LLM Risk Game!")
        if self.gui: self.gui.update(self.engine.game_state)

        game_turn = 0 # For safety break
        running = True
        while running and not self.engine.is_game_over() and game_turn < 200: # Max 200 turns for now
            if self.gui:
                if not self.gui.handle_input(): # Process GUI events and check for quit
                    running = False
                    break

            game_turn +=1
            self.turn_action_log.clear() # Clear log for the new turn

            current_player_obj = self.engine.game_state.get_current_player()
            if not current_player_obj:
                print("Error: No current player. Ending game.")
                break

            current_player_agent = self.get_agent_for_current_player()
            if not current_player_agent:
                print(f"Error: No AI agent for {current_player_obj.name}. Skipping turn.")
                self.engine.next_turn()
                continue

            print(f"\n--- Turn {self.engine.game_state.current_turn_number} | Player: {current_player_obj.name} ({current_player_obj.color}) | Phase: {self.engine.game_state.current_game_phase} ---")
            self.log_turn_info(f"Turn {self.engine.game_state.current_turn_number} starting for {current_player_obj.name}.")

            # --- 1. REINFORCE PHASE ---
            self.handle_reinforce_phase(current_player_obj, current_player_agent)
            if self.gui: self.gui.update(self.engine.game_state)
            if self.engine.is_game_over() or not running : break

            # --- 2. ATTACK/COMMUNICATE PHASE ---
            self.engine.game_state.current_game_phase = "ATTACK"
            self.log_turn_info(f"{current_player_obj.name} starting ATTACK phase.")
            if self.gui: self.gui.update(self.engine.game_state)
            self.handle_attack_communicate_phase(current_player_obj, current_player_agent)
            if self.gui: self.gui.update(self.engine.game_state)
            if self.engine.is_game_over() or not running : break

            # --- 3. FORTIFY PHASE ---
            self.engine.game_state.current_game_phase = "FORTIFY"
            self.log_turn_info(f"{current_player_obj.name} starting FORTIFY phase.")
            if self.gui: self.gui.update(self.engine.game_state)
            self.handle_fortify_phase(current_player_obj, current_player_agent)
            if self.gui: self.gui.update(self.engine.game_state)
            if self.engine.is_game_over() or not running : break

            if running: # Only proceed to next turn if GUI hasn't quit
                self.engine.next_turn()
                if self.gui: self.gui.update(self.engine.game_state)
                # time.sleep(1) # Small delay between turns
            else: # If GUI quit during a phase
                break


        # Game Over
        winner = self.engine.is_game_over()
        if winner:
            win_msg = f"\n--- GAME OVER! Winner is {winner.name}! ---"
            print(win_msg)
            self.log_turn_info(win_msg)
            self.global_chat.broadcast("GameSystem", win_msg)
        elif game_turn >= 200:
            timeout_msg = f"\n--- GAME OVER! Reached maximum turns ({game_turn}). No winner declared by conquest. ---"
            print(timeout_msg)
            self.log_turn_info(timeout_msg)
            self.global_chat.broadcast("GameSystem", timeout_msg)
        elif running: # Game ended unexpectedly but GUI was still running
            print("\n--- GAME ENDED UNEXPECTEDLY ---")
            self.log_turn_info("Game ended unexpectedly.")
        else: # Game ended because GUI quit
            print("\n--- GAME EXITED VIA GUI ---")
            self.log_turn_info("Game exited via GUI.")


        if self.gui and running: # Only show game over if GUI didn't cause the exit
            self.gui.show_game_over_screen(winner.name if winner else "Draw/Timeout")
        elif not running and self.gui: # If GUI quit, ensure pygame is cleaned up if not already by show_game_over_screen
            pygame.quit()


    def handle_reinforce_phase(self, player: GamePlayer, agent: BaseAIAgent):
        print(f"{player.name} has {player.armies_to_deploy} reinforcements to deploy.")
        # TODO: Card trading logic
        # For now, only territory/continent based reinforcements are calculated by engine.next_turn()

        while player.armies_to_deploy > 0:
            game_state_json = self.engine.game_state.to_json()
            valid_actions = self.engine.get_valid_actions(player) # Should primarily be DEPLOY actions

            # Filter for DEPLOY actions or END_REINFORCE_PHASE
            reinforce_actions = [a for a in valid_actions if a['type'] == 'DEPLOY' or a['type'] == 'END_REINFORCE_PHASE']
            if not any(a['type'] == 'DEPLOY' for a in reinforce_actions) and player.armies_to_deploy > 0:
                 # This case implies player has armies but no valid territories to deploy (e.g. lost all territories before deploying)
                 print(f"Warning: {player.name} has {player.armies_to_deploy} armies but no valid DEPLOY actions. Clearing armies.")
                 player.armies_to_deploy = 0
                 break # Exit reinforcement loop

            if not reinforce_actions : # Should not happen if END_REINFORCE_PHASE is always an option
                print(f"Warning: No reinforce actions for {player.name} with {player.armies_to_deploy} armies. Ending phase.")
                break

            ai_response = agent.get_thought_and_action(game_state_json, reinforce_actions, self.game_rules)
            action = ai_response.get("action")
            thought = ai_response.get("thought", "(No thought provided)")
            self.log_ai_thought(player.name, thought)

            if action and action.get("type") == "DEPLOY":
                terr_name = action.get("territory")
                num_armies = action.get("num_armies")
                territory_to_deploy = self.engine.game_state.territories.get(terr_name)

                if territory_to_deploy and territory_to_deploy.owner == player and isinstance(num_armies, int) and num_armies > 0:
                    deployable = min(num_armies, player.armies_to_deploy)
                    territory_to_deploy.army_count += deployable
                    player.armies_to_deploy -= deployable
                    deploy_msg = f"{player.name} deployed {deployable} armies to {terr_name} (New total: {territory_to_deploy.army_count}). Remaining: {player.armies_to_deploy}"
                    print(deploy_msg)
                    self.log_turn_info(deploy_msg)
                    if self.gui: self.gui.update(self.engine.game_state)
                else:
                    err_msg = f"{player.name} provided invalid DEPLOY action: {action}. armies_to_deploy: {player.armies_to_deploy}."
                    print(err_msg)
                    self.log_turn_info(err_msg)
                    # Potentially penalize or force a valid choice. For now, just skip and let AI try again.
                    # To prevent infinite loops on bad AI, break if no progress.
                    if player.armies_to_deploy > 0: # if AI is stuck, force end deploy
                        print(f"AI {player.name} failed to deploy correctly. Forcing end of deployment for this action.")
                        # Don't break the whole loop, let AI try again with remaining armies, but this specific attempt failed.
            elif action and action.get("type") == "END_REINFORCE_PHASE":
                print(f"{player.name} chose to end reinforcement phase.")
                if player.armies_to_deploy > 0:
                    # Distribute remaining armies automatically for now if AI ends phase prematurely
                    print(f"Warning: {player.name} ended reinforcement with {player.armies_to_deploy} armies left. Distributing automatically.")
                    self.auto_distribute_armies(player, player.armies_to_deploy)
                player.armies_to_deploy = 0 # Ensure it's zero
                break # Exit reinforcement loop
            else:
                err_msg = f"{player.name} provided invalid action during REINFORCE: {action}. Forcing distribution of remaining armies."
                print(err_msg)
                self.log_turn_info(err_msg)
                self.auto_distribute_armies(player, player.armies_to_deploy)
                player.armies_to_deploy = 0
                break

        player.armies_to_deploy = 0 # Ensure it's zeroed out


    def auto_distribute_armies(self, player: GamePlayer, armies_to_distribute: int):
        if not player.territories:
            print(f"Cannot auto-distribute armies for {player.name}, has no territories.")
            return

        idx = 0
        while armies_to_distribute > 0:
            territory = player.territories[idx % len(player.territories)]
            territory.army_count += 1
            armies_to_distribute -= 1
            dist_msg = f"Auto-distributed 1 army to {territory.name} for {player.name}."
            # print(dist_msg) # Can be noisy, log_turn_info will handle GUI
            self.log_turn_info(dist_msg)
            idx += 1
        if self.gui: self.gui.update(self.engine.game_state)


    def handle_attack_communicate_phase(self, player: GamePlayer, agent: BaseAIAgent):
        attack_action_limit = 10 # Limit attacks per turn to prevent infinite loops from aggressive AIs
        attacks_this_turn = 0
        player_has_conquered_territory_this_turn = False # For card drawing rule in Risk

        while attacks_this_turn < attack_action_limit:
            game_state_json = self.engine.game_state.to_json()
            # Pass global chat log to AI
            chat_log_for_ai = self.global_chat.get_log(limit=10) # Last 10 messages
            valid_actions = self.engine.get_valid_actions(player) # ATTACK, CHAT, END_ATTACK_PHASE

            if not any(a['type'] == 'ATTACK' for a in valid_actions): # No more possible attacks
                print(f"{player.name} has no more valid attack moves.")
                break # End attack phase

            ai_response = agent.get_thought_and_action(game_state_json, valid_actions, self.game_rules,
                                                       system_prompt_addition=f"It is your attack phase. You have made {attacks_this_turn} attacks so far this turn.")
            action = ai_response.get("action")
            thought = ai_response.get("thought", "(No thought provided)")
            self.log_ai_thought(player.name, thought)

            if not action or not action.get("type"):
                err_msg = f"{player.name} provided invalid action: {action}. Ending attack phase."
                print(err_msg)
                self.log_turn_info(err_msg)
                break

            action_type = action.get("type")

            if action_type == "ATTACK":
                from_terr_name = action.get("from")
                to_terr_name = action.get("to")
                num_armies = action.get("num_armies") # This is num armies joining attack (1-3 dice usually)
                                                    # Engine's perform_attack needs num_attacking_armies (actual count, not dice)

                # The AI should specify num_armies as the actual count of units to send into battle.
                # The engine's perform_attack will then derive dice from this.
                # For now, let's assume AI gives the count of armies to use in the attack.
                # The valid_actions from engine should specify 'max_armies_for_attack'

                attack_log = self.engine.perform_attack(from_terr_name, to_terr_name, num_armies)

                log_summary = f"{player.name} action: ATTACK {from_terr_name} -> {to_terr_name} with {num_armies} armies."
                print(log_summary)
                self.log_turn_info(log_summary)

                if "error" in attack_log:
                    print(f"Attack Error: {attack_log['error']}")
                    self.log_turn_info(f"Attack Error: {attack_log['error']}")
                    # If AI makes invalid attack, it might lose its turn or just this attempt.
                    # For now, let it try another action, but count this as an "attempt".
                else:
                    print(f"Battle Log: {attack_log.get('summary', 'No summary.')}")
                    self.log_turn_info(f"Battle Result: {attack_log.get('summary', 'No summary.')}")
                    if attack_log.get("conquered"):
                        player_has_conquered_territory_this_turn = True
                        # Card drawing is handled by engine.perform_attack if a card is due
                        if attack_log.get("card_drawn"):
                            card = attack_log["card_drawn"]
                            card_msg = f"{player.name} drew a card: {card['territory_name']}-{card['symbol']}."
                            print(card_msg)
                            self.log_turn_info(card_msg)

                        # Check for player elimination
                        eliminated_player_name = attack_log.get("eliminated_player")
                        if eliminated_player_name:
                            elim_msg = f"{player.name} eliminated {eliminated_player_name}!"
                            print(elim_msg)
                            self.log_turn_info(elim_msg)
                            self.global_chat.broadcast("GameSystem", elim_msg)
                            # Remove player from game (engine.game_state.players and self.ai_agents, self.player_map)
                            self.handle_player_elimination(eliminated_player_name)
                            if self.gui: self.gui.update(self.engine.game_state) # Update after player list changes


                    if self.gui: self.gui.update(self.engine.game_state) # Update GUI after attack
                    # if self.gui: self.gui.show_battle_animation(attack_log) # Optional animation

                attacks_this_turn += 1
                if self.engine.is_game_over(): break

            elif action_type == "GLOBAL_CHAT":
                msg = action.get("message", "")
                if msg:
                    self.global_chat.broadcast(player.name, msg)
                    self.log_turn_info(f"{player.name} (Global Chat): {msg}")
                # Chatting doesn't end the attack loop here, AI can choose to attack again or end.

            elif action_type == "PRIVATE_CHAT":
                target_name = action.get("target_player_name")
                initial_msg = action.get("initial_message", "")
                target_agent = self.ai_agents.get(target_name)

                if target_agent and initial_msg:
                    self.log_turn_info(f"{player.name} initiating private chat with {target_name}.")
                    # Run conversation
                    conversation_log = self.private_chat_manager.run_conversation(
                        agent, target_agent, initial_msg, self.engine.game_state.to_json(), self.game_rules # Pass game_state_json
                    )
                    # Log conversation to main action log or specific chat panel
                    if self.gui: self.gui.log_private_chat(conversation_log) # Orchestrator passes full log
                    self.log_turn_info(f"Private chat ended between {player.name} and {target_name}. Log stored.")
                else:
                    err_msg = f"{player.name} private chat failed: Invalid target or message. Target: {target_name}"
                    print(err_msg)
                    self.log_turn_info(err_msg)
                # Private chat also doesn't necessarily end attack loop.

            elif action_type == "END_ATTACK_PHASE":
                print(f"{player.name} chose to end attack phase.")
                self.log_turn_info(f"{player.name} ends attack phase.")
                break # Exit attack loop
            else:
                err_msg = f"{player.name} provided an unknown action type during ATTACK: {action_type}. Ending attack phase."
                print(err_msg)
                self.log_turn_info(err_msg)
                break

        if attacks_this_turn >= attack_action_limit:
            print(f"{player.name} reached attack limit for the turn.")
            self.log_turn_info(f"{player.name} reached attack limit.")

        # Card drawing rule: If a player conquers at least one territory, they get ONE card.
        # This is now handled inside engine.perform_attack for the first conquest that turn.
        # We need a flag per player per turn if we want to strictly enforce "only one card per turn regardless of conquests"
        # The current engine.perform_attack gives a card on *any* conquest if deck available.
        # This should be refined to: "if player_has_conquered_territory_this_turn and not player_has_drawn_card_this_turn".
        # For now, the engine's card draw on conquest is what happens.

    def handle_fortify_phase(self, player: GamePlayer, agent: BaseAIAgent):
        # Player can make one fortify move or skip.
        game_state_json = self.engine.game_state.to_json()
        valid_actions = self.engine.get_valid_actions(player) # FORTIFY, END_TURN (or SKIP_FORTIFY)

        # Filter for FORTIFY or END_TURN
        fortify_actions = [a for a in valid_actions if a['type'] == 'FORTIFY' or a['type'] == 'END_TURN' or a['type'] == 'SKIP_FORTIFY']
        if not fortify_actions: # Should always have END_TURN
            print(f"Warning: No fortify actions for {player.name}. Ending turn.")
            self.log_turn_info(f"{player.name} has no fortify options. Ending turn.")
            return

        ai_response = agent.get_thought_and_action(game_state_json, fortify_actions, self.game_rules,
                                                   system_prompt_addition="It is your fortify phase. You can make one move or end your turn.")
        action = ai_response.get("action")
        thought = ai_response.get("thought", "(No thought provided)")
        self.log_ai_thought(player.name, thought)

        if not action or not action.get("type"):
            err_msg = f"{player.name} provided invalid action during FORTIFY: {action}. Ending turn."
            print(err_msg)
            self.log_turn_info(err_msg)
            return # End turn

        action_type = action.get("type")

        if action_type == "FORTIFY":
            from_terr_name = action.get("from")
            to_terr_name = action.get("to")
            num_armies = action.get("num_armies")

            fortify_result = self.engine.perform_fortify(from_terr_name, to_terr_name, num_armies)

            log_summary = f"{player.name} action: FORTIFY {from_terr_name} -> {to_terr_name} with {num_armies} armies."
            print(log_summary)
            self.log_turn_info(log_summary)

            if fortify_result.get("success"):
                print(f"Fortify successful: {fortify_result['message']}")
                self.log_turn_info(f"Fortify successful: {fortify_result['message']}")
                if self.gui: self.gui.update(self.engine.game_state)
            else:
                print(f"Fortify Error: {fortify_result['message']}")
                self.log_turn_info(f"Fortify Error: {fortify_result['message']}")
                # Failed fortify ends the phase.

        elif action_type == "END_TURN" or action_type == "SKIP_FORTIFY":
            skip_msg = f"{player.name} chose to end turn / skip fortification."
            print(skip_msg)
            self.log_turn_info(skip_msg)
        else:
            err_msg = f"{player.name} provided an unknown action type during FORTIFY: {action_type}. Ending turn."
            print(err_msg)
            self.log_turn_info(err_msg)
            # End turn by default

    def handle_player_elimination(self, eliminated_player_name: str):
        # Remove from engine's list of players
        player_to_remove_engine = None
        for p_obj in self.engine.game_state.players:
            if p_obj.name == eliminated_player_name:
                player_to_remove_engine = p_obj
                break
        if player_to_remove_engine:
            self.engine.game_state.players.remove(player_to_remove_engine)
            print(f"Removed {eliminated_player_name} from engine player list.")
        else:
            print(f"Warning: Could not find {eliminated_player_name} in engine player list to remove.")

        # Remove from orchestrator's AI agent list and player_map
        if eliminated_player_name in self.ai_agents:
            del self.ai_agents[eliminated_player_name]
            print(f"Removed {eliminated_player_name} from orchestrator AI agents.")

        # Rebuild player_map or remove specific entry
        # Find key in player_map by name
        key_to_remove_map = None
        for gp_key, ai_val in self.player_map.items():
            if ai_val.player_name == eliminated_player_name: # Assuming BaseAIAgent has player_name
                key_to_remove_map = gp_key
                break
        if key_to_remove_map:
            del self.player_map[key_to_remove_map]
            print(f"Removed {eliminated_player_name} from orchestrator player map.")

        # Adjust current_player_index if necessary (engine.next_turn should handle this by skipping eliminated players)
        # The engine.next_turn() logic relies on players having territories to be considered active.
        # If an eliminated player was the current player, next_turn needs to correctly find the next valid player.
        # If an eliminated player's turn was upcoming, next_turn should skip them.
        print(f"Player {eliminated_player_name} has been eliminated from the game.")


    def log_ai_thought(self, player_name: str, thought: str):
        """Logs AI's thought process. Could be to console, file, or GUI."""
        print(f"--- {player_name}'s Thought --- \n{thought[:300]}...\n--------------------") # Print truncated thought
        if self.gui: self.gui.update_thought_panel(player_name, thought)

        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "player": player_name,
            "thought": thought
        }
        self.turn_action_log.append({"type": "thought", "player": player_name, "content": thought}) # Keep for existing GUI logic if it uses this

        # File logging for AI thoughts
        # Ensure LOG_DIR exists (it's created by chat loggers, but good to be safe)
        # Similar log directory logic as in chat modules
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        thought_log_file = os.path.join(log_dir, "ai_thoughts.jsonl")
        try:
            with open(thought_log_file, 'a') as f:
                f.write(json.dumps(log_entry) + "\n")
        except IOError as e:
            print(f"Error writing to AI thought log file {thought_log_file}: {e}")


    def log_turn_info(self, message: str):
        """Logs general turn information."""
        # print(f"[Orchestrator Log] {message}") # Console print can be verbose
        if self.gui:
            self.gui.log_action(message) # Send to GUI's action log
        self.turn_action_log.append({"type": "info", "content": message, "timestamp": time.time()})

    def setup_gui(self):
        # GameGUI is already imported at the top
        if not self.gui: # Initialize only once
            self.gui = GameGUI(self.engine, self) # Pass engine and orchestrator for callbacks
            print("GUI setup complete. GUI is active.")
        else:
            print("GUI already setup.")


if __name__ == '__main__':
    print("Setting up Game Orchestrator for a test run...")
    # Create a dummy player_config.json for testing if it doesn't exist
    dummy_player_config = [
        {"name": "Alice (Gemini)", "color": "Red", "ai_type": "Gemini"},
        {"name": "Bob (OpenAI)", "color": "Blue", "ai_type": "OpenAI"}
        # {"name": "Charlie (Claude)", "color": "Green", "ai_type": "Claude"},
        # {"name": "Dave (DeepSeek)", "color": "Yellow", "ai_type": "DeepSeek"}
    ]
    config_path = "player_config.json"
    try:
        with open(config_path, 'w') as f:
            json.dump(dummy_player_config, f, indent=2)
        print(f"Created dummy {config_path} for testing.")
    except IOError:
        print(f"Could not create dummy {config_path}. Ensure you have write permissions or create it manually.")

    orchestrator = GameOrchestrator(player_setup_file=config_path)

    # orchestrator.setup_gui() # If GUI is to be used

    print("Starting game run...")
    orchestrator.run_game()

    print("\nGame run finished.")
    print("Final Global Chat Log:")
    for msg_data in orchestrator.global_chat.get_log():
        print(f"- {msg_data['sender']}: {msg_data['message']} (at {msg_data['timestamp']})")

    # print("\nFinal Turn Action Log (last turn):")
    # for log_entry in orchestrator.turn_action_log:
    #    print(log_entry)
