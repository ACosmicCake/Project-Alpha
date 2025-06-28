def _process_diplomatic_action(self, player: GamePlayer, action: dict) -> bool:
    """
    Handles processing of ACCEPT_ALLIANCE and REJECT_ALLIANCE actions.
    Returns True if a diplomatic action was processed, False otherwise.
    """
    gs = self.engine.game_state
    action_type = action.get("type")

    if action_type == "ACCEPT_ALLIANCE":
        proposing_player_name = action.get("proposing_player_name")
        if not proposing_player_name:
            self.log_turn_info(f"Orchestrator: {player.name} tried ACCEPT_ALLIANCE with no proposing_player_name. Action: {action}")
            return True # Action was of diplomatic type, but invalid

        diplomatic_key = frozenset({player.name, proposing_player_name})
        active_proposal = gs.active_diplomatic_proposals.get(diplomatic_key)

        if active_proposal and \
           active_proposal.get('proposer') == proposing_player_name and \
           active_proposal.get('target') == player.name and \
           active_proposal.get('type') == 'ALLIANCE': # Ensure it's an alliance proposal

            gs.diplomacy[diplomatic_key] = "ALLIANCE"
            del gs.active_diplomatic_proposals[diplomatic_key] # Clear pending proposal

            self.log_turn_info(f"Diplomacy: {player.name} ACCEPTED ALLIANCE with {proposing_player_name}. Status set to ALLIANCE.")
            self.global_chat.broadcast("GameSystem", f"{player.name} and {proposing_player_name} have formed an ALLIANCE!")
            gs.event_history.append({
                "turn": gs.current_turn_number,
                "type": "DIPLOMACY_CHANGE",
                "subtype": "ALLIANCE_FORMED",
                "players": sorted([player.name, proposing_player_name])
            })
        else:
            self.log_turn_info(f"Orchestrator: {player.name} tried to ACCEPT_ALLIANCE from {proposing_player_name}, but no valid matching proposal was active. Action: {action}")

        self._update_gui_full_state()
        return True # Diplomatic action processed (or attempt logged)

    elif action_type == "REJECT_ALLIANCE":
        proposing_player_name = action.get("proposing_player_name")
        if not proposing_player_name:
            self.log_turn_info(f"Orchestrator: {player.name} tried REJECT_ALLIANCE with no proposing_player_name. Action: {action}")
            return True

        diplomatic_key = frozenset({player.name, proposing_player_name})
        active_proposal = gs.active_diplomatic_proposals.get(diplomatic_key)

        if active_proposal and \
           active_proposal.get('proposer') == proposing_player_name and \
           active_proposal.get('target') == player.name and \
           active_proposal.get('type') == 'ALLIANCE':

            # Set diplomacy back to NEUTRAL, or remove if it was implicitly NEUTRAL
            gs.diplomacy[diplomatic_key] = "NEUTRAL"
            del gs.active_diplomatic_proposals[diplomatic_key] # Clear pending proposal

            self.log_turn_info(f"Diplomacy: {player.name} REJECTED ALLIANCE from {proposing_player_name}.")
            self.global_chat.broadcast("GameSystem", f"{player.name} has rejected an alliance proposal from {proposing_player_name}.")
            gs.event_history.append({
                "turn": gs.current_turn_number,
                "type": "DIPLOMACY_REJECTION",
                "subtype": "ALLIANCE_REJECTED",
                "rejector": player.name,
                "proposer": proposing_player_name
            })
        else:
            self.log_turn_info(f"Orchestrator: {player.name} tried to REJECT_ALLIANCE from {proposing_player_name}, but no valid matching proposal was active. Action: {action}")

        self._update_gui_full_state()
        return True # Diplomatic action processed

    return False # Not a processed diplomatic action type by this helper
