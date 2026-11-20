import itertools
import random
import sys

# Terrain codes used by lands and invader cards
MOUNTAIN, WETLAND, JUNGLE, SANDS = 1, 2, 3, 4
TERRAIN_NAMES = {MOUNTAIN: "Mountain", WETLAND: "Wetland", JUNGLE: "Jungle", SANDS: "Sands"}

# Setup piece codes used in the board tables: Dahan 10, town 30, city 40, blight 5
SETUP_DAHAN, SETUP_TOWN, SETUP_CITY, SETUP_BLIGHT = 10, 30, 40, 5

# Element indices
SUN, MOON, FIRE, AIR, WATER, EARTH, PLANT, ANIMAL = range(8)

PLAYERS = 1
FEAR_CARDS = 9                  # 3 per terror level, no adversary
FEAR_POOL = 4 * PLAYERS
HEALTHY_BLIGHT = 2 * PLAYERS + 1
BLIGHTED_ISLAND_BLIGHT = 5 * PLAYERS   # varies by Blighted Island card; 5 per player is common


class GameOver(Exception):
    def __init__(self, win, reason):
        super().__init__(reason)
        self.win = win
        self.reason = reason


# Choosers make every player decision, so the game can run with a human or unattended (for ML).
class Random_Chooser:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def choose(self, prompt, options, allow_none=False):
        options = list(options)
        if allow_none:
            options = [None] + options
        if not options:
            return None
        return self.rng.choice(options)


class Human_Chooser:
    def choose(self, prompt, options, allow_none=False):
        options = list(options)
        if allow_none:
            options = [None] + options
        if not options:
            return None
        if len(options) == 1:
            return options[0]
        print(prompt)
        for i, option in enumerate(options):
            print("  %d: %s" % (i, "nothing" if option is None else option))
        while True:
            answer = input("> ")
            if answer.isdigit() and int(answer) < len(options):
                return options[int(answer)]
            print("Enter a number from 0 to %d" % (len(options) - 1))


class Minor_Power:
    pass

class Major_Power:
    pass

class Fear_Card:
    pass


class Power_Card:
    def __init__(self, name, cost, fast, elements, effect, target_range=None, needs_presence=False, from_sacred_site=False, target_filter=None):
        self.name = name
        self.cost = cost
        self.fast = fast
        self.elements = elements
        self.effect = effect
        self.target_range = target_range      # None means the card targets a spirit, not a land
        self.needs_presence = needs_presence  # range 0: target must hold your presence
        self.from_sacred_site = from_sacred_site
        self.target_filter = target_filter

    def __str__(self):
        return "%s (cost %d, %s)" % (self.name, self.cost, "fast" if self.fast else "slow")


class Invader_Card:
    def __init__(self, stage, terrains, coastal=False):
        self.stage = stage
        self.terrains = set(terrains)
        self.coastal = coastal
        self.escalation = stage == 2

    def matches(self, land):
        if self.coastal:
            return land.coastal
        return land.terrain in self.terrains

    def __str__(self):
        if self.coastal:
            return "Stage %d: Coastal Lands" % self.stage
        return "Stage %d: %s" % (self.stage, " + ".join(TERRAIN_NAMES[t] for t in sorted(self.terrains)))


class Invader_Deck:
    def __init__(self, rng=random):
        terrains = [MOUNTAIN, WETLAND, JUNGLE, SANDS]
        stage1 = [Invader_Card(1, [t]) for t in terrains]
        stage2 = [Invader_Card(2, [t]) for t in terrains] + [Invader_Card(2, [], coastal=True)]
        stage3 = [Invader_Card(3, pair) for pair in itertools.combinations(terrains, 2)]
        self.cards = []
        for stage in (stage1, stage2, stage3):
            rng.shuffle(stage)
            stage.pop()            # one card of each stage is removed unseen
            self.cards += stage    # 3 + 4 + 5 = 12 cards

    def draw(self):
        return self.cards.pop(0) if self.cards else None


class Piece:
    name = ""

    def __init__(self, max_health, attack):
        self.max_health = max_health
        self.health = max_health
        self.attack = attack

    def take_damage(self, amount):
        self.health -= amount
        return self.health <= 0

    def heal(self):
        self.health = self.max_health

    def __str__(self):
        return "%s (%d/%d health)" % (self.name, self.health, self.max_health)

class Explorer(Piece):
    name = "Explorer"
    def __init__(self):
        super().__init__(1, 1)

class Town(Piece):
    name = "Town"
    def __init__(self):
        super().__init__(2, 2)

class City(Piece):
    name = "City"
    def __init__(self):
        super().__init__(3, 3)

class Dahan(Piece):
    name = "Dahan"
    def __init__(self):
        super().__init__(2, 2)


class Board:
    def __init__(self):
        self.lands = []

    def Board_A(self):
        self.lands = [
            Land(1, 1, [], [2, 4, 5, 6], True, 'b', 0),
            Land(2, 2, [10, 40], [1, 3, 4], True, 'd', 0),
            Land(3, 3, [10, 10], [2, 4], True, 'n', 0),
            Land(4, 4, [5], [1, 2, 3, 5], False, 'n', 0),
            Land(5, 2, [], [1, 4, 6, 7, 8], False, 'n', 0),
            Land(6, 1, [10], [1, 5, 8], False, 'n', 0),
            Land(7, 4, [10, 10], [5, 8], False, 'n', 0),
            Land(8, 3, [30], [5, 6, 7], False, 'n', 0)
        ]
    def Board_B(self):
        self.lands = [
            Land(1, 2, [10], [2, 4, 5, 6], True, 'n', 1),
            Land(2, 1, [40], [1, 3, 4], True, 'd', 1),
            Land(3, 4, [10, 10], [2, 4], True, 'n', 1),
            Land(4, 3, [5], [1, 2, 3, 5, 7], False, 'n', 1),
            Land(5, 4, [], [1, 4, 6, 7], False, 'b', 1),
            Land(6, 2, [30], [1, 5, 7, 8], False, 'n', 1),
            Land(7, 1, [10], [4, 5, 6, 8], False, 'n', 1),
            Land(8, 3, [10, 10], [6, 7], False, 'n', 1)
        ]
    def Board_C(self):
        # TODO: every token is 'b' on boards C and D; check against the printed boards
        self.lands = [
            Land(1, 3, [10], [2, 5, 6], True, 'b', 2),
            Land(2, 4, [40], [1, 3, 4, 5], True, 'b', 2),
            Land(3, 1, [10, 10], [2, 4], True, 'b', 2),
            Land(4, 3, [], [2, 3, 5, 7], False, 'b', 2),
            Land(5, 2, [10, 10, 5], [1, 2, 4, 6, 7], False, 'b', 2),
            Land(6, 4, [10], [1, 5, 7, 8], False, 'b', 2),
            Land(7, 1, [30], [4, 5, 6, 8], False, 'b', 2),
            Land(8, 2, [], [6, 7], False, 'b', 2)
        ]
    def Board_D(self):
        self.lands = [
            Land(1, 2, [10, 10], [2, 5, 7, 8], True, 'b', 3),
            Land(2, 3, [40, 10], [1, 3, 4, 5], True, 'b', 3),
            Land(3, 2, [], [2, 4], True, 'b', 3),
            Land(4, 4, [], [2, 3, 5, 6], False, 'b', 3),
            Land(5, 1, [10, 5], [1, 2, 4, 6, 7], False, 'b', 3),
            Land(6, 3, [], [4, 5, 7], False, 'b', 3),
            Land(7, 4, [10, 10, 30], [1, 5, 6, 8], False, 'b', 3),
            Land(8, 1, [], [1, 7], False, 'b', 3)
        ]
    def get_lands(self):
        return self.lands
    def get_land(self, index):
        return self.lands[index-1]
    def get_adjacent(self, land):
        return [self.get_land(n) for n in land.get_adjacencies()]

    def lands_within(self, sources, distance):
        found = set(sources)
        frontier = list(sources)
        for _ in range(distance):
            frontier = [a for l in frontier for a in self.get_adjacent(l) if a not in found]
            found.update(frontier)
        return sorted(found, key=lambda l: l.number)


class Land:
    def __init__(self, number, terrain, setup, adjacencies, coastal, token, board):
        self.number = number
        self.terrain = terrain
        self.setup = setup
        self.adjacencies = adjacencies
        self.coastal = coastal
        self.token = token
        self.board = board
        self.invaders = []
        self.dahan = []
        self.blight = 0
        self.presence = 0
        self.defense = 0
        self.skip_explore = False
        self.skip_build = False
        self.skip_ravage = False
        self.skip_dahan_ravage_damage = False
        for code in setup:
            if code == SETUP_DAHAN:
                self.dahan.append(Dahan())
            elif code == SETUP_TOWN:
                self.invaders.append(Town())
            elif code == SETUP_CITY:
                self.invaders.append(City())
            elif code == SETUP_BLIGHT:
                self.blight += 1
            else:
                raise ValueError("Unknown setup code %r on land %d" % (code, number))

    def count(self, kind):
        return sum(1 for i in self.invaders if isinstance(i, kind))

    @property
    def explorer(self):
        return self.count(Explorer)

    @property
    def town(self):
        return self.count(Town)

    @property
    def city(self):
        return self.count(City)

    def has_invaders(self):
        return bool(self.invaders)

    def has_building(self):
        return self.town > 0 or self.city > 0

    def builds_city(self):
        return self.town > self.city

    def get_adjacencies(self):
        return self.adjacencies

    def get_invaders(self):
        return [self.explorer, self.town, self.city]

    def get_coastal(self):
        return self.coastal

    def __str__(self):
        return "Land %d %s [E%d T%d C%d D%d B%d P%d]" % (
            self.number, TERRAIN_NAMES[self.terrain], self.explorer, self.town, self.city,
            len(self.dahan), self.blight, self.presence)


def setup_board(Board_Letter):
    board = Board()
    getattr(board, "Board_" + Board_Letter)()
    return board


class Spirit(object):
    def __init__(self):
        self.energy = 0
        self.card_plays = 1
        self.hand = []
        self.discard_pile = []
        self.played = []
        self.elements = [0] * 8
        self.resolved = set()
        self.swift_used = 0
        self.power_deck = []    # no Minor/Major power decks yet
        self.bonus_defense = 0
        self.repeat_max_cost = -1
        self.innate_fast = False

    def discard(self, card):
        self.hand.remove(card)
        self.discard_pile.append(card)

    def reclaim_all(self):
        self.hand.extend(self.discard_pile)
        self.discard_pile.clear()

    def gain_card(self):
        # TODO: draw from the Minor/Major power decks once they exist
        if self.power_deck:
            self.hand.append(self.power_deck.pop())

    def forget(self):
        pass

    def presence_lands(self, board):
        return [l for l in board.get_lands() if l.presence > 0]

    def sacred_sites(self, board):
        return [l for l in board.get_lands() if l.presence >= 2]

    #These methods exist to overridden in the child classes to enforce unique rules
    def before_growth_phase(self):
        return None

    def before_spirit_phase(self):
        return None

    def before_fast_phase(self):
        return None

    def before_slow_phase(self):
        return None

    def get_bonus_defense(self, land):
        return 0

    def innate(self, game):
        pass

    def can_resolve(self, card, fast):
        return card.fast == fast and card not in self.resolved

    def play_card(self, card):
        self.hand.remove(card)
        self.energy -= card.cost
        self.played.append(card)
        for e in card.elements:
            self.elements[e] += 1

    def end_turn(self):
        self.discard_pile.extend(self.played)
        self.played.clear()
        self.elements = [0] * 8
        self.resolved = set()
        self.swift_used = 0
        self.repeat_max_cost = -1


# River Surges in Sunlight: unique powers and innate
def boon_of_vigor(game, spirit, land):
    spirit.energy += 1

def flash_floods(game, spirit, land):
    game.damage_invaders(land, 2 if land.coastal else 1)

def rivers_bounty(game, spirit, land):
    for _ in range(2):
        game.gather(land, Dahan, "Gather a Dahan into %s from?" % land)
    if len(land.dahan) >= 2:
        land.dahan.append(Dahan())
        spirit.energy += 1

def wash_away(game, spirit, land):
    for _ in range(3):
        game.push(land, (Explorer, Town), "Push which Explorer/Town from %s?" % land)

RIVER_CARDS = [
    Power_Card("Boon of Vigor", 0, True, [SUN, WATER, PLANT], boon_of_vigor),
    Power_Card("Flash Floods", 2, True, [SUN, WATER], flash_floods, target_range=1),
    Power_Card("River's Bounty", 0, False, [SUN, WATER, ANIMAL], rivers_bounty, target_range=0, needs_presence=True),
    Power_Card("Wash Away", 1, False, [WATER, EARTH], wash_away, target_range=1),
]

# Presence tracks, indexed by presence taken off the track (0-6)
RIVER_ENERGY_TRACK = [1, 2, 2, 3, 4, 4, 5]
RIVER_CARD_TRACK = [1, 2, 2, 3, 3, 4, 5]   # 4th space is "Reclaim One"
RIVER_RECLAIM_FROM = 4

class River_Surges_Like_Sunlight(Spirit):
    def __init__(self):
        super().__init__()
        self.hand = list(RIVER_CARDS)
        self.top_track = 6       # presence left on the energy track
        self.bottom_track = 6    # presence left on the card-play track
        self.update_tracks()

    def update_tracks(self):
        self.energy_turn = RIVER_ENERGY_TRACK[6 - self.top_track]
        self.card_plays = RIVER_CARD_TRACK[6 - self.bottom_track]
        self.reclaim_one = 6 - self.bottom_track >= RIVER_RECLAIM_FROM

    def sacred_sites(self, board):
        # Rivers' Domain: River's presence in a Wetland counts as a sacred site
        return [l for l in board.get_lands() if l.presence >= 2 or (l.presence >= 1 and l.terrain == WETLAND)]

    def setup(self, board):
        wetlands = [l for l in board.get_lands() if l.terrain == WETLAND]
        max(wetlands, key=lambda l: l.number).presence += 1

    def add_presence(self, game, distance):
        tracks = [t for t in ("energy", "card plays") if
                  (self.top_track if t == "energy" else self.bottom_track) > 0]
        track = game.choose("Take presence from which track?", tracks)
        if track is None:
            return
        options = game.board.lands_within(self.presence_lands(game.board), distance)
        land = game.choose("Add presence (range %d) to?" % distance, options)
        if track == "energy":
            self.top_track -= 1
        else:
            self.bottom_track -= 1
        land.presence += 1
        self.update_tracks()

    def G1(self, game):
        self.reclaim_all()
        self.gain_card()
        self.energy += 1

    def G2(self, game):
        self.add_presence(game, 1)
        self.add_presence(game, 1)

    def G3(self, game):
        self.gain_card()
        self.add_presence(game, 2)

    def growth(self, game):
        option = game.choose("Choose growth", ["G1: reclaim all, gain a power, +1 energy",
                                               "G2: add 2 presence (range 1)",
                                               "G3: gain a power, add presence (range 2)"])
        getattr(self, option[:2])(game)
        self.energy += self.energy_turn
        if self.reclaim_one and self.discard_pile:
            card = game.choose("Reclaim which card?", self.discard_pile)
            self.discard_pile.remove(card)
            self.hand.append(card)

    def innate(self, game):
        # Massive Flooding: slow, range 1 from a sacred site, highest threshold met applies
        e = self.elements
        if e[SUN] >= 3 and e[WATER] >= 4 and e[EARTH] >= 1:
            level = 3
        elif e[SUN] >= 2 and e[WATER] >= 3:
            level = 2
        elif e[SUN] >= 1 and e[WATER] >= 2:
            level = 1
        else:
            return
        sites = self.sacred_sites(game.board)
        if not sites:
            return
        land = game.choose("Massive Flooding targets?", game.board.lands_within(sites, 1))
        if level == 1:
            game.push(land, (Explorer, Town), "Push which Explorer/Town from %s?" % land)
        elif level == 2:
            game.damage_invaders(land, 2)
            for _ in range(3):
                game.push(land, (Explorer, Town), "Push which Explorer/Town from %s?" % land)
        else:
            for invader in list(land.invaders):
                if invader.take_damage(2):
                    game.destroy_invader(land, invader)

def Harbingers_of_the_Lightning(game, spirit, land):
    for _ in range(2):
        game.push(land, Dahan, "Choose which Dahan to move")

def Raging_Storm(game, spirit, land):
    for invader in list(land.invaders):
        if invader.take_damage(1):
            game.destroy_invader(land, invader)

def Shatter_Homesteads(game, spirit, land):
    game.add_fear(1)
    target = game.choose("Which town?", [i for i in land.invaders if isinstance(i, (Town))])
    if target is None:
        return
    game.destroy_invader(land, target)

#Won't do anything until I add multi-spirit games, or maybe if I add the non-unique minor/major powers
def Lightnings_Boon(game, spirit, land):
    pass;

LIGHTNING_CARDS = [
    Power_Card("Harbingers of the Lightning", 0, False, [FIRE, AIR], Harbingers_of_the_Lightning, target_range=1),
    Power_Card("Raging Storm", 3, False, [FIRE, AIR, WATER], Raging_Storm, target_range=1),
    Power_Card("Shatter Homesteads", 2, False, [FIRE, AIR], Shatter_Homesteads, target_range=2, from_sacred_site=True),
    Power_Card("Lightning's Boon", 1, True, [FIRE, AIR], Lightnings_Boon, target_range=1),
]
LIGHTNING_ENERGY_TRACK = [1, 1, 2, 2, 3, 4, 4, 5]
LIGHTNING_CARD_TRACK = [2, 3, 4, 5, 6]
class Lightnings_Swift_Strike(Spirit):
    def __init__(self):
        super().__init__()
        self.hand = list(LIGHTNING_CARDS)
        self.top_track = 7       # presence left on the energy track
        self.bottom_track = 4    # presence left on the card-play track
        self.update_tracks()

    def update_tracks(self):
        self.energy_turn = LIGHTNING_ENERGY_TRACK[7 - self.top_track]
        self.card_plays = LIGHTNING_CARD_TRACK[4 - self.bottom_track]

    def setup(self, board):
        sands = [l for l in board.get_lands() if l.terrain == SANDS]
        max(sands, key=lambda l: l.number).presence += 2

    def add_presence(self, game, distance):
        tracks = [t for t in ("energy", "card plays") if
                  (self.top_track if t == "energy" else self.bottom_track) > 0]
        track = game.choose("Take presence from which track?", tracks)
        if track is None:
            return
        options = game.board.lands_within(self.presence_lands(game.board), distance)
        land = game.choose("Add presence (range %d) to?" % distance, options)
        if track == "energy":
            self.top_track -= 1
        else:
            self.bottom_track -= 1
        land.presence += 1
        self.update_tracks()

    def G1(self, game):
        self.reclaim_all()
        self.gain_card()
        self.energy += 1

    def G2(self, game):
        self.add_presence(game, 2)
        self.add_presence(game, 0)

    def G3(self, game):
        self.add_presence(game, 1)
        self.energy += 3

    def growth(self, game):
        option = game.choose("Choose growth", ["G1: reclaim all, gain a power, +1 energy",
                                               "G2: add 2 presence (range 2), and (range 0)",
                                               "G3: add presence (range 1), +3 energy"])
        getattr(self, option[:2])(game)
        self.energy += self.energy_turn

    def innate(self, game):
        e = self.elements
        level = 0
        if e[FIRE] >= 5 and e[AIR] >= 5 and e[WATER] >= 2:
            level = 4
        elif e[FIRE] >= 5 and e[AIR] >= 4 and e[WATER] >= 1:
            level = 3
        elif e[FIRE] >= 4 and e[AIR] >= 3:
            level = 2
        elif e[FIRE] >= 3 and e[AIR] >= 2:
            level = 1

        if level >= 1:
            land = game.choose("Thundering Destruction targets?", game.board.lands_within(self.sacred_sites(game.board), 2))
        if level == 0: return
        if land is None: return
        if level == 4:
            for _ in range(3):
                invader = game.choose("Which invader will you target", [i for i in land.invaders if isinstance(i, (Town, City))])
                if invader is None:
                    return
                game.destroy_invader(land, invader)
        elif level == 3:
            for _ in range(2):
                invader = game.choose("Which invader will you target", [i for i in land.invaders if isinstance(i, (Town, City))])
                if invader is None:
                    return
                game.destroy_invader(land, invader)
        elif level == 2:
            invader = game.choose("Which invader will you target", [i for i in land.invaders if isinstance(i, (Town, City))])
            if invader is None:
                return
            game.destroy_invader(land, invader)
        elif level == 1:
            invader = game.choose("Which invader will you target", [i for i in land.invaders if isinstance(i, (Town))])
            if invader is None:
                return
            game.destroy_invader(land, invader)

    def can_resolve(self, card, fast):
        if card in self.resolved: return False
        if card.fast == fast: return True
        return fast and self.swift_used < self.elements[AIR]


def A_Year_of_Perfect_Stillness(game, spirit, land):
    land.skip_ravage = True
    land.skip_build = True
    land.skip_explore = True

def Draw_of_the_Fruitful_Earth(game, spirit, land):
    for _ in range(2):
        game.gather(land, Explorer, "Choose which Explorers to gather")
    for _ in range(2):
        game.gather(land, Dahan, "Choose which Dahan to gather")

def Guard_the_Healing_Land(game, spirit, land):
    game.remove_blight(land)
    land.defense += 4

def Rituals_of_Destruction(game, spirit, land):
    game.damage_invaders(land, 2)
    if len(land.dahan) >= 3:
        game.damage_invaders(land, 3)
        game.add_fear(2)

EARTH_CARDS = [
    Power_Card("A Year of Perfect Stillness", 3, True, [SUN, EARTH], A_Year_of_Perfect_Stillness, target_range=1),
    Power_Card("Draw of the Fruitful Earth", 1, False, [EARTH, PLANT, ANIMAL], Draw_of_the_Fruitful_Earth, target_range=1),
    Power_Card("Guard the Healing Land", 3, True, [WATER, EARTH, PLANT], Guard_the_Healing_Land, target_range=1, from_sacred_site=True),
    Power_Card("Rituals of Destruction", 3, False, [SUN, MOON, FIRE, EARTH, PLANT], Rituals_of_Destruction, target_range=1, from_sacred_site=True, target_filter =(lambda l: l.dahan))
]
EARTH_ENERGY_TRACK = [2, 3, 4, 6, 7, 8]
EARTH_CARD_TRACK = [1, 1, 2, 2, 3, 4]
class Vital_Strength_of_the_Earth(Spirit):
    def __init__(self):
        super().__init__()
        self.hand = list(EARTH_CARDS)
        self.top_track = 5       # presence left on the energy track
        self.bottom_track = 5    # presence left on the card-play track
        self.update_tracks()
        self.innate_fast = True

    def update_tracks(self):
        self.energy_turn = EARTH_ENERGY_TRACK[5 - self.top_track]
        self.card_plays = EARTH_CARD_TRACK[5 - self.bottom_track]

    def get_bonus_defense(self, land):
        return 3 if land.presence >= 2 else 0

    def before_fast_phase(self):
        self.innate()

    def setup(self, board):
        mountains = [l for l in board.get_lands() if l.terrain == MOUNTAIN]
        jungle = [l for l in board.get_lands() if l.terrain == JUNGLE]
        max(mountains, key=lambda l: l.number).presence += 2
        max(jungle, key=lambda l: l.number).presence += 1


    def add_presence(self, game, distance):
        tracks = [t for t in ("energy", "card plays") if
                  (self.top_track if t == "energy" else self.bottom_track) > 0]
        track = game.choose("Take presence from which track?", tracks)
        if track is None:
            return
        options = game.board.lands_within(self.presence_lands(game.board), distance)
        land = game.choose("Add presence (range %d) to?" % distance, options)
        if track == "energy":
            self.top_track -= 1
        else:
            self.bottom_track -= 1
        land.presence += 1
        self.update_tracks()

    def G1(self, game):
        self.reclaim_all()
        self.add_presence(game, 2)

    def G2(self, game):
        self.gain_card()
        self.add_presence(game, 0)

    def G3(self, game):
        self.add_presence(game, 1)
        self.energy += 2

    def growth(self, game):
        option = game.choose("Choose growth", ["G1: reclaim all, add a presence (range 2)",
                                               "G2: add 1 presence (range 0), gain a power card",
                                               "G3: +2 energy, add presence (range 1)"])
        getattr(self, option[:2])(game)
        self.energy += self.energy_turn

    def innate(self, game=None):
        e = self.elements
        if e[SUN] >= 2 and e[EARTH] >= 4 and e[PLANT] >= 3:
            self.repeat_max_cost = 6
        elif e[SUN] >= 2 and e[EARTH] >= 3 and e[PLANT] >= 2:
            self.repeat_max_cost = 3
        elif e[SUN] >= 1 and e[EARTH] >= 2 and e[PLANT] >= 2:
            self.repeat_max_cost = 1

def Concealing_Shadows(game, spirit, land):
    game.add_fear(1)
    land.skip_dahan_ravage_damage = True

def Crops_Wither_and_Fade(game, spirit, land):
    game.add_fear(2)
    invader = game.choose("Choose a Town or City", [i for i in land.invaders if isinstance(i, (Town, City))])
    if invader is None:
        return
    if isinstance(invader, Town):
        land.invaders.append(Explorer())
    elif isinstance(invader, City):
        land.invaders.append(Town())
    land.invaders.remove(invader)


def Favors_Called_Due(game, spirit, land):
    for _ in range(4):
        game.gather(land, Dahan, "Choose which Dahan to gather")
    if 0 < len(land.invaders) < len(land.dahan):
        game.add_fear(3)

def Mantle_of_Dread(game, spirit, land):
    game.add_fear(2)
    target = game.choose("Choose a land with your presence", spirit.presence_lands(game.board))
    game.push(target, Town, "Choose which Town to push")
    game.push(target, Explorer, "Choose which Explorer to push")

SHADOWS_CARDS = [
    Power_Card("Concealing Shadows", 0, True, [MOON, AIR], Concealing_Shadows, target_range=0),
    Power_Card("Crops Wither and Fade", 1, False, [MOON, FIRE, PLANT], Crops_Wither_and_Fade, target_range=0),
    Power_Card("Favors Called Due", 1, False, [MOON, AIR, ANIMAL], Favors_Called_Due, target_range=1),
    Power_Card("Mantle of Dread", 1, False, [MOON, FIRE, AIR], Mantle_of_Dread)
]
SHADOWS_ENERGY_TRACK = [0, 1, 3, 4, 5, 6]
SHADOWS_CARD_TRACK = [1, 2, 3, 3, 4, 5]
class Shadows_Flicker_Like_Flame(Spirit):
    def __init__(self):
        super().__init__()
        self.hand = list(SHADOWS_CARDS)
        self.top_track = 5       # presence left on the energy track
        self.bottom_track = 5    # presence left on the card-play track
        self.update_tracks()
        self.innate_fast = True

    def update_tracks(self):
        self.energy_turn = SHADOWS_ENERGY_TRACK[5 - self.top_track]
        self.card_plays = SHADOWS_CARD_TRACK[5 - self.bottom_track]

    def setup(self, board):
        jungle = [l for l in board.get_lands() if l.terrain == JUNGLE]
        max(jungle, key=lambda l: l.number).presence += 2
        board.get_land(5).presence += 1

    def add_presence(self, game, distance):
        tracks = [t for t in ("energy", "card plays") if
                  (self.top_track if t == "energy" else self.bottom_track) > 0]
        track = game.choose("Take presence from which track?", tracks)
        if track is None:
            return
        options = game.board.lands_within(self.presence_lands(game.board), distance)
        land = game.choose("Add presence (range %d) to?" % distance, options)
        if track == "energy":
            self.top_track -= 1
        else:
            self.bottom_track -= 1
        land.presence += 1
        self.update_tracks()

    def G1(self, game):
        self.reclaim_all()
        self.gain_card()

    def G2(self, game):
        self.add_presence(game, 1)
        self.gain_card()

    def G3(self, game):
        self.add_presence(game, 3)
        self.energy += 3

    def growth(self, game):
        option = game.choose("Choose growth", ["G1: reclaim all, gain a power",
                                               "G2: add 1 presence (range 1), gain a power",
                                               "G3: gain +3 energy, add presence (range 3)"])
        getattr(self, option[:2])(game)
        self.energy += self.energy_turn

    def innate(self, game):
        level = 0
        e = self.elements

        if e[MOON] >= 4 and e[FIRE] >= 3 and e[AIR] >= 2:
            level = 3
        elif e[MOON] >= 3 and e[FIRE] >= 2:
            level = 2
        elif e[MOON] >= 2 and e[FIRE] >= 1:
            level = 1

        if level == 3:
            land = game.choose("Choose a land?", game.board.lands_within(self.sacred_sites(game.board), 1))
            if land is None: return
            game.gather(land, Explorer, "Choose an explorer to gather")
            for _ in range(2):
                e = game.choose("Destroy which Explorer?", [i for i in land.invaders if isinstance(i, Explorer)], allow_none=True)
                if e is None: break
                game.destroy_invader(land, e)
                game.add_fear(1)
            before = len(land.invaders)
            game.damage_invaders(land, 3)
            game.add_fear(before-len(land.invaders))
        elif level == 2:
            land = game.choose("Choose a land?", game.board.lands_within(self.sacred_sites(game.board), 1))
            if land is None: return
            game.gather(land, Explorer, "Choose an explorer to gather")
            for _ in range(2):
                e = game.choose("Destroy which Explorer?", [i for i in land.invaders if isinstance(i, Explorer)], allow_none=True)
                if e is None: break
                game.destroy_invader(land, e)
                game.add_fear(1)
        elif level == 1:
            land = game.choose("Choose a land?", game.board.lands_within(self.sacred_sites(game.board), 1))
            if land is None: return
            game.gather(land, Explorer, "Choose an explorer to gather")

THUNDERSPEAKER_CARDS = []
THUNDERSPEAKER_ENERGY_TRACK = [1, 1, 2, 2, 2, 3]
THUNDERSPEAKER_CARD_TRACK = [1, 2, 2, 3, 3, 3, 4]
THUNDERSPEAKER_RECLAIM_FROM = 4
THUNDERSPEAKER_AIR = 1
THUNDERSPEAKER_FIRE = 3
THUNDERSPEAKER_SUN = 4
class Thunderspeaker(Spirit):
    pass;

RAMPANT_CARDS = []
RAMPANT_ENERGY_TRACK = [0, 1, 1, 2, 2, 2, 3]
RAMPANT_CARD_TRACK = [1, 1, 2, 2, 3, 4]
RAMPANT_PLANT = [2, 5]
class A_Spread_of_Rampant_Green(Spirit):
    pass;

OCEAN_CARDS = []
OCEAN_ENERGY_TRACK = [0, 0, 0, 1, 1, 1, 2]
OCEAN_CARD_TRACK = [1, 2, 2, 3, 4, 5]
OCEAN_MOON = 1
OCEAN_WATER = [2, 5]
OCEAN_EARTH = 4
class Oceans_Hungry_Grasp(Spirit):
    pass;

NIGHTMARES_CARDS = []
NIGHTMARES_ENERGY_TRACK = [2, 2, 3, 3, 4, 4, 5]
NIGHTMARES_CARD_TRACK = [2, 2, 2, 3, 3, 3]
NIGHTMARE_AIR = 1
NIGHTMARE_MOON = 3
NIGHTMARE_ANY = 5
class Bringer_of_Dreams_and_Nightmares(Spirit):
    pass;

# Decision kinds, matched against the start of each prompt passed to Game.choose
PROMPT_KINDS = ["Choose growth", "Take presence", "Add presence", "Reclaim which", "Play a card",
                "Target land", "Massive Flooding", "Damage which", "Push which", "Push ", "Gather",
                "Blight cascades", "Resolve which"]
MAX_OPTIONS = 16    # options past this many can't be picked by the model
STATE_SIZE = 8 * 6 + 4 + 3 * len(RIVER_CARDS) + 8 + 7 + 2 * 5 + len(PROMPT_KINDS) + 1 + MAX_OPTIONS


def option_code(option):
    # One number that says what an option is: a land's number, a card, a piece type, or 0 for "nothing"
    if isinstance(option, Land):
        return option.number
    if isinstance(option, Power_Card):
        return 10 + RIVER_CARDS.index(option) if option in RIVER_CARDS else 10
    if isinstance(option, Piece):
        return 20 + [Explorer, Town, City, Dahan].index(type(option))
    if isinstance(option, str):
        return 30 + (int(option[1]) if option[:1] == "G" and option[1:2].isdigit() else 0)
    return 0


class Game:
    def __init__(self, Board_Letter="A", chooser=None, seed=None):
        rng = random.Random(seed)
        self.chooser = chooser or Random_Chooser(seed)
        self.current_options = []     # options at the decision being made right now
        self.current_prompt = ""      # the question being asked right now
        self.board = setup_board(Board_Letter)
        self.spirit = River_Surges_Like_Sunlight()
        self.spirit.setup(self.board)
        self.invader_deck = Invader_Deck(rng)
        self.blight_pool = HEALTHY_BLIGHT
        self.blighted_island = False
        self.fear_pool = FEAR_POOL
        self.fear_cards_earned = 0
        self.fear_cards_resolved = 0
        self.turn_number = 0
        self.ravage_card = None
        self.build_card = None
        # Initial explore, then the card advances to Build
        self.build_card = self.explore(self.draw_invader_card())

    def choose(self, prompt, options, allow_none=False):
        # Every player decision goes through here so the current options are always known
        options = list(options)
        self.current_options = ([None] if allow_none else []) + options
        self.current_prompt = prompt
        choice = self.chooser.choose(prompt, options, allow_none)
        self.current_options = []
        self.current_prompt = ""
        return choice

    def num_actions(self):
        # Number of actions available at the current decision point ("do nothing" counts as one).
        # Call it from inside a chooser's choose(); between decisions it is 0.
        return len(self.current_options)

    def getDahan(self):
        dahan = 0
        for land in self.board.get_lands():
            dahan += len(land.dahan)
        return dahan

    def getPresence(self):
        presence = 0
        for land in self.board.get_lands():
            presence += land.presence
        return presence

    def getGameState(self):
        # The game as a flat list of numbers for the model (STATE_SIZE long).
        # Call it from inside a chooser's choose() so the current decision is included.
        state = []
        for land in self.board.get_lands():
            state += [land.explorer, land.town, land.city, len(land.dahan), land.blight, land.presence]
        spirit = self.spirit
        state += [spirit.energy, spirit.card_plays, spirit.top_track, spirit.bottom_track]
        for pile in (spirit.hand, spirit.discard_pile, spirit.played):
            state += [1 if card in pile else 0 for card in RIVER_CARDS]
        state += spirit.elements
        state += [self.blight_pool, int(self.blighted_island), self.fear_pool, self.fear_cards_earned,
                  self.terror_level, self.turn_number, len(self.invader_deck.cards)]
        for card in (self.ravage_card, self.build_card):
            state += [0] * 5 if card is None else [
                                                      int(t in card.terrains) for t in (MOUNTAIN, WETLAND, JUNGLE, SANDS)] + [int(card.coastal)]
        # Which kind of decision this is, how many options it has, and what each option is
        state += [int(self.current_prompt.startswith(p)) for p in PROMPT_KINDS]
        state.append(len(self.current_options))
        for i in range(MAX_OPTIONS):
            state.append(option_code(self.current_options[i]) if i < len(self.current_options) else -1)
        return state

    @property
    def terror_level(self):
        return 1 + self.fear_cards_earned // 3

    def log(self, text):
        if isinstance(self.chooser, Human_Chooser):
            print(text)

    def play_turn(self):
        self.turn_number += 1
        self.log("--- Turn %d ---" % self.turn_number)
        self.spirit_phase()
        self.resolve_powers(fast=True)
        self.invader_phase()
        self.resolve_powers(fast=False)
        self.time_passes()

    def spirit_phase(self):
        spirit = self.spirit
        spirit.growth(self)
        for _ in range(spirit.card_plays):
            affordable = [c for c in spirit.hand if c.cost <= spirit.energy]
            card = self.choose("Play a card? (energy %d)" % spirit.energy, affordable, allow_none=True)
            if card is None:
                break
            spirit.play_card(card)


    def resolve_power(self, card):
        s = self.spirit
        s.resolved.add(card)
        self.apply_power(card, s)
        if 0 <= card.cost <= s.repeat_max_cost and s.energy >= card.cost:
            if self.choose("Repeat %s?" % card.name, ["Repeat"], allow_none=True):
                s.energy -= card.cost
                s.repeat_max_cost = -1
                self.apply_power(card, s)


    def apply_power(self, card, s):
        land = None
        if card.target_range is not None:
            if card.needs_presence:
                options = s.presence_lands(self.board)
            elif card.from_sacred_site:
                options = self.board.lands_within(s.sacred_sites(self.board), card.target_range)
            else:
                options = self.board.lands_within(s.presence_lands(self.board), card.target_range)
            if card.target_filter:
                options = [l for l in options if card.target_filter(l)]
            land = self.choose("Target land for %s?" % card.name, options)
            if land is None:
                return
        card.effect(self, s, land)
        self.check_victory()

    def resolve_powers(self, fast):
        s = self.spirit
        if fast:
            s.before_fast_phase()
        else:
            s.before_slow_phase()
        if s.innate_fast == fast:
            s.innate(self)
        while True:
            options = [c for c in s.played if s.can_resolve(c, fast)]
            card = self.choose("Resolve which power next?", options)
            if card is None: break
            if card.fast != fast: s.swift_used += 1
            self.resolve_power(card)

    def invader_phase(self):
        self.resolve_fear_cards()
        if self.ravage_card:
            for land in self.board.get_lands():
                if self.ravage_card.matches(land) and land.has_invaders() and not land.skip_ravage:
                    self.ravage(land)
        if self.build_card:
            for land in self.board.get_lands():
                if self.build_card.matches(land) and land.has_invaders() and not land.skip_build:
                    self.build(land)
        explored = self.explore(self.draw_invader_card())
        self.ravage_card = self.build_card
        self.build_card = explored

    def draw_invader_card(self):
        card = self.invader_deck.draw()
        if card is None:
            raise GameOver(False, "The invader deck ran out")
        self.log("Invader card: %s" % card)
        return card

    def resolve_fear_cards(self):
        # TODO: fear card effects
        self.fear_cards_resolved = self.fear_cards_earned

    def ravage(self, land):
        damage = max(0, sum(i.attack for i in land.invaders) - land.defense - self.spirit.get_bonus_defense(land))
        if damage >= 2:
            self.add_blight(land)
        # Invaders destroy as many Dahan as they can
        remaining = damage
        for dahan in sorted(land.dahan, key=lambda d: d.health):
            if remaining <= 0:
                break
            hit = min(remaining, dahan.health)
            remaining -= hit
            if not land.skip_dahan_ravage_damage:
                if dahan.take_damage(hit):
                    land.dahan.remove(dahan)
        if land.dahan:
            self.damage_invaders(land, sum(d.attack for d in land.dahan))

    def build(self, land):
        land.invaders.append(City() if land.builds_city() else Town())

    def explore(self, card):
        targets = [land for land in self.board.get_lands() if card.matches(land) and (
                land.coastal or land.has_building()
                or any(a.has_building() for a in self.board.get_adjacent(land)))]
        for land in targets:
            if not land.skip_explore:
                land.invaders.append(Explorer())
        return card

    def damage_invaders(self, land, amount):
        while amount > 0 and land.invaders:
            target = self.choose("Damage which invader in %s? (%d left)" % (land, amount), land.invaders)
            hit = min(amount, target.health)
            amount -= hit
            if target.take_damage(hit):
                self.destroy_invader(land, target)

    def destroy_invader(self, land, invader):
        land.invaders.remove(invader)
        if isinstance(invader, Town):
            self.add_fear(1)
        elif isinstance(invader, City):
            self.add_fear(2)
        self.check_victory()

    def push(self, land, kinds, prompt):
        pieces = [p for p in land.invaders + land.dahan if isinstance(p, kinds)]
        piece = self.choose(prompt, pieces, allow_none=True)
        if piece is None:
            return
        destination = self.choose("Push %s to?" % piece.name, self.board.get_adjacent(land))
        source_list = land.dahan if isinstance(piece, Dahan) else land.invaders
        source_list.remove(piece)
        (destination.dahan if isinstance(piece, Dahan) else destination.invaders).append(piece)

    def gather(self, land, kind, prompt):
        options = [(p, a) for a in self.board.get_adjacent(land)
                   for p in (a.dahan if kind is Dahan else a.invaders) if isinstance(p, kind)]
        labels = ["%s from land %d" % (p.name, a.number) for p, a in options]
        choice = self.choose(prompt, labels, allow_none=True)
        if choice is None:
            return
        piece, source = options[labels.index(choice)]
        if kind is Dahan:
            source.dahan.remove(piece)
            land.dahan.append(piece)
        else:
            source.invaders.remove(piece)
            land.invaders.append(piece)

    def add_fear(self, amount):
        for _ in range(amount):
            self.fear_pool -= 1
            if self.fear_pool == 0:
                self.fear_pool = FEAR_POOL
                self.fear_cards_earned += 1
                if self.fear_cards_earned >= FEAR_CARDS:
                    raise GameOver(True, "The fear deck is empty")

    def add_blight(self, land, blight_num=1):
        had_blight = land.blight > 0
        land.blight += blight_num
        self.blight_pool -= blight_num
        if land.presence > 0:
            land.presence -= 1
            if not self.spirit.presence_lands(self.board):
                raise GameOver(False, "The spirit has no presence left on the island")
        if self.blight_pool <= 0:
            if self.blighted_island:
                raise GameOver(False, "The blight pool ran out")
            self.blighted_island = True
            self.blight_pool += BLIGHTED_ISLAND_BLIGHT

        if had_blight and blight_num > 0:
            target = self.choose("Blight cascades from %s to?" % land, self.board.get_adjacent(land))
            self.add_blight(target)

    def remove_blight(self, land):
        if land.blight > 0:
            land.blight -= 1
            self.blight_pool += 1

    def check_victory(self):
        lands = self.board.get_lands()
        if self.terror_level == 1:
            done = not any(l.has_invaders() for l in lands)
        elif self.terror_level == 2:
            done = not any(l.has_building() for l in lands)
        else:
            done = not any(l.city for l in lands)
        if done:
            raise GameOver(True, "Terror level %d victory" % self.terror_level)

    def time_passes(self):
        for land in self.board.get_lands():
            for piece in land.invaders + land.dahan:
                piece.heal()
            land.defense = 0
            land.skip_ravage = land.skip_build = land.skip_explore = land.skip_dahan_ravage_damage = False
        self.spirit.end_turn()


def num_actions(game):
    return game.num_actions()


def main(Board_Letter="A", chooser=None, seed=None):
    game = Game(Board_Letter, chooser, seed)
    try:
        while True:
            game.play_turn()
    except GameOver as result:
        print("%s after %d turns: %s" % ("Victory" if result.win else "Defeat", game.turn_number, result.reason))
        return result.win


if __name__ == "__main__":
    if "--human" in sys.argv:
        main("A", Human_Chooser())
    else:
        main("A", Random_Chooser())
