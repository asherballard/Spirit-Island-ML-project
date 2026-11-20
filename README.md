The project currently implements a solo-spirit game of Spirit Island in Python for River Surges in Sunlight, Lightning's Swift Strikes, Vital Strength of the Earth, and Shadows Flicker Like Flames. Additionally, the project also has an RL ML model for River Surges in Sunlight. The game provides the user with a chooser that accepts input from a human player, a script, or a neural network.

Overview of Files:
Game.py creates and runs the game itself and wraps it in a gamestate to pass to the other files to train the model and to display the game.
Model.py A Q-network that scores the legal options to play the game.
Agent.py trains the agent using scripted games and some recorded games I played before the agent itself plays the game to learn.
Play.py displays the game for human players and provides a visual reference to make gameplay easier
Plot.py displays the data gathered as the model trains itself to analyze how the model is doing and to see how to improve its learning.
Env.py handles the learning environment for the model

Commands:
  To play the game yourself, use one of the following commands, 
    python Play.py                      # board A, random invader deck
    python Play.py --board C --seed 42  # pick the board (A, B, C or D) and the invader-deck seed
    If you wish to play without the window, replace Play.py with Game.py
  To train your own agent, use one of the following commands,
    python Agent.py                         # train until you close the chart window
    python Agent.py --games 3000            # stop after 3,000 games (the chart is saved to model/training.png)
    python Agent.py --games 3000 --no-window
    python Agent.py --explore 1000          # exploration falls from 100% to 5% over 1,000 games
    python Agent.py --demos 0               # skip the scripted demo games
    python Agent.py --eval                  # test the saved model/model.pth over 200 games vs random play

Current State:
  Only four spirits of the original eight in core Spirit Island are implemented, with only River Surges in Sunlight having a functional model.
  Only one spirit and island can be in a game
  Only unique powers have been implemented
  No Fear cards have been made
  No Adversaries have been implemented

To-do:
  Implement Fear Cards
  Implement Minor and Major Powers
  Add models for Lightning, Vital, and Shadows
  Add the remaining four core spirits to the game(they're currently stubs in Game.py)
  Implement adversaries
  Allow multi-spirit and multi-board games
