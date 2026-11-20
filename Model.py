import os

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

from Env import GLOBAL_FEATURES, OPTION_FEATURES
from Game import MAX_OPTIONS


class Option_QNet(nn.Module):
    # Scores every option with the same small network: Q(state, option) = f(state summary, option features).
    # Because the weights are shared, what it learns about "Flash Floods on a coastal land with a city"
    # carries over no matter which slot (0..15) that option happens to land in.
    def __init__(self, hidden_size=256):
        super().__init__()
        self.state_net = nn.Sequential(
            nn.Linear(GLOBAL_FEATURES, hidden_size), nn.ReLU(),
            nn.Linear(hidden_size, hidden_size), nn.ReLU())
        self.option_net = nn.Sequential(
            nn.Linear(hidden_size + OPTION_FEATURES, hidden_size), nn.ReLU(),
            nn.Linear(hidden_size, 1))

    def forward(self, x):
        single = x.dim() == 1
        if single:
            x = x.unsqueeze(0)
        g = self.state_net(x[:, :GLOBAL_FEATURES])
        options = x[:, GLOBAL_FEATURES:].reshape(-1, MAX_OPTIONS, OPTION_FEATURES)
        g = g.unsqueeze(1).expand(-1, MAX_OPTIONS, -1)
        q = self.option_net(torch.cat([g, options], dim=2)).squeeze(2)
        return q[0] if single else q

    def save(self, file_name='model.pth'):
        model_folder_path = './model'
        if not os.path.exists(model_folder_path):
            os.makedirs(model_folder_path)
        torch.save(self.state_dict(), os.path.join(model_folder_path, file_name))


def masked(q, num_options):
    # Options that don't exist get -inf so they are never picked or used as a target
    idx = torch.arange(MAX_OPTIONS).unsqueeze(0)
    return q.masked_fill(idx >= num_options.unsqueeze(1), float('-inf'))


class QTrainer:
    # Double DQN with a target network and Huber loss, trained on minibatches from the replay memory
    def __init__(self, model, lr, gamma, target_sync=1000):
        self.gamma = gamma
        self.model = model
        self.target = Option_QNet()
        self.target.load_state_dict(model.state_dict())
        self.optimizer = optim.Adam(model.parameters(), lr=lr)
        self.target_sync = target_sync
        self.steps = 0

    def train_step(self, states, actions, rewards, next_states, next_num_options, dones, demos=None,
                   margin=0.8, demo_weight=1.0):
        # demos: 1 for transitions from the scripted player. On those, the expert's choice must also
        # beat every other option by `margin` (a large-margin loss, as in "DQN from Demonstrations").
        states = torch.tensor(states, dtype=torch.float)
        next_states = torch.tensor(next_states, dtype=torch.float)
        actions = torch.tensor(actions, dtype=torch.long)
        rewards = torch.tensor(rewards, dtype=torch.float)
        next_num_options = torch.tensor(next_num_options, dtype=torch.long).clamp(min=1)
        dones = torch.tensor(dones, dtype=torch.float)

        q = self.model(states).gather(1, actions.unsqueeze(1)).squeeze(1)
        with torch.no_grad():
            # online net picks the next action, target net values it (Double DQN)
            next_action = masked(self.model(next_states), next_num_options).argmax(1, keepdim=True)
            next_q = self.target(next_states).gather(1, next_action).squeeze(1)
            target = rewards + self.gamma * next_q * (1 - dones)

        loss = F.smooth_l1_loss(q, target)
        if demos is not None and any(demos):
            demo = torch.tensor(demos, dtype=torch.bool)
            all_q = self.model(states[demo])
            num_options = (states[demo][:, GLOBAL_FEATURES - 1] * MAX_OPTIONS).round().long().clamp(min=1)
            bonus = torch.full_like(all_q, margin)
            bonus.scatter_(1, actions[demo].unsqueeze(1), 0.0)
            best = masked(all_q + bonus, num_options).max(1).values
            loss = loss + demo_weight * (best - all_q.gather(1, actions[demo].unsqueeze(1)).squeeze(1)).mean()
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.model.parameters(), 10)
        self.optimizer.step()

        self.steps += 1
        if self.steps % self.target_sync == 0:
            self.target.load_state_dict(self.model.state_dict())
        return loss.item()
