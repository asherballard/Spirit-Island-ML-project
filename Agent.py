import argparse
import glob
import json
import random
from collections import deque

import torch

torch.set_num_threads(1)   # the network is small; extra threads only add overhead

from Env import Spirit_Island_Env
from Game import Game, GameOver
from Model import Option_QNet, QTrainer, masked
from Script import John_Chooser, script_action


MAX_MEMORY = 100_000
BATCH_SIZE = 128
LR = 0.0005
GAMMA = 0.97          # per decision; ~6 decisions a turn, so the agent looks ~5 turns ahead
WARMUP = 2_000        # transitions collected before training starts
TRAIN_EVERY = 4       # one minibatch update every this many decisions
N_STEP = 4            # learn from the rewards of the next N_STEP decisions at once (faster credit for blight)
EPS_START, EPS_END = 1.0, 0.05
EVAL_EVERY = 100      # games between greedy test runs
EVAL_GAMES = 100
EVAL_SEED = 10_000    # test games use the same invader decks as the random baseline
DEMO_GAMES = 300      # games of the scripted Reclaim Loop shown to the agent before it trains (0 = none)
PRETRAIN_STEPS = 5_000  # updates on those games alone, before the agent starts playing
DEMO_FRACTION = 0.25  # share of every minibatch taken from the scripted games
HUMAN_REPEAT = 10     # each game you recorded with Play.py counts this many times (they are few but strong)
DEMO_EPS_START = 0.3  # with demonstrations the agent already plays sensibly, so it explores less


class Agent:

    def __init__(self, explore_games=600):
        self.n_games = 0
        self.steps = 0
        self.epsilon = EPS_START
        self.explore_games = explore_games
        self.memory = deque(maxlen=MAX_MEMORY)
        self.demo_memory = []   # transitions from the scripted player, kept for the whole run
        self.eps_start = EPS_START
        self.recent = deque()   # this game's last few decisions, waiting to become N_STEP transitions
        self.model = Option_QNet()
        self.trainer = QTrainer(self.model, lr=LR, gamma=GAMMA ** N_STEP)

    def get_state(self, game):
        return game.getGameState()

    def remember(self, state, action, reward, next_state, next_num_options, done, demo=0):
        # Store (state, action, discounted sum of the next N_STEP rewards, state N_STEP decisions later)
        self.recent.append((state, action, reward))
        if done:
            while self.recent:
                self._store(next_state, next_num_options, True, demo)
        elif len(self.recent) == N_STEP:
            self._store(next_state, next_num_options, False, demo)

    def _store(self, next_state, next_num_options, done, demo):
        state, action, _ = self.recent[0]
        ret = sum(r * GAMMA ** i for i, (_, _, r) in enumerate(self.recent))
        (self.demo_memory if demo else self.memory).append(
            (state, action, ret, next_state, next_num_options, done, demo))
        self.recent.popleft()

    def train_batch(self):
        # Keep a fixed share of demonstrations in every batch. (Fading them out was tried: the agent then
        # drifted back to playing for survival and stopped winning.)
        n_demo = int(BATCH_SIZE * DEMO_FRACTION) if self.demo_memory else 0
        if len(self.memory) < WARMUP:
            if not self.demo_memory:
                return
            n_demo = BATCH_SIZE   # still warming up: learn from the scripted games only
        batch = random.sample(self.demo_memory, n_demo) + random.sample(self.memory, BATCH_SIZE - n_demo)
        self.trainer.train_step(*zip(*batch))

    def learn_from_recordings(self, pattern='games/*.json'):
        # Replay games recorded by Play.py (your own play) and keep them as demonstrations
        loaded = 0
        for path in sorted(glob.glob(pattern)):
            with open(path) as f:
                rec = json.load(f)
            env = Spirit_Island_Env(rec.get('board', 'A'), rec['seed'])
            start = len(self.demo_memory)
            for step in rec['decisions']:
                if env.game.current_prompt != step['prompt']:
                    print('%s no longer matches this version of the game; skipped the rest of it' % path)
                    break
                state = env.getGameState()
                move = min(step['choice'], 15)
                reward, done, _ = env.play_step(move)
                self.remember(state, move, reward, env.getGameState(), env.num_actions(), done, demo=1)
                if done:
                    break
            self.recent.clear()
            self.demo_memory += self.demo_memory[start:] * (HUMAN_REPEAT - 1)
            loaded += 1
        if loaded:
            print('Learned from %d recorded games in %s' % (loaded, pattern))
        return loaded

    def learn_from_script(self, games, steps):
        # Watch the scripted Reclaim Loop play, then train on those games before playing itself
        env = Spirit_Island_Env(seed=50_000)
        wins = turns = 0
        for i in range(games):
            if i:
                env.reset()
            script = John_Chooser()
            script.game = env.game
            while True:
                state = env.getGameState()
                move = script_action(script, env.game)
                reward, done, score = env.play_step(move)
                self.remember(state, move, reward, env.getGameState(), env.num_actions(), done, demo=1)
                if done:
                    break
            turns += score
            wins += 1 if env.win else 0
        print('Scripted Reclaim Loop: %.2f turns, %d wins in %d games' % (turns / games, wins, games))
        self.learn_from_recordings()
        for _ in range(steps):
            self.train_batch()
        self.eps_start = DEMO_EPS_START
        self.epsilon = self.eps_start

    def update_epsilon(self):
        # Linear decay from EPS_START to EPS_END over the first explore_games games, then stays at EPS_END
        frac = min(1.0, self.n_games / max(1, self.explore_games))
        self.epsilon = self.eps_start + frac * (EPS_END - self.eps_start)

    def get_action(self, state, num_options, greedy=False):
        num_options = max(1, num_options)
        if not greedy and random.random() < self.epsilon:
            return random.randrange(num_options)
        with torch.no_grad():
            q = self.model(torch.tensor(state, dtype=torch.float))
        return masked(q.unsqueeze(0), torch.tensor([num_options]))[0].argmax().item()


def random_baseline(games=200):
    # Mean turns survived when every choice is random, to compare the agent against
    turns = 0
    for seed in range(games):
        game = Game(seed=EVAL_SEED + seed)
        try:
            while True:
                game.play_turn()
        except GameOver:
            turns += game.turn_number
    return turns / games


def evaluate(agent, games=EVAL_GAMES):
    # Play with no exploration on fixed invader decks; returns (mean turns, wins)
    env = Spirit_Island_Env(seed=EVAL_SEED)
    turns = wins = 0
    for i in range(games):
        if i:
            env.reset()
        while True:
            move = agent.get_action(env.getGameState(), env.num_actions(), greedy=True)
            _, done, score = env.play_step(move)
            if done:
                break
        turns += score
        wins += 1 if env.win else 0
    return turns / games, wins


def train(max_games=None, show_window=True, explore_games=None, demo_games=DEMO_GAMES):
    plot_scores = []
    plot_mean_scores = []
    plot_wins = []
    plot_stats = {}   # name -> value in each game
    plot_evals = []   # (game, mean turns in the greedy test)
    total_score = 0
    record = 0
    best_eval = (-1, -1)
    if explore_games is None:
        explore_games = max(1, (max_games or 1200) // 2)
    agent = Agent(explore_games)
    if demo_games:
        agent.learn_from_script(demo_games, PRETRAIN_STEPS)
        mean, wins = evaluate(agent)
        print('After learning from the script: %.2f turns, %d wins in %d test games' % (mean, wins, EVAL_GAMES))
        best_eval = (wins, mean)
        agent.model.save()
    game = Spirit_Island_Env()

    baseline = random_baseline()
    print('Random play survives %.2f turns on average' % baseline)
    window = None
    if show_window:
        from Plot import Training_Plot
        window = Training_Plot(baseline=baseline)

    while max_games is None or agent.n_games < max_games:
        state_old = agent.get_state(game)
        move = agent.get_action(state_old, game.num_actions())
        reward, done, score = game.play_step(move)
        state_new = agent.get_state(game)
        agent.remember(state_old, move, reward, state_new, game.num_actions(), done)
        agent.steps += 1
        if agent.steps % TRAIN_EVERY == 0:
            agent.train_batch()

        if done:
            won = game.win
            stats = game.stats()
            game.reset()
            agent.n_games += 1
            agent.update_epsilon()

            record = max(record, score)
            for name, value in stats.items():
                plot_stats.setdefault(name, []).append(value)
            plot_scores.append(score)
            plot_wins.append(1 if won else 0)
            total_score += score
            plot_mean_scores.append(total_score / agent.n_games)

            line = 'Game %d Score %d Record %d eps %.2f%s' % (agent.n_games, score, record, agent.epsilon,
                                                              ' Win' if won else '')
            if agent.n_games % EVAL_EVERY == 0:
                mean, wins = evaluate(agent)
                plot_evals.append((agent.n_games, mean))
                line += '   Greedy test: %.2f turns, %d wins in %d games' % (mean, wins, EVAL_GAMES)
                if (wins, mean) > best_eval:
                    best_eval = (wins, mean)
                    agent.model.save()
                    line += ' (saved)'
            print(line)

            if window:
                if not window.is_open():
                    print('Window closed, stopping training')
                    break
                window.update(plot_scores, plot_mean_scores, plot_wins, record, plot_stats, evals=plot_evals)

    print('Best greedy test: %.2f turns, %d wins in %d games (random play: %.2f turns)' % (
        best_eval[1], best_eval[0], EVAL_GAMES, baseline))
    if window and plot_scores:
        window.update(plot_scores, plot_mean_scores, plot_wins, record, plot_stats, evals=plot_evals, force=True)
        window.save('model/training.png')
        print('Chart saved to model/training.png')
        window.keep_open()
    return agent, plot_evals, baseline


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Train the Spirit Island agent and show the results live')
    parser.add_argument('--games', type=int, default=None, help='stop after this many games (default: run until the window is closed)')
    parser.add_argument('--explore', type=int, default=None, help='games over which exploration falls from 100%% to 5%% (default: half of --games, or 600)')
    parser.add_argument('--demos', type=int, default=DEMO_GAMES, help='scripted Reclaim Loop games to learn from first (0 = none)')
    parser.add_argument('--no-window', action='store_true', help='train without the results window')
    parser.add_argument('--eval', action='store_true', help='just test the saved model/model.pth against random play')
    args = parser.parse_args()
    if args.eval:
        agent = Agent()
        agent.model.load_state_dict(torch.load('model/model.pth'))
        mean, wins = evaluate(agent, 200)
        print('Saved model: %.2f turns, %d wins in 200 games.  Random play: %.2f turns' % (mean, wins, random_baseline()))
    else:
        train(args.games, not args.no_window, args.explore, args.demos)
