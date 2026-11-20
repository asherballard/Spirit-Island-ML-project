import argparse
import json
import os
import random
import queue
import threading
import tkinter as tk

from Game import (Game, GameOver, Land, Power_Card, Explorer, Town, City,
                  TERRAIN_NAMES, MOUNTAIN, WETLAND, JUNGLE, SANDS, FEAR_CARDS)

ELEMENT_NAMES = ["Sun", "Moon", "Fire", "Air", "Water", "Earth", "Plant", "Animal"]
TERRAIN_COLORS = {MOUNTAIN: "#b9b3a8", WETLAND: "#8fc1c9", JUNGLE: "#7fb069", SANDS: "#e8cf8a"}
OCEAN_COLOR = "#3f7cac"
HIGHLIGHT = "#ffd400"
PIECE_COLORS = {"E": "#d9d9d9", "T": "#c07a3a", "C": "#8a3b2e", "D": "#6b4f2a", "B": "#222222", "P": "#ffffff"}
PIECE_NAMES = {"E": "Explorer", "T": "Town", "C": "City", "D": "Dahan", "B": "Blight", "P": "Presence"}

# Where each land sits on the map (the ocean is on the left); adjacency lines come from the board data
LAND_POSITIONS = {1: (170, 105), 2: (130, 275), 3: (150, 440), 4: (300, 360),
                  5: (350, 215), 6: (360, 75), 7: (530, 330), 8: (540, 150)}
LAND_W, LAND_H = 150, 92
MAP_W, MAP_H = 640, 510


class Gui_Chooser:
    # Runs on the game thread: sends each decision to the window and waits for the player's click
    def __init__(self, to_gui, record=None):
        self.to_gui = to_gui
        self.to_game = queue.Queue()
        self.record = record   # called with (prompt, options, index) after every real decision

    def choose(self, prompt, options, allow_none=False):
        options = ([None] if allow_none else []) + list(options)
        if not options:
            return None
        if len(options) == 1:
            self.to_gui.put(("log", "%s  (only option: %s)" % (prompt, option_label(options[0]))))
            return options[0]
        self.to_gui.put(("decision", prompt, options))
        index = self.to_game.get()
        if self.record:
            self.record(prompt, options, index)
        return options[index]


def option_label(option):
    if option is None:
        return "Nothing / skip"
    if isinstance(option, Land):
        return "Land %d %s" % (option.number, TERRAIN_NAMES[option.terrain])
    if isinstance(option, Power_Card):
        return "%s  (cost %d, %s, %s)" % (option.name, option.cost, "fast" if option.fast else "slow",
                                          " ".join(ELEMENT_NAMES[e] for e in option.elements))
    return str(option)


class Play_Window:
    def __init__(self, board_letter="A", seed=None):
        self.board_letter = board_letter
        self.seed = seed
        self.root = tk.Tk()
        self.root.title("Spirit Island")
        self.root.configure(bg="#f4f1ea")
        self.build_widgets()
        self.new_game()
        self.root.after(50, self.poll)

    # ---- layout ----
    def build_widgets(self):
        root = self.root
        left = tk.Frame(root, bg="#f4f1ea")
        left.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        right = tk.Frame(root, bg="#f4f1ea")
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 8), pady=8)
        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(left, width=MAP_W, height=MAP_H, bg=OCEAN_COLOR, highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_map_click)
        self.legend = tk.Canvas(left, width=MAP_W, height=26, bg="#f4f1ea", highlightthickness=0)
        self.legend.pack(pady=(4, 0))
        self.draw_legend()

        log_frame = tk.Frame(left)
        log_frame.pack(fill="both", expand=True, pady=(6, 0))
        self.log_text = tk.Text(log_frame, height=10, width=80, wrap="word", font=("Consolas", 9),
                                state="disabled", bg="white")
        scroll = tk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.status = tk.Label(right, justify="left", anchor="nw", font=("Segoe UI", 10),
                               bg="#f4f1ea")
        self.status.pack(fill="x")
        self.spirit_label = tk.Label(right, justify="left", anchor="nw", font=("Segoe UI", 10),
                                     bg="#f4f1ea")
        self.spirit_label.pack(fill="x", pady=(8, 0))

        self.decision = tk.LabelFrame(right, text=" Your decision ", font=("Segoe UI", 10, "bold"),
                                      bg="#fffbe6", padx=8, pady=6)
        self.decision.pack(fill="both", expand=True, pady=(10, 0))

        bottom = tk.Frame(right, bg="#f4f1ea")
        bottom.pack(fill="x", pady=(8, 0))
        tk.Button(bottom, text="New game", command=self.new_game).pack(side="right")

    def draw_legend(self):
        x = 6
        for key in "ETCDBP":
            self.draw_piece(self.legend, key, x + 7, 13)
            self.legend.create_text(x + 17, 13, text=PIECE_NAMES[key], anchor="w", font=("Segoe UI", 9))
            x += 100

    # ---- game thread ----
    def new_game(self):
        self.to_gui = queue.Queue()
        # Every game gets a seed and is saved to games/, so it can be replayed exactly (e.g. to teach the agent)
        seed = self.seed if self.seed is not None else random.randrange(1_000_000)
        recording = {"board": self.board_letter, "seed": seed, "decisions": []}
        path = os.path.join("games", "game_%d.json" % seed)
        def record(prompt, options, index):
            recording["decisions"].append({"turn": self.game.turn_number, "prompt": prompt,
                                           "options": [option_label(o) for o in options], "choice": index})
            recording["result"] = None
            os.makedirs("games", exist_ok=True)
            with open(path, "w") as f:
                json.dump(recording, f, indent=1)
        self.recording, self.recording_path = recording, path
        self.chooser = Gui_Chooser(self.to_gui, record)
        self.game = Game(self.board_letter, self.chooser, seed)
        if self.seed is not None:
            self.seed += 1
        self.options = []
        self.over = None
        self.hook_log(self.game)
        self.clear_log()
        self.log("Seed %d: this game is saved to %s" % (seed, path))
        self.log("New game on board %s. Invader card to build next: %s" % (self.board_letter, self.game.build_card))
        game, to_gui = self.game, self.to_gui

        def run():
            try:
                while True:
                    game.play_turn()
            except GameOver as result:
                recording["result"] = {"win": result.win, "reason": result.reason, "turns": game.turn_number}
                os.makedirs("games", exist_ok=True)
                with open(path, "w") as f:
                    json.dump(recording, f, indent=1)
                to_gui.put(("over", result.win, result.reason))
        threading.Thread(target=run, daemon=True).start()
        self.show_decision(None, [])
        self.redraw()

    def hook_log(self, game):
        # Report what the invaders and the game do, without changing Game.py
        put = lambda text: self.to_gui.put(("log", text))
        game.log = put

        ravage = game.ravage
        def logged_ravage(land):
            before = str(land)
            ravage(land)
            put("Ravage in %s  ->  %s" % (before, land))
        game.ravage = logged_ravage

        build = game.build
        def logged_build(land):
            build(land)
            put("Build: %s in land %d" % (land.invaders[-1].name, land.number))
        game.build = logged_build

        explore = game.explore
        def logged_explore(card):
            before = {l.number: l.explorer for l in game.board.get_lands()}
            result = explore(card)
            lands = [str(n) for n, e in before.items() if game.board.get_land(n).explorer > e]
            put("Explore (%s): explorers arrive in %s" % (card, ", ".join("land " + n for n in lands) or "no lands"))
            return result
        game.explore = logged_explore

        add_blight = game.add_blight
        def logged_add_blight(land):
            put("Blight added to land %d" % land.number)
            add_blight(land)
        game.add_blight = logged_add_blight

        add_fear = game.add_fear
        def logged_add_fear(amount):
            put("+%d fear" % amount)
            add_fear(amount)
        game.add_fear = logged_add_fear

    def poll(self):
        # Handle everything the game thread sent; the game is paused whenever a decision is shown
        changed = False
        try:
            while True:
                message = self.to_gui.get_nowait()
                if message[0] == "log":
                    self.log(message[1])
                elif message[0] == "decision":
                    self.show_decision(message[1], message[2])
                    changed = True
                elif message[0] == "over":
                    self.over = (message[1], message[2])
                    self.log("%s after %d turns: %s" % ("VICTORY" if message[1] else "DEFEAT",
                                                        self.game.turn_number, message[2]))
                    self.show_decision(None, [])
                    changed = True
        except queue.Empty:
            pass
        if changed:
            self.redraw()
        self.root.after(50, self.poll)

    def answer(self, index):
        if not self.options:
            return
        self.log("  You chose: %s" % option_label(self.options[index]))
        self.options = []
        self.show_decision(None, [])
        self.chooser.to_game.put(index)

    # ---- decision panel ----
    def show_decision(self, prompt, options):
        for child in self.decision.winfo_children():
            child.destroy()
        self.options = options
        if self.over:
            win, reason = self.over
            tk.Label(self.decision, text=("Victory!" if win else "Defeat"), font=("Segoe UI", 16, "bold"),
                     fg="#2e7d32" if win else "#b3261e", bg="#fffbe6").pack(anchor="w")
            tk.Label(self.decision, text="%s\nTurns played: %d" % (reason, self.game.turn_number),
                     justify="left", bg="#fffbe6", font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 8))
            tk.Button(self.decision, text="Play again", command=self.new_game).pack(anchor="w")
            return
        if prompt is None:
            tk.Label(self.decision, text="Invaders are acting...", bg="#fffbe6",
                     font=("Segoe UI", 10, "italic")).pack(anchor="w")
            return
        tk.Label(self.decision, text=prompt, wraplength=330, justify="left", bg="#fffbe6",
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 6))
        if any(isinstance(o, Land) for o in options):
            tk.Label(self.decision, text="Click a highlighted land on the map, or a button:", bg="#fffbe6",
                     font=("Segoe UI", 9)).pack(anchor="w")
        for i, option in enumerate(options):
            tk.Button(self.decision, text="%d.  %s" % (i + 1, option_label(option)), anchor="w",
                      command=lambda i=i: self.answer(i)).pack(fill="x", pady=1)
        self.root.bind("<Key>", self.on_key)

    def on_key(self, event):
        if event.char.isdigit() and 1 <= int(event.char) <= min(9, len(self.options)):
            self.answer(int(event.char) - 1)

    def on_map_click(self, event):
        for i, option in enumerate(self.options):
            if isinstance(option, Land):
                x, y = LAND_POSITIONS[option.number]
                if abs(event.x - x) <= LAND_W / 2 and abs(event.y - y) <= LAND_H / 2:
                    self.answer(i)
                    return

    # ---- drawing ----
    def redraw(self):
        self.draw_map()
        self.draw_status()

    def draw_map(self):
        c = self.canvas
        c.delete("all")
        c.create_text(14, MAP_H / 2, text="OCEAN", angle=90, fill="#cfe3f2", font=("Segoe UI", 12, "bold"))
        board = self.game.board
        for land in board.get_lands():
            for n in land.get_adjacencies():
                if n > land.number:
                    (x1, y1), (x2, y2) = LAND_POSITIONS[land.number], LAND_POSITIONS[n]
                    c.create_line(x1, y1, x2, y2, fill="#e8f0f6", width=3)
        choosable = {o.number for o in self.options if isinstance(o, Land)}
        for land in board.get_lands():
            self.draw_land(land, land.number in choosable)

    def draw_land(self, land, highlight):
        c = self.canvas
        x, y = LAND_POSITIONS[land.number]
        x0, y0, x1, y1 = x - LAND_W / 2, y - LAND_H / 2, x + LAND_W / 2, y + LAND_H / 2
        c.create_rectangle(x0, y0, x1, y1, fill=TERRAIN_COLORS[land.terrain],
                           outline=HIGHLIGHT if highlight else "#4a4a4a", width=5 if highlight else 1.5)
        title = "%d  %s%s" % (land.number, TERRAIN_NAMES[land.terrain], "  (coast)" if land.coastal else "")
        c.create_text(x0 + 6, y0 + 10, text=title, anchor="w", font=("Segoe UI", 9, "bold"))
        pieces = [("E", land.explorer), ("T", land.town), ("C", land.city),
                  ("D", len(land.dahan)), ("B", land.blight), ("P", land.presence)]
        shown = [(k, n) for k, n in pieces if n]
        for i, (key, n) in enumerate(shown):
            px = x0 + 16 + (i % 3) * 46
            py = y0 + 38 + (i // 3) * 30
            self.draw_piece(c, key, px, py)
            c.create_text(px + 11, py, text="x%d" % n, anchor="w", font=("Segoe UI", 10, "bold"))

    def draw_piece(self, c, key, x, y):
        color = PIECE_COLORS[key]
        if key in ("E", "D", "P"):
            r = 5 if key == "E" else 7
            c.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="black")
        elif key == "T":
            c.create_polygon(x - 7, y + 6, x - 7, y - 1, x, y - 7, x + 7, y - 1, x + 7, y + 6,
                             fill=color, outline="black")
        elif key == "C":
            c.create_rectangle(x - 8, y - 7, x + 8, y + 7, fill=color, outline="black")
        else:
            c.create_polygon(x, y - 8, x + 8, y, x, y + 8, x - 8, y, fill=color, outline="#aa0000")

    def draw_status(self):
        g = self.game
        s = g.spirit
        self.status.configure(text=(
                                       "Turn %d     Terror level %d\n"
                                       "Fear: %d until next fear card   (cards earned %d of %d)\n"
                                       "Blight pool: %d%s\n"
                                       "Ravage next: %s\n"
                                       "Build next: %s\n"
                                       "Invader cards left: %d") % (
                                       g.turn_number, g.terror_level, g.fear_pool, g.fear_cards_earned, FEAR_CARDS,
                                       g.blight_pool, "   (Blighted Island)" if g.blighted_island else "",
                                       g.ravage_card or "-", g.build_card or "-", len(g.invader_deck.cards)))
        elements = ", ".join("%s %d" % (ELEMENT_NAMES[i], n) for i, n in enumerate(s.elements) if n) or "none"
        cards = lambda pile: ", ".join(c.name for c in pile) or "-"
        self.spirit_label.configure(text=(
                                             "River Surges in Sunlight\n"
                                             "Energy: %d  (+%d per turn)     Card plays: %d\n"
                                             "Presence left on tracks: energy %d, card plays %d\n"
                                             "Elements this turn: %s\n"
                                             "Hand: %s\nPlayed: %s\nDiscard: %s") % (
                                             s.energy, s.energy_turn, s.card_plays, s.top_track, s.bottom_track, elements,
                                             cards(s.hand), cards(s.played), cards(s.discard_pile)))

    # ---- log ----
    def log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Play Spirit Island yourself in a window")
    parser.add_argument("--board", default="A", choices="ABCD", help="board to play on (default A)")
    parser.add_argument("--seed", type=int, default=None, help="random seed for the invader deck")
    args = parser.parse_args()
    Play_Window(args.board, args.seed).run()