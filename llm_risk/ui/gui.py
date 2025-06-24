# import pygame # Would be imported in a real Pygame environment
from ..game_engine.engine import GameEngine
from ..game_engine.data_structures import GameState, Territory, Player as GamePlayer
# from ..game_orchestrator import GameOrchestrator # Avoid circular import if orchestrator imports GUI

import json
import os

# Define some colors (RGB) - Pygame would use these
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
GREY = (128, 128, 128)
DEFAULT_PLAYER_COLORS = {
    "Red": RED, "Blue": BLUE, "Green": GREEN, "Yellow": YELLOW,
    "Purple": (128, 0, 128), "Orange": (255, 165, 0), "Black": BLACK, "White": WHITE
}

# Constants for UI layout (placeholders)
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
MAP_AREA_WIDTH = 900
SIDE_PANEL_WIDTH = SCREEN_WIDTH - MAP_AREA_WIDTH
ACTION_LOG_HEIGHT = 200
THOUGHT_PANEL_HEIGHT = 200
CHAT_PANEL_HEIGHT = SCREEN_HEIGHT - ACTION_LOG_HEIGHT - THOUGHT_PANEL_HEIGHT


class GameGUI:
    def __init__(self, engine: GameEngine, orchestrator): # Orchestrator for callbacks/data
        # Pygame specific initialization (commented out)
        # pygame.init()
        # self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        # pygame.display.set_caption("LLM Risk Game")
        # self.font = pygame.font.SysFont(None, 24)
        # self.map_image = None # Will hold the loaded map image
        # self.clock = pygame.time.Clock()
        print("Pygame GUI Initialized (Placeholder - No graphics will be shown)")

        self.engine = engine
        self.orchestrator = orchestrator # To access chat logs, AI thoughts etc.

        self.territory_coordinates: dict[str, tuple[int, int]] = {}
        self._load_map_config() # Loads map image and territory coordinates

        self.action_log: list[str] = ["Game Started."]
        self.ai_thoughts: dict[str, str] = {} # player_name: latest_thought
        # Global chat will be fetched from orchestrator.global_chat
        # Private chats could be stored or fetched as needed

        # UI State
        self.active_tab_thought_panel = "" # Name of player whose thoughts are shown
        self.active_tab_chat_panel = "global" # "global" or "player1_player2"

    def _load_map_config(self, config_file: str = "map_display_config.json", map_image_path: str = "risk_map_image.png"):
        """
        Loads territory coordinates from a config file and the map background image.
        """
        # Load map image (placeholder)
        # try:
        #     self.map_image = pygame.image.load(map_image_path)
        #     self.map_image = pygame.transform.scale(self.map_image, (MAP_AREA_WIDTH, SCREEN_HEIGHT))
        # except pygame.error as e:
        #     print(f"Warning: Could not load map image '{map_image_path}': {e}. Using blank background.")
        #     self.map_image = pygame.Surface((MAP_AREA_WIDTH, SCREEN_HEIGHT))
        #     self.map_image.fill(GREY)
        print(f"GUI: Would load map image from '{map_image_path}'")

        # Load territory coordinates
        try:
            with open(config_file, 'r') as f:
                self.territory_coordinates = json.load(f)
            print(f"GUI: Loaded territory coordinates from '{config_file}'.")
        except FileNotFoundError:
            print(f"Warning: Map display config file '{config_file}' not found. Creating dummy coordinates.")
            self._create_dummy_coordinates(config_file)
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from '{config_file}'. No territory coordinates loaded.")

    def _create_dummy_coordinates(self, config_file: str):
        """Creates dummy coordinates if the config file is missing and saves it."""
        # Use territories from the game engine's current state
        if not self.engine.game_state.territories:
            print("GUI: Cannot create dummy coordinates, no territories in game engine.")
            return

        dummy_coords = {}
        x_offset = 50
        y_offset = 50
        for i, name in enumerate(self.engine.game_state.territories.keys()):
            dummy_coords[name] = (x_offset + (i % 5) * 150, y_offset + (i // 5) * 100)

        self.territory_coordinates = dummy_coords
        try:
            with open(config_file, 'w') as f:
                json.dump(self.territory_coordinates, f, indent=2)
            print(f"GUI: Created and saved dummy territory coordinates to '{config_file}'.")
        except IOError:
            print(f"GUI: Could not write dummy territory coordinates to '{config_file}'.")


    def update(self, game_state: GameState | None = None):
        """
        Called by the orchestrator after any state change to refresh the display.
        If game_state is None, it uses self.engine.game_state.
        """
        current_game_state = game_state or self.engine.game_state
        if not current_game_state:
            print("GUI Error: No game state to update from.")
            return

        # In a real Pygame app, this is the main drawing loop per frame.
        # For placeholder, we just print that an update is happening.
        # self.screen.fill(BLACK) # Clear screen

        # 1. Draw Map Area
        # self.draw_map(current_game_state)

        # 2. Draw Side Panels
        # self.draw_action_log_panel()
        # self.draw_ai_thought_panel()
        # self.draw_chat_panel()

        # pygame.display.flip() # Update the full display
        # self.clock.tick(30) # Limit to 30 FPS

        print(f"GUI: Update called. Current Turn: {current_game_state.current_turn_number}, Phase: {current_game_state.current_game_phase}, Player: {current_game_state.get_current_player().name if current_game_state.get_current_player() else 'N/A'}")
        # For demonstration, print some territory info
        # for name, terr in current_game_state.territories.items():
        #     owner_name = terr.owner.name if terr.owner else "None"
        #     print(f"  Territory: {name}, Owner: {owner_name}, Armies: {terr.army_count}")


    def draw_map(self, game_state: GameState):
        """Renders the game map with territories, owners, and army counts."""
        # self.screen.blit(self.map_image, (0,0)) # Draw background map
        print("GUI: Drawing map (placeholder)...")

        for terr_name, territory in game_state.territories.items():
            coords = self.territory_coordinates.get(terr_name)
            if not coords:
                # print(f"GUI Warning: No coordinates for territory '{terr_name}'.")
                continue

            owner_color = GREY # Default for unowned
            if territory.owner and territory.owner.color:
                owner_color = DEFAULT_PLAYER_COLORS.get(territory.owner.color, GREY)

            # Pygame drawing calls (commented out)
            # pygame.draw.circle(self.screen, owner_color, coords, 15) # Circle for territory
            # army_text = self.font.render(str(territory.army_count), True, BLACK)
            # text_rect = army_text.get_rect(center=coords)
            # self.screen.blit(army_text, text_rect)
            # name_text = self.font.render(terr_name, True, WHITE) # Basic name label
            # self.screen.blit(name_text, (coords[0] + 20, coords[1] - 10))
            owner_name = territory.owner.name if territory.owner else "None"
            print(f"  Drawing Territory: {terr_name} at {coords}, Owner: {owner_name} ({territory.owner.color if territory.owner else 'N/A'}), Armies: {territory.army_count}")


    def draw_action_log_panel(self):
        """Displays a scrolling list of game actions."""
        # panel_rect = pygame.Rect(MAP_AREA_WIDTH, 0, SIDE_PANEL_WIDTH, ACTION_LOG_HEIGHT)
        # pygame.draw.rect(self.screen, (50,50,50), panel_rect) # Background for panel
        # title_text = self.font.render("Action Log", True, WHITE)
        # self.screen.blit(title_text, (panel_rect.x + 5, panel_rect.y + 5))
        print("GUI: Drawing Action Log Panel...")

        y_offset = 30
        for i, log_entry in enumerate(reversed(self.action_log[-10:])): # Show last 10 actions
            # entry_surface = self.font.render(log_entry, True, WHITE)
            # self.screen.blit(entry_surface, (panel_rect.x + 10, panel_rect.y + y_offset + i * 20))
            print(f"  Log: {log_entry}")


    def draw_ai_thought_panel(self):
        """Displays the latest 'thought' from the selected AI."""
        # panel_rect = pygame.Rect(MAP_AREA_WIDTH, ACTION_LOG_HEIGHT, SIDE_PANEL_WIDTH, THOUGHT_PANEL_HEIGHT)
        # pygame.draw.rect(self.screen, (60,60,60), panel_rect)
        # title_text = self.font.render("AI Thoughts", True, WHITE)
        # self.screen.blit(title_text, (panel_rect.x + 5, panel_rect.y + 5))
        print("GUI: Drawing AI Thought Panel...")

        # Placeholder: Show thoughts for the first AI if no active tab, or current player
        if not self.active_tab_thought_panel and self.orchestrator.ai_agents:
            self.active_tab_thought_panel = list(self.orchestrator.ai_agents.keys())[0]

        current_player = self.engine.game_state.get_current_player()
        if current_player: # Default to current player's thoughts
            self.active_tab_thought_panel = current_player.name


        if self.active_tab_thought_panel in self.ai_thoughts:
            thought = self.ai_thoughts[self.active_tab_thought_panel]
            # Render thought text (potentially multi-line)
            # y_offset = 30
            # for line in thought.split('\n'): # Basic multi-line
            #     line_surface = self.font.render(line, True, WHITE)
            #     self.screen.blit(line_surface, (panel_rect.x + 10, panel_rect.y + y_offset))
            #     y_offset += 20
            print(f"  Thoughts for {self.active_tab_thought_panel}: {thought[:100]}...")
        else:
            # no_thought_text = self.font.render(f"No thoughts yet for {self.active_tab_thought_panel}.", True, GREY)
            # self.screen.blit(no_thought_text, (panel_rect.x + 10, panel_rect.y + 30))
            print(f"  No thoughts yet for {self.active_tab_thought_panel}.")


    def draw_chat_panel(self):
        """Displays global chat and private chat logs."""
        # panel_rect = pygame.Rect(MAP_AREA_WIDTH, ACTION_LOG_HEIGHT + THOUGHT_PANEL_HEIGHT, SIDE_PANEL_WIDTH, CHAT_PANEL_HEIGHT)
        # pygame.draw.rect(self.screen, (70,70,70), panel_rect)
        # title_text = self.font.render(f"Chat ({self.active_tab_chat_panel})", True, WHITE)
        # self.screen.blit(title_text, (panel_rect.x + 5, panel_rect.y + 5))
        print(f"GUI: Drawing Chat Panel (Active: {self.active_tab_chat_panel})...")

        if self.active_tab_chat_panel == "global":
            chat_messages = self.orchestrator.global_chat.get_log(limit=10) # Last 10 global messages
            y_offset = 30
            for msg_data in reversed(chat_messages):
                # msg_render = f"{msg_data['sender']}: {msg_data['message']}"
                # msg_surface = self.font.render(msg_render, True, WHITE)
                # self.screen.blit(msg_surface, (panel_rect.x + 10, panel_rect.y + y_offset + (len(chat_messages) - 1 - chat_messages.index(msg_data)) * 20))
                print(f"  Global Chat - {msg_data['sender']}: {msg_data['message']}")
        else:
            # Placeholder for private chat logs
            # private_log = self.orchestrator.private_chat_manager.conversation_logs.get(self.active_tab_chat_panel)
            # if private_log:
            #     # Render private_log
            #     pass
            print(f"  Displaying private chat for {self.active_tab_chat_panel} (not fully implemented in placeholder GUI).")


    def log_action(self, action_string: str):
        """Adds an action string to the action log."""
        print(f"GUI Action Log: {action_string}")
        self.action_log.append(action_string)
        if len(self.action_log) > 50: # Keep log size manageable
            self.action_log.pop(0)
        # self.update() # Could update GUI immediately, or orchestrator calls update

    def update_thought_panel(self, player_name: str, thought: str):
        """Updates the thought for a specific AI."""
        print(f"GUI Update Thought: {player_name} - {thought[:50]}...")
        self.ai_thoughts[player_name] = thought
        self.active_tab_thought_panel = player_name # Switch to this AI's thoughts
        # self.update()

    def log_private_chat(self, conversation_log: list[dict]):
        """Logs a private conversation. For now, just prints it."""
        if not conversation_log: return
        p1 = conversation_log[0]['sender']
        # Find other participant
        p2 = ""
        for msg in conversation_log:
            if msg['sender'] != p1:
                p2 = msg['sender']
                break
        if not p2 and len(conversation_log) > 1: # Self-chat or only one message
             p2 = p1
        elif not p2 and len(conversation_log) == 1:
             p2 = "UnknownRecipient"


        log_key = f"private_{p1}_vs_{p2}" # Simplified key
        print(f"GUI: Logging private chat under key '{log_key}'")
        # In a real GUI, you'd store this and make it viewable in a tab
        # For now, just add a summary to the main action log
        self.log_action(f"Private chat between {p1} and {p2} concluded ({len(conversation_log)} messages).")


    def show_battle_animation(self, battle_log: dict):
        """(Placeholder) Shows an animation or summary of a battle."""
        print(f"GUI: Showing battle animation/summary (Placeholder) for attack: {battle_log.get('attacker_territory')} vs {battle_log.get('defender_territory')}")
        # This would involve more complex Pygame drawing and timing in a real GUI

    def show_game_over_screen(self, winner_name: str | None):
        """(Placeholder) Displays a game over message."""
        # self.screen.fill(BLACK)
        message = f"Game Over! Winner: {winner_name}" if winner_name else "Game Over! It's a draw or timeout."
        # text_surface = self.font.render(message, True, WHITE)
        # text_rect = text_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
        # self.screen.blit(text_surface, text_rect)
        # pygame.display.flip()
        print(f"GUI: Displaying Game Over Screen: {message}")
        # Wait for a bit or for user to close
        # running = True
        # while running:
        #     for event in pygame.event.get():
        #         if event.type == pygame.QUIT:
        #             running = False
        #     self.clock.tick(10)
        # pygame.quit()


    def handle_input(self):
        """Handles user input (e.g., clicking on UI elements, keyboard shortcuts). Placeholder."""
        # for event in pygame.event.get():
        #     if event.type == pygame.QUIT:
        #         return False # Signal to close the game
        #     if event.type == pygame.MOUSEBUTTONDOWN:
        #         # Check for clicks on tabs, buttons, etc.
        #         # e.g., if event.pos is within thought_panel_tab_playerA_rect:
        #         #    self.active_tab_thought_panel = "PlayerA"
        #         #    self.update()
        #         print(f"GUI: Mouse click at {event.pos} (Placeholder input handling)")
        #         pass
        return True # Game continues

# Example of how the Orchestrator might interact with the GUI (in Orchestrator file)
# class GameOrchestrator:
#     def __init__(self):
#         self.engine = GameEngine(...)
#         self.gui = GameGUI(self.engine, self) # Pass self (orchestrator)
#         # ...
#
#     def run_game_turn(self):
#         # ... after an action ...
#         self.engine.perform_attack(...)
#         self.gui.log_action("Player A attacked B from C")
#         self.gui.update(self.engine.game_state)
#
#         ai_response = agent.get_thought_and_action(...)
#         self.gui.update_thought_panel(agent.name, ai_response['thought'])
#         # ...

if __name__ == '__main__':
    # This test requires a running GameEngine instance and a mock orchestrator
    print("GUI Module - Basic Test (Placeholder)")

    # Mock Game Engine and GameState for testing GUI components
    class MockPlayer:
        def __init__(self, name, color):
            self.name = name
            self.color = color
    class MockTerritory:
        def __init__(self, name, owner, army_count):
            self.name = name
            self.owner = owner
            self.army_count = army_count
    class MockGameState:
        def __init__(self):
            self.territories = {}
            self.players = []
            self.current_turn_number = 1
            self.current_game_phase = "REINFORCE"
            self.current_player_index = 0
        def get_current_player(self):
            return self.players[self.current_player_index] if self.players else None

    class MockEngine:
        def __init__(self):
            self.game_state = MockGameState()
            # Populate with some dummy data
            p1 = MockPlayer("Archibald", "Red")
            p2 = MockPlayer("Beatrice", "Blue")
            self.game_state.players = [p1, p2]
            self.game_state.territories["Alaska"] = MockTerritory("Alaska", p1, 5)
            self.game_state.territories["Alberta"] = MockTerritory("Alberta", p2, 3)
            self.game_state.territories["Greenland"] = MockTerritory("Greenland", p1, 10)


    class MockOrchestrator:
        def __init__(self, engine):
            self.ai_agents = {"Archibald": "AgentA_Instance", "Beatrice": "AgentB_Instance"} # Simplified
            self.global_chat = type('GlobalChat', (), {'get_log': lambda self, limit=0: [{"sender":"System", "message":"Welcome to mock chat!"}]})()
            self.private_chat_manager = type('PrivateChatManager', (), {'conversation_logs': {}})()
            self.engine = engine


    mock_engine = MockEngine()
    mock_orchestrator = MockOrchestrator(mock_engine)

    # Create dummy map_display_config.json if it doesn't exist
    if not os.path.exists("map_display_config.json"):
        dummy_map_coords = {
            "Alaska": (100, 100),
            "Alberta": (150, 150),
            "Greenland": (200, 50)
        }
        with open("map_display_config.json", "w") as f:
            json.dump(dummy_map_coords, f, indent=2)
        print("Created dummy map_display_config.json for GUI test.")


    gui = GameGUI(mock_engine, mock_orchestrator)
    gui.log_action("Test action logged.")
    gui.update_thought_panel("Archibald", "My grand strategy is unfolding perfectly. I shall feign weakness in Alaska while secretly planning to invade Alberta.")

    print("\n--- Simulating GUI Update ---")
    gui.update() # This will print territory info from the mock game state

    print("\n--- Simulating Drawing Specific Panels ---")
    gui.draw_map(mock_engine.game_state)
    gui.draw_action_log_panel()
    gui.draw_ai_thought_panel()
    gui.draw_chat_panel()

    gui.show_game_over_screen("Archibald")

    # In a real app, there would be a game loop here:
    # running = True
    # while running:
    #     running = gui.handle_input() # Process Pygame events
    #     # game_logic_updates from orchestrator would call gui.update()
    #     gui.update(mock_engine.game_state) # Update display
    # pygame.quit()
    print("\nGUI Module - Basic Test Complete.")
