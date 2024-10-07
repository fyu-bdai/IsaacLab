#  Copyright 2021 ETH Zurich, NVIDIA CORPORATION
#  SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from typing import TYPE_CHECKING

import os
import time
import torch
import pathlib
from torch import nn 
from torchrl.modules import NormalParamExtractor
from tensordict.nn import TensorDictModule
from torchrl.objectives.value import GAE

from .torchrl_env_wrapper import InfoDictReaderWrapper, SyncDataCollectorWrapper, TrainerWrapper, WandbLoggerWrapper, ClipPPOLossWrapper
from torchrl.envs.utils import  ExplorationType

from torchrl.envs.libs.gym import GymEnv
from torchrl.modules import ProbabilisticActor, ValueOperator
from torch.distributions import Normal
from torchrl.record.loggers import TensorboardLogger

from torchrl.data.tensor_specs import (
    CompositeSpec,
    UnboundedContinuousTensorSpec,
)
from tensordict.nn import (
    InteractionType,
)
import yaml
import wandb
import math 
from numbers import Real

if TYPE_CHECKING:
    from .torchrl_ppo_runner_cfg import OnPolicyPPORunnerCfg

class NormalWrapper(Normal):
    def __init__(self, loc, scale, max_scale: float | None = None, validate_args=None):
        if max_scale is not None and max_scale >= 0:
            scale = torch.clip(scale, min=0, max=max_scale)
        elif max_scale is not None:
            raise ValueError("Maximum scale must be greater than 0")
        super().__init__(loc, scale, validate_args=validate_args)
    
    def log_prob(self, value):
        if self._validate_args:
            self._validate_sample(value)
        # compute the variance
        var = self.scale**2
        log_scale = (
            math.log(self.scale) if isinstance(self.scale, Real) else self.scale.log()
        )
        log_prob = (
            -((value - self.loc) ** 2) / (2 * var)
            - log_scale
            - math.log(math.sqrt(2 * math.pi))
        )
        return torch.sum(log_prob, dim=-1)


class OnPolicyPPORunner:
    """On-policy runner for training and evaluation."""

    def __init__(self, env: GymEnv, train_cfg: OnPolicyPPORunnerCfg, log_dir=None, device="cpu"):
        self.cfg = train_cfg
        self.log_dir = log_dir
        self.loss_module_cfg = train_cfg.loss_module
        self.collector_module_cfg = train_cfg.collector_module

        self.actor_network_cfg =  self.loss_module_cfg.actor_network
        self.value_network_cfg = self.loss_module_cfg.value_network
        self.device = device
        self.env = env
        num_envs = self.env.unwrapped.num_envs

        self.pre_optim_time_start = 0

        self.saved_video_files = {}

        actor_network = self.actor_network_cfg.actor_network()
        critic_network = self.value_network_cfg.critic_network()
        actor_network.to(device=self.device)
        actor_td = TensorDictModule(
            nn.Sequential(actor_network, 
                          NormalParamExtractor(scale_mapping=f"biased_softplus_{self.actor_network_cfg.init_noise_std}")),
            in_keys=self.actor_network_cfg.in_keys, 
            out_keys=["loc", "scale"],
        )
        actor_module = ProbabilisticActor(
            spec=env.action_spec,
            module=actor_td,
            in_keys=["loc", "scale"],
            distribution_class=NormalWrapper,
            default_interaction_type=InteractionType.RANDOM,
            return_log_prob=True,
        )
        # create the critic module
        critic_network.to(device=self.device)
        value_module = ValueOperator(
            module=critic_network,
            in_keys=self.value_network_cfg.in_keys,
            out_keys=self.value_network_cfg.out_keys,
        )

        # register info dict for logging rewards from extras dict
        keys = env.unwrapped.extras
        info_spec = CompositeSpec({key: UnboundedContinuousTensorSpec([env.unwrapped.num_envs]) for key in keys}, shape=[env.unwrapped.num_envs])
        env.set_info_dict_reader(InfoDictReaderWrapper(spec=info_spec))

        loss_module = ClipPPOLossWrapper(
            actor_network=actor_module,
            critic_network=value_module,
            clip_epsilon=self.loss_module_cfg.clip_param,
            loss_critic_type=self.loss_module_cfg.loss_critic_type,
            desired_kl=self.loss_module_cfg.desired_kl,
            entropy_bonus=self.loss_module_cfg.entropy_bonus,
            entropy_coef=self.loss_module_cfg.entropy_coef,
            critic_coef=self.loss_module_cfg.value_loss_coef,
            normalize_advantage=False,
            separate_losses=True,
            clip_value=self.loss_module_cfg.clip_param,
            device=self.device
        )

        self.advantage_module = GAE(
            gamma=self.loss_module_cfg.gamma,
            lmbda=self.loss_module_cfg.lam,
            value_network=value_module,
            vectorized=True,
            average_gae=True
        )
        
        total_frames=self.cfg.num_steps_per_env*num_envs*self.cfg.max_iterations
        frames_per_batch = self.cfg.num_steps_per_env*num_envs

        collector = SyncDataCollectorWrapper(
            create_env_fn=env, 
            policy=actor_module,
            frames_per_batch=frames_per_batch,
            total_frames=total_frames,
            split_trajs=self.collector_module_cfg.split_trajs,
            exploration_type = ExplorationType.RANDOM,
            set_truncated=False,
            device=self.device
        )

        optimizer = torch.optim.Adam(loss_module.parameters(), lr=self.loss_module_cfg.learning_rate)

        if self.cfg.logger == "wandb":
            self.logger_module = WandbLoggerWrapper(
                exp_name=self.cfg.experiment_name,
                project=self.cfg.wandb_project,
                save_dir=log_dir,
            )
            self.logger_module.log_config(env.unwrapped.cfg)
        elif self.cfg.logger == "tensorboard":
            self.logger_module = TensorboardLogger(
                exp_name=self.cfg.experiment_name,
                log_dir=log_dir
            )
        else:
            raise RuntimeError("logger must be either `wandb` or `tensorboard`")
        
        policy_save_interval = self.cfg.save_trainer_interval*(frames_per_batch - 1)

        self.trainer_module = TrainerWrapper(
            collector=collector,
            loss_module=loss_module,
            total_frames=total_frames,
            frame_skip=1,
            optimizer=optimizer,
            clip_grad_norm=True,
            clip_norm=self.loss_module_cfg.max_grad_norm,
            logger=self.logger_module,
            optim_steps_per_batch=self.cfg.num_epochs,
            num_mini_batches=self.cfg.num_mini_batches,
            save_trainer_interval=policy_save_interval,
            log_interval=frames_per_batch,
            lr_schedule=self.cfg.lr_schedule,
            save_trainer_file=f"{log_dir}/model.pt" 
        )
        self.trainer_module.register_module(module_name="advantage_module", module=self.advantage_module)
        self.trainer_module.register_op("batch_process", self.compute_advantages)
        self.trainer_module.register_op("batch_process", self.bootstrap_reward)

        # register hooks for logging 
        self.trainer_module.register_op("pre_steps_log", self.log_info_dict)
        self.trainer_module.register_op("pre_steps_log", self.log_collection_time)
        self.trainer_module.register_op("pre_optim_steps", self.log_pre_optim_time)
        self.trainer_module.register_op("post_optim_log", self.log_optim_time)
        self.trainer_module.register_op("pre_steps_log", self.log_episode_stats)

        # upload video to wandb 
        if hasattr(env.unwrapped, "video_recorder") and self.cfg.logger == "wandb":
            self.trainer_module.register_op("post_steps_log", self.upload_training_video, log_name="Video", fps=30)

    def learn(self, init_at_random_ep_len: bool = False):
        if init_at_random_ep_len:
            self.env.unwrapped.episode_length_buf = torch.randint_like(
                self.env.unwrapped.episode_length_buf, high=int(self.env.unwrapped.max_episode_length)
            )

        self.trainer_module.train()

    def load(self, path, load_optimizer=True):
        loaded_dict = torch.load(path, weights_only=False)
        self.trainer_module.load_from_file(path)
        if load_optimizer:
            self.trainer_module.optimizer.load_state_dict(loaded_dict["optimizer"])
        return loaded_dict["state"]

    def save_cfg(self):
        # Get the configuration from the environment
        config = self.env.unwrapped.cfg
        
        # Construct the path to the config file
        cfg_file_path = os.path.join(self.log_dir, "env_cfg.yaml")
        
        # Ensure the directory exists
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Write the config dictionary to the YAML file
        with open(cfg_file_path, 'w') as file:
            yaml.dump(config, file, default_flow_style=False)

        wandb.save(cfg_file_path, base_path=os.path.dirname(cfg_file_path))

    def bootstrap_reward(self, batch):
        gamma = self.advantage_module.gamma
        if batch["next"]["truncated"].any():
            batch["next"]["reward"] += gamma * batch["next"]["state_value"] * batch["next"]["truncated"]
 
    def compute_advantages(self, batch):
        self.advantage_module(batch)

    def log_pre_optim_time(self, ):
        self.pre_optim_time_start = time.perf_counter()

    def log_optim_time(self, batch):
        optim_time_end = time.perf_counter()
        optim_time = optim_time_end - self.pre_optim_time_start
        collection_time = batch["rollout_time"][0, 0].item()
        fps = int(self.cfg.num_steps_per_env * self.env.unwrapped.num_envs / (collection_time + optim_time))
        learning_rate = batch["learning_rate"].mean().item()        
        log_dict = {
            "Perf/learning_time" : optim_time,
            "Perf/total_fps" : fps,
            "Loss/learning_rate" : learning_rate
        }
        return log_dict
        
    def log_collection_time(self, batch):
        log_dict = {}
        val = batch["rollout_time"][0, 0].item()
        log_dict["Perf/collection time"] = val 
        return log_dict

    def log_info_dict(self, batch):
        log_dict = {}
        entries = list(self.env.unwrapped.extras)
        for entry in entries:
            key = entry + "_data"
            data = batch[key]
            for k, v in data.items():
                log_dict[k] = v.float().mean().item()
        return log_dict 

    def log_episode_stats(self, batch):
        log_dict = {}
        mean_ep_len = batch["episode_length"].mean().item()
        mean_reward = batch["episode_reward"].mean().item()
        log_dict["Train/mean_reward"] = mean_reward
        log_dict["Train/mean_episode_length"] = mean_ep_len 

        return log_dict 

    def upload_training_video(self, batch, log_name: str = "Video", fps: int = 30):
        """
        Upload locally saved training .mp4 videos from VideoRecorder to WandB.
        """
        log_dir = pathlib.Path(self.log_dir)
        # exclude any files inside the wandb logs folder 
        video_files = [
            file for file in log_dir.rglob("*.mp4")
            if "wandb" not in file.parts
        ]        
        for video_file in video_files:
            file_path = str(video_file)
            file_size_kb = os.stat(file_path).st_size / 1024
            mod_time = os.path.getmtime(file_path)
            
            if file_path not in self.saved_video_files:
                self.saved_video_files[file_path] = {"mod_time": mod_time, "added": False}
            else:
                video_info = self.saved_video_files[file_path]
                current_time = time.time()
                
                # Check if file hasn't been modified in the last 20 seconds and is larger than 100KB
                if not video_info["added"] and (current_time - mod_time > 20) and file_size_kb > 100:
                    print(f"[Wandb] Uploading {os.path.basename(file_path)}.")
                    wandb.log({log_name: wandb.Video(file_path, fps=fps)})
                    video_info["added"] = True
                else:
                    video_info["mod_time"] = mod_time