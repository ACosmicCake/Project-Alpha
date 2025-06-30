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
TAB_COLOR_ACTIVE = GREEN
TAB_COLOR_INACTIVE = GREY

# Define a new color for the ocean
OCEAN_BLUE = (60, 100, 180) # A pleasant blue for the ocean background
CONTINENT_COLORS = { # Example colors, can be expanded
    "North America": (200, 180, 150), # Tan-ish
    "Asia": (150, 200, 150), # Light green-ish
    "Default": (100, 100, 100) # Fallback continent color
}
ADJACENCY_LINE_COLOR = (50, 50, 50) # Dark grey for lines

DEFAULT_PLAYER_COLORS = {
    "Red": RED, "Blue": BLUE, "Green": GREEN, "Yellow": YELLOW,
    "Purple": (128, 0, 128), "Orange": (255, 165, 0), "Black": BLACK, "White": WHITE # White might be hard to see
}

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
MAP_AREA_WIDTH = 900
SIDE_PANEL_WIDTH = SCREEN_WIDTH - MAP_AREA_WIDTH
ACTION_LOG_HEIGHT = 150 # Adjusted
THOUGHT_PANEL_HEIGHT = 200 # Adjusted
CHAT_PANEL_HEIGHT = SCREEN_HEIGHT - ACTION_LOG_HEIGHT - THOUGHT_PANEL_HEIGHT - 50 # Adjusted for player info
PLAYER_INFO_PANEL_HEIGHT = 50 # New panel

TAB_HEIGHT = 30
TAB_FONT_SIZE = 20


class GameGUI:
    def __init__(self, engine: GameEngine, orchestrator, map_display_config_file: str = "map_display_config.json", game_mode: str = "standard"): # Added parameters
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(f"LLM Risk Game - {game_mode.replace('_', ' ').title()} Mode") # Update caption
        self.font = pygame.font.SysFont(None, 24)
        self.large_font = pygame.font.SysFont(None, 36)
        self.tab_font = pygame.font.SysFont(None, TAB_FONT_SIZE)
        self.ocean_color = OCEAN_BLUE
        self.clock = pygame.time.Clock()

        self.engine = engine
        self.orchestrator = orchestrator
        self.game_mode = game_mode # Store the game mode
        print(f"DEBUG: GameGUI.__init__ - Received game_mode: '{self.game_mode}', map_display_config_file: '{map_display_config_file}'")
        print(f"DEBUG: GameGUI.__init__ - Engine's map_file_path: '{engine.game_state.map_file_path if engine and engine.game_state else 'N/A'}'")

        self.current_game_state: GameState = engine.game_state
        self.global_chat_messages: list[dict] = []
        self.private_chat_conversations_map: dict[str, list[dict]] = {}


        self.territory_coordinates: dict[str, tuple[int, int]] = {}
        self.territory_polygons: dict[str, list[tuple[int,int]]] = {} # For world_map mode

        # Use the passed map_display_config_file
        self._load_map_display_config(map_display_config_file)

        self.action_log: list[str] = ["Game Started."]
        self.ai_thoughts: dict[str, str] = {}

        self.player_names_for_tabs: list[str] = [] # Will be populated in update or run
        self.active_tab_thought_panel = ""
        self.active_tab_chat_panel = "global"
        self.thought_tab_rects: dict[str, pygame.Rect] = {}
        self.chat_tab_rects: dict[str, pygame.Rect] = {}

        self.fps = 30
        self.running = False
        self.colors = DEFAULT_PLAYER_COLORS

    def _load_map_display_config(self, config_file: str):
        print(f"DEBUG: GameGUI._load_map_display_config - Attempting to load display config from '{config_file}' for game_mode '{self.game_mode}'.")
        try:
            with open(config_file, 'r') as f:
                content_for_debug = f.read()
                print(f"DEBUG: GameGUI._load_map_display_config - First 500 chars of '{config_file}':\n{content_for_debug[:500]}...")
                f.seek(0) # Reset file pointer to read JSON
                display_data = json.load(f)

            if self.game_mode == "world_map":
                self.territory_polygons = display_data.get("territory_polygons", {})
                self.territory_coordinates = display_data.get("territory_centroids", {})

                print(f"DEBUG: GameGUI._load_map_display_config - Loaded for 'world_map'.")
                print(f"DEBUG: GameGUI._load_map_display_config - Number of polygon entries: {len(self.territory_polygons)}")
                print(f"DEBUG: GameGUI._load_map_display_config - Number of centroid entries: {len(self.territory_coordinates)}")

                if not isinstance(self.territory_polygons, dict) or not isinstance(self.territory_coordinates, dict):
                    print(f"DEBUG: GameGUI._load_map_display_config - WARNING: World map display config '{config_file}' has unexpected structure. Creating dummy data.")
                    self._create_dummy_world_map_display_data(config_file)
                    return

                # Log a sample for verification
                if self.territory_polygons:
                    sample_terr_name = next(iter(self.territory_polygons))
                    print(f"DEBUG: GameGUI._load_map_display_config - Sample polygon for '{sample_terr_name}': {str(self.territory_polygons[sample_terr_name])[:200]}...")
                if self.territory_coordinates:
                    sample_cent_name = next(iter(self.territory_coordinates))
                    print(f"DEBUG: GameGUI._load_map_display_config - Sample centroid for '{sample_cent_name}': {self.territory_coordinates[sample_cent_name]}")

                valid_polygons_format = True
                for name, poly_parts in self.territory_polygons.items():
                    if not isinstance(poly_parts, list): valid_polygons_format = False; break
                    for part in poly_parts:
                        if not isinstance(part, list) or not all(isinstance(pt, (list, tuple)) and len(pt) == 2 and all(isinstance(coord_val, (int, float)) for coord_val in pt) for pt in part):
                            valid_polygons_format = False; print(f"DEBUG: Format error in polygon part for {name}: {part}"); break
                    if not valid_polygons_format: break

                valid_centroids_format = all(isinstance(coord, (list, tuple)) and len(coord) == 2 and all(isinstance(val, (int, float)) for val in coord) for coord in self.territory_coordinates.values())

                if not valid_polygons_format:
                    print(f"DEBUG: GameGUI._load_map_display_config - WARNING: Polygon data format error in '{config_file}'.")
                if not valid_centroids_format:
                    print(f"DEBUG: GameGUI._load_map_display_config - WARNING: Centroid data format error in '{config_file}'.")

                if not valid_polygons_format or not valid_centroids_format:
                    print(f"DEBUG: GameGUI._load_map_display_config - Triggering dummy data due to format errors.")
                    self._create_dummy_world_map_display_data(config_file)
                    return

                if not self.territory_polygons and not self.territory_coordinates:
                    print(f"DEBUG: GameGUI._load_map_display_config - WARNING: World map display config '{config_file}' is empty. Creating dummy data.")
                    self._create_dummy_world_map_display_data(config_file)

            else: # Standard mode
                self.territory_coordinates = display_data
                print(f"DEBUG: GameGUI._load_map_display_config - Loaded for 'standard' mode. Number of territories: {len(self.territory_coordinates)}")
                if not isinstance(self.territory_coordinates, dict):
                    print(f"Warning: Standard map display config '{config_file}' is not a dictionary. Creating dummy data.")
                    self._create_dummy_standard_map_coordinates(config_file)
                    return
                print(f"Successfully loaded standard territory coordinates from '{config_file}'.")
                if not self.territory_coordinates:
                     self._create_dummy_standard_map_coordinates(config_file) # Renamed for clarity

        except FileNotFoundError:
            print(f"Warning: Map display config file '{config_file}' not found.")
            if self.game_mode == "world_map":
                self._create_dummy_world_map_display_data(config_file)
            else:
                self._create_dummy_standard_map_coordinates(config_file)
        except json.JSONDecodeError:
            print(f"Error decoding JSON from '{config_file}'.")
            # Fallback to dummy data based on mode
            if self.game_mode == "world_map":
                self._create_dummy_world_map_display_data(config_file)
            else:
                self._create_dummy_standard_map_coordinates(config_file)

    def _create_dummy_standard_map_coordinates(self, config_file: str): # Renamed
        if not self.engine.game_state.territories: return
        dummy_coords = {}
        x_offset, y_offset = 50, 50
        for i, name in enumerate(self.engine.game_state.territories.keys()):
            dummy_coords[name] = (x_offset + (i % 5) * 150, y_offset + (i // 5) * 100)
        self.territory_coordinates = dummy_coords
        try:
            with open(config_file, 'w') as f: json.dump(self.territory_coordinates, f, indent=2)
            print(f"Created dummy standard map coordinates file '{config_file}'.")
        except IOError: print(f"Could not write dummy standard map coords to '{config_file}'.")

    def _create_dummy_world_map_display_data(self, config_file: str):
        # For world map, we'd ideally have polygons. For dummy, just use centroids like standard.
        if not self.engine.game_state.territories: return
        dummy_centroids = {}
        dummy_polygons = {} # Will be empty for this dummy version
        x_offset, y_offset = 50, 50

        # This part assumes territories are already loaded in engine for the world map
        # which might not be true if world_map_config.json isn't created yet.
        # For now, it will create an empty config if territories aren't there.
        territory_names = list(self.engine.game_state.territories.keys())
        if not territory_names: # If no territories (e.g. world_map_config.json not yet processed)
            print("GUI: No territories in engine to create dummy world map display data. Config will be empty.")

        for i, name in enumerate(territory_names):
            dummy_centroids[name] = (x_offset + (i % 8) * 100, y_offset + (i // 8) * 70) # Adjust layout
            # Dummy polygon (a small square around the centroid)
            cx, cy = dummy_centroids[name]
            dummy_polygons[name] = [(cx-10, cy-10), (cx+10, cy-10), (cx+10, cy+10), (cx-10, cy+10)]


        self.territory_coordinates = dummy_centroids
        self.territory_polygons = dummy_polygons

        data_to_save = {
            "territory_centroids": self.territory_coordinates,
            "territory_polygons": self.territory_polygons
        }
        try:
            with open(config_file, 'w') as f: json.dump(data_to_save, f, indent=2)
            print(f"Created dummy world map display data file '{config_file}'.")
        except IOError: print(f"Could not write dummy world map display data to '{config_file}'.")

    def update(self, game_state: GameState, global_chat_log: list[dict], private_chat_conversations: dict):
        self.current_game_state = game_state
        self.global_chat_messages = global_chat_log
        self.private_chat_conversations_map = private_chat_conversations

        # Update player names for tabs, in case players are eliminated
        if self.current_game_state and self.current_game_state.players:
            self.player_names_for_tabs = [p.name for p in self.current_game_state.players]
            if self.active_tab_thought_panel not in self.player_names_for_tabs and self.player_names_for_tabs:
                self.active_tab_thought_panel = self.player_names_for_tabs[0]
            elif not self.player_names_for_tabs:
                 self.active_tab_thought_panel = ""


    def draw_map(self, game_state: GameState):
        # ... (ocean background) ...
        # Force re-check from orchestrator to be absolutely sure, though this indicates a deeper issue if needed.
        # current_mode_from_orchestrator = self.orchestrator.game_mode # This might be too coupled.
        # print(f"DEBUG: GameGUI.draw_map - self.game_mode: '{self.game_mode}', Orchestrator game_mode: '{current_mode_from_orchestrator}'")

        if hasattr(self, 'game_mode') and self.game_mode == "world_map":
            # print("DEBUG: GameGUI.draw_map - Path taken: world_map")
            self._draw_world_map_polygons(game_state)
        else:
            print(f"DEBUG: GameGUI.draw_map - Path taken: standard_map_circles. self.game_mode is '{getattr(self, 'game_mode', 'NOT SET')}'")
            self._draw_standard_map_circles(game_state)

    def _draw_standard_map_circles(self, game_state: GameState):
        # This is the original draw_map logic for circles
        # print("DEBUG: GameGUI._draw_standard_map_circles - Method called.") # More accurate location for this print
        gs_to_draw = game_state
        if not gs_to_draw: gs_to_draw = getattr(self, 'current_game_state', self.engine.game_state)

        map_area_rect = pygame.Rect(0, 0, MAP_AREA_WIDTH, SCREEN_HEIGHT)
        self.screen.fill(self.ocean_color, map_area_rect) # Ensure map area is cleared

        if not gs_to_draw or not gs_to_draw.territories:
            no_map_text = self.large_font.render("Map Data Unavailable", True, WHITE)
            self.screen.blit(no_map_text, no_map_text.get_rect(center=map_area_rect.center))
            return

        drawn_adjacencies = set()
        for terr_name, territory_obj in gs_to_draw.territories.items():
            coords1 = self.territory_coordinates.get(terr_name)
            if not coords1: continue
            for adj_territory_object in territory_obj.adjacent_territories:
                adj_name = adj_territory_object.name
                adj_pair = tuple(sorted((terr_name, adj_name)))
                if adj_pair in drawn_adjacencies: continue
                coords2 = self.territory_coordinates.get(adj_name)
                if not coords2: continue
                pygame.draw.line(self.screen, ADJACENCY_LINE_COLOR, coords1, coords2, 2)
                drawn_adjacencies.add(adj_pair)

        for terr_name, territory_obj in gs_to_draw.territories.items():
            coords = self.territory_coordinates.get(terr_name)
            if not coords: continue
            owner_color = GREY
            if territory_obj.owner and territory_obj.owner.color:
                owner_color = DEFAULT_PLAYER_COLORS.get(territory_obj.owner.color, GREY)
            pygame.draw.circle(self.screen, owner_color, coords, 20)
            pygame.draw.circle(self.screen, BLACK, coords, 20, 2)
            army_text_color = BLACK if sum(owner_color) / 3 > 128 else WHITE
            army_text = self.font.render(str(territory_obj.army_count), True, army_text_color)
            self.screen.blit(army_text, army_text.get_rect(center=coords))
            name_surf = self.font.render(terr_name, True, WHITE)
            name_rect = name_surf.get_rect(center=(coords[0], coords[1] - 30))
            name_bg_rect = name_rect.inflate(4, 4)
            pygame.draw.rect(self.screen, DARK_GREY, name_bg_rect, border_radius=3)
            self.screen.blit(name_surf, name_rect)

    def _draw_world_map_polygons(self, game_state: GameState):
        gs_to_draw = game_state
        if not gs_to_draw: gs_to_draw = getattr(self, 'current_game_state', self.engine.game_state)

        map_area_rect = pygame.Rect(0, 0, MAP_AREA_WIDTH, SCREEN_HEIGHT)
        self.screen.fill(self.ocean_color, map_area_rect) # Ensure map area is cleared

        if not gs_to_draw or not gs_to_draw.territories:
            print("DEBUG: GameGUI._draw_world_map_polygons - No game_state or territories to draw.")
            no_map_text = self.large_font.render("World Map Data Unavailable", True, WHITE)
            self.screen.blit(no_map_text, no_map_text.get_rect(center=map_area_rect.center))
            return

        print(f"DEBUG: GameGUI._draw_world_map_polygons - Number of territories to draw: {len(gs_to_draw.territories)}")
        if not self.territory_polygons:
            print("DEBUG: GameGUI._draw_world_map_polygons - self.territory_polygons is empty. Cannot draw polygons.")
            # Potentially draw circles as a fallback if centroids exist? Or just the error message.
            # For now, if no polygons, it will just draw adjacency lines and then text if centroids exist.
            # This might be a reason why circles appear if this path is hit and then standard drawing is later invoked.

        # Adjacency lines for world map (can be complex, for now use centroids if polygons are too complex for simple line drawing)
        drawn_adjacencies = set()
        for terr_name_adj, territory_obj_adj in gs_to_draw.territories.items(): # Use different var names to avoid clash
            coords1 = self.territory_coordinates.get(terr_name_adj) # Use centroid for line start/end
            if not coords1:
                # print(f"DEBUG: Adjacency - Missing centroid for {terr_name_adj}")
                continue
            for adj_territory_object in territory_obj_adj.adjacent_territories:
                adj_name = adj_territory_object.name
                adj_pair = tuple(sorted((terr_name_adj, adj_name)))
                if adj_pair in drawn_adjacencies: continue
                coords2 = self.territory_coordinates.get(adj_name)
                if not coords2:
                    # print(f"DEBUG: Adjacency - Missing centroid for adjacent {adj_name}")
                    continue
                pygame.draw.line(self.screen, ADJACENCY_LINE_COLOR, coords1, coords2, 1) # Thinner line
                drawn_adjacencies.add(adj_pair)

        # Draw polygons
        for terr_name, territory_obj in gs_to_draw.territories.items():
            # self.territory_polygons and self.territory_coordinates are now expected to be
            # pre-scaled screen coordinates from MapProcessor's output.

            processed_first_territory_for_debug = False # Debug flag

        # Draw polygons
        for terr_name, territory_obj in gs_to_draw.territories.items():
            list_of_screen_polygon_points = self.territory_polygons.get(terr_name)
            screen_centroid_coords = self.territory_coordinates.get(terr_name)

            if not processed_first_territory_for_debug: # Log details for the first territory
                print(f"DEBUG: _draw_world_map_polygons - Processing territory: '{terr_name}'")
                if list_of_screen_polygon_points:
                    print(f"DEBUG: _draw_world_map_polygons -   Polygons for '{terr_name}' (first part, first 5 points): {str(list_of_screen_polygon_points[0][:5]) if list_of_screen_polygon_points else 'No polygon data'}")
                else:
                    print(f"DEBUG: _draw_world_map_polygons -   No polygon data for '{terr_name}'.")
                print(f"DEBUG: _draw_world_map_polygons -   Centroid for '{terr_name}': {screen_centroid_coords}")
                processed_first_territory_for_debug = True

            owner_color = DEFAULT_PLAYER_COLORS.get(territory_obj.owner.color, GREY) if territory_obj.owner and territory_obj.owner.color else GREY

            if list_of_screen_polygon_points:
                # print(f"DEBUG: Drawing polygons for {terr_name}") # Can be too verbose
                for i, screen_polygon_part_points in enumerate(list_of_screen_polygon_points):
                    if screen_polygon_part_points and len(screen_polygon_part_points) >= 3:
                        try:
                            pygame.draw.polygon(self.screen, owner_color, screen_polygon_part_points)
                            pygame.draw.polygon(self.screen, BLACK, screen_polygon_part_points, 1) # Border
                        except TypeError as e:
                            print(f"DEBUG: GameGUI._draw_world_map_polygons - Error drawing polygon part {i} for {terr_name}: {e}. Screen points: {screen_polygon_part_points}")
                            if screen_centroid_coords: # Fallback for this specific part
                                pygame.draw.circle(self.screen, owner_color, screen_centroid_coords, 5, 0)
                    # else:
                        # print(f"DEBUG: GameGUI._draw_world_map_polygons - Invalid or empty screen polygon part {i} for {terr_name}")
            elif screen_centroid_coords:
                print(f"DEBUG: GameGUI._draw_world_map_polygons - No polygons for '{terr_name}', drawing circle at centroid {screen_centroid_coords}.")
                pygame.draw.circle(self.screen, owner_color, screen_centroid_coords, 10)
                pygame.draw.circle(self.screen, BLACK, screen_centroid_coords, 10, 1)
            # else:
                # print(f"DEBUG: GameGUI._draw_world_map_polygons - No display data (polygon or centroid) for territory {terr_name}. Skipping draw.")


            # Draw army count and name at the screen_centroid_coords (if available)
            if screen_centroid_coords:
                army_text_color = BLACK if sum(owner_color) / 3 > 128 else WHITE
                army_text = self.font.render(str(territory_obj.army_count), True, army_text_color)

                army_text_rect = army_text.get_rect(center=screen_centroid_coords)
                army_bg_rect = army_text_rect.inflate(4,2)
                pygame.draw.rect(self.screen, owner_color, army_bg_rect, border_radius=3)
                pygame.draw.rect(self.screen, BLACK, army_bg_rect, 1, border_radius=3)
                self.screen.blit(army_text, army_text_rect)

                name_surf = self.font.render(terr_name, True, WHITE)
                name_rect = name_surf.get_rect(center=(screen_centroid_coords[0], screen_centroid_coords[1] + 15)) # Offset below
                name_bg_rect = name_rect.inflate(4,2)
                pygame.draw.rect(self.screen, DARK_GREY, name_bg_rect, border_radius=3)
                self.screen.blit(name_surf, name_rect)

    def draw_player_info_panel(self, game_state: GameState):
        panel_rect = pygame.Rect(MAP_AREA_WIDTH, SCREEN_HEIGHT - PLAYER_INFO_PANEL_HEIGHT, SIDE_PANEL_WIDTH, PLAYER_INFO_PANEL_HEIGHT)
        pygame.draw.rect(self.screen, (20,20,20), panel_rect)
        pygame.draw.rect(self.screen, WHITE, panel_rect, 1)

        gs_to_draw = game_state
        if not gs_to_draw: gs_to_draw = getattr(self, 'current_game_state', self.engine.game_state)
        current_player = gs_to_draw.get_current_player()
        y_pos = panel_rect.y + 5
        if current_player:
            info_text = f"Turn: {gs_to_draw.current_turn_number} Player: {current_player.name} ({current_player.color})"
            info_surface = self.font.render(info_text, True, WHITE)
            self.screen.blit(info_surface, (panel_rect.x + 5, y_pos))
            y_pos += 20

            phase_text = f"Phase: {gs_to_draw.current_game_phase}"
            if self.orchestrator and self.orchestrator.ai_is_thinking and self.orchestrator.active_ai_player_name == current_player.name:
                phase_text += " (Thinking...)"

            cards_text = f"Cards: {len(current_player.hand)}, Deploy: {current_player.armies_to_deploy}, {phase_text}"
            cards_surface = self.font.render(cards_text, True, WHITE)
            self.screen.blit(cards_surface, (panel_rect.x + 5, y_pos))
        elif self.orchestrator and self.orchestrator.ai_is_thinking and self.orchestrator.active_ai_player_name:
            # Case where current_player might be None briefly during transitions, but an AI is thinking
            thinking_text = f"AI ({self.orchestrator.active_ai_player_name}) is thinking..."
            thinking_surface = self.font.render(thinking_text, True, YELLOW) # Yellow to stand out
            self.screen.blit(thinking_surface, (panel_rect.x + 5, y_pos))


    def draw_action_log_panel(self):
        panel_rect = pygame.Rect(MAP_AREA_WIDTH, 0, SIDE_PANEL_WIDTH, ACTION_LOG_HEIGHT)
        pygame.draw.rect(self.screen, DARK_GREY, panel_rect)
        pygame.draw.rect(self.screen, WHITE, panel_rect, 1)
        title_text = self.large_font.render("Action Log", True, WHITE)
        self.screen.blit(title_text, (panel_rect.x + 10, panel_rect.y + 5))
        y_offset = 35
        for i, log_entry in enumerate(reversed(self.action_log[-6:])):
            entry_surface = self.font.render(log_entry, True, LIGHT_GREY)
            self.screen.blit(entry_surface, (panel_rect.x + 10, panel_rect.y + y_offset + i * 20))

    def _render_text_wrapped(self, surface, text, rect, font, color):
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
