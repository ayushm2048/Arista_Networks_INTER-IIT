
# #!/usr/bin/env python3
# """
# preprocess_netsim_to_tgn.py

# Robust preprocessing for NetSim logs -> TGN-style CSV (node rows and edge rows).
# Outputs:
#   - <out_dir>/id_map.json        (mapping node_name -> integer id)
#   - <out_dir>/<output>          (CSV, e.g. mywifi.csv)

# Notes:
#  - Produces node events as (src=node_id, dst=-1, timestamp, node_features..., zeros for edge_features)
#  - Produces edge events as (src=node_id, dst=node_id, timestamp, zeros for node_features..., edge_features)
#  - Does NOT yet add retry-rate by default (commented placeholders included).
# """

# import argparse
# import json
# from pathlib import Path
# from collections import defaultdict
# import numpy as np
# import pandas as pd
# import math
# import sys

# # --------------------- helpers ---------------------
# def find_time_col(df):
#     for c in df.columns:
#         if "time" in c.lower() or "timestamp" in c.lower() or "currenttime" in c.lower():
#             return c
#     return None

# def to_seconds(s):
#     # Accept series or scalar
#     s = pd.to_numeric(s, errors="coerce")
#     if s.max() > 1000.0:
#         return s / 1000.0
#     return s

# def choose_col(df, candidates):
#     if df is None:
#         return None
#     for cand in candidates:
#         for c in df.columns:
#             if cand.lower() in c.lower():
#                 return c
#     return None

# def sanitize_str(x):
#     if pd.isna(x):
#         return ""
#     return str(x).strip()

# # --------------------- main ---------------------
# def main():
#     p = argparse.ArgumentParser()
#     p.add_argument("--input_dir", required=True, help="Dir containing logs")
#     p.add_argument("--out_dir", required=True, help="Output directory")
#     p.add_argument("--radio", default="IEEE_802_11_Radio_Measurements_Log.csv")
#     p.add_argument("--link", default="Link_Packet_Log.csv")
#     p.add_argument("--buffer", default="Buffer_Occupancy_Log.csv")
#     p.add_argument("--app", default="Application_Packet_Log.csv")
#     p.add_argument("--backoff", default=None, help="Backoff log (optional) for retry/backoff features)")
#     p.add_argument("--time_window", type=float, default=1.0, help="Time bin width in seconds")
#     p.add_argument("--output", default="dataset.csv", help="Name of output csv inside out_dir")
#     args = p.parse_args()

#     inp = Path(args.input_dir)
#     out = Path(args.out_dir)
#     out.mkdir(parents=True, exist_ok=True)

#     print("=== LOADING LOGS ===")
#     # load logs
#     def try_load(name):
#         path = inp / name
#         if not path.exists():
#             print(f"[WARN] {name} not found at {path}; continuing (empty frame)")
#             return pd.DataFrame()
#         try:
#             return pd.read_csv(path)
#         except Exception as e:
#             print(f"[ERROR] failed to read {path}: {e}")
#             sys.exit(1)

#     radio = try_load(args.radio)
#     link = try_load(args.link)
#     buffer_df = try_load(args.buffer)
#     app = try_load(args.app)
#     backoff = try_load(args.backoff) if args.backoff else pd.DataFrame()

#     # normalize time columns to seconds and create t_s column
#     for name, df in [("radio", radio), ("link", link), ("buffer", buffer_df), ("app", app), ("backoff", backoff)]:
#         if df.empty:
#             continue
#         tcol = find_time_col(df)
#         if tcol is None:
#             raise RuntimeError(f"No time column found in {name} log")
#         df["t_s"] = to_seconds(df[tcol])

#     # global time span and bins
#     all_frames = [df for df in [radio, link, buffer_df, app, backoff] if not df.empty]
#     if len(all_frames) == 0:
#         print("[ERROR] No logs found or all logs empty.")
#         sys.exit(1)

#     global_min = min(df["t_s"].min() for df in all_frames)
#     global_max = max(df["t_s"].max() for df in all_frames)
#     if math.isclose(global_min, global_max):
#         num_bins = 1
#     else:
#         num_bins = int(math.ceil((global_max - global_min) / args.time_window))
#     print(f"[INFO] Time bins: {num_bins} (time range {global_min:.2f}..{global_max:.2f}, window {args.time_window}s)")

#     # assign bins
#     for df in all_frames:
#         if df.empty:
#             continue
#         df["t_bin"] = ((df["t_s"] - global_min) / args.time_window).fillna(0).astype(int).clip(lower=0)

#     # ---------- discover node names (APs and STAs) ----------
#     node_names = set()
#     # heuristic columns that may contain node names
#     cand_cols = ["transmitter", "receiver", "source", "dest", "device", "device name", "node name", "from", "to"]
#     for df in all_frames:
#         if df.empty: continue
#         for c in df.columns:
#             if any(k in c.lower() for k in cand_cols):
#                 node_names.update(df[c].dropna().astype(str).map(str.strip).unique())

#     node_names = sorted([n for n in node_names if n != "" and n.lower() != "nan"])
#     # heuristics to identify APs and STAs
#     ap_names = [n for n in node_names if "access" in n.lower() or "ap_" in n.lower() or "access_point" in n.lower()]
#     sta_names = [n for n in node_names if ("wireless" in n.lower() or "sta" in n.lower() or "station" in n.lower()) and n not in ap_names]

#     # If no APs detected, fallback: try to select a small set
#     if len(ap_names) == 0 and len(node_names) > 0:
#         ap_names = node_names[:max(1, min(5, len(node_names)//4))]

#     # Build id_map: APs first (so AP ids are small)
#     id_map = {}
#     idx = 0
#     for a in ap_names:
#         id_map[a] = idx; idx += 1
#     for s in sta_names:
#         if s not in id_map:
#             id_map[s] = idx; idx += 1
#     # Also include any other node_names not categorized
#     for other in node_names:
#         if other not in id_map:
#             id_map[other] = idx; idx += 1

#     # Save id_map
#     idmap_path = out / "id_map.json"
#     with open(idmap_path, "w") as f:
#         json.dump(id_map, f, indent=2)
#     print(f"[INFO] Found APs: {ap_names}")
#     print(f"[INFO] Found STAs: {sta_names}")
#     print(f"[INFO] Saved id_map -> {idmap_path}")

#     # --------- detect important columns inside logs (flexible names) ----------
#     # radio
#     radio_tx = choose_col(radio, ["transmitter","tx","source"])
#     radio_rx = choose_col(radio, ["receiver","rx","dest"])
#     col_rssi = choose_col(radio, ["rx_power","rx power","rssi"])
#     col_interf = choose_col(radio, ["interference","interf"])
#     # link
#     link_tx = choose_col(link, ["transmitter","tx","source","from"])
#     link_rx = choose_col(link, ["receiver","rx","dest","to"])
#     col_phy_out = choose_col(link, ["physical out","phy out","phy_out","phyout"])
#     col_phy_in  = choose_col(link, ["physical in","phy in","phy_in","phyin"])
#     col_dur = choose_col(link, ["duration","airtime"])
#     # buffer
#     buf_node = choose_col(buffer_df, ["device name","device","node","node name"])
#     buf_occ = choose_col(buffer_df, ["occupied","occupancy","buffer"])
#     # app
#     app_src = choose_col(app, ["source","src"])
#     app_dst = choose_col(app, ["destination","dst","dest"])
#     app_thr = choose_col(app, ["throughput","throughput(mbps)","throughput(mbps)"])
#     app_size = choose_col(app, ["size","bytes","packet size"])
#     # backoff (optional)
#     backoff_node_col = choose_col(backoff, ["device","device name","node"])
#     backoff_retry_col = choose_col(backoff, ["retry","retrycount","retry count"])

#     # ---------- aggregation containers ----------
#     # node_stats[(node_name, bin)] -> dict sums / counts
#     node_stats = defaultdict(lambda: defaultdict(float))
#     node_lists = defaultdict(lambda: defaultdict(list))
#     # edge_stats[(src_name, dst_name, bin)] -> dict
#     edge_stats = defaultdict(lambda: defaultdict(float))
#     edge_lists = defaultdict(lambda: defaultdict(list))

#     # ---------- process buffer log ----------
#     if not buffer_df.empty and buf_node and buf_occ:
#         for _, r in buffer_df.iterrows():
#             try:
#                 n = sanitize_str(r[buf_node])
#                 b = int(r["t_bin"])
#                 if n in id_map:
#                     node_lists[(n,b)]["buffer"].append(float(r[buf_occ]))
#             except Exception:
#                 continue

#     # ---------- process app log ----------
#     if not app.empty:
#         fcols = [c for c in app.columns if c not in ["src","dst","source","destination","timestamp","t_s","t_bin"]]
#         for _, r in app.iterrows():
#             b = int(r["t_bin"])
#             bytes_val = 0.0
#             if app_thr:
#                 try:
#                     mbps = float(r[app_thr])
#                     if mbps > 0:
#                         bytes_val = (mbps * 1e6 * args.time_window) / 8.0
#                 except:
#                     bytes_val = 0.0
#             elif app_size:
#                 try:
#                     bytes_val = float(r[app_size])
#                 except:
#                     bytes_val = 0.0
#             # increment for src and dst nodes if they exist
#             if app_src:
#                 s = sanitize_str(r[app_src])
#                 if s in id_map:
#                     node_stats[(s,b)]["app_bytes"] += bytes_val
#             if app_dst:
#                 d = sanitize_str(r[app_dst])
#                 if d in id_map:
#                     node_stats[(d,b)]["app_bytes"] += bytes_val

#     # ---------- process link log (airtime and tx counts) ----------
#     if not link.empty and link_tx and link_rx:
#         for _, r in link.iterrows():
#             b = int(r["t_bin"])
#             src = sanitize_str(r[link_tx])
#             dst = sanitize_str(r[link_rx])
#             if src not in id_map or dst not in id_map:
#                 continue

#             airtime = 0.0
#             if col_phy_out and col_phy_in:
#                 try:
#                     t_out = float(r[col_phy_out])
#                     t_in = float(r[col_phy_in])
#                     # often phy times are ms -> convert to seconds (heuristic)
#                     if t_out > 1000 or t_in > 1000:
#                         airtime = (t_in - t_out) / 1000.0
#                     else:
#                         airtime = t_in - t_out
#                 except:
#                     airtime = 0.0
#             elif col_dur:
#                 try:
#                     airtime = float(r[col_dur])
#                 except:
#                     airtime = 0.0

#             if airtime < 0:
#                 airtime = 0.0

#             edge_stats[(src, dst, b)]["tx_count"] += 1
#             edge_stats[(src, dst, b)]["airtime"] += airtime

#             node_stats[(src,b)]["tx_count"] += 1
#             node_stats[(dst,b)]["rx_count"] += 1
#             node_stats[(src,b)]["airtime"] += airtime
#             node_stats[(dst,b)]["airtime"] += airtime

#     # ---------- process radio log (RSSI, interference) ----------
#     if not radio.empty and radio_tx and radio_rx:
#         for _, r in radio.iterrows():
#             b = int(r["t_bin"])
#             tx = sanitize_str(r[radio_tx])
#             rx = sanitize_str(r[radio_rx])
#             if tx not in id_map or rx not in id_map:
#                 continue
#             if col_rssi:
#                 try:
#                     v = float(r[col_rssi])
#                     edge_lists[(tx, rx, b)]["rssi"].append(v)
#                     node_lists[(rx, b)]["rssi"].append(v)
#                 except:
#                     pass
#             if col_interf:
#                 try:
#                     v = float(r[col_interf])
#                     edge_lists[(tx, rx, b)]["interf"].append(v)
#                 except:
#                     pass

#     # ---------- optional: process backoff for retry rate (not integrated yet) ----------
#     # If you later want retry-rate as an edge feature you can:
#     # - group backoff rows per (node, t_bin) and count RetryCount>0 occurrences
#     # - convert to rate = retries / total_packets_in_bin
#     # For now we only keep the backoff info in a simple dict for future use.
#     backoff_counts = defaultdict(lambda: defaultdict(int))
#     if not backoff.empty and backoff_node_col:
#         for _, r in backoff.iterrows():
#             try:
#                 n = sanitize_str(r[backoff_node_col])
#                 b = int(r["t_bin"])
#                 if pd.notna(backoff_retry_col):
#                     rc = int(r[backoff_retry_col]) if not pd.isna(r[backoff_retry_col]) else 0
#                     backoff_counts[(n,b)]["retry_events"] += (1 if rc>0 else 0)
#                     backoff_counts[(n,b)]["total_backoff_rows"] += 1
#             except:
#                 continue

#     # ---------- Build output rows ----------
#     rows = []

#     # compute bins list (0 .. num_bins)
#     bins = list(range(num_bins+1))

#     # desired output column order (TGN-friendly)
#     desired_cols = [
#         "src","dst","timestamp",
#         # AP node features
#         "ap_buffer","ap_total_throughput_mbps","ap_num_clients","ap_airtime_fraction","ap_avg_rssi_clients",
#         # STA node features
#         "sta_buffer","sta_rssi_at_ap","sta_tx_count","sta_rx_count","sta_app_load_mbps",
#         # Edge features
#         "edge_rssi_sta_at_ap","edge_interference_at_ap","edge_tx_count","edge_rx_count","edge_per_estimated","edge_airtime_fraction"
#     ]

#     # Node events (src=node_id, dst=-1)
#     for node_name, nid in id_map.items():
#         is_ap = any(x in node_name.lower() for x in ("access","ap","access_point"))
#         is_sta = any(x in node_name.lower() for x in ("wireless","sta","station"))
#         for b in bins:
#             st = node_stats[(node_name,b)]
#             arr = node_lists[(node_name,b)]
#             ts = (global_min + b*args.time_window)  # timestamp in seconds (absolute)
#             # aggregates
#             buffer_val = float(np.mean(arr["buffer"])) if arr.get("buffer") else 0.0
#             rssi_val = float(np.mean(arr["rssi"])) if arr.get("rssi") else 0.0
#             txc = float(st.get("tx_count", 0.0))
#             rxc = float(st.get("rx_count", 0.0))
#             app_bytes = float(st.get("app_bytes", 0.0))
#             app_mbps = (app_bytes * 8) / (args.time_window * 1e6) if args.time_window>0 else 0.0
#             airtime_frac = float(st.get("airtime", 0.0)) / args.time_window if args.time_window>0 else 0.0

#             # AP-specific aggregation: number of associated clients, total client throughput, avg rssi seen on its edges
#             ap_clients = 0
#             ap_total_thr = 0.0
#             ap_rssi_list = []
#             if is_ap:
#                 # consider edges where this AP is dst (uplink from STA) or src (downlink to STA)
#                 for (s,d,bb), est in edge_stats.items():
#                     if bb != b:
#                         continue
#                     if d == node_name and s in id_map:
#                         # count only if s looks like STA
#                         if any(x in s.lower() for x in ("wireless","sta","station")):
#                             ap_clients += 1
#                             sta_app_bytes = node_stats[(s,b)].get("app_bytes", 0.0)
#                             ap_total_thr += (sta_app_bytes * 8) / (args.time_window * 1e6) if args.time_window>0 else 0.0
#                             ap_rssi_list += edge_lists[(s,d,b)].get("rssi", [])
#                     if s == node_name and d in id_map:
#                         # downlink case: treat similarly
#                         if any(x in d.lower() for x in ("wireless","sta","station")):
#                             ap_clients += 1
#                             sta_app_bytes = node_stats[(d,b)].get("app_bytes", 0.0)
#                             ap_total_thr += (sta_app_bytes * 8) / (args.time_window * 1e6) if args.time_window>0 else 0.0
#                             ap_rssi_list += edge_lists[(s,d,b)].get("rssi", [])

#             ap_avg_rssi = float(np.mean(ap_rssi_list)) if ap_rssi_list else 0.0

#             row = {
#                 "src": nid,
#                 "dst": -1,
#                 "timestamp": round(ts, 6),

#                 "ap_buffer": buffer_val if is_ap else 0.0,
#                 "ap_total_throughput_mbps": ap_total_thr if is_ap else 0.0,
#                 "ap_num_clients": ap_clients if is_ap else 0,
#                 "ap_airtime_fraction": airtime_frac if is_ap else 0.0,
#                 "ap_avg_rssi_clients": ap_avg_rssi if is_ap else 0.0,

#                 "sta_buffer": buffer_val if is_sta else 0.0,
#                 "sta_rssi_at_ap": rssi_val if is_sta else 0.0,
#                 "sta_tx_count": txc if is_sta else 0,
#                 "sta_rx_count": rxc if is_sta else 0,
#                 "sta_app_load_mbps": app_mbps if is_sta else 0.0,

#                 # edge features zeroed for node rows
#                 "edge_rssi_sta_at_ap": 0.0,
#                 "edge_interference_at_ap": 0.0,
#                 "edge_tx_count": 0,
#                 "edge_rx_count": 0,
#                 "edge_per_estimated": 0.0,
#                 "edge_airtime_fraction": 0.0
#             }
#             rows.append(row)

#     # Edge events (src,dst pairs)
#     for (src, dst, b), st in edge_stats.items():
#         if src not in id_map or dst not in id_map:
#             continue
#         # only include AP-STA edges (one side AP, other STA) - that is the typical useful set
#         src_is_ap = any(x in src.lower() for x in ("access","ap","access_point"))
#         dst_is_ap = any(x in dst.lower() for x in ("access","ap","access_point"))
#         # include if one is AP and the other not (STA)
#         if not ((src_is_ap and not dst_is_ap) or (dst_is_ap and not src_is_ap)):
#             continue

#         ts = (global_min + b*args.time_window)
#         rssi_list = edge_lists[(src,dst,b)].get("rssi", [])
#         interf_list = edge_lists[(src,dst,b)].get("interf", [])
#         rssi = float(np.mean(rssi_list)) if rssi_list else 0.0
#         interf = float(np.mean(interf_list)) if interf_list else 0.0
#         txc = float(st.get("tx_count", 0.0))
#         rxc = float(st.get("rx_count", txc))
#         per = 0.0
#         if txc > 0 and rxc < txc:
#             per = 1.0 - (rxc / txc)
#         airtime_frac = float(st.get("airtime", 0.0)) / args.time_window if args.time_window>0 else 0.0

#         row = {
#             "src": id_map[src],
#             "dst": id_map[dst],
#             "timestamp": round(ts,6),

#             # node features zeroed for edge rows
#             "ap_buffer": 0.0, "ap_total_throughput_mbps": 0.0, "ap_num_clients": 0, "ap_airtime_fraction": 0.0, "ap_avg_rssi_clients": 0.0,
#             "sta_buffer": 0.0, "sta_rssi_at_ap": 0.0, "sta_tx_count": 0, "sta_rx_count": 0, "sta_app_load_mbps": 0.0,

#             # edge features
#             "edge_rssi_sta_at_ap": rssi,
#             "edge_interference_at_ap": interf,
#             "edge_tx_count": int(txc),
#             "edge_rx_count": int(rxc),
#             "edge_per_estimated": per,
#             "edge_airtime_fraction": airtime_frac
#         }
#         rows.append(row)

#     # final dataframe and ordering
#     df_out = pd.DataFrame(rows)
#     # ensure columns present
#     for c in desired_cols:
#         if c not in df_out.columns:
#             df_out[c] = 0.0

#     df_out = df_out[desired_cols].sort_values("timestamp").reset_index(drop=True)

#     out_csv = out / args.output
#     df_out.to_csv(out_csv, index=False)
#     print(f"[DONE] Generated {len(df_out)} rows -> {out_csv}")

# if __name__ == "__main__":
#     main()

#!/usr/bin/env python3
"""
preprocess_netsim_to_tgn.py
Final robust preprocessing for NetSim logs → TGN CSV with retry-rate edge feature.

Usage example:
 python utils/preprocess_netsim_to_tgn.py \
    --input_dir "path/to/logdir" \
    --out_dir "data/mywifi" \
    --time_window 1.0 \
    --output mywifi.csv
"""

import argparse
import json
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd

# ---------------- utilities ----------------

def choose_col(df, keys):
    if df is None:
        return None
    for k in keys:
        for c in df.columns:
            if k.lower() in c.lower():
                return c
    return None

def find_time_col(df):
    for c in df.columns:
        if "time" in c.lower() or "timestamp" in c.lower():
            return c
    raise RuntimeError("No time-like column found")

def to_seconds(series):
    s = pd.to_numeric(series, errors="coerce")
    if s.max() > 1000:
        return s / 1000.0
    return s

def sanitize(x):
    return str(x).strip()

# ---------------- main preprocessing ----------------

def main(args):
    inp = Path(args.input_dir)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # expected filenames (default but overridable)
    radio_f = inp / args.radio
    link_f = inp / args.link
    buffer_f = inp / args.buffer
    app_f = inp / args.app
    backoff_f = inp / args.backoff

    print("=== LOADING LOGS ===")
    # load with fallback
    def load_if_exists(path):
        if path.exists():
            try:
                return pd.read_csv(path)
            except Exception as e:
                print(f"[WARN] Failed reading {path}: {e}")
                return None
        else:
            return None

    radio = load_if_exists(radio_f)
    link = load_if_exists(link_f)
    buffer_df = load_if_exists(buffer_f)
    app = load_if_exists(app_f)
    backoff = load_if_exists(backoff_f)

    # require at least one relevant file
    if radio is None and link is None and buffer_df is None and app is None:
        raise FileNotFoundError("No input logs found in input_dir")

    # normalize times
    dfs = [d for d in [radio, link, buffer_df, app, backoff] if d is not None]
    for df in dfs:
        tcol = find_time_col(df)
        df["t_s"] = to_seconds(df[tcol])

    # global time bounds
    min_t = min(df["t_s"].min() for df in dfs)
    max_t = max(df["t_s"].max() for df in dfs)
    if max_t == min_t:
        num_bins = 1
    else:
        num_bins = int(np.ceil((max_t - min_t) / args.time_window))
    print(f"[INFO] Time bins: {num_bins} (time range {min_t:.2f}..{max_t:.2f}, window {args.time_window})")

    # assign bins
    for df in dfs:
        df["t_bin"] = ((df["t_s"] - min_t) / args.time_window).astype(int)
        df["t_bin"] = df["t_bin"].clip(0, num_bins)

    # ---------------- identify node names ----------------
    node_candidates = set()
    for df in [radio, link, buffer_df, app, backoff]:
        if df is None: continue
        for c in df.columns:
            if any(k in c.lower() for k in ("transmit","transmitter","source","sender","device name","node","receiver","dest","receiver name")):
                vals = df[c].dropna().astype(str).unique().tolist()
                node_candidates.update(vals)
    # filter for AP/STA by name heuristics
    ap_nodes = sorted([n for n in node_candidates if "access" in n.lower() or "ap_" in n.lower() or "access_point" in n.lower()])
    sta_nodes = sorted([n for n in node_candidates if ("wireless" in n.lower()) or ("sta" in n.lower()) or ("station" in n.lower())])

    # create id_map: APs first to keep stability
    id_map = {}
    idx = 0
    for a in ap_nodes:
        id_map[a] = idx; idx += 1
    for s in sta_nodes:
        if s not in id_map:
            id_map[s] = idx; idx += 1
    # finally include any remaining nodes
    for n in sorted(node_candidates):
        if n not in id_map:
            id_map[n] = idx; idx += 1

    with open(out / "id_map.json", "w") as f:
        json.dump(id_map, f, indent=2)
    print("[INFO] Saved id_map ->", out / "id_map.json")
    print("[INFO] Found APs:", ap_nodes)
    print("[INFO] Found STAs (heuristic):", sta_nodes)

    # ---------------- column detection ----------------
    # Radio
    radio_tx = choose_col(radio, ["transmitter", "tx", "sender", "source"]) if radio is not None else None
    radio_rx = choose_col(radio, ["receiver", "rx", "dest", "to"]) if radio is not None else None
    col_rssi = choose_col(radio, ["rx_power", "rssi", "rx_power(dbm)"]) if radio is not None else None
    col_interf = choose_col(radio, ["interference", "interf"]) if radio is not None else None

    # Link
    link_tx = choose_col(link, ["transmitter", "tx", "source", "from"]) if link is not None else None
    link_rx = choose_col(link, ["receiver", "rx", "dest", "to"]) if link is not None else None
    col_phy_out = choose_col(link, ["physical out", "phy out", "physical_out"]) if link is not None else None
    col_phy_in  = choose_col(link, ["physical in", "phy in", "physical_in"]) if link is not None else None
    col_link_pktid = choose_col(link, ["packet id", "packet_id", "packetid"]) if link is not None else None
    col_link_throughput = choose_col(link, ["throughput", "throughput(mbps)"]) if link is not None else None

    # Buffer
    buf_node = choose_col(buffer_df, ["device name", "node name", "node", "device"]) if buffer_df is not None else None
    buf_size = choose_col(buffer_df, ["occupied buffer", "occupied_buffer", "buffer size", "occupied"]) if buffer_df is not None else None

    # App
    app_src = choose_col(app, ["source", "src", "transmitter"]) if app is not None else None
    app_dst = choose_col(app, ["destination", "dest", "receiver"]) if app is not None else None
    app_thr = choose_col(app, ["throughput", "throughput(mbps)", "throughput_mbps"]) if app is not None else None
    app_size = choose_col(app, ["size", "bytes", "packet size"]) if app is not None else None
    col_app_pktid = choose_col(app, ["packet id", "packet_id", "packetid"]) if app is not None else None

    # Backoff log (for retry)
    backoff_tx = choose_col(backoff, ["transmitter", "tx", "sender", "source"]) if backoff is not None else None
    backoff_rx = choose_col(backoff, ["receiver", "rx", "dest", "to"]) if backoff is not None else None
    backoff_pktid = choose_col(backoff, ["packet id", "packet_id", "packetid"]) if backoff is not None else None
    backoff_retry_col = choose_col(backoff, ["retry", "retransmit", "retransmission", "attempt"]) if backoff is not None else None

    # ---------------- containers ----------------
    node_stats = defaultdict(lambda: defaultdict(float))
    node_arrays = defaultdict(lambda: defaultdict(list))
    edge_stats = defaultdict(lambda: defaultdict(float))
    edge_arrays = defaultdict(lambda: defaultdict(list))

    # ---------------- process buffer ----------------
    if buffer_df is not None and buf_node and buf_size:
        for _, r in buffer_df.iterrows():
            n = sanitize(r[buf_node])
            b = int(r["t_bin"])
            if n in id_map:
                try:
                    node_arrays[(n, b)]["buffer"].append(float(r[buf_size]))
                except: pass

    # ---------------- process app ----------------
    if app is not None:
        for _, r in app.iterrows():
            b = int(r["t_bin"])
            bytes_val = 0.0
            if app_thr:
                try:
                    mbps = float(r[app_thr])
                    if mbps > 0:
                        bytes_val = (mbps * 1e6 * args.time_window) / 8.0
                except: pass
            elif app_size:
                try:
                    bytes_val = float(r[app_size])
                except: pass

            if app_src:
                s = sanitize(r[app_src])
                if s in id_map:
                    node_stats[(s, b)]["app_bytes"] += bytes_val
            if app_dst:
                d = sanitize(r[app_dst])
                if d in id_map:
                    node_stats[(d, b)]["app_bytes"] += bytes_val

    # ---------------- process link (airtime, tx/rx counts) -----------
    if link is not None:
        for _, r in link.iterrows():
            b = int(r["t_bin"])
            src = sanitize(r[link_tx]) if link_tx else ""
            dst = sanitize(r[link_rx]) if link_rx else ""
            if src not in id_map or dst not in id_map:
                continue
            airtime = 0.0
            if col_phy_out and col_phy_in:
                try:
                    t_out = float(r[col_phy_out])
                    t_in  = float(r[col_phy_in])
                    airtime = max(0.0, (t_in - t_out) / 1000.0)
                except: pass
            elif col_link_throughput:
                # not perfect; skip if not available
                try:
                    thr = float(r[col_link_throughput])
                    if thr > 0:
                        airtime = args.time_window  # approximate
                except: pass

            edge_stats[(src, dst, b)]["tx_count"] += 1
            edge_stats[(src, dst, b)]["airtime"] += airtime

            node_stats[(src, b)]["tx_count"] += 1
            node_stats[(dst, b)]["rx_count"] += 1
            node_stats[(src, b)]["airtime"] += airtime
            node_stats[(dst, b)]["airtime"] += airtime

    # ---------------- radio (RSSI/interference) ------------
    if radio is not None and radio_tx and radio_rx:
        for _, r in radio.iterrows():
            b = int(r["t_bin"])
            tx = sanitize(r[radio_tx])
            rx = sanitize(r[radio_rx])
            if tx not in id_map or rx not in id_map:
                continue
            rssi = None
            interf = None
            if col_rssi:
                try: rssi = float(r[col_rssi])
                except: pass
            if col_interf:
                try: interf = float(r[col_interf])
                except: pass
            if rssi is not None:
                edge_arrays[(tx, rx, b)]["rssi"].append(rssi)
                node_arrays[(rx, b)]["rssi"].append(rssi)
            if interf is not None:
                edge_arrays[(tx, rx, b)]["interf"].append(interf)

    # ---------------- BACKOFF / RETRY processing (best-effort) ----------------
    print("[INFO] Processing backoff/retry info (best-effort) ...")
    retry_map = defaultdict(lambda: [0, 0])  # [attempts, retransmissions]

    if backoff is not None:
        if backoff_tx and backoff_rx and backoff_pktid:
            for _, r in backoff.iterrows():
                b = int(r["t_bin"])
                tx = sanitize(r[backoff_tx]); rx = sanitize(r[backoff_rx])
                pk = sanitize(r[backoff_pktid])
                retry_map[(tx, rx, b)][0] += 1
                if backoff_retry_col:
                    try:
                        val = float(r[backoff_retry_col])
                        if val > 0:
                            retry_map[(tx, rx, b)][1] += 1
                    except:
                        pass
        elif backoff_pktid and backoff_tx:
            print("[INFO] backoff has pktid+tx but no rx — attempting map via Link/App logs ...")
            pkt_to_dst = {}
            if link is not None and col_link_pktid and link_tx and link_rx:
                for _, r in link.iterrows():
                    pk = sanitize(r[col_link_pktid])
                    dst = sanitize(r[link_rx])
                    src = sanitize(r[link_tx])
                    b = int(r["t_bin"])
                    pkt_to_dst.setdefault(pk, []).append((src, dst, b))
            if app is not None and col_app_pktid and app_src and app_dst:
                for _, r in app.iterrows():
                    pk = sanitize(r[col_app_pktid])
                    src = sanitize(r[app_src]); dst = sanitize(r[app_dst]); b = int(r["t_bin"])
                    pkt_to_dst.setdefault(pk, []).append((src, dst, b))

            for _, r in backoff.iterrows():
                b = int(r["t_bin"])
                tx = sanitize(r[backoff_tx])
                pk = sanitize(r[backoff_pktid])
                mapped = pkt_to_dst.get(pk, [])
                if mapped:
                    chosen = None
                    for (s, d, bb) in mapped:
                        if s == tx and (abs(bb - b) <= 1):
                            chosen = (s, d, bb); break
                    if chosen is None:
                        chosen = mapped[0]
                    _, dst, bb = chosen
                    retry_map[(tx, dst, b)][0] += 1
                    if backoff_retry_col:
                        try:
                            val = float(r[backoff_retry_col])
                            if val > 0:
                                retry_map[(tx, dst, b)][1] += 1
                        except: pass
                else:
                    retry_map[(tx, None, b)][0] += 1
                    if backoff_retry_col:
                        try:
                            val = float(r[backoff_retry_col])
                            if val > 0:
                                retry_map[(tx, None, b)][1] += 1
                        except: pass
        else:
            print("[INFO] Using fallback retry extraction (DeviceName + RetryCount only).")

    # fallback device-level retry extraction
    dev_col = choose_col(backoff, ["device", "node"])
    time_col = choose_col(backoff, ["time"])
    retry_col = choose_col(backoff, ["retry"])

    if dev_col and time_col and retry_col:
        for _, r in backoff.iterrows():
            dev = sanitize(r[dev_col])
            if dev not in id_map:
                continue
            b = int(r["t_bin"])
            try:
                rc = float(r[retry_col])
            except:
                rc = 0.0
            key = (dev, None, b)  # None = no dst
            retry_map[key][0] += 1        # attempts
            retry_map[key][1] += rc       # retransmissions
    else:
        print("[WARN] Backoff fallback also failed; retry info skipped.")

    # ------------------ PRE-INDEX AP EDGES (speedup) ------------------
    print("[INFO] Pre-indexing AP edges for fast node feature build ...")

    ap_edges_by_bin = defaultdict(list)

    for (src, dst, b), st in edge_stats.items():
        src_is_ap = ("access" in src.lower()) or ("ap_" in src.lower()) or ("access_point" in src.lower())
        dst_is_ap = ("access" in dst.lower()) or ("ap_" in dst.lower()) or ("access_point" in dst.lower())
        
        if src_is_ap and not dst_is_ap:
            # (AP, STA)
            ap_edges_by_bin[b].append((src, dst))
        elif dst_is_ap and not src_is_ap:
            # (AP, STA)
            ap_edges_by_bin[b].append((dst, src))

    # ------------------ build final rows ------------------
    print("[INFO] Building final dataset ...")
    rows = []
    bins = list(range(num_bins + 1))
    feature_cols = [
        "ap_buffer","ap_total_throughput_mbps","ap_num_clients","ap_airtime_fraction","ap_avg_rssi_clients",
        "sta_buffer","sta_rssi_at_ap","sta_tx_count","sta_rx_count","sta_app_load_mbps",
        "edge_rssi_sta_at_ap","edge_interference_at_ap","edge_tx_count","edge_rx_count","edge_per_estimated","edge_airtime_fraction",
        # new retry fields:
        "edge_retry_events","edge_retry_rate"
    ]

    # per-node rows (src, -1)
    for n, nid in id_map.items():
        is_ap = ("access" in n.lower()) or ("ap_" in n.lower()) or ("access_point" in n.lower())
        is_sta = ("wireless" in n.lower()) or ("sta" in n.lower()) or ("station" in n.lower())
        for b in bins:
            st = node_stats[(n,b)]
            arr = node_arrays[(n,b)]
            ts = b * args.time_window

            buffer_val = float(np.mean(arr["buffer"])) if arr["buffer"] else 0.0
            rssi_val = float(np.mean(arr["rssi"])) if arr["rssi"] else 0.0
            txc = st.get("tx_count", 0.0)
            rxc = st.get("rx_count", 0.0)
            app_bytes = st.get("app_bytes", 0.0)
            app_mbps = (app_bytes * 8) / (args.time_window * 1e6) if args.time_window > 0 else 0.0
            airtime_frac = st.get("airtime", 0.0) / args.time_window if args.time_window > 0 else 0.0

            # AP-specific aggregation (clients, total throughput, avg rssi clients)
            ap_clients = 0
            ap_total_thr = 0.0
            ap_rssi_list = []
            if is_ap:
                # use pre-indexed edges for this time bin
                for (ap_name, sta_name) in ap_edges_by_bin.get(b, []):
                    if ap_name != n:
                        continue
                    # count client
                    ap_clients += 1
                    # throughput: get app_bytes for sta
                    sta_bytes = node_stats[(sta_name, b)].get("app_bytes", 0.0)
                    sta_mbps = (sta_bytes * 8) / (args.time_window * 1e6) if args.time_window > 0 else 0.0
                    ap_total_thr += sta_mbps
                    # rssi list from edge_arrays (key is (tx, rx, bin) where tx=sta, rx=ap)
                    ap_rssi_list += edge_arrays.get((sta_name, ap_name, b), {}).get("rssi", [])

            ap_avg_rssi = float(np.mean(ap_rssi_list)) if ap_rssi_list else 0.0

            rows.append({
                "src": nid, "dst": -1, "timestamp": ts,
                "ap_buffer": buffer_val if is_ap else 0.0,
                "ap_total_throughput_mbps": ap_total_thr if is_ap else 0.0,
                "ap_num_clients": ap_clients if is_ap else 0,
                "ap_airtime_fraction": airtime_frac if is_ap else 0.0,
                "ap_avg_rssi_clients": ap_avg_rssi if is_ap else 0.0,
                "sta_buffer": buffer_val if is_sta else 0.0,
                "sta_rssi_at_ap": rssi_val if is_sta else 0.0,
                "sta_tx_count": txc if is_sta else 0.0,
                "sta_rx_count": rxc if is_sta else 0.0,
                "sta_app_load_mbps": app_mbps if is_sta else 0.0,
                # edge fields zeroed for node rows
                "edge_rssi_sta_at_ap": 0.0,
                "edge_interference_at_ap": 0.0,
                "edge_tx_count": 0,
                "edge_rx_count": 0,
                "edge_per_estimated": 0.0,
                "edge_airtime_fraction": 0.0,
                # retry fields (node rows zeroed)
                "edge_retry_events": 0,
                "edge_retry_rate": 0.0
            })

    # edge rows
    for (src, dst, b), st in edge_stats.items():
        if src not in id_map or dst not in id_map:
            continue
        ts = b * args.time_window
        rssi_list = edge_arrays[(src,dst,b)]["rssi"]
        interf_list = edge_arrays[(src,dst,b)]["interf"]
        rssi = float(np.mean(rssi_list)) if rssi_list else 0.0
        interf = float(np.mean(interf_list)) if interf_list else 0.0
        txc = int(st.get("tx_count", 0))
        rxc = int(st.get("rx_count", txc))
        per = 0.0
        if txc > 0 and rxc < txc:
            per = 1.0 - (rxc / txc)
        airtime_frac = float(st.get("airtime", 0.0)) / args.time_window if args.time_window>0 else 0.0

        # retry values from retry_map
        attempts, retrans = 0, 0
        if (src, dst, b) in retry_map:
            attempts, retrans = retry_map[(src, dst, b)]
        else:
            if (src, None, b) in retry_map:
                attempts, retrans = retry_map[(src, None, b)]

        retry_events = int(retrans)
        retry_rate = float(retrans / attempts) if attempts > 0 else 0.0

        rows.append({
            "src": id_map[src],
            "dst": id_map[dst],
            "timestamp": ts,
            "ap_buffer": 0.0, "ap_total_throughput_mbps": 0.0,
            "ap_num_clients": 0, "ap_airtime_fraction": 0.0, "ap_avg_rssi_clients": 0.0,
            "sta_buffer": 0.0, "sta_rssi_at_ap": 0.0, "sta_tx_count": 0, "sta_rx_count": 0, "sta_app_load_mbps": 0.0,
            "edge_rssi_sta_at_ap": rssi,
            "edge_interference_at_ap": interf,
            "edge_tx_count": txc,
            "edge_rx_count": rxc,
            "edge_per_estimated": per,
            "edge_airtime_fraction": airtime_frac,
            "edge_retry_events": retry_events,
            "edge_retry_rate": retry_rate
        })

    # final dataframe
    df_out = pd.DataFrame(rows)
    # ensure ordering of columns
    desired_order = [
        "src","dst","timestamp",
        "ap_buffer","ap_total_throughput_mbps","ap_num_clients","ap_airtime_fraction","ap_avg_rssi_clients",
        "sta_buffer","sta_rssi_at_ap","sta_tx_count","sta_rx_count","sta_app_load_mbps",
        "edge_rssi_sta_at_ap","edge_interference_at_ap","edge_tx_count","edge_rx_count","edge_per_estimated","edge_airtime_fraction",
        "edge_retry_events","edge_retry_rate"
    ]
    # add any missing columns with zeros (ensures consistent columns across sims)
    for c in desired_order:
        if c not in df_out.columns:
            df_out[c] = 0.0

    # DROP any accidental extra columns that might have crept in
    extra_cols = [c for c in df_out.columns if c not in desired_order]
    if extra_cols:
        df_out = df_out.drop(columns=extra_cols)

    df_out = df_out[desired_order].sort_values("timestamp")
    out_csv = out / args.output
    df_out.to_csv(out_csv, index=False)
    print(f"[DONE] Generated {len(df_out)} rows -> {out_csv}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input_dir", required=True)
    p.add_argument("--out_dir", required=True)
    p.add_argument("--time_window", type=float, default=1.0)
    p.add_argument("--output", default="dataset.csv")
    p.add_argument("--radio", default="IEEE_802_11_Radio_Measurements_Log.csv")
    p.add_argument("--link", default="Link_Packet_Log.csv")
    p.add_argument("--buffer", default="Buffer_Occupancy_Log.csv")
    p.add_argument("--app", default="Application_Packet_Log.csv")
    p.add_argument("--backoff", default="IEEE802_11_Backofflog.csv")
    args = p.parse_args()
    main(args)
