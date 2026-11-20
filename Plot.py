import time

import matplotlib.pyplot as plt

SCORE_COLOR = "#86b6ef"     # light blue: each game
MEAN_COLOR = "#2a78d6"      # blue: mean of all games
RECENT_COLOR = "#eb6834"    # orange: mean of the last RECENT games
BASELINE_COLOR = "#52514e"  # gray: random play
RECENT = 50
REDRAW_SECONDS = 0.5
EVAL_COLOR = "#1a1a1a"     # black: greedy test games (no exploration)
STAT_COLORS = ["#1baf7a", "#eda100", "#4a3aa7"]   # aqua, yellow, violet: one per tracked stat


def recent_means(values):
    # Mean of the last RECENT values at each game
    return [sum(values[max(0, i - RECENT + 1):i + 1]) / (i + 1 - max(0, i - RECENT + 1))
            for i in range(len(values))]


class Training_Plot:
    # A live window showing how the agent is doing, game by game
    def __init__(self, baseline=None):
        plt.ion()
        self.fig, (self.ax, self.stats_ax) = plt.subplots(
            2, 1, figsize=(9, 8), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
        self.fig.canvas.manager.set_window_title("Spirit Island training")
        self.baseline = baseline
        self.last_draw = 0

    def is_open(self):
        return plt.fignum_exists(self.fig.number)

    def update(self, scores, mean_scores, wins, record, stats=None, force=False, evals=None):
        if not force and time.time() - self.last_draw < REDRAW_SECONDS:
            return
        self.last_draw = time.time()
        games = range(1, len(scores) + 1)
        recent = recent_means(scores)

        ax = self.ax
        ax.clear()
        ax.plot(games, scores, "o", color=SCORE_COLOR, markersize=3, label="Turns survived (each game)")
        ax.plot(games, mean_scores, color=MEAN_COLOR, linewidth=2, label="Mean, all games")
        ax.plot(games, recent, color=RECENT_COLOR, linewidth=2, label="Mean, last %d games" % RECENT)
        if self.baseline is not None:
            ax.axhline(self.baseline, color=BASELINE_COLOR, linestyle="--", linewidth=1.5,
                       label="Random play (%.1f)" % self.baseline)
        if evals:
            ax.plot([g for g, _ in evals], [m for _, m in evals], "s-", color=EVAL_COLOR, markersize=5,
                    linewidth=1.5, label="Greedy test, no exploration (%.1f)" % evals[-1][1])
        ax.set_ylabel("Score (turns survived)")
        ax.set_ylim(bottom=0)
        ax.set_title("Games: %d   Record: %d turns   Wins: %d (%.0f%%)   Last %d: %.1f turns" % (
            len(scores), record, sum(wins), 100 * sum(wins) / len(wins), RECENT, recent[-1]), fontsize=10)
        ax.grid(alpha=0.25)
        ax.legend(loc="upper left", fontsize=8, frameon=False)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

        sa = self.stats_ax
        sa.clear()
        for color, (name, values) in zip(STAT_COLORS, (stats or {}).items()):
            sa.plot(games, recent_means(values), color=color, linewidth=2,
                    label="%s (all games: %.1f)" % (name, sum(values) / len(values)))
        sa.set_ylabel("Per game, mean of last %d" % RECENT)
        sa.set_xlabel("Game")
        sa.set_ylim(bottom=0)
        sa.grid(alpha=0.25)
        if stats:
            sa.legend(loc="upper left", fontsize=8, frameon=False)
        for side in ("top", "right"):
            sa.spines[side].set_visible(False)

        self.fig.tight_layout()
        self.fig.canvas.draw_idle()
        plt.pause(0.001)

    def save(self, path):
        self.fig.savefig(path, dpi=110)

    def keep_open(self):
        # Leave the finished chart on screen until the window is closed
        plt.ioff()
        if self.is_open():
            plt.show()
