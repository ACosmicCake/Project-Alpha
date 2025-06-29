import json
from llm_risk.game_orchestrator import GameOrchestrator
from game_modes import RealWorldGameMode # Import the new game mode
from dotenv import load_dotenv

# Define available AI types and colors
AVAILABLE_AI_TYPES = ["OpenAI", "Gemini", "Claude", "DeepSeek","Llama","Mistral","Qwen"] # Add "Human" if you implement human players
AVAILABLE_COLORS = ["Red", "Blue", "Green", "Yellow", "Purple", "Orange"]

def load_json_data(file_path):
    """Loads JSON data from a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: The file {file_path} was not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: The file {file_path} is not a valid JSON file.")
        return None

def get_player_configurations(game_mode_type):
    """
    Gets player configurations for the game based on user input.
    """
    player_configs = []
    num_players = 0
    while True:
        try:
            num_players = int(input("Enter the number of AI players (2-6): "))
            if 2 <= num_players <= 6:
                break
            else:
                print("Please enter a number between 2 and 6.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    for i in range(num_players):
        name = f"AI_Player_{i+1}"
        color = AVAILABLE_COLORS[i % len(AVAILABLE_COLORS)] # Assign colors cyclically
        ai_type = ""
        while ai_type not in AVAILABLE_AI_TYPES:
            ai_type = input(f"Enter AI type for {name} {AVAILABLE_AI_TYPES}: ").strip()
            if ai_type not in AVAILABLE_AI_TYPES:
                print(f"Invalid AI type. Please choose from {AVAILABLE_AI_TYPES}.")
        player_configs.append({"name": name, "color": color, "ai_type": ai_type})
    return player_configs

def main():
    """Main function to run the game."""
    load_dotenv()

    # Determine game mode
    game_mode_type = input("Enter game mode (default / real_world): ").lower()

    if game_mode_type == 'real_world':
        geojson_data = load_json_data(r'C:\Users\Kosmic\Desktop\Job Agent\Project-Alpha\map_display_config_polygons.json')
        map_config = load_json_data(r'C:\Users\Kosmic\Desktop\Job Agent\Project-Alpha\map_config.json')
        
        if geojson_data and map_config:
            military_power_ratios = map_config.get('military_power_ratios', {})
            game_mode = RealWorldGameMode(geojson_string_data=json.dumps(geojson_data), 
                                          military_power_ratios=military_power_ratios)
            custom_player_configs = get_player_configurations(game_mode_type)
            orchestrator = GameOrchestrator(player_configs_override=custom_player_configs, game_mode_override=game_mode)
            orchestrator.run_game()
    else:
        custom_player_configs = get_player_configurations(game_mode_type)
        orchestrator = GameOrchestrator(player_configs_override=custom_player_configs)
        orchestrator.run_game()

if __name__ == "__main__":
    main()