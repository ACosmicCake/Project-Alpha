"""
Basic AI logic for Risk game players.
"""
import random
import pygame # For pygame.time.wait

def ai_place_reinforcements(player, game_state):
    """AI logic for placing reinforcements."""
    game_state.log_action(f"AI ({player.name}) is placing {game_state.reinforcements_available_for_player} reinforcements...")
    pygame.time.wait(500) # Brief pause to see the message

    owned_territories = [tid for tid, data in game_state.territories_state.items() if data["owner"] == player.id]
    if not owned_territories:
        game_state.log_action(f"AI ({player.name}) has no territories to reinforce.")
        game_state.reinforcements_available_for_player = 0 # Ensure it's zeroed out
        return

    while game_state.reinforcements_available_for_player > 0:
        terr_to_reinforce = random.choice(owned_territories)
        game_state.territories_state[terr_to_reinforce]["armies"] += 1
        game_state.reinforcements_available_for_player -= 1
        # player.reinforcements_to_place -=1 # Already handled by game_state.reinforcements_available_for_player
        game_state.log_action(f"AI ({player.name}) placed 1 army in {game_state.territories_state[terr_to_reinforce]['name']}. "
                              f"({game_state.reinforcements_available_for_player} left)")
        pygame.time.wait(300) # Pause between each placement

    game_state.log_action(f"AI ({player.name}) finished placing reinforcements.")
    pygame.time.wait(500)


def ai_perform_attack_phase(player, game_state):
    """AI logic for the attack phase. Simplified: attempts one random valid attack if possible."""
    game_state.log_action(f"AI ({player.name}) is considering attacks...")
    pygame.time.wait(500)

    possible_attacks = []
    for attacker_tid, attacker_data in game_state.territories_state.items():
        if attacker_data["owner"] == player.id and attacker_data["armies"] > 1:
            for defender_tid in attacker_data.get("adjacencies", []):
                defender_data = game_state.territories_state.get(defender_tid)
                if defender_data and defender_data["owner"] != player.id:
                    possible_attacks.append((attacker_tid, defender_tid))

    if not possible_attacks:
        game_state.log_action(f"AI ({player.name}) sees no viable attacks.")
        pygame.time.wait(500)
        game_state.clear_attack_selection()
        return

    # Pick one random attack
    attacker_tid, defender_tid = random.choice(possible_attacks)

    attacker_name = game_state.territories_state[attacker_tid]['name']
    defender_name = game_state.territories_state[defender_tid]['name']
    game_state.log_action(f"AI ({player.name}) will attack {defender_name} from {attacker_name}.")
    pygame.time.wait(700)

    game_state.selected_attacker_tid = attacker_tid
    game_state.selected_defender_tid = defender_tid
    game_state.resolve_attack() # This will log dice rolls and outcomes

    # AI will only attempt one attack for now.
    # resolve_attack calls clear_attack_selection if attacker can't attack anymore or territory captured.
    # If not cleared by resolve_attack (e.g. attack failed but can continue), clear it here for AI's single attack turn.
    if game_state.selected_attacker_tid or game_state.selected_defender_tid:
        game_state.clear_attack_selection()

    game_state.log_action(f"AI ({player.name}) finished its attack sequence.")
    pygame.time.wait(500)


def ai_perform_fortification_phase(player, game_state):
    """AI logic for the fortification phase. Simplified: one random valid move or skip."""
    game_state.log_action(f"AI ({player.name}) is considering fortifications...")
    pygame.time.wait(500)

    if game_state.fortification_complete_this_turn: # Should not happen if called once
        game_state.log_action(f"AI ({player.name}) already fortified (should not happen).")
        return

    possible_fortifications = []
    owned_territories = [tid for tid, data in game_state.territories_state.items() if data["owner"] == player.id]

    for source_tid in owned_territories:
        source_data = game_state.territories_state[source_tid]
        if source_data["armies"] > 1: # Must have armies to move
            for dest_tid in source_data.get("adjacencies", []):
                dest_data = game_state.territories_state.get(dest_tid)
                # Must be owned and not the same territory
                if dest_data and dest_data["owner"] == player.id and source_tid != dest_tid:
                    possible_fortifications.append((source_tid, dest_tid))

    if not possible_fortifications:
        game_state.log_action(f"AI ({player.name}) sees no viable fortifications.")
        pygame.time.wait(500)
        game_state.clear_fortify_selection()
        game_state.fortification_complete_this_turn = True # Mark as done even if no move
        return

    source_tid, dest_tid = random.choice(possible_fortifications)

    # Decide how many armies to move (e.g., 1, or half, or random up to source_armies - 1)
    # For simplicity, AI moves 1 army if possible.
    armies_to_move = 1

    source_name = game_state.territories_state[source_tid]['name']
    dest_name = game_state.territories_state[dest_tid]['name']
    game_state.log_action(f"AI ({player.name}) will fortify from {source_name} to {dest_name}, moving {armies_to_move} army.")
    pygame.time.wait(700)

    game_state.selected_fortify_source_tid = source_tid
    game_state.selected_fortify_dest_tid = dest_tid
    game_state.resolve_fortification(armies_to_move) # This will set fortification_complete_this_turn

    # resolve_fortification doesn't clear selection, but AI turn ends here.
    # It will be cleared when phase changes.
    game_state.log_action(f"AI ({player.name}) finished fortification.")
    pygame.time.wait(500)
