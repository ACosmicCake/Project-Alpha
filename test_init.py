import pygame
print("Imported pygame")
from llm_risk.game_orchestrator import GameOrchestrator
print("Imported GameOrchestrator")
from dotenv import load_dotenv
print("Imported load_dotenv")

print("LLM Risk Game - Minimal Init Test Starting...")
load_dotenv()
print("load_dotenv() called")

custom_player_configs = [
    {"name": "PlayerA (Gemini)", "color": "Red", "ai_type": "Gemini"},
    {"name": "PlayerB (OpenAI)", "color": "Blue", "ai_type": "OpenAI"}
]
game_mode = "world_map"

print(f"Attempting to instantiate GameOrchestrator with mode: {game_mode}")
try:
    orchestrator = GameOrchestrator(
        game_mode=game_mode,
        player_configs_override=custom_player_configs
    )
    print("GameOrchestrator instantiated successfully.")
    # We won't call orchestrator.run_game() to avoid the game loop and GUI startup
except Exception as e:
    print(f"Error during GameOrchestrator instantiation: {e}")
    import traceback
    traceback.print_exc()

print("Minimal Init Test Finished.")
