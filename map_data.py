"""
Map data for the Risk game.
Territory polygons are simplified and manually created.
"""

SCREEN_WIDTH = 1024  # Increased screen width for more map space
SCREEN_HEIGHT = 768 # Increased screen height

DEFAULT_TERRITORY_COLOR = (200, 200, 200)  # Light grey
HOVER_TERRITORY_COLOR = (170, 170, 170)    # Darker grey for hover
SELECTED_TERRITORY_COLOR = (100, 200, 100) # Light green for selected
LINE_COLOR = (0, 0, 0)                     # Black for borders and lines
TEXT_COLOR = (0, 0, 0)                     # Black for text

# Placeholder for player colors - will be used later
PLAYER_COLORS = [
    (255, 0, 0, 150),    # Red (with alpha for territory fill)
    (0, 0, 255, 150),    # Blue
    (0, 255, 0, 150),    # Green
    (255, 255, 0, 150),  # Yellow
    (255, 0, 255, 150),  # Magenta
    (0, 255, 255, 150),  # Cyan
]


TERRITORIES = {
    # --- North America ---
    "alaska": {
        "name": "Alaska", "continent_id": "north_america", "armies": 0, "owner": None,
        "polygon_coords": [(30, 70), (100, 50), (120, 100), (80, 130), (40, 100)],
        "label_coords": (75, 85),
        "adjacencies": ["northwest_territory", "alberta", "kamchatka"]
    },
    "northwest_territory": {
        "name": "NW Territory", "continent_id": "north_america", "armies": 0, "owner": None,
        "polygon_coords": [(100, 50), (200, 50), (220, 100), (180, 130), (120, 100)],
        "label_coords": (160, 85),
        "adjacencies": ["alaska", "alberta", "ontario", "greenland"]
    },
    "alberta": {
        "name": "Alberta", "continent_id": "north_america", "armies": 0, "owner": None,
        "polygon_coords": [(80, 130), (180, 130), (170, 180), (90, 180)],
        "label_coords": (130, 155),
        "adjacencies": ["alaska", "northwest_territory", "ontario", "western_us"]
    },
    "ontario": {
        "name": "Ontario", "continent_id": "north_america", "armies": 0, "owner": None,
        "polygon_coords": [(180, 130), (280, 130), (270, 180), (170, 180)],
        "label_coords": (225, 155),
        "adjacencies": ["northwest_territory", "alberta", "western_us", "eastern_us", "quebec", "greenland"]
    },
    "quebec": {
        "name": "Quebec", "continent_id": "north_america", "armies": 0, "owner": None,
        "polygon_coords": [(280, 130), (380, 130), (370, 180), (270, 180)],
        "label_coords": (325, 155),
        "adjacencies": ["ontario", "eastern_us", "greenland"]
    },
    "western_us": {
        "name": "Western US", "continent_id": "north_america", "armies": 0, "owner": None,
        "polygon_coords": [(90, 180), (170, 180), (160, 230), (100, 230)],
        "label_coords": (130, 205),
        "adjacencies": ["alberta", "ontario", "eastern_us", "central_america"]
    },
    "eastern_us": {
        "name": "Eastern US", "continent_id": "north_america", "armies": 0, "owner": None,
        "polygon_coords": [(170, 180), (270, 180), (260, 230), (160, 230)],
        "label_coords": (215, 205),
        "adjacencies": ["ontario", "quebec", "western_us", "central_america"]
    },
    "central_america": {
        "name": "Central America", "continent_id": "north_america", "armies": 0, "owner": None,
        "polygon_coords": [(100, 230), (200, 230), (180, 280), (120, 280)],
        "label_coords": (150, 255),
        "adjacencies": ["western_us", "eastern_us", "venezuela"]
    },
    "greenland": {
        "name": "Greenland", "continent_id": "north_america", "armies": 0, "owner": None,
        "polygon_coords": [(250, 30), (350, 30), (400, 80), (300, 100), (230, 80)],
        "label_coords": (310, 65),
        "adjacencies": ["northwest_territory", "ontario", "quebec", "iceland"]
    },

    # --- Europe ---
    "iceland": {
        "name": "Iceland", "continent_id": "europe", "armies": 0, "owner": None,
        "polygon_coords": [(420, 70), (470, 70), (480, 110), (430, 110)],
        "label_coords": (450, 90),
        "adjacencies": ["greenland", "great_britain", "scandinavia"]
    },
    "scandinavia": {
        "name": "Scandinavia", "continent_id": "europe", "armies": 0, "owner": None,
        "polygon_coords": [(480, 50), (550, 50), (560, 120), (500, 130), (470, 100)],
        "label_coords": (515, 85),
        "adjacencies": ["iceland", "great_britain", "northern_europe", "ukraine"]
    },
    "great_britain": {
        "name": "Great Britain", "continent_id": "europe", "armies": 0, "owner": None,
        "polygon_coords": [(430, 120), (490, 130), (480, 170), (420, 160)],
        "label_coords": (455, 145),
        "adjacencies": ["iceland", "scandinavia", "northern_europe", "western_europe"]
    },
    "northern_europe": {
        "name": "Northern Europe", "continent_id": "europe", "armies": 0, "owner": None,
        "polygon_coords": [(490, 130), (560, 120), (570, 180), (480, 170)],
        "label_coords": (525, 150),
        "adjacencies": ["scandinavia", "great_britain", "western_europe", "southern_europe", "ukraine"]
    },
    "western_europe": {
        "name": "Western Europe", "continent_id": "europe", "armies": 0, "owner": None,
        "polygon_coords": [(420, 170), (480, 170), (490, 220), (430, 210)],
        "label_coords": (455, 190),
        "adjacencies": ["great_britain", "northern_europe", "southern_europe", "north_africa"]
    },
    "southern_europe": {
        "name": "Southern Europe", "continent_id": "europe", "armies": 0, "owner": None,
        "polygon_coords": [(490, 180), (570, 180), (560, 230), (500, 230)], # Adjusted y-coords
        "label_coords": (530, 205),
        "adjacencies": ["northern_europe", "western_europe", "ukraine", "middle_east", "egypt", "north_africa"]
    },
    "ukraine": {
        "name": "Ukraine", "continent_id": "europe", "armies": 0, "owner": None,
        "polygon_coords": [(560, 120), (650, 120), (640, 190), (570, 180)],
        "label_coords": (605, 155),
        "adjacencies": ["scandinavia", "northern_europe", "southern_europe", "ural", "afghanistan", "middle_east"]
    },

    # --- Asia (Partial, for connections) ---
    "kamchatka": {
        "name": "Kamchatka", "continent_id": "asia", "armies": 0, "owner": None,
        "polygon_coords": [(700, 50), (780, 50), (770, 120), (710, 120)], # Placeholder
        "label_coords": (740, 85),
        "adjacencies": ["alaska", "japan", "irkutsk", "yakutsk", "mongolia"] # Example adj.
    },
     "ural": {
        "name": "Ural", "continent_id": "asia", "armies": 0, "owner": None,
        "polygon_coords": [(660, 100), (720, 100), (710, 170), (650, 170)], # Placeholder
        "label_coords": (685, 135),
        "adjacencies": ["ukraine", "siberia", "china", "afghanistan"]
    },
    "siberia": {
        "name": "Siberia", "continent_id": "asia", "armies": 0, "owner": None,
        "polygon_coords": [(730, 80), (800, 80), (790, 150), (720, 150)], # Placeholder
        "label_coords": (765, 115),
        "adjacencies": ["ural", "yakutsk", "irkutsk", "mongolia", "china"]
    },
    "yakutsk": {
        "name": "Yakutsk", "continent_id": "asia", "armies": 0, "owner": None,
        "polygon_coords": [(790, 30), (860, 30), (850, 100), (780, 100)], # Placeholder
        "label_coords": (825, 65),
        "adjacencies": ["kamchatka", "siberia", "irkutsk"]
    },
    "irkutsk": {
        "name": "Irkutsk", "continent_id": "asia", "armies": 0, "owner": None,
        "polygon_coords": [(780, 110), (850, 110), (840, 180), (770, 180)], # Placeholder
        "label_coords": (815, 145),
        "adjacencies": ["kamchatka", "siberia", "yakutsk", "mongolia"]
    },
    "mongolia": {
        "name": "Mongolia", "continent_id": "asia", "armies": 0, "owner": None,
        "polygon_coords": [(770, 130), (840, 130), (830, 200), (760, 200)], # Placeholder, distinct y from Irkutsk
        "label_coords": (805, 165),
        "adjacencies": ["kamchatka", "siberia", "irkutsk", "japan", "china"]
    },
    "japan": {
        "name": "Japan", "continent_id": "asia", "armies": 0, "owner": None,
        "polygon_coords": [(850, 100), (900, 100), (890, 170), (840, 170)], # Placeholder
        "label_coords": (870, 135),
        "adjacencies": ["kamchatka", "mongolia"]
    },
    "afghanistan": {
        "name": "Afghanistan", "continent_id": "asia", "armies": 0, "owner": None,
        "polygon_coords": [(630, 190), (700, 190), (690, 250), (620, 250)], # Placeholder
        "label_coords": (660, 220),
        "adjacencies": ["ukraine", "ural", "china", "india", "middle_east"]
    },
    "china": {
        "name": "China", "continent_id": "asia", "armies": 0, "owner": None,
        "polygon_coords": [(700, 200), (780, 200), (770, 270), (690, 270)], # Placeholder
        "label_coords": (735, 235),
        "adjacencies": ["afghanistan", "ural", "siberia", "mongolia", "india", "siam"]
    },
     "middle_east": {
        "name": "Middle East", "continent_id": "asia", "armies": 0, "owner": None,
        "polygon_coords": [(570, 230), (640, 230), (630, 290), (560, 290)], # Placeholder
        "label_coords": (600, 260),
        "adjacencies": ["southern_europe", "ukraine", "afghanistan", "india", "egypt", "east_africa"]
    },
    "india": {
        "name": "India", "continent_id": "asia", "armies": 0, "owner": None,
        "polygon_coords": [(650, 260), (720, 260), (710, 320), (640, 320)], # Placeholder
        "label_coords": (680, 290),
        "adjacencies": ["middle_east", "afghanistan", "china", "siam"]
    },
    "siam": {
        "name": "Siam", "continent_id": "asia", "armies": 0, "owner": None,
        "polygon_coords": [(730, 280), (800, 280), (790, 340), (720, 340)], # Placeholder
        "label_coords": (760, 310),
        "adjacencies": ["china", "india", "indonesia"]
    },


    # --- South America (Partial, for connections) ---
    "venezuela": {
        "name": "Venezuela", "continent_id": "south_america", "armies": 0, "owner": None,
        "polygon_coords": [(120, 290), (220, 290), (200, 340), (140, 340)], # Placeholder
        "label_coords": (170, 315),
        "adjacencies": ["central_america", "peru", "brazil"]
    },
    "peru": {
        "name": "Peru", "continent_id": "south_america", "armies": 0, "owner": None,
        "polygon_coords": [(100, 350), (200, 350), (180, 400), (120, 400)], # Placeholder
        "label_coords": (150, 375),
        "adjacencies": ["venezuela", "brazil", "argentina"]
    },
    "brazil": {
        "name": "Brazil", "continent_id": "south_america", "armies": 0, "owner": None,
        "polygon_coords": [(200, 300), (300, 300), (280, 400), (180, 400), (200, 340)], # Larger, central
        "label_coords": (240, 350),
        "adjacencies": ["venezuela", "peru", "argentina", "north_africa"]
    },
    "argentina": {
        "name": "Argentina", "continent_id": "south_america", "armies": 0, "owner": None,
        "polygon_coords": [(120, 410), (220, 410), (200, 460), (140, 460)], # Placeholder
        "label_coords": (170, 435),
        "adjacencies": ["peru", "brazil"]
    },

    # --- Africa (Partial, for connections) ---
    "north_africa": {
        "name": "North Africa", "continent_id": "africa", "armies": 0, "owner": None,
        "polygon_coords": [(350, 250), (480, 250), (470, 330), (360, 320)], # Wide
        "label_coords": (415, 285),
        "adjacencies": ["western_europe", "southern_europe", "egypt", "east_africa", "congo", "brazil"]
    },
    "egypt": {
        "name": "Egypt", "continent_id": "africa", "armies": 0, "owner": None,
        "polygon_coords": [(490, 240), (550, 240), (540, 300), (480, 300)], # Connects to S. Europe and Middle East
        "label_coords": (515, 270),
        "adjacencies": ["southern_europe", "middle_east", "north_africa", "east_africa"]
    },
    "east_africa": {
        "name": "East Africa", "continent_id": "africa", "armies": 0, "owner": None,
        "polygon_coords": [(480, 310), (540, 310), (530, 370), (470, 370)],
        "label_coords": (505, 340),
        "adjacencies": ["egypt", "middle_east", "north_africa", "congo", "south_africa", "madagascar"]
    },
     "congo": {
        "name": "Congo", "continent_id": "africa", "armies": 0, "owner": None,
        "polygon_coords": [(400, 330), (470, 330), (460, 390), (410, 390)],
        "label_coords": (435, 360),
        "adjacencies": ["north_africa", "east_africa", "south_africa"]
    },
    "south_africa": {
        "name": "South Africa", "continent_id": "africa", "armies": 0, "owner": None,
        "polygon_coords": [(410, 400), (480, 400), (470, 460), (420, 460)],
        "label_coords": (445, 430),
        "adjacencies": ["congo", "east_africa", "madagascar"]
    },
    "madagascar": {
        "name": "Madagascar", "continent_id": "africa", "armies": 0, "owner": None,
        "polygon_coords": [(550, 380), (590, 380), (580, 430), (540, 430)],
        "label_coords": (565, 405),
        "adjacencies": ["east_africa", "south_africa"]
    },

    # --- Australia (Partial, for connections) ---
    "indonesia": {
        "name": "Indonesia", "continent_id": "australia", "armies": 0, "owner": None,
        "polygon_coords": [(750, 350), (820, 350), (810, 400), (740, 400)], # Placeholder
        "label_coords": (780, 375),
        "adjacencies": ["siam", "new_guinea", "western_australia"]
    },
    "new_guinea": {
        "name": "New Guinea", "continent_id": "australia", "armies": 0, "owner": None,
        "polygon_coords": [(830, 360), (900, 360), (890, 410), (820, 410)], # Placeholder
        "label_coords": (860, 385),
        "adjacencies": ["indonesia", "eastern_australia", "western_australia"] # Classic map has this link
    },
    "western_australia": {
        "name": "Western Australia", "continent_id": "australia", "armies": 0, "owner": None,
        "polygon_coords": [(750, 410), (820, 410), (810, 470), (740, 470)], # Placeholder
        "label_coords": (780, 440),
        "adjacencies": ["indonesia", "new_guinea", "eastern_australia"]
    },
    "eastern_australia": {
        "name": "Eastern Australia", "continent_id": "australia", "armies": 0, "owner": None,
        "polygon_coords": [(830, 410), (900, 410), (890, 470), (820, 470)], # Placeholder
        "label_coords": (860, 440),
        "adjacencies": ["new_guinea", "western_australia"]
    },
}

CONTINENTS = {
    "north_america": {
        "name": "North America", "bonus_armies": 5, "color": (255, 165, 0, 150), # Orange
        "territories": ["alaska", "northwest_territory", "alberta", "ontario", "quebec", "western_us", "eastern_us", "central_america", "greenland"]
    },
    "south_america": {
        "name": "South America", "bonus_armies": 2, "color": (255, 255, 0, 150), # Yellow
        "territories": ["venezuela", "peru", "brazil", "argentina"]
    },
    "europe": {
        "name": "Europe", "bonus_armies": 5, "color": (0, 0, 255, 150),       # Blue
        "territories": ["iceland", "scandinavia", "great_britain", "northern_europe", "western_europe", "southern_europe", "ukraine"]
    },
    "africa": {
        "name": "Africa", "bonus_armies": 3, "color": (165, 42, 42, 150),      # Brown
        "territories": ["north_africa", "egypt", "east_africa", "congo", "south_africa", "madagascar"]
    },
    "asia": {
        "name": "Asia", "bonus_armies": 7, "color": (0, 128, 0, 150),         # Green
        "territories": ["kamchatka", "ural", "siberia", "yakutsk", "irkutsk", "mongolia", "japan", "afghanistan", "china", "middle_east", "india", "siam"]
    },
    "australia": {
        "name": "Australia", "bonus_armies": 2, "color": (128, 0, 128, 150),   # Purple
        "territories": ["indonesia", "new_guinea", "western_australia", "eastern_australia"]
    }
}

# Adjacency lines (can be derived from TERRITORIES[terr_id]["adjacencies"] but explicit for now)
# This list will be very long for a full map.
# For now, we will rely on the "adjacencies" list in each territory.
# The draw_connections function in the UI should be updated to use this.
CONNECTIONS_LINES = [] # This can be populated dynamically from adjacencies

def get_all_connections():
    """
    Generates a list of connection pairs from territory adjacencies.
    Ensures each connection is listed only once (e.g., (A,B) not (B,A) as well).
    """
    connections = set()
    for terr_id, data in TERRITORIES.items():
        for adj_id in data.get("adjacencies", []):
            # Ensure adj_id is also a valid territory before adding
            if adj_id in TERRITORIES:
                pair = tuple(sorted((terr_id, adj_id)))
                connections.add(pair)
    return list(connections)

# Populate CONNECTIONS_LINES dynamically
CONNECTIONS_LINES = get_all_connections()

# Sanity check for adjacencies: ensure they are bidirectional
# (or at least that the target of an adjacency exists)
for terr_id, data in TERRITORIES.items():
    for adj_id in data.get("adjacencies", []):
        if adj_id not in TERRITORIES:
            print(f"Warning: Territory '{terr_id}' lists non-existent adjacency '{adj_id}'")
        elif terr_id not in TERRITORIES[adj_id].get("adjacencies", []):
            # This is a one-way connection, which is fine for some maps, but usually bidirectional in Risk
            # For our purpose, we assume they should be bidirectional for drawing.
            # print(f"Warning: Adjacency '{terr_id}' -> '{adj_id}' is not bidirectional.")
            pass


# Example: Check if all territories in a continent are defined in TERRITORIES
for cont_id, cont_data in CONTINENTS.items():
    for terr_id in cont_data.get("territories", []):
        if terr_id not in TERRITORIES:
            print(f"Warning: Continent '{cont_id}' lists non-existent territory '{terr_id}'")

FPS = 30

# Add armies and owner to territories
for terr_id in TERRITORIES:
    TERRITORIES[terr_id]["armies"] = 0 # Initialized to 0
    TERRITORIES[terr_id]["owner"] = None # No owner initially

# Ensure continent colors have alpha for semi-transparent fill if desired
# If not, they will be opaque. Pygame handles 3-tuple (RGB) and 4-tuple (RGBA) colors.
# The current continent colors already include an alpha component (150).
# DEFAULT_TERRITORY_COLOR does not, it will be opaque.
# Player colors also include alpha.
