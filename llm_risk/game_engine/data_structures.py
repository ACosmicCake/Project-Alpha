import json

class Territory:
    def __init__(self, name: str, continent: 'Continent' = None, owner: 'Player' = None, army_count: int = 0):
        self.name = name
        self.continent = continent
        self.owner = owner
        self.army_count = army_count
        self.adjacent_territories: list['Territory'] = []

    def __repr__(self):
        return f"Territory({self.name}, Armies: {self.army_count}, Owner: {self.owner.name if self.owner else 'None'})"

    def to_dict(self):
        return {
            "name": self.name,
            "continent": self.continent.name if self.continent else None,
            "owner": self.owner.name if self.owner else None,
            "army_count": self.army_count,
            "adjacent_territories": [t.name for t in self.adjacent_territories]
        }

class Continent:
    def __init__(self, name: str, bonus_armies: int):
        self.name = name
        self.territories: list[Territory] = []
        self.bonus_armies = bonus_armies

    def __repr__(self):
        return f"Continent({self.name}, Bonus: {self.bonus_armies})"

    def to_dict(self):
        return {
            "name": self.name,
            "territories": [t.name for t in self.territories],
            "bonus_armies": self.bonus_armies
        }

class Card:
    def __init__(self, territory_name: str, symbol: str): # Symbol can be Infantry, Cavalry, Artillery, or Wildcard
        self.territory_name = territory_name # Name of the territory, or None for wildcards
        self.symbol = symbol

    def __repr__(self):
        return f"Card({self.territory_name if self.territory_name else 'Wildcard'}, {self.symbol})"

    def to_dict(self):
        return {
            "territory_name": self.territory_name,
            "symbol": self.symbol
        }

class Player:
    def __init__(self, name: str, color: str, is_neutral: bool = False):
        self.name = name
        self.color = color
        self.is_neutral = is_neutral
        self.armies_to_deploy: int = 0
        self.initial_armies_pool: int = 0
        self.armies_placed_in_setup: int = 0
        self.territories: list[Territory] = []
        self.hand: list[Card] = [] # Neutral player will not use cards
        self.has_fortified_this_turn: bool = False
        self.has_conquered_territory_this_turn: bool = False


    def __repr__(self):
        return (f"Player({self.name}, Color: {self.color}, Neutral: {self.is_neutral}, Territories: {len(self.territories)}, "
                f"Cards: {len(self.hand)}, Deploy: {self.armies_to_deploy}, "
                f"InitialPool: {self.initial_armies_pool}, PlacedInSetup: {self.armies_placed_in_setup}, "
                f"Fortified: {self.has_fortified_this_turn}, Conquered: {self.has_conquered_territory_this_turn})")

    def to_dict(self):
        return {
            "name": self.name,
            "color": self.color,
            "is_neutral": self.is_neutral,
            "armies_to_deploy": self.armies_to_deploy,
            "initial_armies_pool": self.initial_armies_pool,
            "armies_placed_in_setup": self.armies_placed_in_setup,
            "territories": [t.name for t in self.territories],
            "hand": [card.to_dict() for card in self.hand],
            "has_fortified_this_turn": self.has_fortified_this_turn,
            "has_conquered_territory_this_turn": self.has_conquered_territory_this_turn
        }

class GameState:
    def __init__(self):
        self.territories: dict[str, Territory] = {}
        self.continents: dict[str, Continent] = {}
        self.players: list[Player] = [] # Will include the Neutral player in 2-player games
        self.current_turn_number: int = 1
        # Game Phases: SETUP_START, SETUP_DETERMINE_ORDER, SETUP_CLAIM_TERRITORIES, SETUP_PLACE_ARMIES,
        # SETUP_2P_DEAL_CARDS, SETUP_2P_PLACE_REMAINING, REINFORCE, ATTACK, FORTIFY, GAME_OVER
        self.current_game_phase: str = "SETUP_START"
        self.deck: list[Card] = []
        self.current_player_index: int = 0
        self.requires_post_attack_fortify: bool = False
        self.conquest_context: dict | None = None

        # Setup specific state
        self.unclaimed_territory_names: list[str] = []
        self.player_setup_order: list[Player] = []
        self.current_setup_player_index: int = 0
        self.first_player_of_game: Player | None = None

        # State for mandatory card trading after eliminating another player
        self.elimination_card_trade_player_name: str | None = None

    def get_current_player(self) -> Player | None: # For regular game turns
        if not self.players or self.current_player_index < 0 or self.current_player_index >= len(self.players):
            return None
        # Skip neutral player in regular turn sequence
        if self.players[self.current_player_index].is_neutral:
            # This should ideally be handled by next_turn logic to always land on a non-neutral player
            # For safety, if we land here, try to find the next non-neutral.
            # This indicates an issue in turn progression if current_player_index points to neutral.
            # For now, this method just returns the player at index. Orchestrator should ensure index is valid.
            pass
        return self.players[self.current_player_index]

    def get_current_setup_player(self) -> Player | None: # For setup phases
        if not self.player_setup_order or \
           self.current_setup_player_index < 0 or \
           self.current_setup_player_index >= len(self.player_setup_order):
            return None
        return self.player_setup_order[self.current_setup_player_index]

    def to_dict(self):
        return {
            "territories": {name: t.to_dict() for name, t in self.territories.items()},
            "continents": {name: c.to_dict() for name, c in self.continents.items()},
            "players": [p.to_dict() for p in self.players],
            "current_turn_number": self.current_turn_number,
            "current_game_phase": self.current_game_phase,
            "deck_size": len(self.deck),
            "current_player": self.get_current_player().name if self.get_current_player() else None,
            "requires_post_attack_fortify": self.requires_post_attack_fortify,
            "conquest_context": self.conquest_context,
            "unclaimed_territory_count": len(self.unclaimed_territory_names),
            "current_setup_player": self.get_current_setup_player().name if self.get_current_setup_player() else None,
            "first_player_of_game": self.first_player_of_game.name if self.first_player_of_game else None,
            "elimination_card_trade_player_name": self.elimination_card_trade_player_name
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class GameState:
    def __init__(self):
        self.territories: dict[str, Territory] = {}
        self.continents: dict[str, Continent] = {}
        self.players: list[Player] = []
        self.current_turn_number: int = 1
        # Game Phases: SETUP_START, SETUP_DETERMINE_ORDER, SETUP_CLAIM_TERRITORIES, SETUP_PLACE_ARMIES, REINFORCE, ATTACK, FORTIFY, GAME_OVER
        self.current_game_phase: str = "SETUP_START"
        self.deck: list[Card] = []
        self.current_player_index: int = 0 # Index for self.players for regular game turns
        self.requires_post_attack_fortify: bool = False
        self.conquest_context: dict | None = None

        # Setup specific state
        self.unclaimed_territory_names: list[str] = [] # List of names for territories yet to be claimed
        self.player_setup_order: list[Player] = [] # Order of players for setup actions
        self.current_setup_player_index: int = 0 # Index for self.player_setup_order
        self.first_player_of_game: Player | None = None # Player who will take the first actual game turn

        # State for mandatory card trading after eliminating another player
        self.elimination_card_trade_player_name: str | None = None # Name of player who must trade cards

    def get_current_player(self) -> Player | None: # For regular game turns
        if not self.players or self.current_player_index < 0 or self.current_player_index >= len(self.players):
            return None
        return self.players[self.current_player_index]

    def to_dict(self):
        return {
            "territories": {name: t.to_dict() for name, t in self.territories.items()},
            "continents": {name: c.to_dict() for name, c in self.continents.items()},
            "players": [p.to_dict() for p in self.players],
            "current_turn_number": self.current_turn_number,
            "current_game_phase": self.current_game_phase,
            "deck_size": len(self.deck), # Don't reveal actual cards in deck
            "current_player": self.get_current_player().name if self.get_current_player() else None,
            "requires_post_attack_fortify": self.requires_post_attack_fortify,
            "conquest_context": self.conquest_context # This will be None if not active, or a dict if active
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

if __name__ == '__main__':
    # Example Usage (Optional basic test)
    p1 = Player("Player 1", "Red")
    p2 = Player("Player 2", "Blue")

    alaska = Territory("Alaska")
    alberta = Territory("Alberta")
    western_us = Territory("Western US")

    alaska.adjacent_territories = [alberta]
    alberta.adjacent_territories = [alaska, western_us]
    western_us.adjacent_territories = [alberta]

    north_america = Continent("North America", 5)
    north_america.territories = [alaska, alberta, western_us]

    alaska.continent = north_america
    alberta.continent = north_america
    western_us.continent = north_america

    alaska.owner = p1
    alaska.army_count = 3
    p1.territories.append(alaska)

    alberta.owner = p2
    alberta.army_count = 2
    p2.territories.append(alberta)

    western_us.owner = p1
    western_us.army_count = 1
    p1.territories.append(western_us)

    gs = GameState()
    gs.territories = {"Alaska": alaska, "Alberta": alberta, "Western US": western_us}
    gs.continents = {"North America": north_america}
    gs.players = [p1, p2]
    gs.deck = [Card("Alaska", "Infantry"), Card(None, "Wildcard")]

    p1.hand.append(Card("Alberta", "Cavalry"))

    print(gs.to_json())

    # Test current player
    print(f"Current player: {gs.get_current_player().name if gs.get_current_player() else 'None'}")
    gs.current_player_index = 1
    print(f"Current player after change: {gs.get_current_player().name if gs.get_current_player() else 'None'}")
