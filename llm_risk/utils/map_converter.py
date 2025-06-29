import json
import os

# GeoJSON snippet provided by the user
geojson_data_string = """
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": { "admin": "Costa Rica", "gdp_md": 61801 },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[-82.546196, 9.566134], [-82.932890, 9.476812], [-82.927154, 9.074330], [-82.719183, 8.925708], [-82.868657, 8.807266], [-82.829770, 8.626295], [-82.913176, 8.423517], [-82.965783, 8.225027], [-83.508437, 8.446926], [-83.711473, 8.656836], [-83.596313, 8.830443], [-83.632641, 9.051385], [-83.909885, 9.290802], [-84.303401, 9.487354], [-84.647644, 9.615537], [-84.713350, 9.908051], [-84.975660, 10.086723], [-84.911374, 9.795991], [-85.110923, 9.557039], [-85.339488, 9.834542], [-85.660786, 9.933347], [-85.797444, 10.134885], [-85.791708, 10.439337], [-85.659313, 10.754330], [-85.941725, 10.895278], [-85.712540, 11.088444], [-85.561851, 11.217119], [-84.903003, 10.952303], [-84.673069, 11.082657], [-84.355930, 10.999225], [-84.190178, 10.793450], [-83.895054, 10.726839], [-83.655611, 10.938764], [-83.402319, 10.395438], [-83.015676, 9.992982], [-82.546196, 9.566134]]]
      }
    },
    {
      "type": "Feature",
      "properties": { "admin": "Nicaragua", "gdp_md": 12520 },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[-83.655611, 10.938764], [-83.895054, 10.726839], [-84.190178, 10.793450], [-84.355930, 10.999225], [-84.673069, 11.082657], [-84.903003, 10.952303], [-85.561851, 11.217119], [-85.712540, 11.088444], [-86.058488, 11.403438], [-86.525849, 11.806876], [-86.745991, 12.143961], [-87.167516, 12.458257], [-87.668493, 12.909909], [-87.557466, 13.064551], [-87.392386, 12.914018], [-87.316654, 12.984685], [-87.005769, 13.025794], [-86.880557, 13.254204], [-86.733821, 13.263092], [-86.755086, 13.754845], [-86.520708, 13.778487], [-86.312142, 13.771356], [-86.096263, 14.038187], [-85.801294, 13.836054], [-85.698665, 13.960078], [-85.514413, 14.079011], [-85.165364, 14.354369], [-85.148750, 14.560196], [-85.052787, 14.551541], [-84.924500, 14.790492], [-84.820036, 14.819586], [-84.649582, 14.666805], [-84.449335, 14.621614], [-84.228341, 14.748764], [-83.975721, 14.749435], [-83.628584, 14.880073], [-83.489988, 15.016267], [-83.147219, 14.995829], [-83.233234, 14.899866], [-83.284161, 14.676623], [-83.182126, 14.310703], [-83.412499, 13.970077], [-83.519831, 13.567699], [-83.552207, 13.127054], [-83.498515, 12.869292], [-83.473323, 12.419087], [-83.626104, 12.320850], [-83.719613, 11.893124], [-83.650857, 11.629032], [-83.855470, 11.373311], [-83.808935, 11.103043], [-83.655611, 10.938764]]]
      }
    },
    {
      "type": "Feature",
      "properties": { "admin": "Haiti", "gdp_md": 14332 },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[-71.712361, 19.714455], [-71.624873, 19.169837], [-71.701302, 18.785416], [-71.945112, 18.616900], [-71.687737, 18.316660], [-71.708304, 18.044997], [-72.372476, 18.214960], [-72.844411, 18.145611], [-73.454554, 18.217906], [-73.922433, 18.030992], [-74.458033, 18.342549], [-74.369925, 18.664907], [-73.449542, 18.526052], [-72.694937, 18.445799], [-72.334881, 18.668421], [-72.791649, 19.101625], [-72.784104, 19.483591], [-73.415022, 19.639550], [-73.189790, 19.915683], [-72.579672, 19.871500], [-71.712361, 19.714455]]]
      }
    },
    {
      "type": "Feature",
      "properties": { "admin": "Dominican Rep.", "gdp_md": 88941 },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[-71.708304, 18.044997], [-71.687737, 18.316660], [-71.945112, 18.616900], [-71.701302, 18.785416], [-71.624873, 19.169837], [-71.712361, 19.714455], [-71.587304, 19.884910], [-70.806706, 19.880285], [-70.214364, 19.622885], [-69.950815, 19.647999], [-69.769250, 19.293267], [-69.222125, 19.313214], [-69.254346, 19.015196], [-68.809411, 18.979074], [-68.317943, 18.612197], [-68.689315, 18.205142], [-69.164945, 18.422648], [-69.623987, 18.380712], [-69.952933, 18.428306], [-70.133232, 18.245915], [-70.517137, 18.184290], [-70.669298, 18.426885], [-70.999950, 18.283328], [-71.400209, 17.598564], [-71.657661, 17.757572], [-71.708304, 18.044997]]]
      }
    }
  ]
}
"""

# Define the target display area for the map
MAP_DISPLAY_WIDTH = 900
MAP_DISPLAY_HEIGHT = 700

# def get_bounding_box(features): # Commented out for timeout debugging
#     min_lon, min_lat = float('inf'), float('inf')
#     max_lon, max_lat = float('-inf'), float('-inf')
#     for feature in features:
#         geom_type = feature["geometry"]["type"]
#         coordinates = feature["geometry"]["coordinates"]
#         if geom_type == "Polygon":
#             coordinates = [coordinates]
#         for polygon in coordinates:
#             for ring in polygon:
#                 for lon, lat in ring:
#                     min_lon = min(min_lon, lon)
#                     max_lon = max(max_lon, lon)
#                     min_lat = min(min_lat, lat)
#                     max_lat = max(max_lat, lat)
#     return min_lon, min_lat, max_lon, max_lat

# def scale_coordinates(lon, lat, bbox, target_width, target_height, padding=20): # Commented out
#     min_lon, min_lat, max_lon, max_lat = bbox
#     effective_width = target_width - 2 * padding
#     effective_height = target_height - 2 * padding
#     scale_x = effective_width / (max_lon - min_lon) if (max_lon - min_lon) != 0 else 1
#     scale_y = effective_height / (max_lat - min_lat) if (max_lat - min_lat) != 0 else 1
#     scale = min(scale_x, scale_y)
#     scaled_x = padding + (lon - min_lon) * scale
#     scaled_y = padding + (max_lat - lat) * scale
#     return int(scaled_x), int(scaled_y)

def process_geojson_to_configs(geojson_str, map_config_path, display_config_path):
    try:
        data = json.loads(geojson_str)
    except json.JSONDecodeError as e:
        print(f"Error decoding GeoJSON: {e}")
        return

    features = data.get("features", [])
    if not features:
        print("No features found in GeoJSON data.")
        return

    # Bounding box and display config are commented out.
    # Focus only on processing territories for map_config.json.

    territories_map_config_additions = {}
    new_territory_names = []

    for feature in features:
        props = feature.get("properties", {})
        country_name = props.get("admin", props.get("name", f"UnknownTerritory_{len(territories_map_config_additions)}"))
        new_territory_names.append(country_name)

        gdp_md = props.get("gdp_md", 0)
        initial_armies = 3 # Default
        if country_name == "Dominican Rep." or gdp_md > 80000: initial_armies = 10
        elif country_name == "Costa Rica" or gdp_md > 50000: initial_armies = 7
        elif country_name == "United States of America": initial_armies = 12
        elif country_name == "France": initial_armies = 9
        elif country_name == "Nicaragua" or gdp_md > 10000: initial_armies = 5
        else: initial_armies = 3

        territories_map_config_additions[country_name] = {
            "initial_armies_override": initial_armies
            # "continent" and "adjacent_to" will be preserved or defaulted by the loading logic below
        }

    # Update map_config.json
    map_data_to_update = {
        "continents": [{"name": "World", "bonus_armies": 0, "territories": []}],
        "territories": {}
    }
    if os.path.exists(map_config_path):
        try:
            with open(map_config_path, 'r') as f_read:
                map_data_to_update = json.load(f_read)
        except json.JSONDecodeError:
            print(f"Warning: Could not decode existing {map_config_path}. Starting fresh for this file.")

    # Ensure "territories" key exists
    if "territories" not in map_data_to_update:
        map_data_to_update["territories"] = {}

    for terr_name, terr_details_additions in territories_map_config_additions.items():
        if terr_name not in map_data_to_update["territories"]:
            map_data_to_update["territories"][terr_name] = {
                "continent": "World", # Default new territories to "World"
                "adjacent_to": [],    # Default new territories to no adjacencies
                "initial_armies_override": terr_details_additions["initial_armies_override"]
            }
        else: # Preserve existing continent and adjacencies, only update army override
            map_data_to_update["territories"][terr_name]["initial_armies_override"] = terr_details_additions["initial_armies_override"]
            if "continent" not in map_data_to_update["territories"][terr_name]:
                 map_data_to_update["territories"][terr_name]["continent"] = "World"
            if "adjacent_to" not in map_data_to_update["territories"][terr_name]:
                 map_data_to_update["territories"][terr_name]["adjacent_to"] = []


    # Update the 'World' continent's territory list if it exists
    world_continent_found = False
    if "continents" not in map_data_to_update: # Ensure continents list exists
        map_data_to_update["continents"] = []

    for cont_data in map_data_to_update.get("continents", []):
        if cont_data.get("name") == "World":
            current_continent_territories = set(cont_data.get("territories", []))
            current_continent_territories.update(new_territory_names)
            cont_data["territories"] = sorted(list(current_continent_territories))
            world_continent_found = True
            break
    if not world_continent_found: # If "World" continent doesn't exist, add it
        map_data_to_update["continents"].append({
            "name": "World",
            "bonus_armies": 0,
            "territories": sorted(list(set(new_territory_names)))
        })

    try:
        with open(map_config_path, 'w') as f:
            json.dump(map_data_to_update, f, indent=2)
        print(f"Simplified update of '{map_config_path}' complete with army overrides.")
    except IOError as e:
        print(f"Error writing to {map_config_path}: {e}")

    print(f"Skipped writing display config file '{display_config_path}' for timeout debugging.")


if __name__ == "__main__":
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # Ensure target directory exists
    target_dir = project_root # Store in project root for simplicity during debug
    # target_dir = os.path.join(project_root, "llm_risk_maps")
    # if not os.path.exists(target_dir):
    #     try:
    #         os.makedirs(target_dir)
    #     except OSError as e:
    #         print(f"Error creating directory {target_dir}: {e}")
    #         target_dir = project_root

    world_map_config_file = os.path.join(target_dir, "world_map_config.json")

    if not os.path.exists(world_map_config_file):
        initial_world_config = {
            "continents": [{"name": "World", "bonus_armies": 0, "territories": []}],
            "territories": {}
        }
        try:
            with open(world_map_config_file, 'w') as f:
                json.dump(initial_world_config, f, indent=2)
            print(f"Initialized empty '{world_map_config_file}'.")
        except IOError as e:
            print(f"Could not initialize {world_map_config_file}: {e}")

    dummy_display_path = os.path.join(target_dir, "dummy_world_map_display_config_not_written.json")

    process_geojson_to_configs(geojson_data_string, world_map_config_file, dummy_display_path)
    print("GeoJSON processing (for map_config.json only) complete.")
