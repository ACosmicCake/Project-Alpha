import pygame
from ..game_engine.engine import GameEngine
from ..game_engine.data_structures import GameState, Territory, Player as GamePlayer

import json
import os

# --- New Aesthetic Color Palette ---
BACKGROUND_COLOR = (48, 135, 179)      # Dark, desaturated slate blue for map background/ocean
PANEL_BACKGROUND_COLOR = (40, 44, 48) # Slightly lighter dark grey for side panels
TEXT_COLOR = (220, 220, 220)        # Off-white for general text
TEXT_COLOR_MUTED = (160, 160, 160)    # Medium grey for less important text/logs
TEXT_COLOR_HEADER = (230, 230, 230)   # Slightly brighter for headers
BORDER_COLOR = (60, 66, 72)          # Subtle border for panels and elements
BORDER_COLOR_LIGHT = (80, 88, 96)     # Lighter border for emphasis if needed

ACCENT_COLOR_PRIMARY = (0, 180, 180)    # Vibrant Teal/Cyan for active tabs, highlights
ACCENT_COLOR_SECONDARY = (0, 130, 130)  # Darker Teal for inactive tabs or secondary highlights
ACCENT_COLOR_ATTENTION = (255, 100, 100) # For alerts or important warnings (e.g. must_trade)

# Standard Colors (some might be replaced by theme colors)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (220, 50, 50) # Adjusted Red for better harmony
GREEN = (50, 200, 50) # Adjusted Green
BLUE = (50, 100, 220) # Adjusted Blue
YELLOW = (220, 200, 50) # Adjusted Yellow

# Old color names mapped to new theme (or kept if distinct)
OCEAN_BLUE = BACKGROUND_COLOR # Map background is now the main background
DARK_GREY_OLD = (50, 50, 50) # Keep for reference if needed during transition
LIGHT_GREY_OLD = (200, 200, 200) # Keep for reference
GREY_OLD = (128, 128, 128)

# Continent Colors (can be refined based on new palette)
# For now, let's make them slightly desaturated or themed if map is dark
CONTINENT_COLORS = {
    "North America": (100, 90, 80),   # Muted brown/tan
    "Asia": (80, 100, 80),      # Muted green
    "Europe": (80, 80, 100),    # Muted blue/purple
    "South America": (110, 100, 70), # Muted orange/yellow
    "Africa": (120, 110, 90),   # Muted darker tan
    "Australia": (70, 110, 110), # Muted teal/blue-green
    "Default": (75, 75, 75)     # Fallback continent color (darker grey)
}
ADJACENCY_LINE_COLOR = (80, 88, 96) # Use a lighter border color for lines on dark map

DEFAULT_PLAYER_COLORS = {
    "Red": RED, "Blue": BLUE, "Green": GREEN, "Yellow": YELLOW,
    "Purple": (160, 70, 160), "Orange": (255, 140, 0),
    "Pink": (230, 100, 180), "Cyan": (70, 200, 200)
    # Black/White player colors might be problematic on a dark theme.
    # Consider replacing them or ensuring high contrast outlines.
}
# Ensure BLACK and WHITE are available if used by player colors explicitly
DEFAULT_PLAYER_COLORS["Black"] = (20,20,20) # Very dark grey instead of pure black for player
DEFAULT_PLAYER_COLORS["White"] = (230,230,230) # Off-white for player

SCREEN_WIDTH = 1600
SCREEN_HEIGHT = 800
MAP_AREA_WIDTH = 1200 # Adjusted for 1600x900
SIDE_PANEL_WIDTH = SCREEN_WIDTH - MAP_AREA_WIDTH # Will be 600
PLAYER_INFO_PANEL_HEIGHT = 50 # Adjusted
ACTION_LOG_HEIGHT = 150 # Adjusted
THOUGHT_PANEL_HEIGHT = 300 # Adjusted
CHAT_PANEL_HEIGHT = SCREEN_HEIGHT - ACTION_LOG_HEIGHT - THOUGHT_PANEL_HEIGHT - PLAYER_INFO_PANEL_HEIGHT -50 # Adjusted for new screen height

TAB_HEIGHT = 30
TAB_FONT_SIZE = 15


class GameGUI:
    def __init__(self, engine: GameEngine, orchestrator, map_display_config_file: str = "map_display_config.json", game_mode: str = "standard"): # Added parameters
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(f"LLM Risk Game - {game_mode.replace('_', ' ').title()} Mode") # Update caption

        # Attempt to use a more common, aesthetically pleasing sans-serif font
        common_sans_serif_fonts = "Arial, Helvetica, Calibri, Liberation Sans, DejaVu Sans"
        try:
            self.font = pygame.font.SysFont(common_sans_serif_fonts, 15) # Reduced size
            self.large_font = pygame.font.SysFont(common_sans_serif_fonts, 20) # Reduced size
            self.tab_font = pygame.font.SysFont(common_sans_serif_fonts, TAB_FONT_SIZE) # Remains 20
            # print(f"Successfully loaded system font.") # Simpler print
        except pygame.error:
            print(f"Warning: Could not find specified system fonts ({common_sans_serif_fonts}). Falling back to default.")
            self.font = pygame.font.SysFont(None, 15) # Reduced size
            self.large_font = pygame.font.SysFont(None, 20) # Reduced size
            self.tab_font = pygame.font.SysFont(None, TAB_FONT_SIZE)

        self.ocean_color = OCEAN_BLUE # OCEAN_BLUE is now mapped to BACKGROUND_COLOR
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

        # Camera and panning attributes
        self.camera_offset_x = 0
        self.camera_offset_y = 0
        self.panning_active = False
        self.last_mouse_pos = None

        # Zoom attributes
        self.zoom_level = 1.0
        self.min_zoom = 0.2
        self.max_zoom = 10.0  # Increased max zoom level
        self.zoom_increment = 0.1

    def _load_map_display_config(self, config_file: str):
        print(f"DEBUG: GameGUI._load_map_display_config - Attempting to load display config from '{config_file}' for game_mode '{self.game_mode}'.")
        try:
            with open(config_file, 'r') as f:

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
            coords1_orig = self.territory_coordinates.get(terr_name)
            if not coords1_orig: continue
            # Apply zoom and offset
            screen_x1 = (coords1_orig[0] * self.zoom_level) + self.camera_offset_x
            screen_y1 = (coords1_orig[1] * self.zoom_level) + self.camera_offset_y
            coords1 = (screen_x1, screen_y1)

            for adj_info in territory_obj.adjacent_territories:
                # adj_info is expected to be a dict like {'name': 'TerritoryName', 'type': 'land'}
                # as per engine.py loading logic.
                if not isinstance(adj_info, dict) or "name" not in adj_info:
                    # Fallback or warning if structure is not as expected
                    # This might happen if old data structures are mixed in or error in loading
                    if hasattr(adj_info, 'name'): # Check if it's an actual Territory object (legacy)
                        adj_name = adj_info.name
                        # print(f"DEBUG: adj_info for {terr_name} was Territory object: {adj_name}")
                    else:
                        # print(f"DEBUG: Skipping malformed adj_info: {adj_info} for {terr_name} in _draw_standard_map_circles")
                        continue
                else:
                    adj_name = adj_info["name"]

                adj_pair = tuple(sorted((terr_name, adj_name)))
                if adj_pair in drawn_adjacencies: continue
                coords2_orig = self.territory_coordinates.get(adj_name)
                if not coords2_orig: continue
                # Apply zoom and offset
                screen_x2 = (coords2_orig[0] * self.zoom_level) + self.camera_offset_x
                screen_y2 = (coords2_orig[1] * self.zoom_level) + self.camera_offset_y
                coords2 = (screen_x2, screen_y2)
                pygame.draw.line(self.screen, ADJACENCY_LINE_COLOR, coords1, coords2, 2)
                drawn_adjacencies.add(adj_pair)

        for terr_name, territory_obj in gs_to_draw.territories.items():
            coords_orig = self.territory_coordinates.get(terr_name)
            if not coords_orig: continue
            # Apply zoom and offset
            screen_x = (coords_orig[0] * self.zoom_level) + self.camera_offset_x
            screen_y = (coords_orig[1] * self.zoom_level) + self.camera_offset_y
            coords = (screen_x, screen_y)

            radius = max(5, int(20 * self.zoom_level)) # Scale radius, with a minimum size

            owner_color = DEFAULT_PLAYER_COLORS.get("Default", (75,75,75)) # Use new default from palette
            if territory_obj.owner and territory_obj.owner.color:
                owner_color = DEFAULT_PLAYER_COLORS.get(territory_obj.owner.color, owner_color)

            pygame.draw.circle(self.screen, owner_color, coords, radius)
            pygame.draw.circle(self.screen, BORDER_COLOR, coords, radius, 2) # Use theme BORDER_COLOR

            # Determine text color based on luminance of owner_color for better readability
            luminance = 0.299 * owner_color[0] + 0.587 * owner_color[1] + 0.114 * owner_color[2]
            army_text_color = TEXT_COLOR if luminance < 140 else PANEL_BACKGROUND_COLOR # Adjusted threshold

            army_text = self.font.render(str(territory_obj.army_count), True, army_text_color)
            if self.zoom_level >= 0.25: # Lowered threshold
                self.screen.blit(army_text, army_text.get_rect(center=coords))

            if self.zoom_level >= 0.2: # Lowered threshold
                name_surf = self.font.render(terr_name, True, TEXT_COLOR) # Use theme TEXT_COLOR
                name_rect_center_x = coords[0]
                # Ensure name is offset reasonably, especially when zoomed out
                scaled_offset = int(radius * 1.5) # Offset based on current circle radius
                name_rect_center_y = coords[1] - max(int(15 * self.zoom_level), scaled_offset)


                name_rect = name_surf.get_rect(center=(name_rect_center_x, name_rect_center_y))

                # Background for territory name for readability
                name_bg_rect = name_rect.inflate(6, 4)
                # Create a temporary surface for transparency
                temp_surface = pygame.Surface(name_bg_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(temp_surface, PANEL_BACKGROUND_COLOR + (220,), temp_surface.get_rect(), border_radius=4) # Panel bg with alpha
                self.screen.blit(temp_surface, name_bg_rect.topleft)
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


        if not self.territory_polygons:
            print("DEBUG: GameGUI._draw_world_map_polygons - self.territory_polygons is empty. Cannot draw polygons.")
            # Potentially draw circles as a fallback if centroids exist? Or just the error message.
            # For now, if no polygons, it will just draw adjacency lines and then text if centroids exist.
            # This might be a reason why circles appear if this path is hit and then standard drawing is later invoked.

        # Adjacency lines for world map (can be complex, for now use centroids if polygons are too complex for simple line drawing)
        drawn_adjacencies = set()
        for terr_name_adj, territory_obj_adj in gs_to_draw.territories.items(): # Use different var names to avoid clash
            coords1_orig = self.territory_coordinates.get(terr_name_adj) # Use centroid for line start/end
            if not coords1_orig:
                continue
            # Apply zoom and offset
            screen_x1 = (coords1_orig[0] * self.zoom_level) + self.camera_offset_x
            screen_y1 = (coords1_orig[1] * self.zoom_level) + self.camera_offset_y
            coords1 = (screen_x1, screen_y1)

            # territory_obj_adj.adjacent_territories is now a list of dicts
            for adj_info in territory_obj_adj.adjacent_territories:
                if not (isinstance(adj_info, dict) and "name" in adj_info):
                    # print(f"DEBUG: Skipping malformed adj_info: {adj_info} for {terr_name_adj}")
                    continue

                adj_name = adj_info["name"]
                adj_type = adj_info.get("type", "unknown") # Get type for potential different line styles

                adj_pair = tuple(sorted((terr_name_adj, adj_name)))
                if adj_pair in drawn_adjacencies: continue

                coords2_orig = self.territory_coordinates.get(adj_name)
                if not coords2_orig:
                    # print(f"DEBUG: Centroid not found for adjacent territory {adj_name} of {terr_name_adj}")
                    continue

                # Apply zoom and offset
                screen_x2 = (coords2_orig[0] * self.zoom_level) + self.camera_offset_x
                screen_y2 = (coords2_orig[1] * self.zoom_level) + self.camera_offset_y
                coords2 = (screen_x2, screen_y2)

                line_color = ADJACENCY_LINE_COLOR
                line_thickness = 1
                # Example: differentiate line types (optional)
                if adj_type == "sea":
                    line_color = (100, 100, 200) # Light blue for sea routes
                    line_thickness = 1
                elif adj_type == "air":
                    line_color = (150, 150, 150) # Light grey for air routes
                    line_thickness = 1
                    # Could also draw dashed lines for air, but that's more complex with pygame.draw.line

                pygame.draw.line(self.screen, line_color, coords1, coords2, line_thickness)
                drawn_adjacencies.add(adj_pair)

        # --- First Pass: Draw all territory polygons and their borders ---
        for terr_name, territory_obj in gs_to_draw.territories.items():
            list_of_original_polygon_points = self.territory_polygons.get(terr_name)
            original_centroid_coords = self.territory_coordinates.get(terr_name) # Needed for fallback circle

            owner_color = DEFAULT_PLAYER_COLORS.get("Default", (75,75,75))
            if territory_obj.owner and territory_obj.owner.color:
                owner_color = DEFAULT_PLAYER_COLORS.get(territory_obj.owner.color, owner_color)

            if list_of_original_polygon_points:
                for i, original_polygon_part_points in enumerate(list_of_original_polygon_points):
                    if original_polygon_part_points and len(original_polygon_part_points) >= 3:
                        screen_polygon_part_points = [
                            ( (pt[0] * self.zoom_level) + self.camera_offset_x,
                              (pt[1] * self.zoom_level) + self.camera_offset_y)
                            for pt in original_polygon_part_points
                        ]
                        try:
                            pygame.draw.polygon(self.screen, owner_color, screen_polygon_part_points)
                            pygame.draw.polygon(self.screen, BORDER_COLOR, screen_polygon_part_points, 1) # Use theme BORDER_COLOR
                        except TypeError as e:
                            print(f"DEBUG: GameGUI._draw_world_map_polygons - Error drawing polygon part {i} for {terr_name}: {e}.")
                            if original_centroid_coords: # Use original_centroid_coords for fallback
                                screen_centroid_for_fallback = ( (original_centroid_coords[0] * self.zoom_level) + self.camera_offset_x,
                                                                 (original_centroid_coords[1] * self.zoom_level) + self.camera_offset_y )
                                pygame.draw.circle(self.screen, owner_color, screen_centroid_for_fallback, max(2, int(5 * self.zoom_level)), 0)
            elif original_centroid_coords: # If no polygons, but original_centroid_coords exists
                screen_centroid_for_fallback = ( (original_centroid_coords[0] * self.zoom_level) + self.camera_offset_x,
                                                 (original_centroid_coords[1] * self.zoom_level) + self.camera_offset_y )
                radius = max(3, int(10 * self.zoom_level))
                pygame.draw.circle(self.screen, owner_color, screen_centroid_for_fallback, radius)
                pygame.draw.circle(self.screen, BORDER_COLOR, screen_centroid_for_fallback, radius, 1) # Use theme BORDER_COLOR

        # --- Second Pass: Draw all text elements (army counts and names) ---
        # This ensures text is drawn on top of all polygons.
        for terr_name, territory_obj in gs_to_draw.territories.items():
            original_centroid_coords = self.territory_coordinates.get(terr_name)
            if not original_centroid_coords: # Skip if no centroid to place text
                continue

            screen_centroid_coords = ( (original_centroid_coords[0] * self.zoom_level) + self.camera_offset_x,
                                       (original_centroid_coords[1] * self.zoom_level) + self.camera_offset_y )

            owner_color = DEFAULT_PLAYER_COLORS.get("Default", (75,75,75))
            if territory_obj.owner and territory_obj.owner.color:
                owner_color = DEFAULT_PLAYER_COLORS.get(territory_obj.owner.color, owner_color)

            if screen_centroid_coords and self.zoom_level >= 0.25: # Lowered threshold & check screen_centroid_coords
                luminance = 0.299 * owner_color[0] + 0.587 * owner_color[1] + 0.114 * owner_color[2]
                army_text_color = TEXT_COLOR if luminance < 140 else PANEL_BACKGROUND_COLOR
                army_text = self.font.render(str(territory_obj.army_count), True, army_text_color)
                army_text_rect = army_text.get_rect(center=screen_centroid_coords)
                army_bg_rect = army_text_rect.inflate(6, 4)
                temp_surface_army = pygame.Surface(army_bg_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(temp_surface_army, PANEL_BACKGROUND_COLOR + (200,), temp_surface_army.get_rect(), border_radius=3)
                self.screen.blit(temp_surface_army, army_bg_rect.topleft)
                pygame.draw.rect(self.screen, BORDER_COLOR, army_bg_rect, 1, border_radius=3)
                self.screen.blit(army_text, army_text_rect)

                if self.zoom_level >= 0.2: # Lowered threshold
                    name_surf = self.font.render(terr_name, True, TEXT_COLOR)
                    name_rect_center_x = screen_centroid_coords[0]
                    scaled_offset = int(max(10, 15 * self.zoom_level))
                    name_rect_center_y = screen_centroid_coords[1] + scaled_offset
                    name_rect = name_surf.get_rect(center=(name_rect_center_x, name_rect_center_y))
                    name_bg_rect = name_rect.inflate(6, 4)
                    temp_surface_name = pygame.Surface(name_bg_rect.size, pygame.SRCALPHA)
                    pygame.draw.rect(temp_surface_name, PANEL_BACKGROUND_COLOR + (220,), temp_surface_name.get_rect(), border_radius=4)
                    self.screen.blit(temp_surface_name, name_bg_rect.topleft) # Draw background first
                    self.screen.blit(name_surf, name_rect) # Then text on top

    def _get_map_content_bounds(self) -> tuple[float, float, float, float] | None:
        """
        Calculates the bounding box of the map content in zoomed coordinates.
        Returns (min_x, min_y, max_x, max_y) or None if no territories.
        These coordinates are relative to a map origin (0,0) after zoom,
        BEFORE camera offset is applied.
        """
        if not self.current_game_state or not self.current_game_state.territories:
            return None

        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')

        has_elements = False

        if self.game_mode == "world_map" and self.territory_polygons:
            for terr_name in self.current_game_state.territories.keys():
                list_of_original_polygon_points = self.territory_polygons.get(terr_name)
                if list_of_original_polygon_points:
                    has_elements = True
                    for poly_part in list_of_original_polygon_points:
                        for pt_x, pt_y in poly_part:
                            zoomed_pt_x = pt_x * self.zoom_level
                            zoomed_pt_y = pt_y * self.zoom_level
                            min_x = min(min_x, zoomed_pt_x)
                            min_y = min(min_y, zoomed_pt_y)
                            max_x = max(max_x, zoomed_pt_x)
                            max_y = max(max_y, zoomed_pt_y)
        elif self.territory_coordinates: # Standard mode or fallback for world_map if no polygons
            # For circle map, bounds are based on circle centers and radii
            # Radius also needs to be scaled by zoom for accurate bounds.
            scaled_radius = max(5, int(20 * self.zoom_level))
            for terr_name in self.current_game_state.territories.keys():
                coords_orig = self.territory_coordinates.get(terr_name)
                if coords_orig:
                    has_elements = True
                    center_x_zoomed = coords_orig[0] * self.zoom_level
                    center_y_zoomed = coords_orig[1] * self.zoom_level
                    min_x = min(min_x, center_x_zoomed - scaled_radius)
                    min_y = min(min_y, center_y_zoomed - scaled_radius)
                    max_x = max(max_x, center_x_zoomed + scaled_radius)
                    max_y = max(max_y, center_y_zoomed + scaled_radius)

        if not has_elements:
            return None

        return min_x, min_y, max_x, max_y

    def draw_player_info_panel(self, game_state: GameState):
        panel_rect = pygame.Rect(MAP_AREA_WIDTH, SCREEN_HEIGHT - PLAYER_INFO_PANEL_HEIGHT, SIDE_PANEL_WIDTH, PLAYER_INFO_PANEL_HEIGHT)
        pygame.draw.rect(self.screen, PANEL_BACKGROUND_COLOR, panel_rect)
        pygame.draw.rect(self.screen, BORDER_COLOR, panel_rect, 1)

        gs_to_draw = game_state
        if not gs_to_draw: gs_to_draw = getattr(self, 'current_game_state', self.engine.game_state)
        current_player = gs_to_draw.get_current_player()
        padding = 10
        line_height = self.font.get_linesize() + 2
        y_pos = panel_rect.y + padding // 2

        if current_player:
            player_display_color = DEFAULT_PLAYER_COLORS.get(current_player.color, TEXT_COLOR_MUTED)
            info_text = f"Turn: {gs_to_draw.current_turn_number} | Player: {current_player.name}"
            info_surface = self.font.render(info_text, True, TEXT_COLOR)
            self.screen.blit(info_surface, (panel_rect.x + padding, y_pos))

            # Small colored rect next to player name
            color_rect_size = line_height - 4
            pygame.draw.rect(self.screen, player_display_color,
                             (panel_rect.x + padding + self.font.size(info_text)[0] + 5, y_pos + 2, color_rect_size, color_rect_size))

            y_pos += line_height

            phase_text_str = f"Phase: {gs_to_draw.current_game_phase}"
            phase_color = TEXT_COLOR
            if self.orchestrator and self.orchestrator.ai_is_thinking and self.orchestrator.active_ai_player_name == current_player.name:
                phase_text_str += " (Thinking...)"
                phase_color = ACCENT_COLOR_PRIMARY # Highlight thinking status

            phase_surface = self.font.render(phase_text_str, True, phase_color)
            self.screen.blit(phase_surface, (panel_rect.x + padding, y_pos))
            y_pos += line_height

            cards_text = f"Cards: {len(current_player.hand)} | Deploy: {current_player.armies_to_deploy}"
            cards_surface = self.font.render(cards_text, True, TEXT_COLOR)
            self.screen.blit(cards_surface, (panel_rect.x + padding, y_pos))

        elif self.orchestrator and self.orchestrator.ai_is_thinking and self.orchestrator.active_ai_player_name:
            thinking_text = f"AI ({self.orchestrator.active_ai_player_name}) is thinking..."
            thinking_surface = self.font.render(thinking_text, True, ACCENT_COLOR_ATTENTION) # Use attention color
            self.screen.blit(thinking_surface, (panel_rect.x + 5, y_pos))


    def draw_action_log_panel(self):
        panel_rect = pygame.Rect(MAP_AREA_WIDTH, 0, SIDE_PANEL_WIDTH, ACTION_LOG_HEIGHT)
        pygame.draw.rect(self.screen, PANEL_BACKGROUND_COLOR, panel_rect)
        pygame.draw.rect(self.screen, BORDER_COLOR, panel_rect, 1)

        padding = 10
        title_text = self.large_font.render("Action Log", True, TEXT_COLOR_HEADER)
        self.screen.blit(title_text, (panel_rect.x + padding, panel_rect.y + padding // 2))

        y_offset = title_text.get_height() + padding
        max_log_entries = (ACTION_LOG_HEIGHT - y_offset - padding //2 ) // (self.font.get_linesize() + 2)

        for i, log_entry in enumerate(reversed(self.action_log[-max_log_entries:])):
            entry_surface = self.font.render(log_entry[:55], True, TEXT_COLOR_MUTED) # Adjusted truncation
            self.screen.blit(entry_surface, (panel_rect.x + padding, panel_rect.y + y_offset + i * (self.font.get_linesize() + 2)))

    def _render_text_wrapped(self, surface, text, rect, font, color):
        words = text.split(' ')
        lines = []
        current_line = ""

        # Add a small line spacing factor
        line_spacing_factor = 1.1
        line_height = int(font.get_linesize() * line_spacing_factor)
        if line_height == 0: line_height = font.get_linesize() # Avoid division by zero if font size is tiny

        # Padding inside the already padded text_area_rect
        internal_padding = 2 # Small padding for top/left within the text_area_rect

        max_lines = (rect.height - internal_padding) // line_height

        for word in words:
            test_line = current_line + word + " "
            if font.size(test_line)[0] < (rect.width - 2 * internal_padding):
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word + " "
        lines.append(current_line)

        y = rect.y + internal_padding
        for i, line_text in enumerate(lines):
            if i >= max_lines:
                # Optional: Add a "..." if text is truncated due to max_lines
                if i > 0 and lines[i-1]: # Check if there was a previous line
                    prev_line_surf = font.render(lines[i-1].strip() + "...", True, color)
                    # Clear the previous line approximately
                    clear_rect = pygame.Rect(rect.x + internal_padding, y - line_height, rect.width - 2*internal_padding, line_height)
                    pygame.draw.rect(surface, PANEL_BACKGROUND_COLOR, clear_rect) # Fill with panel bg
                    surface.blit(prev_line_surf, (rect.x + internal_padding, y - line_height))
                break
            line_surface = font.render(line_text.strip(), True, color)
            surface.blit(line_surface, (rect.x + internal_padding, y))
            y += line_height

    def draw_tabs(self, base_y_offset: int, panel_title: str, tab_options: list[str], active_tab_var_name: str, tab_rects_dict_name: str, mouse_click_pos: tuple[int, int] | None):
        tab_bar_rect = pygame.Rect(MAP_AREA_WIDTH, base_y_offset, SIDE_PANEL_WIDTH, TAB_HEIGHT)
        # No separate background for tab bar itself, panel background will show through
        # pygame.draw.rect(self.screen, PANEL_BACKGROUND_COLOR, tab_bar_rect)

        tab_rects_dict = getattr(self, tab_rects_dict_name)
        tab_rects_dict.clear()

        padding = 5
        current_x = MAP_AREA_WIDTH + padding
        # Calculate available width for tabs, considering padding on both sides
        available_width_for_tabs = SIDE_PANEL_WIDTH - (2 * padding)

        num_tabs = len(tab_options)
        if num_tabs == 0: return base_y_offset + TAB_HEIGHT # Should not happen if called

        # Calculate tab width: either distribute equally or based on text, with a max
        # For simplicity and cleaner look, let's try equal width for now.
        # Add small spacing between tabs
        spacing_between_tabs = 2
        total_spacing = (num_tabs -1) * spacing_between_tabs
        individual_tab_width = (available_width_for_tabs - total_spacing) / num_tabs

        for option_name in tab_options:
            is_active = getattr(self, active_tab_var_name) == option_name
            tab_bg_color = ACCENT_COLOR_PRIMARY if is_active else ACCENT_COLOR_SECONDARY
            text_color = PANEL_BACKGROUND_COLOR if is_active else TEXT_COLOR # Dark text on active, light on inactive

            # Truncate text if too long for the calculated tab width
            # Max 2 chars for very short names, else more.
            max_chars = max(2, int(individual_tab_width / (self.tab_font.size("M")[0] * 0.8))) # Estimate char width
            display_name = option_name[:max_chars] + ".." if len(option_name) > max_chars + 2 else option_name

            text_surface = self.tab_font.render(display_name, True, text_color)
            text_width, text_height = text_surface.get_size()

            # Ensure tab_width is at least text_width + some padding, but not exceeding individual_tab_width
            # current_tab_actual_width = min(max(text_width + 10, individual_tab_width), individual_tab_width)
            current_tab_actual_width = individual_tab_width


            tab_rect = pygame.Rect(current_x, base_y_offset, current_tab_actual_width, TAB_HEIGHT)

            pygame.draw.rect(self.screen, tab_bg_color, tab_rect, border_top_left_radius=3, border_top_right_radius=3)
            # No separate border color for tabs, background difference implies separation
            # pygame.draw.rect(self.screen, BORDER_COLOR, tab_rect, 1, border_top_left_radius=3, border_top_right_radius=3)

            # Center text in tab
            text_x = tab_rect.x + (current_tab_actual_width - text_width) // 2
            text_y = tab_rect.y + (TAB_HEIGHT - text_height) // 2
            self.screen.blit(text_surface, (text_x, text_y))

            tab_rects_dict[option_name] = tab_rect

            if mouse_click_pos and tab_rect.collidepoint(mouse_click_pos):
                setattr(self, active_tab_var_name, option_name)
                print(f"GUI: Switched {panel_title} tab to {option_name}")

            current_x += current_tab_actual_width + spacing_between_tabs

        return base_y_offset + TAB_HEIGHT


    def draw_ai_thought_panel(self, mouse_click_pos: tuple[int, int] | None):
        tab_options = self.player_names_for_tabs
        if not self.active_tab_thought_panel and tab_options:
            self.active_tab_thought_panel = tab_options[0]

        content_y_start = self.draw_tabs(ACTION_LOG_HEIGHT, "AI Thoughts", tab_options, "active_tab_thought_panel", "thought_tab_rects", mouse_click_pos)

        panel_rect = pygame.Rect(MAP_AREA_WIDTH, content_y_start, SIDE_PANEL_WIDTH, THOUGHT_PANEL_HEIGHT - TAB_HEIGHT)
        pygame.draw.rect(self.screen, PANEL_BACKGROUND_COLOR, panel_rect) # Use new panel background
        pygame.draw.rect(self.screen, BORDER_COLOR, panel_rect, 1) # Use new border color

        player_to_show = self.active_tab_thought_panel
        current_thoughts_map = self.ai_thoughts

        padding = 10
        text_area_rect = panel_rect.inflate(-padding, -padding) # Create a text area rect with padding

        if player_to_show and player_to_show in current_thoughts_map:
            thought = current_thoughts_map[player_to_show]
            self._render_text_wrapped(self.screen, thought, text_area_rect, self.font, TEXT_COLOR) # Use new text color
        else:
            no_thought_text_str = f"No thoughts for {player_to_show if player_to_show else 'N/A'}."
            # Render centered placeholder text
            no_thought_text_surf = self.font.render(no_thought_text_str, True, TEXT_COLOR_MUTED) # Use muted text color
            text_rect = no_thought_text_surf.get_rect(center=panel_rect.center)
            text_rect.top = panel_rect.top + padding # Align to top with padding
            self.screen.blit(no_thought_text_surf, text_rect)


    def draw_chat_panel(self, mouse_click_pos: tuple[int, int] | None):
        base_y = ACTION_LOG_HEIGHT + THOUGHT_PANEL_HEIGHT

        chat_tab_options = ["global"] + list(getattr(self, 'private_chat_conversations_map', {}).keys())
        content_y_start = self.draw_tabs(base_y, "Chat", chat_tab_options, "active_tab_chat_panel", "chat_tab_rects", mouse_click_pos)

        panel_rect = pygame.Rect(MAP_AREA_WIDTH, content_y_start, SIDE_PANEL_WIDTH, CHAT_PANEL_HEIGHT - TAB_HEIGHT)
        pygame.draw.rect(self.screen, PANEL_BACKGROUND_COLOR, panel_rect) # Use new panel background
        pygame.draw.rect(self.screen, BORDER_COLOR, panel_rect, 1) # Use new border color

        messages_to_render = []
        max_messages_display = (panel_rect.height - 10) // (self.font.get_linesize() + 2) # Calculate max messages based on height

        if self.active_tab_chat_panel == "global":
            messages_to_render = getattr(self, 'global_chat_messages', [])[-max_messages_display:]
        else:
            all_private_chats = getattr(self, 'private_chat_conversations_map', {})
            messages_to_render = all_private_chats.get(self.active_tab_chat_panel, [])[-max_messages_display:]

        padding = 10
        y_render_offset = panel_rect.y + padding // 2
        line_spacing = 2

        for msg_data in reversed(messages_to_render):
            sender = msg_data.get('sender', 'System')
            message_text = msg_data.get('message', '')

            # Determine sender color (e.g., player color or accent for system)
            sender_color = TEXT_COLOR_MUTED # Default for system or unknown
            if sender != 'System' and sender in DEFAULT_PLAYER_COLORS: # Check if sender is a known player color name
                sender_color = DEFAULT_PLAYER_COLORS[sender]
            elif sender in self.player_names_for_tabs: # Check if sender is a player name
                # Find player object to get their color
                player_obj = next((p for p in self.current_game_state.players if p.name == sender), None)
                if player_obj and player_obj.color in DEFAULT_PLAYER_COLORS:
                    sender_color = DEFAULT_PLAYER_COLORS[player_obj.color]
                else: # Fallback if player color not in DEFAULT_PLAYER_COLORS
                    sender_color = ACCENT_COLOR_PRIMARY


            full_msg_str = f"{sender}: {message_text}"
            # Simple text wrapping for chat messages
            available_width = panel_rect.width - (2 * padding)

            words = full_msg_str.split(' ')
            lines_for_this_message = []
            current_line_text = ""
            for word in words:
                test_line = current_line_text + word + " "
                if self.font.size(test_line)[0] < available_width:
                    current_line_text = test_line
                else:
                    lines_for_this_message.append(current_line_text.strip())
                    current_line_text = word + " "
            lines_for_this_message.append(current_line_text.strip())

            # Render lines for this message from bottom up (in reverse order of how they are added)
            for line_text in reversed(lines_for_this_message):
                if y_render_offset + self.font.get_linesize() > panel_rect.bottom - padding // 2:
                    break # Stop if panel is full

                # For the first line of a message part (which is the sender part), color the sender
                if line_text.startswith(sender + ":"):
                    sender_part = sender + ":"
                    message_part = line_text[len(sender_part):]

                    sender_surf = self.font.render(sender_part, True, sender_color)
                    message_surf = self.font.render(message_part, True, TEXT_COLOR)

                    self.screen.blit(sender_surf, (panel_rect.x + padding, y_render_offset))
                    self.screen.blit(message_surf, (panel_rect.x + padding + sender_surf.get_width(), y_render_offset))
                else: # Subsequent wrapped lines
                    line_surf = self.font.render(line_text, True, TEXT_COLOR)
                    self.screen.blit(line_surf, (panel_rect.x + padding, y_render_offset))

                y_render_offset += self.font.get_linesize() + line_spacing
            y_render_offset += line_spacing # Extra spacing between messages


        if not messages_to_render:
            no_chat_text_str = f"No messages in chat '{self.active_tab_chat_panel}'."
            no_chat_surf = self.font.render(no_chat_text_str, True, TEXT_COLOR_MUTED)
            text_rect = no_chat_surf.get_rect(center=panel_rect.center)
            text_rect.top = panel_rect.top + padding
            self.screen.blit(no_chat_surf, text_rect)


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
        self.screen.fill(PANEL_BACKGROUND_COLOR) # Use panel background for game over screen
        message = f"Game Over! Winner: {winner_name}" if winner_name else "Game Over! Draw/Timeout."

        text_surface = self.large_font.render(message, True, TEXT_COLOR_HEADER) # Use header text color
        text_rect = text_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 30))

        sub_text_surface = self.font.render("Click anywhere or close window to exit.", True, TEXT_COLOR_MUTED)
        sub_text_rect = sub_text_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 30))

        self.screen.blit(text_surface, text_rect)
        self.screen.blit(sub_text_surface, sub_text_rect)
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
                    if event.button == 1: # Left click
                        mouse_click_pos = event.pos
                    elif event.button == 2: # Middle mouse button for panning
                        self.panning_active = True
                        self.last_mouse_pos = event.pos
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 2: # Middle mouse button
                        self.panning_active = False
                        self.last_mouse_pos = None
                elif event.type == pygame.MOUSEMOTION:
                    if self.panning_active and self.last_mouse_pos:
                        dx = event.pos[0] - self.last_mouse_pos[0]
                        dy = event.pos[1] - self.last_mouse_pos[1]
                        self.camera_offset_x += dx
                        self.camera_offset_y += dy
                        self.last_mouse_pos = event.pos
                elif event.type == pygame.MOUSEWHEEL:
                    mouse_x, mouse_y = pygame.mouse.get_pos()
                    # Ensure zoom is applied only to map area
                    if mouse_x < MAP_AREA_WIDTH:
                        old_zoom_level = self.zoom_level

                        if event.y > 0: # Scroll up
                            self.zoom_level += self.zoom_increment
                        elif event.y < 0: # Scroll down
                            self.zoom_level -= self.zoom_increment

                        self.zoom_level = max(self.min_zoom, min(self.max_zoom, self.zoom_level))

                        # Adjust camera offset to zoom towards the mouse cursor
                        # World coordinates of the mouse pointer before zoom
                        world_x_before_zoom = (mouse_x - self.camera_offset_x) / old_zoom_level
                        world_y_before_zoom = (mouse_y - self.camera_offset_y) / old_zoom_level

                        # New camera offset to keep the world coordinates at the same screen position
                        self.camera_offset_x = mouse_x - (world_x_before_zoom * self.zoom_level)
                        self.camera_offset_y = mouse_y - (world_y_before_zoom * self.zoom_level)


            if self.orchestrator and self.running:
                if not self.orchestrator.advance_game_turn():
                    self.running = False

            # Clamp camera offsets to keep map within bounds
            map_bounds = self._get_map_content_bounds()
            if map_bounds:
                content_min_x, content_min_y, content_max_x, content_max_y = map_bounds
                map_margin = 50 # Allow map to go 50px off-screen

                # Clamp X offset
                # Left edge: content_min_x + self.camera_offset_x should not be > MAP_AREA_WIDTH - map_margin
                # self.camera_offset_x should not be > MAP_AREA_WIDTH - map_margin - content_min_x
                max_offset_x = MAP_AREA_WIDTH - map_margin - content_min_x
                # Right edge: content_max_x + self.camera_offset_x should not be < map_margin
                # self.camera_offset_x should not be < map_margin - content_max_x
                min_offset_x = map_margin - content_max_x

                # Prevent map from being smaller than view area if possible
                map_width_zoomed = content_max_x - content_min_x
                if map_width_zoomed < MAP_AREA_WIDTH - 2 * map_margin: # If map is narrower than viewable area
                    # Center it
                    self.camera_offset_x = (MAP_AREA_WIDTH - map_width_zoomed) / 2 - content_min_x
                else:
                    self.camera_offset_x = max(min_offset_x, min(self.camera_offset_x, max_offset_x))

                # Clamp Y offset
                # Top edge: content_min_y + self.camera_offset_y should not be > SCREEN_HEIGHT - map_margin
                max_offset_y = SCREEN_HEIGHT - map_margin - content_min_y
                # Bottom edge: content_max_y + self.camera_offset_y should not be < map_margin
                min_offset_y = map_margin - content_max_y

                map_height_zoomed = content_max_y - content_min_y
                if map_height_zoomed < SCREEN_HEIGHT - 2 * map_margin: # If map is shorter than viewable area
                    # Center it
                    self.camera_offset_y = (SCREEN_HEIGHT - map_height_zoomed) / 2 - content_min_y
                else:
                    self.camera_offset_y = max(min_offset_y, min(self.camera_offset_y, max_offset_y))


            self.screen.fill(BACKGROUND_COLOR) # Use the main background color for the whole screen initially

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
