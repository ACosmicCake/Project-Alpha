import pygame
import sys
from map_data import (
    SCREEN_WIDTH, SCREEN_HEIGHT, TEXT_COLOR, DEFAULT_TERRITORY_COLOR, HOVER_TERRITORY_COLOR, SELECTED_TERRITORY_COLOR,
    TERRITORIES, CONNECTIONS_LINES, LINE_COLOR, CONTINENTS, PLAYER_COLORS
)
from game_state import GameState
import random
import ai_player # Import the AI player logic

# --- Pygame Setup ---
pygame.init()
pygame.font.init() # Initialize the font module

# Screen setup
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Risk Game UI")

# Font for labels (using a default system font)
try:
    FONT = pygame.font.SysFont(None, 24) # Use default system font, size 24
    SMALL_FONT = pygame.font.SysFont(None, 18)
except Exception as e:
    print(f"Could not load default system font: {e}. Using pygame's default font.")
    FONT = pygame.font.Font(None, 24) # Pygame's default font
    SMALL_FONT = pygame.font.Font(None, 18)

# This will be our main drawing surface for the map
map_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
map_surface.fill((240, 240, 240)) # A light background color for the map surface, not the screen background


def draw_text(surface, text, position, font, color=TEXT_COLOR):
    """Helper function to draw text on a surface."""
    text_surface = font.render(text, True, color)
    # Center the text if the position is a center point, otherwise use as top-left
    text_rect = text_surface.get_rect(center=position if isinstance(position, tuple) and len(position) == 2 else position)
    surface.blit(text_surface, text_rect)


def is_point_in_polygon(point, polygon_vertices):
    """
    Check if a point is inside a polygon using the ray casting algorithm.
    point: (x, y)
    polygon_vertices: list of (x, y) tuples
    """
    x, y = point
    n = len(polygon_vertices)
    inside = False

    p1x, p1y = polygon_vertices[0]
    for i in range(n + 1):
        p2x, p2y = polygon_vertices[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def get_territory_color(gs, territory_id, selected_territory_id, hovered_territory_id):
    """Gets the color for a territory, based on owner, selection, or hover state."""
    owner_color = gs.get_territory_owner_color(territory_id)

    if territory_id == selected_territory_id:
        # Blend selection color with owner color if owned, otherwise use plain selection color
        base_color = owner_color if owner_color else DEFAULT_TERRITORY_COLOR
        # Simple way to make it look distinct: average with white or a highlight color
        # For now, just use SELECTED_TERRITORY_COLOR directly if selected
        return SELECTED_TERRITORY_COLOR

    if territory_id == hovered_territory_id:
        # Blend hover color
        base_color = owner_color if owner_color else DEFAULT_TERRITORY_COLOR
        # For now, just use HOVER_TERRITORY_COLOR
        return HOVER_TERRITORY_COLOR

    if owner_color:
        return owner_color

    # Fallback to continent color if no owner and not selected/hovered
    # territory_data = TERRITORIES.get(territory_id)
    # if territory_data:
    #     continent_id = territory_data.get("continent_id")
    #     continent_data = CONTINENTS.get(continent_id)
    #     if continent_data and "color" in continent_data:
    #         return continent_data["color"] # This color should have alpha from map_data

    return DEFAULT_TERRITORY_COLOR # Default for unowned, not hovered, not selected


def draw_territories(surface, gs, selected_territory_id, hovered_territory_id):
    """Draws all territories on the given surface, including army counts."""
    for terr_id, data in gs.territories_state.items(): # Use game_state's territory data
        color = get_territory_color(gs, terr_id, selected_territory_id, hovered_territory_id)

        # Draw filled polygon for territory
        pygame.draw.polygon(surface, color, data["polygon_coords"])
        # Draw border
        pygame.draw.polygon(surface, LINE_COLOR, data["polygon_coords"], 2)

        # Draw territory name
        name_pos = (data["label_coords"][0], data["label_coords"][1] - 8) # Adjust upwards for army count
        draw_text(surface, data["name"], name_pos, SMALL_FONT, TEXT_COLOR)

        # Draw army count
        army_pos = (data["label_coords"][0], data["label_coords"][1] + 8) # Adjust downwards
        draw_text(surface, str(data["armies"]), army_pos, FONT, TEXT_COLOR)


def get_player_config_input(prompt_text, valid_keys, current_value=""):
    """Helper for text input during setup. Not a full input box, just handles key presses for simple choices."""
    input_active = True
    user_text = current_value

    while input_active:
        screen.fill((220, 220, 220)) # Light grey background for setup screen

        # Draw the prompt
        prompt_surface = FONT.render(prompt_text + user_text, True, TEXT_COLOR)
        prompt_rect = prompt_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 50))
        screen.blit(prompt_surface, prompt_rect)

        # Draw valid options hint
        options_hint = FONT.render(f"Valid: {', '.join(valid_keys.keys())}. ENTER to confirm.", True, (100,100,100))
        hint_rect = options_hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
        screen.blit(options_hint, hint_rect)

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    if user_text in valid_keys.values(): # Check if current input is a valid *result*
                        return user_text
                    # For numeric input, this needs adjustment, here we assume single key press maps to value
                elif event.key == pygame.K_BACKSPACE:
                     user_text = user_text[:-1]
                else:
                    # Check if pressed key corresponds to a valid choice key
                    key_char = event.unicode.upper() # Or pygame.key.name(event.key).upper()
                    if key_char in valid_keys:
                        user_text = valid_keys[key_char] # Directly set to the value
                        # For multi-char input (like numbers), append: user_text += event.unicode
                        # For this specific setup, we expect single key for H/A or numbers 2-6

    return None # Should not be reached if loop is exited by RETURN


def configure_game_setup():
    """Handles the UI for configuring number of players and their types."""
    num_players = 0
    player_types = []
    current_stage = "NUM_PLAYERS" # NUM_PLAYERS, PLAYER_TYPES

    input_text = ""

    configuring = True
    while configuring:
        screen.fill((200, 200, 220)) # Setup screen background

        prompt_y = SCREEN_HEIGHT // 2 - 100

        if current_stage == "NUM_PLAYERS":
            prompt = "Enter number of players (2-6): " + input_text
            draw_text(screen, prompt, (SCREEN_WIDTH // 2, prompt_y), FONT, TEXT_COLOR)
            draw_text(screen, "Press ENTER to confirm.", (SCREEN_WIDTH // 2, prompt_y + 40), SMALL_FONT, (100,100,100))

        elif current_stage == "PLAYER_TYPES":
            player_num_display = len(player_types) + 1
            prompt = f"Player {player_num_display} type - Human (H) or AI (A): " + input_text
            draw_text(screen, prompt, (SCREEN_WIDTH // 2, prompt_y), FONT, TEXT_COLOR)
            draw_text(screen, "Press ENTER to confirm type.", (SCREEN_WIDTH // 2, prompt_y + 40), SMALL_FONT, (100,100,100))

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None # Indicate quit
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: # Allow escape to quit setup
                    return None

                if current_stage == "NUM_PLAYERS":
                    if event.key == pygame.K_RETURN:
                        if input_text.isdigit() and 2 <= int(input_text) <= 6:
                            num_players = int(input_text)
                            input_text = ""
                            current_stage = "PLAYER_TYPES"
                            if num_players == 0: # Should not happen if logic is right
                                current_stage = "NUM_PLAYERS" # Go back
                        else:
                            input_text = "" # Clear invalid input
                            # Optionally, show an error message briefly
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif event.unicode.isdigit():
                        input_text += event.unicode

                elif current_stage == "PLAYER_TYPES":
                    if event.key == pygame.K_RETURN:
                        type_choice = input_text.upper()
                        if type_choice == "H":
                            player_types.append("human")
                            input_text = ""
                        elif type_choice == "A":
                            player_types.append("ai_easy") # Default AI type
                            input_text = ""
                        else:
                            input_text = "" # Clear invalid input

                        if len(player_types) == num_players:
                            configuring = False # All players configured
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif event.unicode.isalpha():
                        input_text += event.unicode.upper() # Keep it simple, allow only one char for H/A
                        if len(input_text) > 1: input_text = input_text[-1]


    return {"num_players": num_players, "player_types": player_types}


def draw_connections(surface, gs):
    """Draws lines connecting territories based on their label_coords."""
    drawn_connections = set()
    for terr_id1, terr_id2 in CONNECTIONS_LINES:
        # Create a canonical representation of the connection pair
        connection_pair = tuple(sorted((terr_id1, terr_id2)))
        if connection_pair in drawn_connections:
            continue

        if terr_id1 in TERRITORIES and terr_id2 in TERRITORIES:
            pos1 = TERRITORIES[terr_id1]["label_coords"]
            pos2 = TERRITORIES[terr_id2]["label_coords"]
            pygame.draw.line(surface, LINE_COLOR, pos1, pos2, 1)
            drawn_connections.add(connection_pair)


def main():
    """Main game loop."""

    # --- New Game Setup UI Loop ---
    setup_configs = configure_game_setup()
    if not setup_configs: # User quit during setup
        pygame.quit()
        sys.exit()

    num_players_input = setup_configs["num_players"]
    player_types_input = setup_configs["player_types"]

    game_state = GameState()

    # --- Player Initialization from Setup ---
    player_default_names = ["Player Red", "Player Blue", "Player Green", "Player Yellow", "Player Purple", "Player Orange"]
    for i in range(num_players_input):
        player_id = f"p{i+1}"
        player_name = player_default_names[i % len(player_default_names)] # Cycle through names if more players than names
        player_type = player_types_input[i]
        game_state.add_player(player_id, player_name, player_type)

    # --- Territory Assignment (Random) ---
    all_territory_ids = list(game_state.territories_state.keys())
    random.shuffle(all_territory_ids)

    player_idx_turn = 0
    for terr_id in all_territory_ids:
        # Use active_players list from game_state for assignment, as it's based on num_players_input
        current_player_id_for_assign = game_state.active_players[player_idx_turn]
        game_state.assign_territory_owner(terr_id, current_player_id_for_assign, 1) # Assign with 1 army
        player_idx_turn = (player_idx_turn + 1) % num_players_input


    # --- Initial Army Placement (Basic - distribute remaining armies) ---
    # Standard Risk army counts based on number of players
    initial_armies_map = {2: 40, 3: 35, 4: 30, 5: 25, 6: 20} # Armies per player
    total_initial_armies = initial_armies_map.get(num_players_input, 35) # Default to 35 if not in map

    for player_id in game_state.active_players:
        player_obj = game_state.get_player_by_id(player_id)
        if not player_obj: continue

        num_player_territories = sum(1 for data in game_state.territories_state.values() if data["owner"] == player_id)
        # Armies to distribute after placing 1 on each owned territory
        armies_to_distribute_for_this_player = total_initial_armies - num_player_territories

        owned_territories = [tid for tid, data in game_state.territories_state.items() if data["owner"] == player_id]
        if not owned_territories: continue

        for _ in range(armies_to_distribute_per_player):
            terr_to_add_army = random.choice(owned_territories)
            game_state.territories_state[terr_to_add_army]["armies"] += 1

    game_state.set_phase("REINFORCE") # After setup, usually start with reinforcement
    # --- End Initial Game Setup ---

    running = True
    clock = pygame.time.Clock()
    selected_territory_id = None
    hovered_territory_id = None
    action_this_frame = False # To help manage AI turn progression in a single frame pass

    while running:
        mouse_pos = pygame.mouse.get_pos()
        action_this_frame = False # Reset for each frame

        current_player = game_state.get_current_player() # Get current player at start of frame

        if not game_state.game_over:
            if current_player and current_player.player_type == "human": # Only update hover for human players
                current_hovered_id = None
                for terr_id, data in game_state.territories_state.items():
                    if is_point_in_polygon(mouse_pos, data["polygon_coords"]):
                        current_hovered_id = terr_id; break
                hovered_territory_id = current_hovered_id
            else: # No hover for AI turns or if no current player
                hovered_territory_id = None


        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False

            if game_state.game_over:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_q: running = False
                continue

            # --- Human Player Input Processing ---
            if current_player and current_player.player_type == "human":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    clicked_territory = None
                    for terr_id, data in game_state.territories_state.items():
                        if is_point_in_polygon(event.pos, data["polygon_coords"]):
                            clicked_territory = terr_id; break

                    if clicked_territory:
                        selected_territory_id = clicked_territory
                        # current_player already fetched
                        clicked_territory_data = game_state.territories_state[selected_territory_id]

                        game_state.log_action(
                            f"Clicked: {clicked_territory_data['name']} "
                            f"(Owner: {game_state.get_player_by_id(clicked_territory_data['owner']).name if clicked_territory_data['owner'] else 'None'}, "
                            f"Armies: {clicked_territory_data['armies']})"
                        )

                        if game_state.current_phase == "REINFORCE": # current_player is implied human here
                            if clicked_territory_data["owner"] == current_player.id:
                                if game_state.reinforcements_available_for_player > 0:
                                    clicked_territory_data["armies"] += 1
                                    game_state.reinforcements_available_for_player -= 1
                                    game_state.log_action(f"Placed 1 in {clicked_territory_data['name']}. {game_state.reinforcements_available_for_player} left.")
                                else: game_state.log_action("No more reinforcements.")
                            else: game_state.log_action("Not your territory.")

                        elif game_state.current_phase == "ATTACK":
                            if not game_state.selected_attacker_tid:
                                if clicked_territory_data["owner"] == current_player.id and clicked_territory_data["armies"] > 1:
                                    game_state.selected_attacker_tid = selected_territory_id
                                    game_state.log_action(f"Attack from: {clicked_territory_data['name']}.")
                                else: game_state.log_action("Select own territory with >1 army.")
                            elif not game_state.selected_defender_tid:
                                if clicked_territory_data["owner"] != current_player.id and \
                                   selected_territory_id in game_state.territories_state[game_state.selected_attacker_tid].get("adjacencies", []):
                                    game_state.selected_defender_tid = selected_territory_id
                                    game_state.log_action(f"Attack to: {clicked_territory_data['name']}. 'A' to attack, 'C' clear.")
                                elif clicked_territory_data["owner"] == current_player.id and selected_territory_id != game_state.selected_attacker_tid and clicked_territory_data["armies"] > 1:
                                    game_state.selected_attacker_tid = selected_territory_id
                                    game_state.log_action(f"Attack from: {clicked_territory_data['name']}.")
                                else: game_state.log_action("Invalid defender. 'C' to clear.")
                            else: game_state.log_action("Attack primed. 'A' or 'C'.")

                        elif game_state.current_phase == "FORTIFY":
                            if game_state.fortification_complete_this_turn: game_state.log_action("Fortified this turn.")
                            elif not game_state.selected_fortify_source_tid:
                                if clicked_territory_data["owner"] == current_player.id and clicked_territory_data["armies"] > 1:
                                    game_state.selected_fortify_source_tid = selected_territory_id
                                    game_state.log_action(f"Fortify from: {clicked_territory_data['name']}.")
                                else: game_state.log_action("Select own territory with >1 army.")
                            elif not game_state.selected_fortify_dest_tid:
                                if clicked_territory_data["owner"] == current_player.id and selected_territory_id != game_state.selected_fortify_source_tid and \
                                   selected_territory_id in game_state.territories_state[game_state.selected_fortify_source_tid].get("adjacencies", []):
                                    game_state.selected_fortify_dest_tid = selected_territory_id
                                    game_state.log_action(f"Fortify to: {clicked_territory_data['name']}. 'M' to move 1, 'X' clear.")
                                elif clicked_territory_data["owner"] == current_player.id and selected_territory_id != game_state.selected_fortify_source_tid and clicked_territory_data["armies"] > 1:
                                     game_state.selected_fortify_source_tid = selected_territory_id
                                     game_state.selected_fortify_dest_tid = None
                                     game_state.log_action(f"Fortify from: {clicked_territory_data['name']}.")
                                else: game_state.log_action("Invalid destination. 'X' clear.")
                            else: game_state.log_action("Fortify primed. 'M' or 'X'.")
                    else:
                        selected_territory_id = None
                        game_state.log_action("Clicked empty space.")

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        if game_state.current_phase == "REINFORCE":
                            if game_state.reinforcements_available_for_player == 0: game_state.set_phase("ATTACK"); action_this_frame = True
                            else: game_state.log_action(f"Place {game_state.reinforcements_available_for_player} reinforcements.")
                        elif game_state.current_phase == "ATTACK": game_state.set_phase("FORTIFY"); action_this_frame = True
                        elif game_state.current_phase == "FORTIFY":
                            game_state.next_player(); game_state.set_phase("REINFORCE"); action_this_frame = True

                    elif event.key == pygame.K_a and game_state.current_phase == "ATTACK":
                        if game_state.selected_attacker_tid and game_state.selected_defender_tid:
                            game_state.resolve_attack()
                            if not game_state.selected_attacker_tid: selected_territory_id = None
                            action_this_frame = True
                        else: game_state.log_action("Select attacker & defender.")

                    elif event.key == pygame.K_c and game_state.current_phase == "ATTACK":
                        game_state.clear_attack_selection(); selected_territory_id = None
                        game_state.log_action("Attack selection cleared.")
                        action_this_frame = True

                    elif event.key == pygame.K_m and game_state.current_phase == "FORTIFY":
                        if game_state.selected_fortify_source_tid and game_state.selected_fortify_dest_tid:
                            source_armies = game_state.territories_state[game_state.selected_fortify_source_tid]["armies"]
                            if source_armies > 1: game_state.resolve_fortification(1); action_this_frame = True
                            else: game_state.log_action("Source needs >1 army.")
                        else: game_state.log_action("Select source & destination.")

                    elif event.key == pygame.K_x and game_state.current_phase == "FORTIFY":
                        game_state.clear_fortify_selection(); selected_territory_id = None
                        game_state.log_action("Fortify selection cleared.")
                        action_this_frame = True

        # --- AI Player Turn Logic ---
        if not game_state.game_over and current_player and current_player.player_type.startswith("ai_") and not action_this_frame:
            if game_state.current_phase == "REINFORCE":
                ai_player.ai_place_reinforcements(current_player, game_state)
                if game_state.reinforcements_available_for_player == 0: # Ensure AI placed all
                    game_state.set_phase("ATTACK")
            elif game_state.current_phase == "ATTACK":
                ai_player.ai_perform_attack_phase(current_player, game_state)
                game_state.set_phase("FORTIFY") # AI does its attacks then moves to fortify
            elif game_state.current_phase == "FORTIFY":
                ai_player.ai_perform_fortification_phase(current_player, game_state)
                game_state.next_player()
                if not game_state.game_over : # Only set phase if game not ended by AI's last move
                    game_state.set_phase("REINFORCE")

            pygame.display.flip() # Update display after AI action
            # pygame.time.wait(100) # Shorter wait, individual AI actions have waits

        # --- Drawing starts ---
        screen.fill((200, 200, 220))
        map_surface.fill((240, 240, 240))

        draw_territories(map_surface, game_state, selected_territory_id, hovered_territory_id)
        draw_connections(map_surface, game_state)

        # Display Game Info
        info_y_offset = 10
        if game_state.game_over:
            winner_name = game_state.winner.name if game_state.winner else "Nobody"
            game_over_text_title = f"!!! GAME OVER !!!"
            game_over_text_winner = f"Winner: {winner_name}"
            game_over_text_quit = "Press 'Q' to Quit"

            title_surf = FONT.render(game_over_text_title, True, (200,0,0))
            winner_surf = FONT.render(game_over_text_winner, True, TEXT_COLOR)
            quit_surf = SMALL_FONT.render(game_over_text_quit, True, TEXT_COLOR)

            map_surface.blit(title_surf, (SCREEN_WIDTH // 2 - title_surf.get_width() // 2, SCREEN_HEIGHT // 2 - 50))
            map_surface.blit(winner_surf, (SCREEN_WIDTH // 2 - winner_surf.get_width() // 2, SCREEN_HEIGHT // 2 - 10))
            map_surface.blit(quit_surf, (SCREEN_WIDTH // 2 - quit_surf.get_width() // 2, SCREEN_HEIGHT // 2 + 30))
        else:
            current_player = game_state.get_current_player()
            player_text = f"Player: {current_player.name if current_player else 'None'}"
            phase_text = f"Phase: {game_state.current_phase}"

            draw_text(map_surface, player_text, (10, info_y_offset), FONT, TEXT_COLOR); info_y_offset += 25
            draw_text(map_surface, phase_text, (10, info_y_offset), FONT, TEXT_COLOR); info_y_offset += 25

            if game_state.current_phase == "REINFORCE" and current_player:
                reinforcements_text = f"To place: {game_state.reinforcements_available_for_player}"
                draw_text(map_surface, reinforcements_text, (10, info_y_offset), FONT, TEXT_COLOR); info_y_offset += 25

            elif game_state.current_phase == "ATTACK":
                attacker_name = game_state.territories_state[game_state.selected_attacker_tid]['name'] if game_state.selected_attacker_tid else "None"
                defender_name = game_state.territories_state[game_state.selected_defender_tid]['name'] if game_state.selected_defender_tid else "None"
                draw_text(map_surface, f"From: {attacker_name}", (10, info_y_offset), SMALL_FONT, TEXT_COLOR); info_y_offset += 20
                draw_text(map_surface, f"To: {defender_name}", (10, info_y_offset), SMALL_FONT, TEXT_COLOR); info_y_offset += 20

                if game_state.selected_attacker_tid and game_state.selected_defender_tid:
                     draw_text(map_surface, "Press 'A' to Attack, 'C' to Clear", (10, info_y_offset), SMALL_FONT, (200,0,0)); info_y_offset += 20
                elif game_state.selected_attacker_tid:
                     draw_text(map_surface, "Select adjacent enemy territory.", (10, info_y_offset), SMALL_FONT, TEXT_COLOR); info_y_offset += 20
                else:
                     draw_text(map_surface, "Select your territory to attack from.", (10, info_y_offset), SMALL_FONT, TEXT_COLOR); info_y_offset += 20

                dice_display_y = info_y_offset
                if game_state.combat_results_message:
                    lines = game_state.combat_results_message.split('\n')
                    for line in lines:
                        draw_text(map_surface, line, (10, info_y_offset), SMALL_FONT, (50,50,50)); info_y_offset += 15

                if game_state.attack_dice_results["attacker"] or game_state.attack_dice_results["defender"]:
                    dice_text_attacker = f"Attacker: {game_state.attack_dice_results['attacker']}"
                    dice_text_defender = f"Defender: {game_state.attack_dice_results['defender']}"
                    draw_text(map_surface, dice_text_attacker, (SCREEN_WIDTH - 150, dice_display_y), SMALL_FONT, TEXT_COLOR)
                    draw_text(map_surface, dice_text_defender, (SCREEN_WIDTH - 150, dice_display_y + 15), SMALL_FONT, TEXT_COLOR)

            elif game_state.current_phase == "FORTIFY":
                source_name = game_state.territories_state[game_state.selected_fortify_source_tid]['name'] if game_state.selected_fortify_source_tid else "None"
                dest_name = game_state.territories_state[game_state.selected_fortify_dest_tid]['name'] if game_state.selected_fortify_dest_tid else "None"
                draw_text(map_surface, f"Move from: {source_name}", (10, info_y_offset), SMALL_FONT, TEXT_COLOR); info_y_offset += 20
                draw_text(map_surface, f"Move to: {dest_name}", (10, info_y_offset), SMALL_FONT, TEXT_COLOR); info_y_offset += 20

                if game_state.fortification_complete_this_turn:
                    draw_text(map_surface, "Fortified. Press SPACE for next turn.", (10, info_y_offset), SMALL_FONT, (0,100,0)); info_y_offset += 20
                elif game_state.selected_fortify_source_tid and game_state.selected_fortify_dest_tid:
                     draw_text(map_surface, "Press 'M' to Move 1 army, 'X' to Clear.", (10, info_y_offset), SMALL_FONT, (200,0,0)); info_y_offset += 20
                elif game_state.selected_fortify_source_tid:
                     draw_text(map_surface, "Select destination territory (adjacent, owned).", (10, info_y_offset), SMALL_FONT, TEXT_COLOR); info_y_offset += 20
                else:
                     draw_text(map_surface, "Select source territory (>1 army).", (10, info_y_offset), SMALL_FONT, TEXT_COLOR); info_y_offset += 20

                if game_state.fortify_message: # Display fortify specific messages like "Moved X armies..."
                    lines = game_state.fortify_message.split('\n')
                    for line in lines:
                        draw_text(map_surface, line, (10, info_y_offset), SMALL_FONT, (50,50,50)); info_y_offset += 15

        screen.blit(map_surface, (0, 0))
        pygame.display.flip()
        clock.tick(FPS) # Use FPS from map_data

    pygame.quit()
    sys.exit()

if __name__ == '__main__':
    main()
