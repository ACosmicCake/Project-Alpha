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
    def __init__(self, name: str, color: str):
        self.name = name
        self.color = color
        self.armies_to_deploy: int = 0
        self.territories: list[Territory] = []
        self.hand: list[Card] = []

    def __repr__(self):
        return f"Player({self.name}, Color: {self.color}, Territories: {len(self.territories)}, Cards: {len(self.hand)})"

    def to_dict(self):
        return {
            "name": self.name,
            "color": self.color,
            "armies_to_deploy": self.armies_to_deploy,
            "territories": [t.name for t in self.territories],
            "hand": [card.to_dict() for card in self.hand]
        }

class GameState:
    def __init__(self):
        self.territories: dict[str, Territory] = {}
        self.continents: dict[str, Continent] = {}
        self.players: list[Player] = []
        self.current_turn_number: int = 1
        self.current_game_phase: str = "REINFORCE" # REINFORCE, ATTACK, FORTIFY
        self.deck: list[Card] = []
        self.current_player_index: int = 0

    def get_current_player(self) -> Player | None:
        if not self.players:
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
            "current_player": self.get_current_player().name if self.get_current_player() else None
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
