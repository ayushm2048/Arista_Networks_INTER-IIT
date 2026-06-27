import gymnasium as gym
import numpy as np
import pandas as pd
import os
import shutil
import math
import csv
import time

# --- IMPORTS ---
from v3 import NetSimConfig, run_netsim_cli
from io_utils import load_table
from throughput_metrics import p50_throughput_all_clients, _per_client_downlink_tput
from retry_metrics import p95_retry_rate, uplink_per_p95
from supporting_metrics import save_supporting_metrics

class NetSimGlobalEnv(gym.Env):
    def __init__(self, config_path, app_path, iopath, license_path):
        super(NetSimGlobalEnv, self).__init__()
        
        self.config_path = config_path
        self.app_path = app_path
        self.iopath = iopath
        self.license_path = license_path
        self.output_dir = os.path.join(self.iopath, "preprocessing_outputs")
        
        # --- 1. LOGGING SETUP ---
        self.log_file = os.path.join(self.iopath, "training_log_detailed.csv")
        print("\n" + "="*40)
        print(f"[Env] LOGGING TO: {self.log_file}")
        print("="*40 + "\n")

        try:
            if not os.path.exists(self.log_file):
                with open(self.log_file, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Step', 'Timestamp', 'Global_Tput_Mbps', 'Global_Retry_Pct', 'Cost', 'Reward', 'AP_Status', 'Client_Details'])
        except Exception as e:
            print(f"[Env] ERROR: Cannot create log file: {e}")

        # --- 2. LOAD TOPOLOGY ---
        self.netsim_tool = NetSimConfig(self.config_path)
        self.aps = self.netsim_tool.get_all_access_points()
        self.num_aps = len(self.aps)
        print(f"[Env] Initialized Global Planner for {self.num_aps} APs")

        # --- 3. VALID CHANNELS ---
        self.VALID_CHANNELS = [
            "1_2412", "2_2417", "3_2422", "4_2427", "5_2432", 
            "6_2437", "7_2442", "8_2447", "9_2452", "10_2457", "11_2462"
        ]
        
        # --- 4. SPACES ---
        self.action_space = gym.spaces.Box(
            low=-1.0, high=1.0, shape=(self.num_aps * 2,), dtype=np.float32
        )
        self.observation_space = gym.spaces.Box(
            low=0.0, high=1.0, shape=(self.num_aps * 7,), dtype=np.float32
        )

        # --- 5. STATE INIT ---
        self.ap_states = {}
        for ap in self.aps:
            phy = ap.get_wireless_phy_params()
            
            # --- FIX: FORCE INT ---
            try: pwr = int(float(phy.get('TX_POWER', 100)))
            except: pwr = 100
            
            raw_ch = str(phy.get('STANDARD_CHANNEL', '1_2412'))
            current_idx = 0
            try:
                if "_" in raw_ch and raw_ch in self.VALID_CHANNELS:
                    current_idx = self.VALID_CHANNELS.index(raw_ch)
                else:
                    num = int(raw_ch.split('_')[0]) if "_" in raw_ch else int(raw_ch)
                    if 1 <= num <= 11: current_idx = num - 1
            except: current_idx = 0

            safe_ch_str = self.VALID_CHANNELS[current_idx]
            safe_ch_num = int(safe_ch_str.split('_')[0])

            self.ap_states[ap.name] = {
                'pwr': pwr, # Integer
                'ch_str': safe_ch_str,
                'ch_num': safe_ch_num,
                'steps_since_change': 0
            }
            ap.set_wireless_phy_param('TX_POWER', pwr)
            ap.set_wireless_phy_param('STANDARD_CHANNEL', safe_ch_str)
        
        self.netsim_tool.save_config(self.config_path)
        self.step_count = 0
        self.EPISODE_LENGTH = 10 

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.step_count = 0
        for ap in self.aps:
            self.ap_states[ap.name]['steps_since_change'] = 0
        
        print("[Env] Running Baseline Simulation...")
        sim_success = self._run_simulation()
        
        if not sim_success:
            print("[Env] CRITICAL: Baseline crashed.")
            return np.zeros(self.num_aps * 7, dtype=np.float32), {}

        obs, _, _, _ = self._get_global_metrics()
        return np.nan_to_num(obs, nan=0.0), {}

    def step(self, action):
        self.step_count += 1
        print(f"[NetSim] Step {self.step_count}/{self.EPISODE_LENGTH}...", end=" ", flush=True)

        total_changes = 0
        
        # 1. APPLY ACTIONS
        for i, ap in enumerate(self.aps):
            p_act = 0.0 if np.isnan(action[2*i]) else action[2*i]
            c_act = 0.0 if np.isnan(action[2*i + 1]) else action[2*i + 1]

            state = self.ap_states[ap.name]
            state['steps_since_change'] += 1
            prev_p, prev_c_str = state['pwr'], state['ch_str']

            # --- FIX: INTEGER POWER LOGIC (1-100) ---
            # OmniSafe sends float [-1.0, 1.0]
            # We scale it: +/- 10 units
            pwr_change = p_act * 10.0
            
            # Add to current state and ROUND to nearest integer
            new_pwr_raw = round(state['pwr'] + pwr_change)
            
            # Clip strictly between 1 and 100 and cast to int
            new_pwr = int(np.clip(new_pwr_raw, 1, 100))
            
            state['pwr'] = new_pwr # Save back to state as int

            # --- CHANNEL LOGIC ---
            norm_act = (c_act + 1.0) / 2.0
            idx = int(norm_act * len(self.VALID_CHANNELS))
            idx = max(0, min(idx, len(self.VALID_CHANNELS) - 1))
            
            new_ch_str = self.VALID_CHANNELS[idx]
            new_ch_num = int(new_ch_str.split('_')[0])
            state['ch_str'] = new_ch_str
            state['ch_num'] = new_ch_num

            # Apply
            if state['pwr'] != prev_p or state['ch_str'] != prev_c_str:
                total_changes += 1
                state['steps_since_change'] = 0
                ap.set_wireless_phy_param('TX_POWER', state['pwr'])
                ap.set_wireless_phy_param('STANDARD_CHANNEL', state['ch_str'])

        if total_changes > 0:
            self.netsim_tool.save_config(self.config_path)

        # 2. RUN SIM
        sim_success = self._run_simulation()

        # 3. METRICS
        obs = np.zeros(self.num_aps * 7, dtype=np.float32)
        total_tput = 0.0
        max_retry = 0.0
        cost = 0.0
        reward = 0.0
        df_granular = pd.DataFrame()

        if not sim_success:
            print("CRASHED! ", end=" ")
            cost = 10.0
            reward = -10.0
        else:
            obs, total_tput, max_retry, df_granular = self._get_global_metrics()
            
            # Cost
            excess_retries = max(0.0, max_retry - 0.08) 
            cost = (excess_retries * 100) + (total_changes * 0.1)
            cost += np.random.uniform(0, 0.0001) 
            
            # Reward
            reward = (total_tput / 5.0) - cost
            reward += np.random.uniform(0, 0.0001)

        # 4. SANITIZE
        if math.isnan(cost): cost = 0.0
        if math.isnan(reward): reward = 0.0
        obs = np.nan_to_num(obs, nan=0.0)

        # 5. LOG
        self._log_step(total_tput, max_retry, cost, reward, df_granular)

        # 6. TERMINATE
        truncated = False
        if self.step_count >= self.EPISODE_LENGTH:
            truncated = True

        info = {'cost': cost}
        print(f"Done. (Tput: {total_tput:.2f}, Retry: {max_retry*100:.2f}%, Cost: {cost:.4f})")
        
        return obs, reward, False, truncated, info

    def _log_step(self, tput, retry, cost, reward, df_granular=None):
        try:
            with open(self.log_file, 'a', newline='') as f:
                writer = csv.writer(f)
                
                ap_status = ""
                for ap in self.aps:
                    st = self.ap_states[ap.name]
                    # FIX: Removed .1f formatting, now prints raw int
                    ap_status += f"[{ap.name}:P{st['pwr']}/C{st['ch_num']}] "

                client_status = ""
                if df_granular is not None and not df_granular.empty:
                    for _, row in df_granular.iterrows():
                        client_status += f"{row['Client']}={row['Throughput_Mbps']:.2f} | "
                else:
                    client_status = "No Traffic"

                row = [
                    self.step_count,
                    time.strftime("%H:%M:%S"),
                    f"{tput:.4f}",
                    f"{retry:.4f}",
                    f"{cost:.4f}",
                    f"{reward:.4f}",
                    ap_status.strip(),
                    client_status.strip()
                ]
                writer.writerow(row)
        except Exception as e:
            print(f"\n[Env] LOGGING ERROR: {e}")

    def _get_global_metrics(self):
        log_dir = os.path.join(self.iopath, "log")
        link_log = os.path.join(log_dir, "Link_Packet_Log.csv")
        backoff_log = os.path.join(log_dir, "IEEE802_11_Backofflog.csv")
        radio_log = os.path.join(log_dir, "IEEE_802_11_Radio_Measurements_Log.csv")

        if not os.path.exists(link_log):
            print(f" [Env] MISSING LOG: {link_log}")
            return np.zeros(self.num_aps * 7, dtype=np.float32), 0.0, 0.0, pd.DataFrame()

        try:
            link_df = load_table(link_log)
            backoff_df = load_table(backoff_log) if os.path.exists(backoff_log) else pd.DataFrame()
            radio_df = load_table(radio_log) if os.path.exists(radio_log) else pd.DataFrame()

            df_tput_summary = p50_throughput_all_clients(link_df)
            df_granular_tput = _per_client_downlink_tput(link_df)
            df_retry = p95_retry_rate(backoff_df, link_df)
            df_per   = uplink_per_p95(backoff_df, link_df)
            
            if not radio_df.empty:
                save_supporting_metrics(radio_log, self.output_dir)
                df_rssi = load_table(os.path.join(self.output_dir, "metric_avg_rssi.csv"))
                df_snr  = load_table(os.path.join(self.output_dir, "metric_avg_snr.csv"))
            else:
                df_rssi = pd.DataFrame()
                df_snr = pd.DataFrame()

            obs_list = []
            total_tput = 0.0
            max_retry = 0.0

            for ap in self.aps:
                def get_v(df, col='Value'):
                    if df.empty: return 0.0
                    try:
                        row = df[df['AP'] == ap.name]
                        if row.empty and 'AP' in df.columns:
                            row = df[df['AP'].astype(str).str.upper() == ap.name.upper()]
                        if row.empty: return 0.0
                        return float(row[col].iloc[0])
                    except: return 0.0

                val_tput = get_v(df_tput_summary)
                val_retry = get_v(df_retry) # Already Percentage
                val_per = get_v(df_per)
                val_rssi = get_v(df_rssi)
                val_snr = get_v(df_snr)
                
                total_tput += val_tput
                max_retry = max(max_retry, val_retry)

                n_tput  = np.clip(val_tput / 10.0, 0, 1)
                n_retry = np.clip(val_retry, 0, 1)
                n_per   = np.clip(val_per / 100.0, 0, 1)
                n_rssi  = np.clip((val_rssi + 100) / 80.0, 0, 1)
                n_snr   = np.clip(val_snr / 100.0, 0, 1)
                # Normalize using 100 (mW)
                n_pwr   = np.clip(self.ap_states[ap.name]['pwr'] / 100.0, 0, 1)
                n_ch    = np.clip(self.ap_states[ap.name]['ch_num'] / 14.0, 0, 1)

                obs_list.extend([n_tput, n_retry, n_per, n_rssi, n_snr, n_pwr, n_ch])

            return np.array(obs_list, dtype=np.float32), total_tput, max_retry, df_granular_tput

        except Exception as e:
            print(f" [Env] Metric Calc Failed: {e}")
            return np.zeros(self.num_aps * 7, dtype=np.float32), 0.0, 0.0, pd.DataFrame()

    def _run_simulation(self):
        log_dir = os.path.join(self.iopath, "log")
        if os.path.exists(log_dir):
            for f in os.listdir(log_dir):
                if f.endswith(".csv"):
                    try: os.remove(os.path.join(log_dir, f))
                    except: pass
        
        ret_code, _, _ = run_netsim_cli(
            netsimcore_exe=os.path.join(self.app_path, "NetSimCore.exe"),
            apppath=self.app_path,
            iopath=self.iopath,
            license_path=self.license_path,
            show_cmd=False
        )
        return (ret_code == 0)