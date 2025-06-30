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
OCEAN_BLUE = (40, 60, 100) # Deeper, less saturated blue for ocean
CONTINENT_COLORS = { # Example colors, can be expanded - these are not currently used for territory fill. Player color is used.
    "North America": (200, 180, 150),
    "Asia": (150, 200, 150),
    "Default": (100, 100, 100)
}
ADJACENCY_LINE_COLOR = (70, 70, 90) # Slightly lighter, bluish grey for adjacency lines

DEFAULT_PLAYER_COLORS = {
    "Red": RED, "Blue": BLUE, "Green": GREEN, "Yellow": YELLOW,
    "Purple": (128, 0, 128), "Orange": (255, 165, 0), "Black": BLACK, "White": WHITE # White might be hard to see
}

# Increased screen size
SCREEN_WIDTH = 1600
SCREEN_HEIGHT = 900

# Adjusted layout for new screen size
MAP_AREA_WIDTH = 1100  # Increased map area
SIDE_PANEL_WIDTH = SCREEN_WIDTH - MAP_AREA_WIDTH # Recalculate side panel width

# Panel heights - give more relative space to thoughts and chat
PLAYER_INFO_PANEL_HEIGHT = 60
ACTION_LOG_HEIGHT = 150
THOUGHT_PANEL_HEIGHT = (SCREEN_HEIGHT - PLAYER_INFO_PANEL_HEIGHT - ACTION_LOG_HEIGHT) * 0.5 # Adjusted to take 50% of remaining space
CHAT_PANEL_HEIGHT = (SCREEN_HEIGHT - PLAYER_INFO_PANEL_HEIGHT - ACTION_LOG_HEIGHT) * 0.5 # Adjusted to take 50% of remaining space

TAB_HEIGHT = 35 # Slightly larger tabs
TAB_FONT_SIZE = 22 # Slightly larger tab font
INFO_FONT_SIZE = 20 # For player info panel
STANDARD_FONT_SIZE = 26 # For general text
LARGE_FONT_SIZE = 40 # For titles

# Define some more colors for UI elements
PANEL_BG_COLOR = (30, 30, 40) # Dark bluish grey
PANEL_BORDER_COLOR = (80, 80, 100) # Lighter bluish grey
TEXT_COLOR_LIGHT = (230, 230, 230) # Off-white
TEXT_COLOR_MEDIUM = (180, 180, 180) # Light grey
TEXT_COLOR_DARK = (130, 130, 130) # Medium grey
ACTIVE_TAB_BG = (70, 130, 70) # Muted green
INACTIVE_TAB_BG = (50, 50, 60) # Darker tab color
TEXT_COLOR_HEADER = (200, 200, 220) # Light lavender for headers

class GameGUI:
    def __init__(self, engine: GameEngine, orchestrator, map_display_config_file: str = "map_display_config.json", game_mode: str = "standard"): # Added parameters
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(f"LLM Risk Game - {game_mode.replace('_', ' ').title()} Mode") # Update caption

        # Initialize fonts
        self.info_font = pygame.font.SysFont(None, INFO_FONT_SIZE)
        self.font = pygame.font.SysFont(None, STANDARD_FONT_SIZE) # Standard text font
        self.large_font = pygame.font.SysFont(None, LARGE_FONT_SIZE) # Titles
        self.tab_font = pygame.font.SysFont(None, TAB_FONT_SIZE) # Tabs

        self.ocean_color = OCEAN_BLUE # Kept as is, can be changed in visual polish stage
        self.clock = pygame.time.Clock()

        self.engine = engine
        self.orchestrator = orchestrator
        self.game_mode = game_mode # Store the game mode
        print(f"DEBUG: GameGUI.__init__ - Received game_mode: '{self.game_mode}', map_display_config_file: '{map_display_config_file}'")
        print(f"DEBUG: GameGUI.__init__ - Engine's map_file_path: '{engine.map_file_path if engine else 'N/A'}'") # Corrected attribute access

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

        # Map interaction attributes
        self.map_zoom = 1.0
        self.min_zoom = 0.3
        self.max_zoom = 3.0
        self.zoom_step = 0.1
        self.map_offset_x = 0
        self.map_offset_y = 0
        self.is_panning = False
        self.pan_start_pos = (0, 0)

        # Store original coordinates before zoom/pan transformations for calculations
        self.original_territory_coordinates: dict[str, tuple[int, int]] = {}
        self.original_territory_polygons: dict[str, list[tuple[int,int]]] = {}


    def _load_map_display_config(self, config_file: str):
        print(f"DEBUG: GameGUI._load_map_display_config - Attempting to load display config from '{config_file}' for game_mode '{self.game_mode}'.")
        try:
            with open(config_file, 'r') as f:
                content_for_debug = f.read()
                print(f"DEBUG: GameGUI._load_map_display_config - First 500 chars of '{config_file}':\n{content_for_debug[:500]}...")
                f.seek(0) # Reset file pointer to read JSON
                display_data = json.load(f)

            if self.game_mode == "world_map":
                # Store raw loaded data into original_* attributes
                self.original_territory_polygons = display_data.get("territory_polygons", {})
                self.original_territory_coordinates = display_data.get("territory_centroids", {})

                # self.territory_polygons and self.territory_coordinates will be updated by _apply_zoom_and_pan
                # For initial load, we can copy them or let the first draw call populate them.
                # It's safer to initialize them here.
                self.territory_polygons = self.original_territory_polygons.copy()
                self.territory_coordinates = self.original_territory_coordinates.copy()


                print(f"DEBUG: GameGUI._load_map_display_config - Loaded for 'world_map'.")
                print(f"DEBUG: GameGUI._load_map_display_config - Number of original polygon entries: {len(self.original_territory_polygons)}")
                print(f"DEBUG: GameGUI._load_map_display_config - Number of original centroid entries: {len(self.original_territory_coordinates)}")

                if not isinstance(self.original_territory_polygons, dict) or not isinstance(self.original_territory_coordinates, dict):
                    print(f"DEBUG: GameGUI._load_map_display_config - WARNING: World map display config '{config_file}' has unexpected structure. Creating dummy data.")
                    self._create_dummy_world_map_display_data(config_file) # This will populate original_ and current
                    return

                # Log a sample for verification
                if self.original_territory_polygons:
                    sample_terr_name = next(iter(self.original_territory_polygons))
                    print(f"DEBUG: GameGUI._load_map_display_config - Sample original polygon for '{sample_terr_name}': {str(self.original_territory_polygons[sample_terr_name])[:200]}...")
                if self.original_territory_coordinates:
                    sample_cent_name = next(iter(self.original_territory_coordinates))
                    print(f"DEBUG: GameGUI._load_map_display_config - Sample original centroid for '{sample_cent_name}': {self.original_territory_coordinates[sample_cent_name]}")

                valid_polygons_format = True
                for name, poly_parts in self.original_territory_polygons.items():
                    if not isinstance(poly_parts, list): valid_polygons_format = False; break
                    for part in poly_parts:
                        if not isinstance(part, list) or not all(isinstance(pt, (list, tuple)) and len(pt) == 2 and all(isinstance(coord_val, (int, float)) for coord_val in pt) for pt in part):
                            valid_polygons_format = False; print(f"DEBUG: Format error in polygon part for {name}: {part}"); break
                    if not valid_polygons_format: break

                valid_centroids_format = all(isinstance(coord, (list, tuple)) and len(coord) == 2 and all(isinstance(val, (int, float)) for val in coord) for coord in self.original_territory_coordinates.values())

                if not valid_polygons_format:
                    print(f"DEBUG: GameGUI._load_map_display_config - WARNING: Polygon data format error in '{config_file}'.")
                if not valid_centroids_format:
                    print(f"DEBUG: GameGUI._load_map_display_config - WARNING: Centroid data format error in '{config_file}'.")

                if not valid_polygons_format or not valid_centroids_format:
                    print(f"DEBUG: GameGUI._load_map_display_config - Triggering dummy data due to format errors.")
                    self._create_dummy_world_map_display_data(config_file)
                    return

                if not self.original_territory_polygons and not self.original_territory_coordinates:
                    print(f"DEBUG: GameGUI._load_map_display_config - WARNING: World map display config '{config_file}' is empty. Creating dummy data.")
                    self._create_dummy_world_map_display_data(config_file)

            else: # Standard mode
                self.original_territory_coordinates = display_data.copy() # Store original
                self.territory_coordinates = display_data # Current (will be transformed)
                print(f"DEBUG: GameGUI._load_map_display_config - Loaded for 'standard' mode. Number of original territories: {len(self.original_territory_coordinates)}")
                if not isinstance(self.original_territory_coordinates, dict):
                    print(f"Warning: Standard map display config '{config_file}' is not a dictionary. Creating dummy data.")
                    self._create_dummy_standard_map_coordinates(config_file) # This populates original_ and current
                    return
                print(f"Successfully loaded standard territory coordinates from '{config_file}'.")
                if not self.original_territory_coordinates:
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

        self.original_territory_coordinates = dummy_coords.copy()
        self.territory_coordinates = dummy_coords # Current will be transformed
        try:
            with open(config_file, 'w') as f: json.dump(self.original_territory_coordinates, f, indent=2) # Save original
            print(f"Created dummy standard map coordinates file '{config_file}'.")
        except IOError: print(f"Could not write dummy standard map coords to '{config_file}'.")

    def _create_dummy_world_map_display_data(self, config_file: str):
        if not self.engine.game_state.territories: return
        dummy_centroids = {}
        dummy_polygons = {}
        x_offset, y_offset = 50, 50

        territory_names = list(self.engine.game_state.territories.keys())
        if not territory_names:
            print("GUI: No territories in engine to create dummy world map display data. Config will be empty.")

        for i, name in enumerate(territory_names):
            cx_orig, cy_orig = (x_offset + (i % 8) * 100, y_offset + (i // 8) * 70)
            dummy_centroids[name] = (cx_orig, cy_orig)
            dummy_polygons[name] = [[(cx_orig-10, cy_orig-10), (cx_orig+10, cy_orig-10), (cx_orig+10, cy_orig+10), (cx_orig-10, cy_orig+10)]] # Polygon parts are lists of lists

        self.original_territory_coordinates = dummy_centroids.copy()
        self.territory_coordinates = dummy_centroids # Current
        self.original_territory_polygons = dummy_polygons.copy()
        self.territory_polygons = dummy_polygons # Current

        data_to_save = {
            "territory_centroids": self.original_territory_coordinates, # Save original
            "territory_polygons": self.original_territory_polygons # Save original
        }
        try:
            with open(config_file, 'w') as f: json.dump(data_to_save, f, indent=2)
            print(f"Created dummy world map display data file '{config_file}'.")
        except IOError: print(f"Could not write dummy world map display data to '{config_file}'.")

    def _apply_zoom_and_pan(self):
        """
        Recalculates self.territory_coordinates and self.territory_polygons
        based on self.original_*, self.map_zoom, self.map_offset_x, self.map_offset_y.
        This should be called after zoom or pan changes, before drawing the map.
        """
        # Get the center of the map area, which will be the zoom focus point
        map_center_x = MAP_AREA_WIDTH / 2
        map_center_y = SCREEN_HEIGHT / 2 # Assuming map takes full screen height for now for simplicity

        # Apply to centroids (self.territory_coordinates)
        self.territory_coordinates = {}
        for name, (orig_x, orig_y) in self.original_territory_coordinates.items():
            # Translate to map_center as origin, scale, then translate back, then apply pan
            scaled_x = (orig_x - map_center_x) * self.map_zoom + map_center_x + self.map_offset_x
            scaled_y = (orig_y - map_center_y) * self.map_zoom + map_center_y + self.map_offset_y
            self.territory_coordinates[name] = (int(scaled_x), int(scaled_y))

        # Apply to polygons (self.territory_polygons)
        self.territory_polygons = {}
        if hasattr(self, 'original_territory_polygons'): # Check if it exists (for standard mode)
            for name, list_of_orig_polygon_parts in self.original_territory_polygons.items():
                scaled_polygon_parts = []
                for orig_polygon_part in list_of_orig_polygon_parts:
                    scaled_part = []
                    for orig_px, orig_py in orig_polygon_part:
                        scaled_px = (orig_px - map_center_x) * self.map_zoom + map_center_x + self.map_offset_x
                        scaled_py = (orig_py - map_center_y) * self.map_zoom + map_center_y + self.map_offset_y
                        scaled_part.append((int(scaled_px), int(scaled_py)))
                    scaled_polygon_parts.append(scaled_part)
                self.territory_polygons[name] = scaled_polygon_parts
        # print(f"DEBUG: Applied zoom {self.map_zoom}, offset ({self.map_offset_x}, {self.map_offset_y})")


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
            pygame.draw.circle(self.screen, BLACK, coords, 20, 2) # Keep border for circles

            # Army count text (centered on circle)
            army_text_color = TEXT_COLOR_LIGHT if sum(owner_color) < 384 else TEXT_COLOR_DARK # Light on dark, dark on light
            army_text_surf = self.font.render(str(territory_obj.army_count), True, army_text_color)
            army_text_rect = army_text_surf.get_rect(center=coords)
            self.screen.blit(army_text_surf, army_text_rect)

            # Territory name text (below circle)
            name_surf = self.font.render(terr_name, True, TEXT_COLOR_LIGHT)
            name_rect = name_surf.get_rect(center=(coords[0], coords[1] - 35)) # Adjusted offset

            # Semi-transparent background for name text
            name_bg_surface = pygame.Surface(name_rect.inflate(6, 4).size, pygame.SRCALPHA)
            name_bg_surface.fill((*PANEL_BG_COLOR, 180)) # PANEL_BG_COLOR with alpha
            self.screen.blit(name_bg_surface, name_rect.inflate(6,4).topleft)

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
                # Army count text with semi-transparent background
                army_text_color = TEXT_COLOR_LIGHT if sum(owner_color) < 384 else TEXT_COLOR_DARK
                army_text_surf = self.font.render(str(territory_obj.army_count), True, army_text_color)
                army_text_rect = army_text_surf.get_rect(center=screen_centroid_coords)

                army_bg_surface = pygame.Surface(army_text_rect.inflate(8, 4).size, pygame.SRCALPHA)
                # Use owner's color for bg, but make it more transparent
                bg_owner_color_with_alpha = (*owner_color[:3], 180) if len(owner_color) == 3 else (*owner_color[:3], owner_color[3] * 0.7 if len(owner_color) == 4 else 180) # handle if owner_color already has alpha
                army_bg_surface.fill(bg_owner_color_with_alpha)
                self.screen.blit(army_bg_surface, army_text_rect.inflate(8,4).topleft)
                pygame.draw.rect(self.screen, PANEL_BORDER_COLOR, army_text_rect.inflate(8,4), 1, border_radius=3) # Thin border for army count
                self.screen.blit(army_text_surf, army_text_rect)

                # Territory name text (offset below centroid) with semi-transparent background
                name_font_size_adjust = max(0, int(5 - self.map_zoom * 5)) # Smaller font for name when zoomed out
                current_name_font = pygame.font.SysFont(None, STANDARD_FONT_SIZE - name_font_size_adjust)

                name_surf = current_name_font.render(terr_name, True, TEXT_COLOR_LIGHT)
                name_rect = name_surf.get_rect(center=(screen_centroid_coords[0], screen_centroid_coords[1] + 20 + (STANDARD_FONT_SIZE - name_font_size_adjust)/2)) # Adjusted offset

                name_bg_surface = pygame.Surface(name_rect.inflate(6, 4).size, pygame.SRCALPHA)
                name_bg_surface.fill((*PANEL_BG_COLOR, 180)) # PANEL_BG_COLOR with alpha
                self.screen.blit(name_bg_surface, name_rect.inflate(6,4).topleft)
                self.screen.blit(name_surf, name_rect)


    def draw_player_info_panel(self, game_state: GameState):
        panel_rect = pygame.Rect(MAP_AREA_WIDTH, SCREEN_HEIGHT - PLAYER_INFO_PANEL_HEIGHT, SIDE_PANEL_WIDTH, PLAYER_INFO_PANEL_HEIGHT)
        pygame.draw.rect(self.screen, PANEL_BG_COLOR, panel_rect)
        pygame.draw.rect(self.screen, PANEL_BORDER_COLOR, panel_rect, 1)

        gs_to_draw = game_state
        if not gs_to_draw: gs_to_draw = getattr(self, 'current_game_state', self.engine.game_state)
        current_player = gs_to_draw.get_current_player()

        padding = 5
        line_spacing = self.info_font.get_linesize() + 2
        y_pos = panel_rect.y + padding

        if current_player:
            info_text = f"Turn: {gs_to_draw.current_turn_number} Player: {current_player.name} ({current_player.color})"
            info_surface = self.info_font.render(info_text, True, TEXT_COLOR_LIGHT)
            self.screen.blit(info_surface, (panel_rect.x + padding, y_pos))
            y_pos += line_spacing

            phase_text = f"Phase: {gs_to_draw.current_game_phase}"
            if self.orchestrator and self.orchestrator.ai_is_thinking and self.orchestrator.active_ai_player_name == current_player.name:
                phase_text += " (Thinking...)"

            cards_text = f"Cards: {len(current_player.hand)}, Deploy: {current_player.armies_to_deploy}"
            phase_surface = self.info_font.render(phase_text, True, TEXT_COLOR_LIGHT)
            self.screen.blit(phase_surface, (panel_rect.x + padding, y_pos))
            y_pos += line_spacing
            cards_surface = self.info_font.render(cards_text, True, TEXT_COLOR_LIGHT)
            self.screen.blit(cards_surface, (panel_rect.x + padding, y_pos))

        elif self.orchestrator and self.orchestrator.ai_is_thinking and self.orchestrator.active_ai_player_name:
            thinking_text = f"AI ({self.orchestrator.active_ai_player_name}) is thinking..."
            thinking_surface = self.info_font.render(thinking_text, True, YELLOW) # Yellow for emphasis
            self.screen.blit(thinking_surface, (panel_rect.x + padding, y_pos))


    def draw_action_log_panel(self):
        # Action Log is at the top of the side panel
        panel_rect = pygame.Rect(MAP_AREA_WIDTH, 0, SIDE_PANEL_WIDTH, ACTION_LOG_HEIGHT)
        pygame.draw.rect(self.screen, PANEL_BG_COLOR, panel_rect)
        pygame.draw.rect(self.screen, PANEL_BORDER_COLOR, panel_rect, 1)

        title_text_surface = self.large_font.render("Action Log", True, TEXT_COLOR_HEADER)
        title_rect = title_text_surface.get_rect(topleft=(panel_rect.x + 10, panel_rect.y + 5))
        self.screen.blit(title_text_surface, title_rect)

        y_offset = title_rect.bottom + 5 # Start entries below title
        line_height = self.font.get_linesize()
        max_entries = (panel_rect.height - y_offset - 5) // line_height # Calculate how many entries fit

        for i, log_entry in enumerate(reversed(self.action_log[-max_entries:])):
            entry_surface = self.font.render(log_entry, True, TEXT_COLOR_MEDIUM)
            self.screen.blit(entry_surface, (panel_rect.x + 10, y_offset + i * line_height))

    def _render_text_wrapped(self, surface, text, rect, font, color):
        # Ensure there's a minimum height for rendering, e.g., one line_height + padding
        min_render_height = font.get_linesize() + 10
        if rect.height < min_render_height:
            # Not enough space to render anything meaningful, or could render ellipsis.
            # For now, just skip if too small to avoid issues.
            # print(f"Warning: Text wrap rect too small. Height: {rect.height}, Min: {min_render_height}")
            return

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
        # pygame.draw.rect(self.screen, DARK_GREY, tab_bar_rect) # No separate bar bg, tabs fill it

        tab_rects_dict = getattr(self, tab_rects_dict_name)
        tab_rects_dict.clear()

        padding_x = 5 # Padding on left/right of tab bar
        gap_between_tabs = 2
        available_width_for_tabs = SIDE_PANEL_WIDTH - (2 * padding_x)

        current_x = MAP_AREA_WIDTH + padding_x

        # Calculate tab width: distribute available space, or use text width if enough space
        num_tabs = len(tab_options) if tab_options else 1
        calculated_tab_width = (available_width_for_tabs - (num_tabs - 1) * gap_between_tabs) / num_tabs
        calculated_tab_width = max(calculated_tab_width, 50) # Minimum tab width


        for option_name in tab_options:
            # Use a slightly lighter text color for active tab for better contrast
            is_active = getattr(self, active_tab_var_name) == option_name
            text_color = TEXT_COLOR_LIGHT if is_active else TEXT_COLOR_MEDIUM

            # Truncate text if it's too long for the tab
            # Estimate max chars based on tab_width and font size (approx)
            avg_char_width = self.tab_font.size("a")[0]
            max_chars = int((calculated_tab_width - 10) / avg_char_width) if avg_char_width > 0 else 10
            display_name = option_name
            if len(option_name) > max_chars and max_chars > 3:
                display_name = option_name[:max_chars-3] + "..."

            text_surface = self.tab_font.render(display_name, True, text_color)
            text_width, text_height = text_surface.get_size()

            # Ensure actual tab width isn't smaller than text
            actual_tab_width = max(calculated_tab_width, text_width + 10)

            tab_rect = pygame.Rect(current_x, base_y_offset, actual_tab_width, TAB_HEIGHT)
            tab_bg_color = ACTIVE_TAB_BG if is_active else INACTIVE_TAB_BG

            pygame.draw.rect(self.screen, tab_bg_color, tab_rect, border_top_left_radius=5, border_top_right_radius=5)
            # pygame.draw.rect(self.screen, PANEL_BORDER_COLOR, tab_rect, 1, border_top_left_radius=5, border_top_right_radius=5) # Border

            # Center text in tab
            text_x = tab_rect.x + (actual_tab_width - text_width) // 2
            text_y = tab_rect.y + (TAB_HEIGHT - text_height) // 2
            self.screen.blit(text_surface, (text_x, text_y))

            tab_rects_dict[option_name] = tab_rect

            if mouse_click_pos and tab_rect.collidepoint(mouse_click_pos):
                setattr(self, active_tab_var_name, option_name)
                # print(f"GUI: Switched {panel_title} tab to {option_name}") # Keep for debug if needed

            current_x += actual_tab_width + gap_between_tabs

        # Draw a line under the tabs to connect to the panel below
        line_y = base_y_offset + TAB_HEIGHT -1 # -1 to overlap with panel border
        pygame.draw.line(self.screen, PANEL_BORDER_COLOR, (MAP_AREA_WIDTH, line_y), (SCREEN_WIDTH, line_y), 1)

        return base_y_offset + TAB_HEIGHT


    def draw_ai_thought_panel(self, mouse_click_pos: tuple[int, int] | None):
        # AI Thought panel is below Action Log
        base_y = ACTION_LOG_HEIGHT
        tab_options = self.player_names_for_tabs
        if not self.active_tab_thought_panel and tab_options:
            self.active_tab_thought_panel = tab_options[0]

        content_y_start = self.draw_tabs(base_y, "AI Thoughts", tab_options, "active_tab_thought_panel", "thought_tab_rects", mouse_click_pos)

        # Panel for the content of the thoughts
        panel_rect = pygame.Rect(MAP_AREA_WIDTH, content_y_start, SIDE_PANEL_WIDTH, THOUGHT_PANEL_HEIGHT - TAB_HEIGHT)
        pygame.draw.rect(self.screen, PANEL_BG_COLOR, panel_rect)
        pygame.draw.rect(self.screen, PANEL_BORDER_COLOR, panel_rect, 1) # Border for the content area

        player_to_show = self.active_tab_thought_panel
        current_thoughts_map = self.ai_thoughts

        if player_to_show and player_to_show in current_thoughts_map:
            thought = current_thoughts_map[player_to_show]
            self._render_text_wrapped(self.screen, thought, panel_rect.inflate(-10, -10), self.font, TEXT_COLOR_LIGHT) # Padding for text
        else:
            no_thought_text_str = f"No thoughts for {player_to_show if player_to_show else 'N/A'}."
            no_thought_text = self.font.render(no_thought_text_str, True, TEXT_COLOR_DARK)
            text_rect = no_thought_text.get_rect(center=panel_rect.center)
            self.screen.blit(no_thought_text, text_rect)

    def draw_chat_panel(self, mouse_click_pos: tuple[int, int] | None):
        # Chat panel is below AI Thought panel
        base_y = ACTION_LOG_HEIGHT + THOUGHT_PANEL_HEIGHT

        chat_tab_options = ["global"] + list(getattr(self, 'private_chat_conversations_map', {}).keys())
        content_y_start = self.draw_tabs(base_y, "Chat", chat_tab_options, "active_tab_chat_panel", "chat_tab_rects", mouse_click_pos)

        panel_rect = pygame.Rect(MAP_AREA_WIDTH, content_y_start, SIDE_PANEL_WIDTH, CHAT_PANEL_HEIGHT - TAB_HEIGHT)
        pygame.draw.rect(self.screen, PANEL_BG_COLOR, panel_rect)
        pygame.draw.rect(self.screen, PANEL_BORDER_COLOR, panel_rect, 1)

        messages_to_render = []
        active_chat_key = self.active_tab_chat_panel

        if active_chat_key == "global":
            messages_to_render = getattr(self, 'global_chat_messages', [])
        else:
            all_private_chats = getattr(self, 'private_chat_conversations_map', {})
            messages_to_render = all_private_chats.get(active_chat_key, [])

        padding = 5
        y_render_offset = panel_rect.y + padding
        line_height = self.font.get_linesize()
        max_messages_to_show = (panel_rect.height - (2 * padding)) // line_height

        # Display latest messages at the bottom, so iterate through relevant slice of messages
        start_index = max(0, len(messages_to_render) - max_messages_to_show)

        for msg_data in messages_to_render[start_index:]:
            sender = msg_data.get('sender','System')
            message = msg_data.get('message','')
            msg_str = f"{sender}: {message}"

            # Simple wrap for chat messages manually if too long
            # This is a very basic wrap, could be improved with _render_text_wrapped if complex formatting is needed
            max_chars_line = (panel_rect.width - (2*padding)) // (self.font.size("a")[0] if self.font.size("a")[0] > 0 else 1)

            lines_for_message = []
            current_line_msg = ""
            for word in msg_str.split(" "):
                if self.font.size(current_line_msg + word + " ")[0] < (panel_rect.width - (2*padding)):
                    current_line_msg += word + " "
                else:
                    lines_for_message.append(current_line_msg)
                    current_line_msg = word + " "
            lines_for_message.append(current_line_msg)


            for line_text in lines_for_message:
                if y_render_offset + line_height > panel_rect.bottom - padding: break # Check bounds
                msg_surface = self.font.render(line_text.strip(), True, TEXT_COLOR_LIGHT)
                self.screen.blit(msg_surface, (panel_rect.x + padding, y_render_offset))
                y_render_offset += line_height
            if y_render_offset + line_height > panel_rect.bottom - padding: break


        if not messages_to_render:
            no_chat_text_str = f"No messages in '{active_chat_key}'."
            no_chat_text = self.font.render(no_chat_text_str, True, TEXT_COLOR_DARK)
            text_rect = no_chat_text.get_rect(center=panel_rect.center)
            self.screen.blit(no_chat_text, text_rect)


    def log_action(self, action_string: str):
        self.action_log.append(action_string)
        if len(self.action_log) > 50: self.action_log.pop(0)

    def update_thought_panel(self, player_name: str, thought: str):
        self.ai_thoughts[player_name] = thought
        # Optionally, immediately switch to this player's thought tab:
        if player_name in self.player_names_for_tabs:
           self.active_tab_thought_panel = player_name

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
        needs_redraw = True # Flag to redraw map only when necessary (e.g. after pan/zoom)

        # Ensure player_names_for_tabs is initialized if game state is available
        if self.current_game_state and self.current_game_state.players:
             self.player_names_for_tabs = [p.name for p in self.current_game_state.players]
             if not self.active_tab_thought_panel and self.player_names_for_tabs:
                 self.active_tab_thought_panel = self.player_names_for_tabs[0]

        self._apply_zoom_and_pan() # Initial application of zoom/pan

        while self.running:
            mouse_click_pos = None # Reset for tab clicks etc.

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                # --- Map Panning Logic ---
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    # Check if click is within map area for panning or other map interactions
                    if event.pos[0] < MAP_AREA_WIDTH:
                        if event.button == 1: # Left click to start panning
                            self.is_panning = True
                            self.pan_start_pos = event.pos
                        # Zoom with mouse wheel
                        elif event.button == 4: # Scroll up / Zoom in
                            old_zoom = self.map_zoom
                            self.map_zoom = min(self.max_zoom, self.map_zoom + self.zoom_step)
                            if old_zoom != self.map_zoom: needs_redraw = True
                        elif event.button == 5: # Scroll down / Zoom out
                            old_zoom = self.map_zoom
                            self.map_zoom = max(self.min_zoom, self.map_zoom - self.zoom_step)
                            if old_zoom != self.map_zoom: needs_redraw = True
                    else: # Click is in the side panel
                         if event.button == 1:
                            mouse_click_pos = event.pos # For tab clicks

                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1: # Left click release
                        self.is_panning = False

                elif event.type == pygame.MOUSEMOTION:
                    if self.is_panning:
                        dx = event.pos[0] - self.pan_start_pos[0]
                        dy = event.pos[1] - self.pan_start_pos[1]
                        self.map_offset_x += dx
                        self.map_offset_y += dy
                        self.pan_start_pos = event.pos
                        needs_redraw = True

            if needs_redraw:
                self._apply_zoom_and_pan()


            # --- Game Logic Advancement ---
            # This should ideally be decoupled from rendering framerate
            # For now, advance_game_turn also handles GUI updates from orchestrator
            if self.orchestrator and self.running:
                if not self.orchestrator.advance_game_turn(): # This call might update game_state and logs
                    self.running = False
                # If advance_game_turn caused a state change, we likely need a full redraw
                # This is implicitly handled as draw calls happen every frame currently.
                # More sophisticated state change detection could optimize this.

            # --- Drawing ---
            self.screen.fill(PANEL_BG_COLOR) # Fill entire screen with a base color

            gs_to_draw = getattr(self, 'current_game_state', self.engine.game_state)

            # Draw map (always, or only if needs_redraw or game state changed)
            self.draw_map(gs_to_draw)

            # Draw side panels
            self.draw_action_log_panel()
            self.draw_ai_thought_panel(mouse_click_pos)
            self.draw_chat_panel(mouse_click_pos)
            self.draw_player_info_panel(gs_to_draw)

            pygame.display.flip()
            needs_redraw = False # Reset redraw flag after drawing
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
