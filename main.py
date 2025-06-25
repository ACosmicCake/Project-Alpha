"""
Main entry point for the LLM Risk Game application.
Allows for console-based configuration of players and AI types.
"""
from llm_risk.game_orchestrator import GameOrchestrator


# Define available AI types and colors
AVAILABLE_AI_TYPES = ["OpenAI", "Gemini", "Claude", "DeepSeek"] # Add "Human" if you implement human players
AVAILABLE_COLORS = ["Red", "Blue", "Green", "Yellow", "Purple", "Orange"]

def get_player_configurations_from_console():
    """
    Prompts the user in the console to define player configurations.
    Returns a list of player configuration dictionaries or None if skipped.
    """
    print("\n--- LLM Risk Game Setup ---")
    print("Configure players and AI types. Press Enter at the first prompt to skip and use default player_config.json.")

    while True:
        try:
            num_players_str = input(f"Enter number of players (2-{len(AVAILABLE_COLORS)}, or 0 to skip): ").strip()
            if not num_players_str: # User pressed Enter
                print("Skipping console configuration. Using default player_config.json.")
                return None

            num_players = int(num_players_str)
            if num_players == 0:
                print("Skipping console configuration. Using default player_config.json.")
                return None
            if 2 <= num_players <= len(AVAILABLE_COLORS):
                break
            else:
                print(f"Please enter a number between 2 and {len(AVAILABLE_COLORS)}.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    player_configs = []
    used_names = set()
    used_colors = set()

    for i in range(num_players):
        print(f"\n--- Configuring Player {i+1} ---")

        # Player Name
        while True:
            name = input(f"Enter name for Player {i+1}: ").strip()
            if not name:
                print("Name cannot be empty.")
                continue
            if name in used_names:
                print(f"Name '{name}' is already taken. Please choose a different name.")
                continue
            used_names.add(name)
            break

        # AI Type
        print("Available AI types:")
        for idx, ai_type in enumerate(AVAILABLE_AI_TYPES):
            print(f"  {idx + 1}. {ai_type}")

        while True:
            try:
                ai_choice_str = input(f"Choose AI type for {name} (number): ").strip()
                ai_choice = int(ai_choice_str) - 1
                if 0 <= ai_choice < len(AVAILABLE_AI_TYPES):
                    selected_ai_type = AVAILABLE_AI_TYPES[ai_choice]
                    break
                else:
                    print(f"Invalid choice. Please enter a number between 1 and {len(AVAILABLE_AI_TYPES)}.")
            except ValueError:
                print("Invalid input. Please enter a number.")

        # Assign Color (can be made a choice later if desired)
        player_color = AVAILABLE_COLORS[i % len(AVAILABLE_COLORS)] # Cycle through colors
        if player_color in used_colors: # Should not happen if num_players <= len(AVAILABLE_COLORS)
            # Fallback if somehow a color is repeated (e.g. more players than colors)
            # This part is more robust if color selection is also manual
            for c in AVAILABLE_COLORS:
                if c not in used_colors:
                    player_color = c
                    break
        used_colors.add(player_color)

        player_configs.append({
            "name": name,
            "color": player_color,
            "ai_type": selected_ai_type
        })
        print(f"Player {name} configured as {selected_ai_type} with color {player_color}.")

    return player_configs

def main():
    """
    Initializes and runs the LLM Risk game.
    Allows for console-based player configuration.
    """
    print("LLM Risk Game - Main Application Starting...")

    custom_player_configs = get_player_configurations_from_console()

    # Instantiate the GameOrchestrator.
    # If custom_player_configs is None, GameOrchestrator will use its default player_config.json.
    # Otherwise, it will use the configurations provided by the user.
    # This requires GameOrchestrator to be modified to accept this parameter.
    if custom_player_configs:
        print("\nUsing custom player configurations from console.")
        orchestrator = GameOrchestrator(player_configs_override=custom_player_configs)
    else:
        print("\nUsing default player configurations (player_config.json).")
        orchestrator = GameOrchestrator() # Assumes GameOrchestrator handles player_config.json by default

    # Run the game.
    orchestrator.run_game()

    print("LLM Risk Game - Application Finished.")

if __name__ == "__main__":
    main()
