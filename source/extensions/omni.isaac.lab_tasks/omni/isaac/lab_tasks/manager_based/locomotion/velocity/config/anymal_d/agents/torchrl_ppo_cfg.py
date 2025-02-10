# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

import torch
import torch.nn as nn
from tensordict.nn.distributions import NormalParamExtractor
from dataclasses import MISSING

from omni.isaac.lab.utils import configclass

from omni.isaac.lab_tasks.utils.wrappers.torchrl.torchrl_ppo_runner_cfg import (
    ClipPPOLossCfg,
    CollectorCfg,
    OnPolicyPPORunnerCfg,
    ProbabilisticActorCfg,
    ValueOperatorCfg,
)


class AnymalDActorNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.model = nn.Sequential(
            nn.Linear(in_features=48, out_features=512, bias=True),
            nn.ELU(alpha=1.0),
            nn.Linear(in_features=512, out_features=256, bias=True),
            nn.ELU(alpha=1.0),
            nn.Linear(in_features=256, out_features=128, bias=True),
            nn.ELU(alpha=1.0),
            nn.Linear(in_features=128, out_features=12 * 2, bias=True),
        )

    def forward(self, x):
        return self.model(x)

class AnymalDActorModNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.model = nn.Sequential(
            nn.Linear(in_features=48, out_features=128, bias=True),
            nn.ELU(alpha=1.0),
            nn.Linear(in_features=128, out_features=128, bias=True),
            nn.ELU(alpha=1.0),
            nn.Linear(in_features=128, out_features=128, bias=True),
            nn.ELU(alpha=1.0),
            nn.Linear(in_features=128, out_features=12, bias=True),
        )  
        self.std = nn.Parameter(1.0 * torch.ones(12))

    def forward(self, x):
        action_mean = self.model(x)
        batch_size = action_mean.shape[0]
        std_broadcasted = self.std.unsqueeze(0).expand(batch_size, -1)
        action_dist = torch.cat((action_mean, std_broadcasted), dim=1)
        return action_dist


class AnymalDCriticNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.model = nn.Sequential(
            nn.Linear(in_features=48, out_features=128, bias=True),
            nn.ELU(alpha=1.0),
            nn.Linear(in_features=128, out_features=128, bias=True),
            nn.ELU(alpha=1.0),
            nn.Linear(in_features=128, out_features=128, bias=True),
            nn.ELU(alpha=1.0),
            nn.Linear(in_features=128, out_features=1, bias=True),
        )  

    def forward(self, x):
        return self.model(x)


@configclass
class AnymalDActorModule(ProbabilisticActorCfg):

    actor_network = AnymalDActorModNN

    init_noise_std = 1.0

    in_keys = ["policy"]

    out_keys: list[str] = ["loc", "scale"]


@configclass
class AnymalDCriticModule(ValueOperatorCfg):

    critic_network = AnymalDCriticNN

    in_keys = ["policy"]

    out_keys = ["state_value"]


"""
Collector Module Definition
"""


@configclass
class AnymalDCollectorModule(CollectorCfg):

    actor_network = AnymalDActorModule()

    split_trajs = False


"""
Loss Module Definition
"""


@configclass
class AnymalDPPOLossModule(ClipPPOLossCfg):

    actor_network = AnymalDActorModule()

    value_network = AnymalDCriticModule()

    value_key = "state_value"

    desired_kl = 0.01

    beta = 1.0

    decrement = 0.5

    increment = 2.0

    value_loss_coef = 1.0

    clip_param = 0.2

    entropy_coef = 0.005

    entropy_bonus = True

    loss_critic_type = "l2"

    normalize_advantage = True

    learning_rate = 1e-3

    gamma = 0.99

    lam = 0.95

    max_grad_norm = 1.0


"""
Trainer Module Definition
"""


@configclass
class AnymalDPPORunnerCfg(OnPolicyPPORunnerCfg):

    loss_module = AnymalDPPOLossModule()

    collector_module = AnymalDCollectorModule()

    seed = 42

    num_steps_per_env = 24

    num_epochs = 5

    num_mini_batches = 4

    lr_schedule = "adaptive"

    max_iterations = 500 #25000

    save_interval = 50

    save_trainer_interval = 100

    experiment_name = MISSING

    wandb_project = MISSING

    logger = "wandb"


@configclass
class AnymalDFlatPPORunnerCfg(AnymalDPPORunnerCfg):
    def __post_init__(self):
        """Post initialization."""

        # change experiment name
        self.experiment_name = "anymal_d_flat"

        # change wandb project
        self.wandb_project = "elin_anymal_d_flat"


@configclass
class AnymalDRoughPPORunnerCfg(AnymalDPPORunnerCfg):
    def __post_init__(self):
        """Post initialization."""

        # change experiment name
        self.experiment_name = "anymal_d_rough"

        # change wandb project
        self.wandb_project = "anymal_d_rough"
