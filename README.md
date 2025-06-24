# LLM Risk Game (Project-Alpha)

## Overview

Project-Alpha is a simulation of the classic board game Risk, where AI agents, powered by various Large Language Models (LLMs), strategize and compete for world domination. The project features a complete game engine handling core Risk rules, integration points for different AI models, communication channels for AI diplomacy (global and private chat), and a Pygame-based Graphical User Interface (GUI) for visualizing the game's progress.

## Features

*   **Core Risk Gameplay:** Implements standard game phases:
    *   Reinforcement (calculating and deploying armies based on territories, continents, and card trades).
    *   Attack (dice-based combat between territories).
    *   Fortification (strategic movement of armies between connected territories).
*   **Card Trading System:** Players earn cards for conquests and can trade them in for bonus armies with an escalating bonus scale.
*   **Strategic Post-Conquest Movement:** After conquering a territory, the attacking AI decides how many armies to move into the newly acquired territory.
*   **Player Elimination:** Handles player elimination, including the transfer of cards to the victor.
*   **Multiple AI Agent Integration:**
    *   Supports different LLM backends (e.g., Google Gemini, OpenAI GPT models, Anthropic Claude, DeepSeek).
    *   Base agent class (`BaseAIAgent`) for easy extension.
*   **Dynamic AI Prompting:** Provides AI agents with context-specific information and game rules dynamically to aid decision-making.
*   **AI Diplomacy:**
    *   **Global Chat:** AI agents can broadcast messages to all other players.
    *   **Private Chat:** AI agents can engage in direct, multi-turn private conversations with other specific AIs.
*   **Pygame-based GUI:**
    *   Visualizes the game map, territory ownership, and army counts.
    *   Displays action logs, AI thought processes, and chat messages.
    *   Interactive tabs for viewing different AI thoughts and chat conversations.
*   **Configurable Game Setup:**
    *   Map layout (continents, territories, adjacencies, bonuses) defined in `map_config.json`.
    *   Player setup (names, colors, AI types) defined in `player_config.json`.
    *   GUI display coordinates for map elements in `map_display_config.json`.
*   **Logging:** Generates logs for game events, AI thoughts, and chat messages in the `logs/` directory.

## Project Structure

```
Project-Alpha/
├── llm_risk/                  # Main application package
│   ├── ai/                    # AI agent implementations and base class
│   ├── communication/         # Global and private chat managers
│   ├── game_engine/           # Core game logic, data structures, and engine
│   ├── ui/                    # Pygame GUI components
│   └── game_orchestrator.py   # Main class coordinating game flow
├── logs/                      # Directory for runtime logs (chats, thoughts)
├── main.py                    # Main entry point to run the game
├── map_config.json            # Default map configuration
├── player_config.json         # Default player and AI setup
├── map_display_config.json    # Default GUI map display coordinates
├── requirements.txt           # Python dependencies
├── .env.example               # Example for API key configuration
└── README.md                  # This file
```

## Configuration Files

*   **`map_config.json`**: Defines the game map structure.
    *   `continents`: Lists continents with their names and army bonus values.
    *   `territories`: Defines each territory, its continent, and its adjacent territories.
*   **`player_config.json`**: Configures the players for the game.
    *   Each entry specifies a player's `name`, `color`, and `ai_type` (e.g., "Gemini", "OpenAI", "Claude", "DeepSeek").
*   **`map_display_config.json`**: Used by the GUI to determine the (x, y) pixel coordinates for rendering each territory on the map image.
*   **`.env.example` / `.env`**:
    *   Rename `.env.example` to `.env`.
    *   Fill in your API keys for the desired LLMs (e.g., `GOOGLE_API_KEY`, `OPENAI_API_KEY`). These are loaded by `python-dotenv`.

## Setup and Installation

1.  **Prerequisites:**
    *   Python 3.10 or higher is recommended.
    *   Access to API keys for any LLMs you intend to use (see `.env.example`).

2.  **Clone the Repository:**
    ```bash
    git clone <repository_url>  # Replace <repository_url> with the actual URL
    cd Project-Alpha
    ```

3.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    This will install `pygame` for the GUI and libraries for LLM interactions (`google-generativeai`, `openai`, `anthropic`, `requests`), and `python-dotenv`.

5.  **Set Up API Keys:**
    *   Copy the `.env.example` file to a new file named `.env`:
        ```bash
        cp .env.example .env
        ```
    *   Open the `.env` file with a text editor and add your API keys for the respective services:
        ```
        GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY_HERE"
        OPENAI_API_KEY="YOUR_OPENAI_API_KEY_HERE"
        ANTHROPIC_API_KEY="YOUR_ANTHROPIC_API_KEY_HERE"
        DEEPSEEK_API_KEY="YOUR_DEEPSEEK_API_KEY_HERE"
        ```
    *   **Important:** Ensure the `.env` file is added to your `.gitignore` if you are using version control to prevent accidentally committing your private keys.

## How to Run

1.  Ensure you have completed the "Setup and Installation" steps, especially installing dependencies and configuring API keys in the `.env` file.
2.  Navigate to the root directory of the project (`Project-Alpha/`).
3.  Run the main application script:
    ```bash
    python main.py
    ```
4.  If Pygame initializes successfully (it should if `pygame` was installed correctly), the game GUI will launch. The game will then proceed automatically, driven by AI decisions.
5.  The `GameOrchestrator` attempts to set up the GUI by default. If Pygame is unavailable or encounters an issue during initialization that isn't caught, the application might not run as expected. True headless mode (guaranteed no GUI attempt) would require a specific configuration or command-line flag (not currently implemented).

## Development Notes
* The game uses several JSON configuration files for map data, player setup, and GUI display. Modifying these allows for different game scenarios.
* AI agent behavior is determined by their respective classes in `llm_risk/ai/`. The prompts and game rules provided to them are key to their strategic capabilities.
* Logs for AI thoughts and chat messages are saved in the `logs/` directory (e.g., `ai_thoughts.jsonl`, `global_chat.jsonl`, `private_chats.jsonl`), which can be useful for debugging and analyzing AI behavior.