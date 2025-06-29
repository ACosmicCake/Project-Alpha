import json
import os
from shapely.geometry import shape, MultiPolygon, Polygon
from shapely.ops import unary_union
import math

class MapProcessor:
    def __init__(self, geojson_data: dict, map_area_width: int, map_area_height: int):
        self.geojson_data = geojson_data
        self.map_area_width = map_area_width
        self.map_area_height = map_area_height
        self.countries = []
        self.map_config = {"continents": [], "countries": {}} # Using "countries" key for world map
        self.map_display_config = {"territory_polygons": {}, "territory_centroids": {}}

        self._extract_country_data()
        self._normalize_and_scale_polygons()
        self._generate_map_config_entries()
        # Adjacency calculation will be a separate, more complex step
        # For now, adjacencies will be empty.

    def _extract_country_data(self):
        """Extracts country name and geometry from GeoJSON features."""
        for feature in self.geojson_data.get("features", []):
            properties = feature.get("properties", {})
            name = properties.get("NAME")
            if not name:
                name = properties.get("name") # Fallback for different casing

            geometry = feature.get("geometry")
            if name and geometry:
                geom_shape = shape(geometry)
                self.countries.append({"name": name, "shape": geom_shape, "original_geojson_coords": geometry.get("coordinates")})
        print(f"MapProcessor: Extracted {len(self.countries)} countries.")

    def _normalize_and_scale_polygons(self):
        """
        Normalizes coordinates to fit within the map_area_width and map_area_height.
        Handles MultiPolygons by taking their union or largest part.
        Calculates centroids for each country.
        """
        if not self.countries:
            return

        all_shapes = [country["shape"] for country in self.countries if country["shape"].is_valid]

        # Filter out invalid or empty geometries before creating the bounding box
        valid_shapes = [s for s in all_shapes if not s.is_empty and s.is_valid]
        if not valid_shapes:
            print("MapProcessor: No valid shapes to process for normalization.")
            return

        # Create a single MultiPolygon or GeometryCollection from all valid shapes to get global bounds
        # Using unary_union can be slow for many complex polygons.
        # A simpler approach is to iterate and find min/max of all coordinates.
        min_x_all, min_y_all, max_x_all, max_y_all = float('inf'), float('inf'), float('-inf'), float('-inf')

        for country_data in self.countries:
            geom = country_data["shape"]
            if geom.is_valid and not geom.is_empty:
                bounds = geom.bounds
                min_x_all = min(min_x_all, bounds[0])
                min_y_all = min(min_y_all, bounds[1])
                max_x_all = max(max_x_all, bounds[2])
                max_y_all = max(max_y_all, bounds[3])

        if not all(math.isfinite(val) for val in [min_x_all, min_y_all, max_x_all, max_y_all]):
            print("MapProcessor: Could not determine valid global bounds for shapes. Skipping normalization.")
            # Populate display_config with empty polygons/centroids for all countries
            for country_data in self.countries:
                self.map_display_config["territory_polygons"][country_data["name"]] = []
                self.map_display_config["territory_centroids"][country_data["name"]] = (0,0) # Default
            return


        original_width = max_x_all - min_x_all
        original_height = max_y_all - min_y_all

        if original_width == 0 or original_height == 0:
            print("MapProcessor: Original map dimensions are zero. Cannot scale.")
            for country_data in self.countries: # Populate with empty/default
                self.map_display_config["territory_polygons"][country_data["name"]] = []
                self.map_display_config["territory_centroids"][country_data["name"]] = (0,0)
            return


        # Calculate scale factors, maintaining aspect ratio
        scale_x = (self.map_area_width - 20) / original_width  # -20 for padding
        scale_y = (self.map_area_height - 20) / original_height
        scale = min(scale_x, scale_y) # Use the smaller scale to fit all

        # Calculate offsets to center the map
        new_map_width = original_width * scale
        new_map_height = original_height * scale
        offset_x = (self.map_area_width - new_map_width) / 2
        offset_y = (self.map_area_height - new_map_height) / 2


        for country_data in self.countries:
            name = country_data["name"]
            geom = country_data["shape"]

            if not geom.is_valid or geom.is_empty:
                print(f"MapProcessor: Invalid or empty geometry for {name}. Skipping polygon processing.")
                self.map_display_config["territory_polygons"][name] = []
                self.map_display_config["territory_centroids"][name] = (self.map_area_width // 2, self.map_area_height // 2) # Default centroid
                continue

            scaled_polygons_for_country = []

            def process_polygon(poly):
                exterior_coords = []
                for x, y in poly.exterior.coords:
                    # Apply scaling and transformation
                    # GeoJSON Y is typically Latitude (North-South), X is Longitude (East-West)
                    # Pygame Y is typically Downwards. We need to flip the Y.
                    new_x = offset_x + (x - min_x_all) * scale
                    new_y = offset_y + (max_y_all - y) * scale # Flipping Y: (max_y_all - y)
                    exterior_coords.append((int(new_x), int(new_y)))

                # TODO: Handle interior rings (holes) if necessary for complex polygons
                # For now, just processing exterior.
                return exterior_coords

            if isinstance(geom, Polygon):
                scaled_polygons_for_country.append(process_polygon(geom))
            elif isinstance(geom, MultiPolygon):
                # Option 1: Take the largest polygon
                # largest_poly = max(geom.geoms, key=lambda p: p.area)
                # scaled_polygons_for_country.append(process_polygon(largest_poly))
                # Option 2: Process all polygons in the MultiPolygon
                for poly in geom.geoms:
                    if poly.is_valid and not poly.is_empty:
                         scaled_polygons_for_country.append(process_polygon(poly))

            self.map_display_config["territory_polygons"][name] = scaled_polygons_for_country

            # Calculate centroid of the scaled geometry for placing army counts/names
            # For MultiPolygons, this will be the centroid of the combined shape.
            # If using only the largest polygon from a MultiPolygon, calculate centroid of that.

            # Re-create a scaled shapely object to get its centroid easily
            # This is a bit inefficient but simpler for now.
            scaled_shapely_polygons = []
            for poly_coords_list in scaled_polygons_for_country:
                 if len(poly_coords_list) >= 3: # Need at least 3 points for a polygon
                    try:
                        scaled_shapely_polygons.append(Polygon(poly_coords_list))
                    except Exception as e:
                        print(f"MapProcessor: Error creating Polygon for centroid for {name}: {e}")

            if scaled_shapely_polygons:
                # If multiple polygons after scaling (from MultiPolygon), unite them for centroid
                country_shape_scaled = unary_union(scaled_shapely_polygons) if len(scaled_shapely_polygons) > 1 else scaled_shapely_polygons[0]
                if country_shape_scaled.is_valid and not country_shape_scaled.is_empty:
                    centroid = country_shape_scaled.centroid
                    self.map_display_config["territory_centroids"][name] = (int(centroid.x), int(centroid.y))
                else:
                    print(f"MapProcessor: Scaled shape for {name} is invalid/empty for centroid calculation. Using default.")
                    self.map_display_config["territory_centroids"][name] = (self.map_area_width // 2, self.map_area_height // 2)
            else:
                # Fallback if no valid scaled polygons were generated
                print(f"MapProcessor: No valid scaled polygons for {name} to calculate centroid. Using default.")
                self.map_display_config["territory_centroids"][name] = (self.map_area_width // 2, self.map_area_height // 2)


    def _generate_map_config_entries(self):
        """Generates entries for map_config.json (territory names)."""
        for country_data in self.countries:
            name = country_data["name"]
            # Adjacencies will be empty for now.
            # Continent will be None as we are not processing continents from this GeoJSON.
            self.map_config["countries"][name] = {"continent": None, "adjacent_to": []}
            # Note: map_config.json uses "territories", but for world map, let's use "countries" internally
            # and the GameEngine will adapt. Or, we stick to "territories" key even for world map.
            # For consistency with GameEngine's current map_config loader, let's use "territories"
            # and just populate it with country data.
            # Decision: Sticking to "countries" for the new map_config to differentiate,
            # GameEngine's initialize_from_map will need to check for this key if game_mode is world_map.

    def get_map_config(self) -> dict:
        # Adjusting the output key to be "territories" for compatibility with current GameEngine map loading
        # if GameEngine is not modified to look for "countries".
        # For now, let's assume GameEngine will be updated.
        return self.map_config

    def get_map_display_config(self) -> dict:
        return self.map_display_config

    def save_configs(self, map_config_path: str, display_config_path: str):
        """Saves the generated configurations to files."""
        # Ensure parent directories exist
        os.makedirs(os.path.dirname(map_config_path), exist_ok=True)
        os.makedirs(os.path.dirname(display_config_path), exist_ok=True)

        try:
            with open(map_config_path, 'w') as f:
                json.dump(self.get_map_config(), f, indent=2)
            print(f"MapProcessor: Successfully saved map config to {map_config_path}")
        except IOError as e:
            print(f"MapProcessor: Error saving map config to {map_config_path}: {e}")

        try:
            with open(display_config_path, 'w') as f:
                json.dump(self.get_map_display_config(), f, indent=2)
            print(f"MapProcessor: Successfully saved display config to {display_config_path}")
        except IOError as e:
            print(f"MapProcessor: Error saving display config to {display_config_path}: {e}")


if __name__ == '__main__':
    # This is a placeholder for where the GeoJSON string would be defined or loaded
    # For the actual run, the user's provided GeoJSON string will be used.
    geojson_input_string = """
    {"type":"FeatureCollection","features":[{"type":"Feature","properties":{"NAME":"CountryA"},"geometry":{"type":"Polygon","coordinates":[[[-10,10],[10,10],[10,-10],[-10,-10],[-10,10]]]}},{"type":"Feature","properties":{"NAME":"CountryB"},"geometry":{"type":"Polygon","coordinates":[[[15,15],[35,15],[35,-5],[15,-5],[15,15]]]}}]}
    """
    geojson_data_dict = json.loads(geojson_input_string)

    # Example usage:
    processor = MapProcessor(geojson_data=geojson_data_dict, map_area_width=900, map_area_height=720)

    # Define output paths (these will be used by the orchestrator later)
    # For testing, save in a local 'generated_maps' folder
    output_dir = "generated_maps"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    world_map_config_file = os.path.join(output_dir, "world_map_config.json")
    world_map_display_config_file = os.path.join(output_dir, "world_map_display_config.json")

    processor.save_configs(world_map_config_file, world_map_display_config_file)

    print("\\nGenerated map_config.json content:")
    print(json.dumps(processor.get_map_config(), indent=2))
    print("\\nGenerated map_display_config.json content:")
    print(json.dumps(processor.get_map_display_config(), indent=2))

    # To use this in the game, you'd pass the GeoJSON data to an instance of MapProcessor,
    # then save the configs. The GameOrchestrator would then load these files
    # when game_mode="world_map".
    # The GeoJSON data itself should be stored perhaps as a large string constant or loaded from a file
    # within the orchestrator or a dedicated data loader when the world_map mode is selected.
    # Adjacency calculation is not yet implemented here.
    # Scaling might need further refinement for complex world maps (e.g. handling antimeridian).
    # Polygon simplification might be needed for performance if GeoJSON is too detailed.
    # GUI's draw_map will need to be updated to use territory_polygons.
"""
