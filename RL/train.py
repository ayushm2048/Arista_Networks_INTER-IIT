import gymnasium as gym
import omnisafe
import torch
import numpy as np
from gymnasium.envs.registration import register
from omnisafe.envs.core import CMDP, ENV_REGISTRY

# --- CONFIGURATION ---
CONFIG_PATH = r"F:\EndTerm\testing\Configuration.netsim"
IOPATH      = r"F:\EndTerm\testing"
APP_PATH    = r"C:\Program Files\NetSim\Standard_v14_4\bin\bin_x64"
LICENSE_PATH= r"C:\Program Files\NetSim"

# --- REGISTER ENV ---
register(
    id='NetSimGlobal-v0',
    entry_point='netsim_env:NetSimGlobalEnv',
    kwargs={'config_path': CONFIG_PATH, 'app_path': APP_PATH, 'iopath': IOPATH, 'license_path': LICENSE_PATH}
)

# --- ADAPTER (FIXED) ---
@ENV_REGISTRY.register
class NetSimAdapter(CMDP):
    _support_envs = ['NetSimGlobal-v0']

    def __init__(self, env_id, num_envs=1, seed=None, cfgs=None, device='cpu', **kwargs):
        super().__init__(env_id)
        self._num_envs = num_envs
        self._device = torch.device(device if device else 'cpu')
        self._env = gym.make(env_id)
        self._action_space = self._env.action_space
        self._observation_space = self._env.observation_space
        self._metadata = cfgs if cfgs else {}
        if seed: self.set_seed(seed)

    @property
    def need_time_limit_wrapper(self): return False
    @property
    def need_auto_reset_wrapper(self): return True
    @property
    def num_envs(self): return self._num_envs
    @property
    def max_episode_steps(self): return 1000

    def step(self, action):
        if isinstance(action, torch.Tensor):
            action = action.detach().cpu().numpy()
        
        # STANDARD GYM UNPACK (5 Values)
        obs, reward, terminated, truncated, info = self._env.step(action)
        
        # EXTRACT COST MANUALLY
        cost = info.get('cost', 0.0)

        # CONVERT TO TORCH
        def t(x): return torch.as_tensor(x, dtype=torch.float32, device=self._device)
        return t(obs), t(reward), t(cost), t(terminated), t(truncated), info

    def reset(self, seed=None, options=None):
        obs, info = self._env.reset(seed=seed, options=options)
        return torch.as_tensor(obs, dtype=torch.float32, device=self._device), info

    def set_seed(self, seed): self._env.reset(seed=seed)
    def close(self): self._env.close()
    def render(self): return self._env.render()
    def save(self): return {}

# --- WHITELIST PATCH ---
from omnisafe.envs.core import support_envs as native
import omnisafe.envs.core
import omnisafe.adapter.online_adapter
import omnisafe.adapter.onpolicy_adapter
def p(): return native() + ['NetSimGlobal-v0']
omnisafe.envs.core.support_envs = p
omnisafe.adapter.online_adapter.support_envs = p
omnisafe.adapter.onpolicy_adapter.support_envs = p

# --- RUN ---
custom_cfgs = {
    'train_cfgs': {
        'total_steps': 200,      # Total simulation runs
        'vector_env_nums': 1,
        'torch_threads': 1,
    },
    'algo_cfgs': {
        'steps_per_epoch': 10,   # CRITICAL: Update weights every 10 steps (approx 40 seconds)
        'update_iters': 1,
    },
    'lagrange_cfgs': {
        'cost_limit': 0.1,
        'lagrangian_multiplier_init': 0.001,
        'lambda_lr': 0.1,
    },
    'logger_cfgs': {
        'use_wandb': False,
        'log_dir': './netsim_rl_logs'
    }
}

agent = omnisafe.Agent('PPOLag', 'NetSimGlobal-v0', custom_cfgs=custom_cfgs)
print("Starting NetSim Safe RL Training Loop...")
agent.learn()