import pygame
from ..game_engine.engine import GameEngine
from ..game_engine.data_structures import GameState, Territory, Player as GamePlayer

import json
import os

# Define some colors (RGB)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
GREY = (128, 128, 128)
LIGHT_GREY = (200, 200, 200)
DARK_GREY = (50, 50, 50)
MEDIUM_GREY = (100, 100, 100)
PANEL_BG_COLOR = (30, 30, 40) # Dark bluish grey for panels
TEXT_COLOR = WHITE
HIGHLIGHT_COLOR = YELLOW
PLAYER_INFO_BG = (40, 40, 50)
TAB_COLOR_ACTIVE = GREEN
TAB_COLOR_INACTIVE = GREY

# Define a new color for the ocean
OCEAN_BLUE = (20, 60, 120) # Darker, more appealing ocean blue
CONTINENT_COLORS = { # Example colors, can be expanded - these would ideally be part of map data
    "North America": (180, 160, 130), # Sandy brown
    "South America": (120, 180, 90),  # Light green
    "Europe": (150, 150, 200),       # Light purple/blue
    "Africa": (210, 140, 80),        # Orange-brown
    "Asia": (140, 190, 140),         # Sage green
    "Australia": (200, 120, 120),    # Light red/pink
    "Default": (100, 100, 100)       # Fallback continent color
}
ADJACENCY_LINE_COLOR = (70, 70, 90) # Slightly lighter for visibility on dark ocean
TERRITORY_BORDER_COLOR = BLACK
TERRITORY_BORDER_WIDTH = 1 # Thinner border for polygons

DEFAULT_PLAYER_COLORS = {
    "Red": (200, 50, 50), "Blue": (50, 100, 200), "Green": (50, 180, 50), "Yellow": (200, 200, 50),
    "Purple": (150, 80, 150), "Orange": (220, 140, 50), "Black": (80, 80, 80), "White": (220, 220, 220)
}

# Screen and Panel Layout Redesign
SCREEN_WIDTH = 1600  # Increased width for more space
SCREEN_HEIGHT = 900 # Increased height

# Left side for the map
MAP_AREA_WIDTH = 1100 # Increased map area

# Right side for information panels
SIDE_PANEL_WIDTH = SCREEN_WIDTH - MAP_AREA_WIDTH
PLAYER_INFO_HEIGHT = 60
KEY_ACTIONS_HEIGHT = 180 # New panel for key game developments
ACTION_LOG_HEIGHT = 150  # General action log
THOUGHT_PANEL_HEIGHT = 250 # Larger LLM thought panel
CHAT_PANEL_HEIGHT = SCREEN_HEIGHT - PLAYER_INFO_HEIGHT - KEY_ACTIONS_HEIGHT - ACTION_LOG_HEIGHT - THOUGHT_PANEL_HEIGHT

TAB_HEIGHT = 30
TAB_FONT_SIZE = 18
DEFAULT_FONT_SIZE = 20
LARGE_FONT_SIZE = 30
SMALL_FONT_SIZE = 16


class GameGUI:
    def __init__(self, engine: GameEngine, orchestrator):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("LLM Risk Game - Advanced UI")
        self.font = pygame.font.SysFont(None, DEFAULT_FONT_SIZE)
        self.large_font = pygame.font.SysFont(None, LARGE_FONT_SIZE)
        self.small_font = pygame.font.SysFont(None, SMALL_FONT_SIZE)
        self.tab_font = pygame.font.SysFont(None, TAB_FONT_SIZE)

        self.ocean_color = OCEAN_BLUE
        self.clock = pygame.time.Clock()
        print("Pygame GUI Initialized with Advanced Polygon Map")

        self.engine = engine
        self.orchestrator = orchestrator
        self.current_game_state: GameState = engine.game_state
        self.global_chat_messages: list[dict] = []
        self.private_chat_conversations_map: dict[str, list[dict]] = {}

        # This will store the polygon data: {"TerritoryName": {"polygons": [[[...]]], "label_position": [x,y]}}
        self.territory_display_data: dict[str, dict] = {}
        self._load_map_config("map_display_config_polygons.json") # Load new polygon config

        self.action_log: list[str] = ["Game Started."]
        self.key_actions_log: list[str] = ["Key Developments:"] # For the new panel
        self.ai_thoughts: dict[str, str] = {}

        self.player_names_for_tabs: list[str] = []
        self.active_tab_thought_panel = ""
        self.active_tab_chat_panel = "global"
        self.thought_tab_rects: dict[str, pygame.Rect] = {}
        self.chat_tab_rects: dict[str, pygame.Rect] = {}

        self.fps = 30
        self.running = False
        self.colors = DEFAULT_PLAYER_COLORS

    def _load_map_config(self, config_file: str = "map_display_config_polygons.json"):
        print(f"Attempting to load territory display data from '{config_file}'")
        try:
            with open(config_file, 'r') as f:
                self.territory_display_data = json.load(f)
            print(f"Successfully loaded territory display data from '{config_file}'.")
            if not self.territory_display_data:
                 print("Warning: Loaded map display data is empty. Map may not render correctly.")
                 self._create_dummy_polygon_coordinates(config_file, True) # force dummy if empty
            # Validate structure for one entry (optional)
            # sample_key = next(iter(self.territory_display_data))
            # if "polygons" not in self.territory_display_data[sample_key] or \
            #    "label_position" not in self.territory_display_data[sample_key]:
            #    print("Warning: Map data structure seems incorrect. Expected {'polygons': ..., 'label_position': ...}")

        except FileNotFoundError:
            print(f"Warning: Map display config file '{config_file}' not found. Creating dummy polygon coordinates.")
            self._create_dummy_polygon_coordinates(config_file)
        except json.JSONDecodeError:
            print(f"Error decoding JSON from '{config_file}'. Creating dummy polygon coordinates.")
            self._create_dummy_polygon_coordinates(config_file)

    def _create_dummy_polygon_coordinates(self, config_file: str, force_if_empty=False):
        if not self.engine.game_state.territories and not force_if_empty:
             print("No territories in game state, cannot create dummy data.")
             return

        # Use territory names from game engine if available, otherwise create some generic ones
        territory_names = list(self.engine.game_state.territories.keys())
        if not territory_names and force_if_empty: # If called because the file was empty
            territory_names = [f"DummyTerritory{i+1}" for i in range(10)]


        dummy_data = {}
        x_offset, y_offset = 50, 50
        spacing_x, spacing_y = 150, 120
        cols = MAP_AREA_WIDTH // spacing_x
        if cols == 0: cols = 1 # Avoid division by zero

        for i, name in enumerate(territory_names):
            center_x = x_offset + (i % cols) * spacing_x
            center_y = y_offset + (i // cols) * spacing_y
            # Create a simple square polygon
            square_poly = [
                [center_x - 40, center_y - 20], [center_x + 40, center_y - 20],
                [center_x + 40, center_y + 20], [center_x - 40, center_y + 20],
                [center_x - 40, center_y - 20] # Close the polygon
            ]
            dummy_data[name] = {
                "polygons": [[square_poly]], # Structure: list of polygons, each polygon is a list of rings (exterior first)
                "label_position": [center_x, center_y]
            }
        self.territory_display_data = dummy_data
        try:
            with open(config_file, 'w') as f:
                json.dump(self.territory_display_data, f, indent=2)
            print(f"Wrote dummy polygon coordinates to '{config_file}'.")
        except IOError:
            print(f"Could not write dummy polygon coords to '{config_file}'.")

    def update(self, game_state: GameState, global_chat_log: list[dict], private_chat_conversations: dict):
        self.current_game_state = game_state
        self.global_chat_messages = global_chat_log
        self.private_chat_conversations_map = private_chat_conversations

        if self.current_game_state and self.current_game_state.players:
            self.player_names_for_tabs = [p.name for p in self.current_game_state.players]
            if self.active_tab_thought_panel not in self.player_names_for_tabs and self.player_names_for_tabs:
                self.active_tab_thought_panel = self.player_names_for_tabs[0]
            elif not self.player_names_for_tabs:
                self.active_tab_thought_panel = ""

    def draw_map(self, game_state: GameState):
        gs_to_draw = game_state
        if not gs_to_draw: gs_to_draw = getattr(self, 'current_game_state', self.engine.game_state)

        map_area_rect = pygame.Rect(0, 0, MAP_AREA_WIDTH, SCREEN_HEIGHT)
        self.screen.fill(self.ocean_color, map_area_rect)

        if not gs_to_draw or not gs_to_draw.territories or not self.territory_display_data:
            no_map_text_str = "Map Data Unavailable"
            if not self.territory_display_data:
                no_map_text_str = "Map Display Config Missing/Empty"
            no_map_text = self.large_font.render(no_map_text_str, True, WHITE)
            self.screen.blit(no_map_text, no_map_text.get_rect(center=map_area_rect.center))
            return

        # Adjacency lines (optional with polygons, but can be useful)
        # Consider drawing these first so polygons draw over them.
        # For now, let's skip them to simplify, as polygon borders should be clear.
        # If re-added, use label_position from self.territory_display_data for line endpoints.

        for terr_name, territory_obj in gs_to_draw.territories.items():
            display_data = self.territory_display_data.get(terr_name)
            if not display_data or "polygons" not in display_data or "label_position" not in display_data:
                # print(f"Warning: No display data for territory {terr_name}. Skipping draw.")
                if terr_name not in getattr(self, "_missing_data_warnings", set()): # Avoid spamming console
                    print(f"Warning: No display data or incomplete data for territory '{terr_name}'. Skipping draw.")
                    if not hasattr(self, "_missing_data_warnings"): self._missing_data_warnings = set()
                    self._missing_data_warnings.add(terr_name)
                continue


            owner_color = GREY
            if territory_obj.owner and territory_obj.owner.color:
                owner_color = self.colors.get(territory_obj.owner.color, GREY)

            # Draw each polygon part of the territory
            for polygon_structure in display_data["polygons"]:
                exterior_ring = polygon_structure[0]
                if len(exterior_ring) < 3: continue # Need at least 3 points for a polygon

                pygame.draw.polygon(self.screen, owner_color, exterior_ring)
                pygame.draw.polygon(self.screen, TERRITORY_BORDER_COLOR, exterior_ring, TERRITORY_BORDER_WIDTH)

                # Handle holes if any (though our Risk map might not have them)
                if len(polygon_structure) > 1:
                    for interior_ring in polygon_structure[1:]:
                        if len(interior_ring) < 3: continue
                        pygame.draw.polygon(self.screen, self.ocean_color, interior_ring) # Fill hole with ocean
                        pygame.draw.polygon(self.screen, TERRITORY_BORDER_COLOR, interior_ring, TERRITORY_BORDER_WIDTH)


            label_pos = display_data["label_position"]
            army_text_color = BLACK if sum(owner_color[:3]) / 3 > 128 else WHITE # Ensure owner_color is subscriptable

            # Draw army count at label_position
            army_text = self.font.render(str(territory_obj.army_count), True, army_text_color)
            army_rect = army_text.get_rect(center=label_pos)
            self.screen.blit(army_text, army_rect)

            # Draw territory name slightly above the army count
            name_surf = self.small_font.render(terr_name, True, TEXT_COLOR)
            name_rect = name_surf.get_rect(center=(label_pos[0], label_pos[1] - 20))

            # Simple background for name text for better readability
            name_bg_rect = name_rect.inflate(6, 2)
            pygame.draw.rect(self.screen, DARK_GREY, name_bg_rect, border_radius=3)
            self.screen.blit(name_surf, name_rect)

    def draw_player_info_panel(self, game_state: GameState):
        panel_rect = pygame.Rect(MAP_AREA_WIDTH, 0, SIDE_PANEL_WIDTH, PLAYER_INFO_HEIGHT)
        pygame.draw.rect(self.screen, PLAYER_INFO_BG, panel_rect)
        pygame.draw.rect(self.screen, WHITE, panel_rect, 1) # Border

        gs_to_draw = game_state
        if not gs_to_draw: gs_to_draw = getattr(self, 'current_game_state', self.engine.game_state)
        current_player = gs_to_draw.get_current_player()

        y_pos = panel_rect.y + 5
        if current_player:
            player_color = self.colors.get(current_player.color, WHITE)
            info_text = f"Player: {current_player.name}"
            info_surface = self.font.render(info_text, True, player_color)
            self.screen.blit(info_surface, (panel_rect.x + 5, y_pos))

            turn_text = f"Turn: {gs_to_draw.current_turn_number}"
            turn_surface = self.font.render(turn_text, True, TEXT_COLOR)
            turn_rect = turn_surface.get_rect(topright=(panel_rect.right - 5, y_pos))
            self.screen.blit(turn_surface, turn_rect)
            y_pos += self.font.get_linesize()

            phase_text = f"Phase: {gs_to_draw.current_game_phase}"
            if self.orchestrator and self.orchestrator.ai_is_thinking and self.orchestrator.active_ai_player_name == current_player.name:
                phase_text += " (Thinking...)"

            cards_text = f"Cards: {len(current_player.hand)} | Deploy: {current_player.armies_to_deploy}"

            phase_surface = self.small_font.render(phase_text, True, TEXT_COLOR)
            self.screen.blit(phase_surface, (panel_rect.x + 5, y_pos))

            cards_surface = self.small_font.render(cards_text, True, TEXT_COLOR)
            cards_rect = cards_surface.get_rect(bottomright=(panel_rect.right - 5, panel_rect.bottom - 5))
            self.screen.blit(cards_surface, cards_rect)

        elif self.orchestrator and self.orchestrator.ai_is_thinking and self.orchestrator.active_ai_player_name:
            thinking_text = f"AI ({self.orchestrator.active_ai_player_name}) is thinking..."
            thinking_surface = self.font.render(thinking_text, True, HIGHLIGHT_COLOR)
            self.screen.blit(thinking_surface, (panel_rect.x + 5, y_pos))

    def draw_key_actions_panel(self):
        base_y = PLAYER_INFO_HEIGHT
        panel_rect = pygame.Rect(MAP_AREA_WIDTH, base_y, SIDE_PANEL_WIDTH, KEY_ACTIONS_HEIGHT)
        pygame.draw.rect(self.screen, PANEL_BG_COLOR, panel_rect)
        pygame.draw.rect(self.screen, WHITE, panel_rect, 1) # Border

        title_text = self.font.render("Key Developments", True, TEXT_COLOR)
        self.screen.blit(title_text, (panel_rect.x + 10, panel_rect.y + 5))

        y_offset = self.font.get_linesize() + 10
        max_entries = (KEY_ACTIONS_HEIGHT - y_offset - 5) // (self.small_font.get_linesize() + 2)

        for i, log_entry in enumerate(reversed(self.key_actions_log[-max_entries:])):
            entry_surface = self.small_font.render(log_entry, True, LIGHT_GREY)
            self.screen.blit(entry_surface, (panel_rect.x + 10, panel_rect.y + y_offset + i * (self.small_font.get_linesize() + 2)))

    def draw_action_log_panel(self):
        base_y = PLAYER_INFO_HEIGHT + KEY_ACTIONS_HEIGHT
        panel_rect = pygame.Rect(MAP_AREA_WIDTH, base_y, SIDE_PANEL_WIDTH, ACTION_LOG_HEIGHT)
        pygame.draw.rect(self.screen, PANEL_BG_COLOR, panel_rect) # Use new panel bg color
        pygame.draw.rect(self.screen, WHITE, panel_rect, 1) # Border

        title_text = self.font.render("Action Log", True, TEXT_COLOR) # Use themed text color
        self.screen.blit(title_text, (panel_rect.x + 10, panel_rect.y + 5))

        y_offset = self.font.get_linesize() + 10 # Consistent padding from title
        max_entries = (ACTION_LOG_HEIGHT - y_offset - 5) // (self.small_font.get_linesize() + 2)

        for i, log_entry in enumerate(reversed(self.action_log[-max_entries:])): # Show more entries if space allows
            entry_surface = self.small_font.render(log_entry, True, LIGHT_GREY) # Use smaller font for more entries
            self.screen.blit(entry_surface, (panel_rect.x + 10, panel_rect.y + y_offset + i * (self.small_font.get_linesize() + 2)))

    def _render_text_wrapped(self, surface, text, rect, font, color): # Keep this useful helper
        words = text.split(' ')
        lines = []
        current_line = ""
        line_height = font.get_linesize()
        max_lines = (rect.height - 10) // line_height # -10 for padding

        for word in words:
            test_line = current_line + word + " "
            if font.size(test_line)[0] < rect.width - 10: # -10 for padding
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word + " "
        lines.append(current_line)

        y = rect.y + 5
        for i, line_text in enumerate(lines):
            if i >= max_lines: break
            line_surface = font.render(line_text.strip(), True, color)
            surface.blit(line_surface, (rect.x + 5, y))
            y += line_height

    def draw_tabs(self, base_y_offset: int, panel_title: str, tab_options: list[str], active_tab_var_name: str, tab_rects_dict_name: str, mouse_click_pos: tuple[int, int] | None):
        tab_bar_rect = pygame.Rect(MAP_AREA_WIDTH, base_y_offset, SIDE_PANEL_WIDTH, TAB_HEIGHT)
        pygame.draw.rect(self.screen, DARK_GREY, tab_bar_rect)

        tab_rects_dict = getattr(self, tab_rects_dict_name)
        tab_rects_dict.clear()

        current_x = MAP_AREA_WIDTH + 5
        max_tab_width = (SIDE_PANEL_WIDTH - 10) / len(tab_options) if tab_options else SIDE_PANEL_WIDTH - 10

        for option_name in tab_options:
            text_surface = self.tab_font.render(option_name[:10], True, BLACK) # Truncate for display
            text_width, text_height = text_surface.get_size()
            tab_width = min(text_width + 10, max_tab_width)

            tab_rect = pygame.Rect(current_x, base_y_offset, tab_width, TAB_HEIGHT)
            is_active = getattr(self, active_tab_var_name) == option_name
            tab_bg_color = TAB_COLOR_ACTIVE if is_active else TAB_COLOR_INACTIVE

            pygame.draw.rect(self.screen, tab_bg_color, tab_rect)
            pygame.draw.rect(self.screen, BLACK, tab_rect, 1) # Border
            self.screen.blit(text_surface, (tab_rect.x + (tab_width - text_width) // 2, tab_rect.y + (TAB_HEIGHT - text_height) // 2))

            tab_rects_dict[option_name] = tab_rect

            if mouse_click_pos and tab_rect.collidepoint(mouse_click_pos):
                setattr(self, active_tab_var_name, option_name)
                print(f"GUI: Switched {panel_title} tab to {option_name}")

            current_x += tab_width + 2 # Small gap

        return base_y_offset + TAB_HEIGHT


    def draw_ai_thought_panel(self, mouse_click_pos: tuple[int, int] | None):
        tab_options = self.player_names_for_tabs
        if not self.active_tab_thought_panel and tab_options:
            self.active_tab_thought_panel = tab_options[0]

        content_y_start = self.draw_tabs(ACTION_LOG_HEIGHT, "AI Thoughts", tab_options, "active_tab_thought_panel", "thought_tab_rects", mouse_click_pos)

        panel_rect = pygame.Rect(MAP_AREA_WIDTH, content_y_start, SIDE_PANEL_WIDTH, THOUGHT_PANEL_HEIGHT - TAB_HEIGHT)
        pygame.draw.rect(self.screen, (40,40,40), panel_rect)
        pygame.draw.rect(self.screen, WHITE, panel_rect, 1)

        player_to_show = self.active_tab_thought_panel
        current_thoughts_map = self.ai_thoughts

        if player_to_show and player_to_show in current_thoughts_map:
            thought = current_thoughts_map[player_to_show]
            self._render_text_wrapped(self.screen, thought, panel_rect, self.font, WHITE)
        else:
            no_thought_text_str = f"No thoughts for {player_to_show if player_to_show else 'N/A'}."
            no_thought_text = self.font.render(no_thought_text_str, True, GREY)
            self.screen.blit(no_thought_text, (panel_rect.x + 5, panel_rect.y + 5))

    def draw_chat_panel(self, mouse_click_pos: tuple[int, int] | None):
        base_y = ACTION_LOG_HEIGHT + THOUGHT_PANEL_HEIGHT

        chat_tab_options = ["global"] + list(getattr(self, 'private_chat_conversations_map', {}).keys())
        content_y_start = self.draw_tabs(base_y, "Chat", chat_tab_options, "active_tab_chat_panel", "chat_tab_rects", mouse_click_pos)

        panel_rect = pygame.Rect(MAP_AREA_WIDTH, content_y_start, SIDE_PANEL_WIDTH, CHAT_PANEL_HEIGHT - TAB_HEIGHT)
        pygame.draw.rect(self.screen, (50,50,50), panel_rect)
        pygame.draw.rect(self.screen, WHITE, panel_rect, 1)

        messages_to_render = []
        if self.active_tab_chat_panel == "global":
            messages_to_render = getattr(self, 'global_chat_messages', [])[-10:] # Last 10 global
        else:
            all_private_chats = getattr(self, 'private_chat_conversations_map', {})
            messages_to_render = all_private_chats.get(self.active_tab_chat_panel, [])[-10:] # Last 10 for this private chat

        y_render_offset = panel_rect.y + 5
        for msg_data in reversed(messages_to_render):
            msg_str = f"{msg_data.get('sender','System')}: {msg_data.get('message','')}"
            # Simple rendering for now, could wrap text if needed
            if y_render_offset + self.font.get_linesize() > panel_rect.bottom - 5: break
            msg_surface = self.font.render(msg_str[:50], True, WHITE) # Truncate long messages
            self.screen.blit(msg_surface, (panel_rect.x + 5, y_render_offset))
            y_render_offset += self.font.get_linesize()

        if not messages_to_render:
            no_chat_text = self.font.render(f"No messages in chat '{self.active_tab_chat_panel}'.", True, GREY)
            self.screen.blit(no_chat_text, (panel_rect.x + 5, panel_rect.y + 5))

    def log_action(self, action_string: str):
        self.action_log.append(action_string)
        if len(self.action_log) > 50: self.action_log.pop(0)

    def update_thought_panel(self, player_name: str, thought: str):
        self.ai_thoughts[player_name] = thought
        # Optionally, immediately switch to this player's thought tab:
        # if player_name in self.player_names_for_tabs:
        #    self.active_tab_thought_panel = player_name

    def log_private_chat(self, conversation_log: list[dict], p1_name: str, p2_name: str):
        if not conversation_log: return
        # Create a consistent key for the conversation
        sorted_names = sorted([p1_name, p2_name])
        log_key = f"private_{sorted_names[0]}_vs_{sorted_names[1]}"

        # The orchestrator now passes the full map, so GUI doesn't need to manage this itself.
        # This method is more for if GUI was directly told about a new conversation.
        # For now, we can assume private_chat_conversations_map is updated by gui.update()
        self.log_action(f"Private chat: {p1_name} & {p2_name} ({len(conversation_log)} msgs).")
        # If orchestrator doesn't update the map via gui.update, then GUI needs to do it:
        # if not hasattr(self, 'private_chat_conversations_map'):
        #     self.private_chat_conversations_map = {}
        # self.private_chat_conversations_map[log_key] = conversation_log


    def show_game_over_screen(self, winner_name: str | None):
        self.screen.fill(BLACK)
        message = f"Game Over! Winner: {winner_name}" if winner_name else "Game Over! Draw/Timeout."
        text_surface = self.large_font.render(message, True, WHITE)
        text_rect = text_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
        self.screen.blit(text_surface, text_rect)
        pygame.display.flip()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: running = False
            self.clock.tick(10)
        pygame.quit()

    def handle_input(self): # This method is effectively replaced by the event loop in run()
        pass

    def run(self):
        self.running = True
        mouse_click_pos = None

        # Ensure player_names_for_tabs is initialized if game state is available
        if self.current_game_state and self.current_game_state.players:
             self.player_names_for_tabs = [p.name for p in self.current_game_state.players]
             if not self.active_tab_thought_panel and self.player_names_for_tabs:
                 self.active_tab_thought_panel = self.player_names_for_tabs[0]


        while self.running:
            mouse_click_pos = None
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        mouse_click_pos = event.pos

            if self.orchestrator and self.running:
                if not self.orchestrator.advance_game_turn():
                    self.running = False

            self.screen.fill(self.colors.get('grey', GREY))

            gs_to_draw = getattr(self, 'current_game_state', self.engine.game_state)

            self.draw_map(gs_to_draw)
            self.draw_action_log_panel() # Draws self.action_log
            self.draw_ai_thought_panel(mouse_click_pos) # Draws self.ai_thoughts, handles its own tabs
            self.draw_chat_panel(mouse_click_pos) # Draws global/private chats, handles its own tabs
            self.draw_player_info_panel(gs_to_draw) # New panel for current player info

            pygame.display.flip()
            self.clock.tick(self.fps)

        print("GUI: Exiting run loop.")
        return 'QUIT_BY_USER'

if __name__ == '__main__':
    print("GUI Module - Basic Test (Placeholder)")
    class MockPlayer:
        def __init__(self, name, color): self.name, self.color, self.hand, self.armies_to_deploy = name, color, [], 0
    class MockTerritory:
        def __init__(self, name, owner, army_count): self.name, self.owner, self.army_count = name, owner, army_count
    class MockGameState:
        def __init__(self): self.territories, self.players, self.current_turn_number, self.current_game_phase, self.current_player_index, self.deck, self.continents = {}, [], 1, "REINFORCE", 0, [], {}
        def get_current_player(self): return self.players[self.current_player_index] if self.players and 0 <= self.current_player_index < len(self.players) else None
    class MockEngine:
        def __init__(self): self.game_state = MockGameState(); p1,p2 = MockPlayer("Archie","Red"), MockPlayer("Bea","Blue"); self.game_state.players=[p1,p2]; self.game_state.territories={"Alaska":MockTerritory("Alaska",p1,5), "Alberta":MockTerritory("Alberta",p2,3)}
    class MockOrchestrator:
        def __init__(self, eng): self.engine,self.ai_agents,self.global_chat,self.private_chat_manager,self.game_should_continue,self._gui = eng,{"Archie":"A","Bea":"B"},type('GC',(),{'get_log':lambda s,l=0:[{"s":"Sys","m":"Global"}]})(),type('PCM',(),{'get_all_conversations':lambda s:{"pvp_Archie_Bea":[{"s":"Archie","m":"Hi"}]}})(),True,None
        def set_gui(self,g):self._gui=g
        def advance_game_turn(self):
            if not self.game_should_continue or not self.engine.game_state.get_current_player(): return False
            if self.engine.game_state.current_turn_number > 2: self.game_should_continue = False; return False
            self.engine.game_state.current_player_index = (self.engine.game_state.current_player_index + 1) % len(self.engine.game_state.players)
            if self.engine.game_state.current_player_index == 0: self.engine.game_state.current_turn_number +=1
            if self._gui: self._gui.log_action(f"Mock Turn {self.engine.game_state.current_turn_number}"); self._gui.update(self.engine.game_state, self.global_chat.get_log(), self.private_chat_manager.get_all_conversations())
            return True

    me = MockEngine(); mo = MockOrchestrator(me)
    if not os.path.exists("map_display_config.json"):
        with open("map_display_config.json","w") as f: json.dump({"Alaska":(100,100),"Alberta":(150,150)},f)

    gui = GameGUI(me, mo); mo.set_gui(gui)
    gui.player_names_for_tabs = [p.name for p in me.game_state.players] # Manual setup for test
    if gui.player_names_for_tabs: gui.active_tab_thought_panel = gui.player_names_for_tabs[0]
    gui.ai_thoughts["Archie"] = "Archie's plan..."
    gui.ai_thoughts["Bea"] = "Bea's counter-plan..."
    gui.active_tab_chat_panel = "pvp_Archie_Bea" # Test private chat tab

    gui.run()
    print("GUI Module - Basic Test Complete.")
