"""
Main entry point for the LLM Risk Game application.
"""
from llm_risk.game_orchestrator import GameOrchestrator
# Ensure Pygame is available if GUI is intended.
# The GameGUI class will attempt to import and initialize Pygame.
# No explicit Pygame import is needed here unless main.py directly handles Pygame events,
# which it won't; that's delegated to GameGUI via GameOrchestrator.

def main():
    """
    Initializes and runs the LLM Risk game.
    """
    print("LLM Risk Game - Main Application Starting...")

    # Instantiate the GameOrchestrator.
    # It handles its own setup including engine, players, AI agents, and GUI.
    # Default map_config.json and player_config.json will be used if not specified.
    orchestrator = GameOrchestrator()

    # Run the game.
    # The orchestrator.run_game() method will either start a headless game loop
    # or delegate to the GUI's run() method if GUI is enabled and initialized.
    orchestrator.run_game()

    print("LLM Risk Game - Application Finished.")

if __name__ == "__main__":
    main()
