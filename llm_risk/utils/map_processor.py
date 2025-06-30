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
        self.country_shapes_for_adjacency = {} # To store Shapely objects for adjacency calculation
        self.country_to_continent_map = {} # To store continent for each country

        self._extract_country_data() # This will now also populate country_to_continent_map
        self._generate_continent_config() # New method to create continent entries
        self._calculate_adjacencies() # Calculate after extracting continents
        self._normalize_and_scale_polygons() # Scaling for display
        # _generate_map_config_entries is effectively replaced by _calculate_adjacencies and _generate_continent_config
        # for the structure of map_config.

    def _extract_country_data(self):
        """Extracts country name, geometry, and continent from GeoJSON features."""
        print("MapProcessor: Starting _extract_country_data...")
        extracted_continent_names = set()
        processed_feature_count = 0
        successful_extractions = 0

        features = self.geojson_data.get("features", [])
        print(f"MapProcessor: Found {len(features)} features in GeoJSON.")

        for i, feature in enumerate(features):
            processed_feature_count += 1
            properties = feature.get("properties", {})
            geometry = feature.get("geometry")

            # Detailed logging of raw properties
            # print(f"MapProcessor: Processing feature {i+1}/{len(features)}. Properties: {properties}")

            name = properties.get("NAME")
            if not name:
                name = properties.get("name")

            continent_name = properties.get("continent")
            if not continent_name: continent_name = properties.get("CONTINENT")
            if not continent_name: continent_name = properties.get("region_un")
            if not continent_name: continent_name = properties.get("region_wb")
            if not continent_name: continent_name = "Unknown"

            if not name:
                print(f"MapProcessor: Feature {i+1} missing 'NAME' or 'name' property. Skipping.")
                continue
            if not geometry:
                print(f"MapProcessor: Feature {i+1} for '{name}' missing 'geometry'. Skipping.")
                continue

            try:
                geom_shape = shape(geometry)
                is_valid_shape = geom_shape.is_valid
                is_empty_shape = geom_shape.is_empty

                # print(f"MapProcessor: Feature '{name}': Extracted Name='{name}', Continent='{continent_name}'. Shape valid: {is_valid_shape}, Shape empty: {is_empty_shape}")

                if is_valid_shape and not is_empty_shape:
                    self.countries.append({
                        "name": name,
                        "shape": geom_shape,
                        "continent": continent_name,
                        "original_geojson_coords": geometry.get("coordinates") # Keep for potential debugging
                    })
                    self.country_shapes_for_adjacency[name] = geom_shape
                    self.country_to_continent_map[name] = continent_name
                    if continent_name != "Unknown":
                         extracted_continent_names.add(continent_name)
                    successful_extractions += 1
                else:
                    print(f"MapProcessor: Invalid or empty geometry for {name} (Valid: {is_valid_shape}, Empty: {is_empty_shape}). Skipping.")
            except Exception as e:
                print(f"MapProcessor: Error processing geometry for {name}: {e}. Skipping.")

        print(f"MapProcessor: Processed {processed_feature_count} features.")
        print(f"MapProcessor: Successfully extracted {successful_extractions} valid countries with shapes.")
        self.countries.sort(key=lambda x: x["name"]) # Sort for consistent processing later if needed
        print(f"MapProcessor: Found unique continents in GeoJSON: {sorted(list(extracted_continent_names))}")
        if not self.countries:
            print("MapProcessor: CRITICAL - No countries were extracted. Check GeoJSON structure and 'NAME'/'name' properties.")


    def _generate_continent_config(self, default_bonus: int = 3):
        """Generates the 'continents' part of map_config.json."""
        gs_continents = {}
        continent_territories = {} # Temp dict to group territories by continent

        for country_data in self.countries:
            name = country_data["name"]
            continent_name = self.country_to_continent_map.get(name, "Unknown")
            if continent_name == "Unknown":
                continue # Skip countries with unknown continent for continent config

            if continent_name not in continent_territories:
                continent_territories[continent_name] = []
            continent_territories[continent_name].append(name)

        for continent_name, territories in continent_territories.items():
            # Use a default bonus, or derive one (e.g., based on number of territories)
            # Standard Risk continent bonuses: NA=5, SA=2, EU=5, AF=3, AS=7, AU=2
            # For now, let's use a default, can be refined.
            bonus = default_bonus
            if continent_name == "Asia": bonus = 7
            elif continent_name == "Europe": bonus = 5
            elif continent_name == "North America": bonus = 5
            elif continent_name == "Africa": bonus = 3
            elif continent_name == "South America": bonus = 2
            elif continent_name == "Oceania": bonus = 2 # Assuming "Oceania" might be a value

            gs_continents[continent_name] = {
                "name": continent_name,
                "bonus_armies": bonus,
                "territories": sorted(territories) # List of country names in this continent
            }

        # Convert dict to list of dicts for map_config.json format
        self.map_config["continents"] = [cont_data for cont_data in gs_continents.values()]
        print(f"MapProcessor: Generated continent configurations for {len(self.map_config['continents'])} continents.")
        # Add a sample print:
        if self.map_config["continents"]:
            print(f"MapProcessor: Sample continent config: {json.dumps(self.map_config['continents'][0], indent=2)}")


    def _calculate_adjacencies(self):
        """Calculates adjacencies between countries and populates map_config."""
        print("MapProcessor: Calculating adjacencies...")
        country_names = list(self.country_shapes_for_adjacency.keys())

        # Initialize/ensure "countries" structure in map_config
        if "countries" not in self.map_config: # Should be {"continents": [], "countries": {}}
            self.map_config["countries"] = {}

        for name in country_names:
            if name not in self.map_config["countries"]: # If a country was valid for shape but not for continent processing (e.g. "Unknown" continent)
                self.map_config["countries"][name] = {
                    "continent": self.country_to_continent_map.get(name, "Unknown"),
                    "adjacent_to": []
                }
            else: # Entry might exist if _generate_continent_config created it (though unlikely now with changed order)
                 self.map_config["countries"][name]["continent"] = self.country_to_continent_map.get(name, "Unknown") # Ensure continent is set
                 if "adjacent_to" not in self.map_config["countries"][name]: # Should always be true if this runs after _generate_continent_config
                      self.map_config["countries"][name]["adjacent_to"] = []


        for i in range(len(country_names)):
            for j in range(i + 1, len(country_names)):
                name1 = country_names[i]
                name2 = country_names[j]
                shape1 = self.country_shapes_for_adjacency[name1]
                shape2 = self.country_shapes_for_adjacency[name2]

                # Using `touches` for shared boundaries.
                # A very small positive buffer can sometimes help with floating point inaccuracies
                # if `touches` is too strict, but start without it.
                # if shape1.is_valid and shape2.is_valid and shape1.touches(shape2):
                # Using intersects with a small buffer might be more robust for imperfect GeoJSON data
                # but can also connect things that only touch at a point if buffer is too large.
                # Let's try with a small intersection check first, as 'touches' can be very strict.
                # A common approach is to check if intersection is not a Point or LineString (implies area overlap or shared line)
                # but `touches` is specifically for shared boundaries without interior overlap.

                # Using `intersects` and checking the type of intersection can be more robust.
                # However, for simplicity and typical adjacency, `touches` is often preferred.
                # If `touches` fails for some valid adjacencies due to data precision,
                # then `shape1.buffer(1e-9).intersects(shape2.buffer(1e-9))` could be an alternative.
                # For now, using `touches`.
                try:
                    if shape1.touches(shape2):
                        self.map_config["countries"][name1]["adjacent_to"].append(name2)
                        self.map_config["countries"][name2]["adjacent_to"].append(name1)
                except Exception as e:
                    print(f"MapProcessor: Error checking adjacency between {name1} and {name2}: {e}")

        for name in country_names: # Ensure all country entries exist even if no adjacencies
            if name in self.map_config["countries"]:
                 self.map_config["countries"][name]["adjacent_to"].sort()
            else: # Should not happen if initialization above is correct
                 print(f"MapProcessor: Warning - country {name} was in shapes but not in map_config['countries'] for adjacency sort.")


        print(f"MapProcessor: Adjacency calculation complete. Example for {country_names[0] if country_names else 'N/A'}: {self.map_config['countries'].get(country_names[0] if country_names else '', {}).get('adjacent_to')}")
        # Add a sample print for the "countries" structure
        if country_names:
            sample_country_name = country_names[0]
            print(f"MapProcessor: Sample country config for '{sample_country_name}': {json.dumps(self.map_config['countries'].get(sample_country_name, {}), indent=2)}")


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
            scaled_shapely_polygons = []
            for poly_coords_list in scaled_polygons_for_country:
                if len(poly_coords_list) >= 3: # Need at least 3 points for a polygon
                    try:
                        polygon = Polygon(poly_coords_list)
                        if not polygon.is_valid:
                            # Try to fix invalid polygon
                            polygon = polygon.buffer(0)
                        if polygon.is_valid and not polygon.is_empty:
                            scaled_shapely_polygons.append(polygon)
                        # else:
                            # print(f"MapProcessor: Scaled polygon part for {name} is invalid or empty after buffer(0). Skipping this part for centroid.")
                    except Exception as e:
                        print(f"MapProcessor: Error creating/validating Polygon part for centroid for {name}: {e}")

            if scaled_shapely_polygons:
                final_shape_for_centroid = None
                if len(scaled_shapely_polygons) > 1:
                    try:
                        final_shape_for_centroid = unary_union(scaled_shapely_polygons)
                        if not final_shape_for_centroid.is_valid:
                            final_shape_for_centroid = final_shape_for_centroid.buffer(0)
                    except Exception as e: # Catches GEOSException like TopologyException
                        print(f"MapProcessor: unary_union failed for {name}: {e}. Trying largest valid part for centroid.")
                        valid_polys_for_largest = [p for p in scaled_shapely_polygons if p.is_valid and not p.is_empty]
                        if valid_polys_for_largest:
                            final_shape_for_centroid = max(valid_polys_for_largest, key=lambda p: p.area)
                        else:
                            final_shape_for_centroid = None
                elif len(scaled_shapely_polygons) == 1:
                    final_shape_for_centroid = scaled_shapely_polygons[0]

                if final_shape_for_centroid and final_shape_for_centroid.is_valid and not final_shape_for_centroid.is_empty:
                    centroid = final_shape_for_centroid.centroid
                    self.map_display_config["territory_centroids"][name] = (int(centroid.x), int(centroid.y))
                else:
                    print(f"MapProcessor: No valid shape for centroid calculation for {name} after fallbacks. Using default.")
                    self.map_display_config["territory_centroids"][name] = (self.map_area_width // 2, self.map_area_height // 2)
            else:
                # Fallback if no valid scaled polygons were generated at all
                print(f"MapProcessor: No valid scaled polygon parts for {name} to calculate centroid. Using default.")
                self.map_display_config["territory_centroids"][name] = (self.map_area_width // 2, self.map_area_height // 2)

    # The _generate_map_config_entries method was previously responsible for creating the
    # self.map_config["countries"] structure. This initialization is now handled within
    # _calculate_adjacencies, which also populates the continent for each country.
    # Therefore, _generate_map_config_entries as a separate method for this purpose is removed.

    def get_map_config(self) -> dict:
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
    # Adjacency calculation is not yet implemented here. # This was actually done
    # Scaling might need further refinement for complex world maps (e.g. handling antimeridian).
    # Polygon simplification might be needed for performance if GeoJSON is too detailed.
    # GUI's draw_map will need to be updated to use territory_polygons. # This was also done
"""
"""
