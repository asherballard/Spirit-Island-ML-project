import queue
import threading

from Game import (Game, GameOver, MAX_OPTIONS, FEAR_POOL, FEAR_CARDS, PROMPT_KINDS, RIVER_CARDS,
                  Land, Power_Card, Piece, Explorer, Town, City, Dahan,
                  MOUNTAIN, WETLAND, JUNGLE, SANDS)


# Rewards the agent gets between two of its decisions.
# They are kept small (around -1..1 per turn) so no single signal drowns out the others,
# and so the Q values the network has to predict stay in a sensible range.
TURN_REWARD = 1.0         # for every invader phase the island survives: this is what "score" measures
BLIGHT_REWARD = -0.5      # per blight added to the island (8 blight loses the game)
BLIGHT_REMOVED_REWARD = 0.5 # per blight removed from the island until there's no blight
FEAR_REWARD = 0.1         # per fear generated
CLEAR_REWARD = 0.1        # per point of invader size removed from the island (explorer 1, town 2, city 3):
# a win needs every invader gone (Terror Level 1), so shrinking them is progress
PRESENCE_REWARD = 0.1     # per presence taken off a track (a one-off bonus, not paid again every step)
CARD_REWARD = 0.2 # per card played each turn, meant to help encourage the model to find River's optimal playstyle
SPEED_REWARD = -1.0 # This is meant to encourage faster wins by penalizing the model for not winning sooner, will ideally help the model avoid excessive buildup
WIN_REWARD = 20
LOSS_REWARD = -1

TERRAINS = (MOUNTAIN, WETLAND, JUNGLE, SANDS)
PIECES = (Explorer, Town, City, Dahan)
LAND_FEATURES = 16
OPTION_FEATURES = 2 + 4 + 3 + 4 + 1 + 3 + 2 + 1 + LAND_FEATURES
GLOBAL_FEATURES = 8 * LAND_FEATURES + 4 + 3 * len(RIVER_CARDS) + 8 + 7 + len(PROMPT_KINDS) + 1
STATE_SIZE = GLOBAL_FEATURES + MAX_OPTIONS * OPTION_FEATURES


class _Env_Chooser:
    # Runs on the game thread: hands each decision to the agent and waits for its answer
    def __init__(self, env):
        self.env = env

    def choose(self, prompt, options, allow_none=False):
        options = ([None] if allow_none else []) + list(options)
        if not options:
            return None
        if len(options) == 1:
            return options[0]    # nothing to decide, so don't make the agent learn it
        self.env._to_agent.put(("decision", None))
        action = self.env._to_game.get()
        return options[min(action, len(options) - 1)]


class Spirit_Island_Env:
    # Wraps Game so the agent can drive it one decision at a time:
    #   state = env.getGameState(); reward, done, score = env.play_step(action); env.reset()
    # The game runs on its own thread and pauses at every choice until play_step answers it.
    def __init__(self, Board_Letter="A", seed=None):
        self.Board_Letter = Board_Letter
        self.seed = seed
        self.reset()

    def reset(self):
        self._to_agent = queue.Queue()
        self._to_game = queue.Queue()
        self.game = Game(self.Board_Letter, _Env_Chooser(self), self.seed)
        if self.seed is not None:
            self.seed += 1
        self.win = None
        self.reason = ""
        self._blight_added = 0
        self._count_blight()
        self._count_stats()
        self._last = self._totals()
        threading.Thread(target=self._run, daemon=True).start()
        self._wait()

    def _count_blight(self):
        # Wrap add_blight so blight (including cascades) is counted for the reward
        add_blight = self.game.add_blight
        def counted(land):
            self._blight_added += 1
            add_blight(land)
        self.game.add_blight = counted

    def _count_stats(self):
        # Per-game stats for tracking progress: cards played and invaders destroyed
        self.cards_played = 0
        self.invaders_destroyed = 0
        play_card = self.game.spirit.play_card
        def counted_play(card):
            self.cards_played += 1
            play_card(card)
        self.game.spirit.play_card = counted_play
        destroy_invader = self.game.destroy_invader
        def counted_destroy(land, invader):
            self.invaders_destroyed += 1
            destroy_invader(land, invader)
        self.game.destroy_invader = counted_destroy

    def presence_placed(self):
        # Presence taken off the two tracks so far this game
        spirit = self.game.spirit
        return (6 - spirit.top_track) + (6 - spirit.bottom_track)

    def stats(self):
        return {"Cards played": self.cards_played,
                "Presence placed": self.presence_placed(),
                "Invaders destroyed": self.invaders_destroyed}

    def _fear_total(self):
        return self.game.fear_cards_earned * FEAR_POOL + (FEAR_POOL - self.game.fear_pool)

    def _totals(self):
        size = sum(i.max_health for l in self.game.board.get_lands() for i in l.invaders)
        return {"turns": self.game.turn_number, "blight": self._blight_added, "fear": self._fear_total(),
                "size": size, "presence": self.presence_placed()}

    def _run(self):
        try:
            while True:
                self.game.play_turn()
        except GameOver as result:
            self._to_agent.put(("over", result))

    def _wait(self):
        kind, result = self._to_agent.get()
        if kind == "over":
            self.win = result.win
            self.reason = result.reason
        return kind == "over"

    def num_actions(self):
        return min(self.game.num_actions(), MAX_OPTIONS)

    def getGameState(self):
        return encode_state(self.game)

    def score(self):
        # Turns survived; a win counts every turn as played
        return self.game.turn_number

    def play_step(self, action):
        self._to_game.put(action)
        done = self._wait()
        now = self._totals()
        d = {k: now[k] - self._last[k] for k in now}
        self._last = now
        reward = (d["turns"] * TURN_REWARD + d["blight"] * BLIGHT_REWARD + d["fear"] * FEAR_REWARD
                  - d["size"] * CLEAR_REWARD + max(0, d["presence"]) * PRESENCE_REWARD)
        if done:
            reward += WIN_REWARD if self.win else LOSS_REWARD
        return reward, done, self.score()


# ---- state encoding ----
# Every number is scaled to roughly 0..1, and each option the agent can pick is described by what
# it actually is (which land and what is on it, which card, which piece), not by a single code number.

def land_features(game, land):
    ravage, build = game.ravage_card, game.build_card
    sites = game.spirit.sacred_sites(game.board)
    in_flood_range = land in game.board.lands_within(sites, 1) if sites else False
    return [int(land in sites), int(in_flood_range), int(sum(i.attack for i in land.invaders) >= 2),
            land.explorer / 3, land.town / 3, land.city / 3, len(land.dahan) / 3, land.blight / 3,
            land.presence / 3, int(land.coastal),
            int(bool(ravage and ravage.matches(land))), int(bool(build and build.matches(land)))] + \
        [int(land.terrain == t) for t in TERRAINS]


def option_features(game, option):
    f = [1, int(option is None)]
    f += [int(option is c) for c in RIVER_CARDS]
    f += [option.cost / 2, int(option.fast), 1] if isinstance(option, Power_Card) else [0, 0, 0]
    f += [int(type(option) is p) for p in PIECES]
    f += [option.health / 3] if isinstance(option, Piece) else [0]
    is_text = isinstance(option, str)
    f += [int(is_text and option.startswith("G%d" % g)) for g in (1, 2, 3)]
    f += [int(option == "energy"), int(option == "card plays")]
    land = option if isinstance(option, Land) else None
    if is_text and " from land " in option:           # gather: "Dahan from land 3"
        land = game.board.get_land(int(option.rsplit(" ", 1)[1]))
    f += [int(land is not None)]
    f += land_features(game, land) if land is not None else [0] * LAND_FEATURES
    return f


def encode_state(game):
    # The game as a flat list of numbers for the model (STATE_SIZE long).
    # Call it while the game is waiting on a decision so the current options are included.
    state = []
    for land in game.board.get_lands():
        state += land_features(game, land)
    spirit = game.spirit
    state += [spirit.energy / 5, spirit.card_plays / 4, spirit.top_track / 6, spirit.bottom_track / 6]
    for pile in (spirit.hand, spirit.discard_pile, spirit.played):
        state += [1 if card in pile else 0 for card in RIVER_CARDS]
    state += [e / 4 for e in spirit.elements]
    state += [game.blight_pool / 5, int(game.blighted_island), game.fear_pool / FEAR_POOL,
              game.fear_cards_earned / FEAR_CARDS, game.terror_level / 3, game.turn_number / 12,
              len(game.invader_deck.cards) / 12]
    state += [int(game.current_prompt.startswith(p)) for p in PROMPT_KINDS]
    state.append(len(game.current_options) / MAX_OPTIONS)
    for i in range(MAX_OPTIONS):
        if i < len(game.current_options):
            state += option_features(game, game.current_options[i])
        else:
            state += [0] * OPTION_FEATURES
    return state
