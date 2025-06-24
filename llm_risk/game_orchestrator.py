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
        self.private_chat_manager = PrivateChatManager(max_exchanges_per_conversation=3)

        self.gui = None
        self.setup_gui()

        self.ai_agents: dict[str, BaseAIAgent] = {}
        self.player_map: dict[GamePlayer, BaseAIAgent] = {}

        self._load_player_setup(player_setup_file)

        players_data_for_engine = [{"name": p.name, "color": p.color} for p in self.engine.game_state.players]
        self.engine.initialize_board(players_data=players_data_for_engine)

        self._map_game_players_to_ai_agents()

        self.game_rules = GAME_RULES_SNIPPET
        self.turn_action_log = []
        self.max_turns = 200
        self.game_running_via_gui = False

    def _load_player_setup(self, player_setup_file: str):
        try:
            with open(player_setup_file, 'r') as f:
                player_configs = json.load(f)
        except FileNotFoundError:
            print(f"Warning: Player setup file '{player_setup_file}' not found. Using default AI setup.")
            player_configs = [
                {"name": "PlayerA (Gemini)", "color": "Red", "ai_type": "Gemini"},
                {"name": "PlayerB (OpenAI)", "color": "Blue", "ai_type": "OpenAI"},
                {"name": "PlayerC (Claude)", "color": "Green", "ai_type": "Claude"},
                {"name": "PlayerD (DeepSeek)", "color": "Yellow", "ai_type": "DeepSeek"}
            ]
            try:
                with open(player_setup_file, 'w') as f:
                    json.dump(player_configs, f, indent=2)
                print(f"Created default player_config.json.")
            except IOError:
                print(f"Could not write default player_config.json.")

        for config in player_configs:
            player_name = config["name"]
            player_color = config["color"]
            ai_type = config.get("ai_type", "Gemini")
            game_player_obj = GamePlayer(name=player_name, color=player_color)
            self.engine.game_state.players.append(game_player_obj)
            agent: BaseAIAgent | None = None
            if ai_type == "Gemini": agent = GeminiAgent(player_name, player_color)
            elif ai_type == "OpenAI": agent = OpenAIAgent(player_name, player_color)
            elif ai_type == "Claude": agent = ClaudeAgent(player_name, player_color)
            elif ai_type == "DeepSeek": agent = DeepSeekAgent(player_name, player_color)
            else:
                print(f"Warning: Unknown AI type '{ai_type}' for player {player_name}. Defaulting to Gemini.")
                agent = GeminiAgent(player_name, player_color)
            if agent: self.ai_agents[player_name] = agent
        if len(self.engine.game_state.players) < 2 :
            print("Error: At least two players are required to start the game.")
            raise ValueError("Insufficient players configured.")

    def _map_game_players_to_ai_agents(self):
        self.player_map.clear()
        for gp in self.engine.game_state.players:
            if gp.name in self.ai_agents:
                self.player_map[gp] = self.ai_agents[gp.name]
            else:
                print(f"Critical Error: GamePlayer {gp.name} from engine does not have a corresponding AI agent.")

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
            self.engine.next_turn()
            if self.gui: self._update_gui_full_state()
            return True

        print(f"\n--- Turn {self.engine.game_state.current_turn_number} | Player: {current_player_obj.name} ({current_player_obj.color}) | Phase: {self.engine.game_state.current_game_phase} ---")
        self.log_turn_info(f"Turn {self.engine.game_state.current_turn_number} starting for {current_player_obj.name}.")
        self._update_gui_full_state()

        if self.engine.game_state.current_game_phase == "REINFORCE":
            self.handle_reinforce_phase(current_player_obj, current_player_agent)
            self._update_gui_full_state()
            if self.engine.is_game_over(): return self.advance_game_turn()

        if not self.engine.is_game_over() and self.engine.game_state.current_game_phase == "ATTACK":
            self.log_turn_info(f"{current_player_obj.name} continuing/starting ATTACK phase.")
            self.handle_attack_communicate_phase(current_player_obj, current_player_agent)
            self._update_gui_full_state()
            if self.engine.is_game_over(): return self.advance_game_turn()

        if not self.engine.is_game_over() and self.engine.game_state.current_game_phase == "FORTIFY":
            self.log_turn_info(f"{current_player_obj.name} continuing/starting FORTIFY phase.")
            self.handle_fortify_phase(current_player_obj, current_player_agent)
            self._update_gui_full_state()
            if self.engine.is_game_over(): return self.advance_game_turn()

        if self.engine.is_game_over(): return False

        self.engine.next_turn()
        print(f"--- End of Turn for {current_player_obj.name}. Next player: {self.engine.game_state.get_current_player().name if self.engine.game_state.get_current_player() else 'N/A'} ---")
        self._update_gui_full_state()
        return True

    def handle_reinforce_phase(self, player: GamePlayer, agent: BaseAIAgent):
        print(f"{player.name} has {player.armies_to_deploy} initial reinforcements.")
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
    orchestrator = GameOrchestrator(player_setup_file=config_path)
    print("Starting game run...")
    orchestrator.run_game()
    print("\nGame run finished.")
    # ... (final log print remains same) ...
