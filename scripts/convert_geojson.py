import json
import os

# --- Configuration ---
# Input files
GEOJSON_FILE_PATH = "world_countries.geojson"  # Expected GeoJSON file
MAP_CONFIG_PATH = "map_config.json"      # Risk map configuration

# Output file
OUTPUT_MAP_DISPLAY_CONFIG_PATH = "map_display_config_polygons.json"

# Target map display dimensions (from gui.py, can be adjusted)
TARGET_MAP_WIDTH = 900
TARGET_MAP_HEIGHT = 700 # SCREEN_HEIGHT from gui.py, effectively
MAP_PADDING = 50  # Padding around the map

# --- Helper Functions ---

def calculate_polygon_centroid(points):
    """Calculates the centroid of a polygon."""
    if not points:
        return [0, 0]
    x_sum = sum(p[0] for p in points)
    y_sum = sum(p[1] for p in points)
    return [x_sum / len(points), y_sum / len(points)]

def calculate_overall_label_position(polygons_data):
    """
    Calculates a label position based on the largest polygon's centroid.
    Polygons_data is a list of polygon structures, where each polygon structure
    is a list of rings, and the first ring is the exterior.
    """
    if not polygons_data:
        return [TARGET_MAP_WIDTH / 2, TARGET_MAP_HEIGHT / 2] # Default fallback

    largest_polygon_exterior = []
    max_points = 0

    for polygon_structure in polygons_data:
        if polygon_structure and polygon_structure[0]: # Check if exterior ring exists
            exterior_ring = polygon_structure[0]
            if len(exterior_ring) > max_points:
                max_points = len(exterior_ring)
                largest_polygon_exterior = exterior_ring

    if not largest_polygon_exterior: # Fallback if no valid polygons found
         return [TARGET_MAP_WIDTH / 2, TARGET_MAP_HEIGHT / 2]

    return calculate_polygon_centroid(largest_polygon_exterior)


def normalize_and_scale_coords(coordinates_data, min_lon, max_lon, min_lat, max_lat):
    """
    Normalizes and scales geographic coordinates (lon, lat) to fit target map dimensions.
    Handles Polygon and MultiPolygon structures.
    """
    scaled_polygons = []

    # Determine the range of geographic coordinates
    lon_range = max_lon - min_lon
    lat_range = max_lat - min_lat

    # Avoid division by zero if the range is zero (e.g., a single point)
    if lon_range == 0: lon_range = 1
    if lat_range == 0: lat_range = 1

    # Calculate scale factors
    # We want to fit the map within TARGET_MAP_WIDTH - 2*MAP_PADDING and TARGET_MAP_HEIGHT - 2*MAP_PADDING
    # The actual drawing area is (TARGET_MAP_WIDTH - 2*MAP_PADDING) x (TARGET_MAP_HEIGHT - 2*MAP_PADDING)
    # Origin (0,0) for drawing is top-left.
    # Latitude increases downwards in screen coordinates.

    scale_x = (TARGET_MAP_WIDTH - 2 * MAP_PADDING) / lon_range
    scale_y = (TARGET_MAP_HEIGHT - 2 * MAP_PADDING) / lat_range

    # Use the smaller scale factor to maintain aspect ratio
    final_scale = min(scale_x, scale_y)

    # Apply scaling to each point in each polygon ring
    for polygon_rings in coordinates_data: # For MultiPolygon, this iterates through each Polygon
        scaled_polygon_rings = []
        for ring in polygon_rings: # Iterates through exterior and interior rings
            scaled_ring = []
            for lon, lat in ring:
                # Normalize (0-1 range)
                norm_x = (lon - min_lon) / lon_range
                norm_y = (lat - min_lat) / lat_range

                # Scale to fit dimensions and apply padding
                # Y is inverted because screen Y increases downwards, latitude increases upwards
                screen_x = MAP_PADDING + norm_x * (TARGET_MAP_WIDTH - 2 * MAP_PADDING)
                screen_y = MAP_PADDING + (1 - norm_y) * (TARGET_MAP_HEIGHT - 2 * MAP_PADDING) # Invert Y
                scaled_ring.append([int(screen_x), int(screen_y)])
            scaled_polygon_rings.append(scaled_ring)
        scaled_polygons.append(scaled_polygon_rings)

    return scaled_polygons

# --- Main Script Logic ---
def main():
    # 1. Load Risk map configuration
    try:
        with open(MAP_CONFIG_PATH, 'r') as f:
            risk_map_config = json.load(f)
        risk_territories = risk_map_config.get("territories", {}).keys()
        if not risk_territories:
            print(f"Error: No territories found in {MAP_CONFIG_PATH}")
            return
    except FileNotFoundError:
        print(f"Error: Risk map config file '{MAP_CONFIG_PATH}' not found.")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{MAP_CONFIG_PATH}'.")
        return

    # 2. Load GeoJSON data
    geojson_data = None
    try:
        # Try to load the actual file if it exists
        if os.path.exists(GEOJSON_FILE_PATH):
            with open(GEOJSON_FILE_PATH, 'r', encoding='utf-8') as f:
                geojson_data = json.load(f)
        else:
            # Fallback to placeholder if file doesn't exist
            print(f"Warning: GeoJSON file '{GEOJSON_FILE_PATH}' not found. Using placeholder data.")
            # This is a very simplified placeholder. A real GeoJSON is much more complex.
            geojson_data = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"ADMIN": "Alaska", "NAME": "Alaska"}, # Common property names
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[-170, 50], [-170, 70], [-130, 70], [-130, 50], [-170, 50]]]
                        }
                    },
                    {
                        "type": "Feature",
                        "properties": {"ADMIN": "Canada", "NAME": "Canada"}, # Example: Canada might map to multiple Risk territories
                        "geometry": {
                            "type": "MultiPolygon",
                            "coordinates": [
                                [[[-140, 50], [-140, 80], [-50, 80], [-50, 50], [-140, 50]]], # Mainland
                                [[[-70, 40], [-70, 45], [-60, 45], [-60, 40], [-70, 40]]]    # An island
                            ]
                        }
                    }
                    # Add more placeholder features if needed for testing
                ]
            }
            print("Using placeholder GeoJSON with Alaska and a mock Canada.")

    except FileNotFoundError: # This block might be redundant now due to os.path.exists check
        print(f"Error: GeoJSON file '{GEOJSON_FILE_PATH}' not found and no placeholder mechanism fully implemented here yet beyond basic.")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{GEOJSON_FILE_PATH}'.")
        return

    if not geojson_data or "features" not in geojson_data:
        print("Error: GeoJSON data is invalid or has no features.")
        return

    # 3. Pre-calculate overall bounds from GeoJSON for scaling
    all_coords = []
    for feature in geojson_data["features"]:
        geom = feature.get("geometry")
        if not geom: continue

        coords_list = []
        if geom["type"] == "Polygon":
            coords_list = geom["coordinates"]
        elif geom["type"] == "MultiPolygon":
            for poly_coords in geom["coordinates"]:
                coords_list.extend(poly_coords) # Add rings from each polygon part

        for ring in coords_list:
            all_coords.extend(ring)

    if not all_coords:
        print("Error: No coordinates found in GeoJSON features to determine bounds.")
        return

    min_lon = min(c[0] for c in all_coords)
    max_lon = max(c[0] for c in all_coords)
    min_lat = min(c[1] for c in all_coords)
    max_lat = max(c[1] for c in all_coords)

    # 4. Process features and map to Risk territories
    output_map_data = {}
    found_risk_territories = set()

    # Name variations for matching GeoJSON properties to Risk territory names
    # (This is crucial and often needs manual adjustment based on the GeoJSON source)
    name_mapping_priority = ["NAME", "ADMIN", "SOVEREIGNT", "formal_en", "name_long", "admin", "name"]

    for feature in geojson_data["features"]:
        props = feature.get("properties", {})
        geom = feature.get("geometry")

        if not geom or ("coordinates" not in geom or not geom["coordinates"]):
            continue

        country_name_from_geojson = None
        for prop_key in name_mapping_priority:
            if prop_key in props:
                country_name_from_geojson = props[prop_key]
                break

        if not country_name_from_geojson:
            # print(f"Warning: Feature found with no recognizable name property. Skipping. Properties: {props}")
            continue

        # Attempt to match GeoJSON country name with Risk territory names
        # This is a simple exact match. More sophisticated matching might be needed (e.g., fuzzy matching, manual map).
        matched_risk_territory = None
        if country_name_from_geojson in risk_territories:
            matched_risk_territory = country_name_from_geojson
        else:
            # Simple check for common variations (e.g., "United States" vs "Western US" / "Eastern US")
            # This part would need significant expansion for a real map.
            if "United States" in country_name_from_geojson:
                # This is a placeholder. A real solution would need to split USA polygon, which is complex.
                # For now, we might assign the whole USA polygon to one if not careful.
                # Or, we could try to map based on which Risk territory is still available.
                if "Western US" in risk_territories and "Western US" not in found_risk_territories:
                    matched_risk_territory = "Western US"
                elif "Eastern US" in risk_territories and "Eastern US" not in found_risk_territories:
                    matched_risk_territory = "Eastern US"
            elif "Russia" in country_name_from_geojson: # Russia might map to Ukraine, Ural, Siberia etc.
                # This is also highly complex.
                pass # Add more specific mapping rules here

        if not matched_risk_territory:
            # print(f"Debug: GeoJSON country '{country_name_from_geojson}' not directly in Risk territories or simple map. Skipping.")
            continue

        if matched_risk_territory in found_risk_territories:
            # print(f"Warning: Risk territory '{matched_risk_territory}' already matched. GeoJSON country '{country_name_from_geojson}' might be a duplicate or requires finer mapping. Skipping.")
            continue


        # Extract and structure coordinates based on geometry type
        current_territory_polygons_geo = [] # List of Polygons (each polygon is a list of rings)
        if geom["type"] == "Polygon":
            # GeoJSON Polygon: [exterior_ring, interior_ring1, interior_ring2, ...]
            # Our format: [ [exterior_ring, interior_ring1, ... ] ] (list containing one polygon structure)
            current_territory_polygons_geo.append(geom["coordinates"])
        elif geom["type"] == "MultiPolygon":
            # GeoJSON MultiPolygon: [poly1_rings, poly2_rings, ...] where poly_rings = [ext_ring, int_ring1,...]
            # Our format: [ poly1_rings, poly2_rings, ... ] (list of multiple polygon structures)
            current_territory_polygons_geo.extend(geom["coordinates"])
        else:
            # print(f"Warning: Unsupported geometry type '{geom['type']}' for '{country_name_from_geojson}'. Skipping.")
            continue

        # Normalize and scale the geographic coordinates to screen coordinates
        scaled_polygons_screen = normalize_and_scale_coords(current_territory_polygons_geo, min_lon, max_lon, min_lat, max_lat)

        # Calculate label position based on the scaled screen coordinates
        label_pos = calculate_overall_label_position(scaled_polygons_screen)

        output_map_data[matched_risk_territory] = {
            "polygons": scaled_polygons_screen,
            "label_position": [int(label_pos[0]), int(label_pos[1])]
        }
        found_risk_territories.add(matched_risk_territory)
        print(f"Successfully processed and mapped: GeoJSON '{country_name_from_geojson}' -> Risk '{matched_risk_territory}'")

    # 5. Check for Risk territories not found in GeoJSON
    missing_territories = [t for t in risk_territories if t not in found_risk_territories]
    if missing_territories:
        print(f"\nWarning: The following Risk territories were not found in the GeoJSON or could not be mapped:")
        for mt in missing_territories:
            print(f"  - {mt}")
        print("You may need to adjust GeoJSON properties, name mapping, or provide placeholder data for them.")
        # Optionally, create dummy data for missing territories:
        for i, mt in enumerate(missing_territories):
            dummy_x = (i % 5) * 100 + 50
            dummy_y = (i // 5) * 100 + 50
            output_map_data[mt] = {
                 "polygons": [[[ [dummy_x-10, dummy_y-10], [dummy_x+10, dummy_y-10], [dummy_x+10, dummy_y+10], [dummy_x-10, dummy_y+10], [dummy_x-10, dummy_y-10] ]]], # Small square
                 "label_position": [dummy_x, dummy_y]
            }
            print(f"  - Added dummy square for missing territory: {mt}")


    # 6. Save the output
    try:
        with open(OUTPUT_MAP_DISPLAY_CONFIG_PATH, 'w') as f:
            json.dump(output_map_data, f, indent=2)
        print(f"\nSuccessfully created '{OUTPUT_MAP_DISPLAY_CONFIG_PATH}' with {len(output_map_data)} territories.")
    except IOError:
        print(f"Error: Could not write output to '{OUTPUT_MAP_DISPLAY_CONFIG_PATH}'.")

if __name__ == "__main__":
    # Create dummy map_config.json if it doesn't exist, for standalone script running
    if not os.path.exists(MAP_CONFIG_PATH):
        print(f"Warning: '{MAP_CONFIG_PATH}' not found. Creating a dummy version for script execution.")
        dummy_map_config = {
            "territories": {
                "Alaska": {}, "Canada": {}, "United States": {} # Simplified for testing
            }
        }
        with open(MAP_CONFIG_PATH, 'w') as f:
            json.dump(dummy_map_config, f, indent=2)

    # Create a dummy world_countries.geojson if it doesn't exist
    if not os.path.exists(GEOJSON_FILE_PATH):
        print(f"Warning: '{GEOJSON_FILE_PATH}' not found. Creating a dummy version for script execution.")
        dummy_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature", "properties": {"ADMIN": "Alaska"},
                    "geometry": {"type": "Polygon", "coordinates": [[[-170,50],[-170,70],[-130,70],[-130,50],[-170,50]]]}
                },
                {
                    "type": "Feature", "properties": {"ADMIN": "Canada"},
                    "geometry": {"type": "Polygon", "coordinates": [[[-130,50],[-130,80],[-60,80],[-60,50],[-130,50]]]}
                },
                 {
                    "type": "Feature", "properties": {"ADMIN": "United States of America"}, # Test name variation
                    "geometry": {"type": "Polygon", "coordinates": [[[-125,25],[-125,49],[-65,49],[-65,25],[-125,25]]]}
                }
            ]
        }
        with open(GEOJSON_FILE_PATH, 'w') as f:
            json.dump(dummy_geojson, f, indent=2)

    main()
    # Clean up dummy files after run if they were created by this script block
    # (This is for cleaner subsequent runs if the user provides actual files)
    # if not os.path.exists(MAP_CONFIG_PATH.replace(".json", "_original.json")): # A bit hacky way to check if it was dummy
    #     if os.path.exists(MAP_CONFIG_PATH) and '"Canada": {}' in open(MAP_CONFIG_PATH).read(): # check if it's the dummy
    #         # os.remove(MAP_CONFIG_PATH) # Decided not to remove, let user manage it.
    #         pass
    # if not os.path.exists(GEOJSON_FILE_PATH.replace(".geojson", "_original.geojson")):
    #      if os.path.exists(GEOJSON_FILE_PATH) and '"United States of America"' in open(GEOJSON_FILE_PATH).read():
    #         # os.remove(GEOJSON_FILE_PATH)
    #         pass

print("Conversion script created at scripts/convert_geojson.py")
print("It includes placeholder GeoJSON data and logic for scaling and transformation.")
print("To use it with actual data, place a 'world_countries.geojson' file in the root directory and run 'python scripts/convert_geojson.py'.")
print("The output will be 'map_display_config_polygons.json'.")

# Note: This script is quite complex and makes many assumptions about GeoJSON structure
# and naming. Real-world GeoJSON can vary, and the name mapping section
# (country_name_from_geojson -> matched_risk_territory) is critical and often requires
# manual configuration or more sophisticated matching logic (e.g., fuzzywuzzy library)
# for robust results with arbitrary GeoJSON files.
# The placeholder for splitting complex countries (like USA into Western/Eastern US)
# is also very basic and would need a geometric library for proper handling.
# The scaling ensures all longitudes/latitudes from the GeoJSON are mapped into the
# defined game map area.
