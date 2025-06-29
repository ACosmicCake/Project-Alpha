import json

class Territory:
    def __init__(self, name, geometry, military_power=0):
        self.name = name
        self.geometry = geometry
        self.military_power = military_power
        self.owner = None  # Or initialize as needed

    def __repr__(self):
        return f"Territory({self.name}, Power: {self.military_power}, Owner: {self.owner})"

class GameMode:
    def __init__(self):
        self.territories = []

    def initialize_territories(self):
        raise NotImplementedError("This method should be overridden by subclasses")

    def get_territory_by_name(self, name):
        for territory in self.territories:
            if territory.name == name:
                return territory
        return None

class RealWorldGameMode(GameMode):
    def __init__(self, geojson_string_data, military_power_ratios, players_list=None):
        super().__init__()
        self.geojson_string_data = geojson_string_data
        self.military_power_ratios = military_power_ratios
        self.map_bounds = None  # To store (min_lon, min_lat, max_lon, max_lat)
        # Players_list will be passed from the engine/orchestrator after players are created
        # but before territories are fully assigned to them by this mode.
        self.initialize_territories(players_list if players_list else [])


    def initialize_territories(self, players: list = None): # Added players parameter
        """
        Initializes territories from GeoJSON.
        Assigns military power based on ratios.
        Distributes initial ownership of territories among active players.
        Calculates map boundaries.
        """
        if players is None:
            players = []

        try:
            data = json.loads(self.geojson_string_data)
        except json.JSONDecodeError as e:
            print(f"Error decoding GeoJSON string: {e}")
            return

        if 'features' not in data or not isinstance(data['features'], list):
            print("GeoJSON data must contain a 'features' list.")
            return

        min_lon, min_lat = float('inf'), float('inf')
        max_lon, max_lat = float('-inf'), float('-inf')

        temp_territories = []

        for feature in data['features']:
            properties = feature.get('properties', {})
            geometry = feature.get('geometry', {})
            country_name = properties.get('name') or \
                           properties.get('NAME') or \
                           properties.get('ADMIN') or \
                           properties.get('SOVEREIGNT') or \
                           f"UnknownCountry_{len(self.territories)}"

            initial_military_power = self.military_power_ratios.get(country_name, 1)

            # Create Territory object. Owner is None for now.
            territory = Territory(name=country_name,
                                  geometry=geometry,
                                  military_power=initial_military_power)
            temp_territories.append(territory)

            # Update map bounds
            if geometry and 'coordinates' in geometry:
                geom_type = geometry.get('type')
                coordinates = geometry['coordinates']

                def update_bounds_from_coords(coords_list_of_lists_or_tuples):
                    nonlocal min_lon, min_lat, max_lon, max_lat
                    # Check if it's a list of lists (like Polygon rings) or a list of tuples (like a simple LineString or Point sequence)
                    if not coords_list_of_lists_or_tuples: return

                    first_element = coords_list_of_lists_or_tuples[0]
                    if isinstance(first_element, list) and len(first_element) == 2 and isinstance(first_element[0], (int, float)):
                        # It's a list of coordinate tuples [lon, lat]
                        for lon, lat in coords_list_of_lists_or_tuples:
                            if isinstance(lon, (int, float)) and isinstance(lat, (int, float)):
                                min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)
                                min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)
                    elif isinstance(first_element, list) and first_element and isinstance(first_element[0], list):
                         # It's a list of lists of coordinate tuples (e.g. Polygon with holes, or MultiPolygon part)
                         for sub_list in coords_list_of_lists_or_tuples:
                             update_bounds_from_coords(sub_list) # Recursive call for deeper structures


                if geom_type == 'Polygon':
                    for ring in coordinates: # coordinates is list of rings
                        update_bounds_from_coords(ring)
                elif geom_type == 'MultiPolygon':
                    for polygon_coords in coordinates: # coordinates is list of polygons
                        for ring in polygon_coords: # each polygon is list of rings
                            update_bounds_from_coords(ring)

        # Assign territories to players (round-robin)
        if players and len(players) > 0:
            num_players = len(players)
            for i, territory in enumerate(temp_territories):
                player_owner = players[i % num_players]
                territory.owner = player_owner
                # The territory already has its military_power set.
                # We don't modify player.initial_armies_pool or armies_placed_in_setup here,
                # as the game engine's standard setup for those is being bypassed for this mode.
                # The engine will need to be aware that these territories start owned and with armies.
                self.territories.append(territory) # Add to the game mode's list
        else:
            # If no players provided (e.g. during initial instantiation before engine creates players),
            # just add territories as unowned. The engine will need a way to assign them later.
            # Or, this indicates RealWorldGameMode should be initialized *after* players exist.
            # For now, we'll add them as unowned if no players.
            self.territories.extend(temp_territories)
            print("Warning: RealWorldGameMode initialized without players list. Territories will be unowned.")


        if len(self.territories) > 0:
            if min_lon != float('inf'): # Check if bounds were actually updated
                 self.map_bounds = (min_lon, min_lat, max_lon, max_lat)
                 print(f"Map bounds calculated: {self.map_bounds}")
            else:
                print("Warning: Map bounds could not be calculated (no valid coordinates in GeoJSON).")
        else:
            print("No territories were initialized from GeoJSON.")

        print(f"Initialized {len(self.territories)} territories for RealWorldGameMode. Ownership assigned if players provided.")
        # Adjacencies and Continents are not handled by this basic initialization.

    def display_territories(self):
        """
        Displays the initialized territories and their military power.
        """
        for territory in self.territories:
            print(territory)

# Example Usage (for testing purposes, can be removed or moved later)
if __name__ == '__main__':
    # Provided GeoJSON data (truncated for brevity in this example)
    geojson_input = """
    {"type":"FeatureCollection","features":[{"type":"Feature","properties":{"name":"Costa Rica"},"geometry":{"type":"Polygon","coordinates":[[[-82.54,9.56],[-82.93,9.47]]]}},{"type":"Feature","properties":{"name":"Nicaragua"},"geometry":{"type":"Polygon","coordinates":[[[-83.65,10.93],[-83.89,10.72]]]}}]}
    """

    # Example military power ratios (these would need to be properly defined)
    military_ratios = {
        "Costa Rica": 5, # Example value
        "Nicaragua": 10, # Example value
        # ... other countries
    }

    real_world_mode = RealWorldGameMode(geojson_data=geojson_input, military_power_ratios=military_ratios)
    real_world_mode.display_territories()
