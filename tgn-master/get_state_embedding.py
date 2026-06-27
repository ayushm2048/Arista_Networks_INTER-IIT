# #!/usr/bin/env python3
# """
# get_state_embedding.py
# Compute AP embeddings for a NEW NetSim log directory (debug or RL loop).

# Steps performed:
# 1. Run preprocessing (same as run_full_pipeline step 1)
# 2. Load the temporary CSV
# 3. Use trained TGN encoder to generate embeddings for 5 APs
# 4. Save embeddings to numpy file
# """

# import argparse
# import subprocess
# import pandas as pd
# import numpy as np
# import json
# import os
# import sys
# from pathlib import Path

# # IMPORTANT: This import already exists in your project
# from modules.embedding_module import load_embedding_model


# # -----------------------------------------------------------------------------
# # STEP 1 — Run preprocessing automatically
# # -----------------------------------------------------------------------------
# def run_preprocess(log_dir, output_csv):
#     """
#     Calls utils/preprocess_netsim_to_tgn.py exactly like full pipeline.
#     Writes output CSV to output_csv.
#     """
#     cmd = [
#         sys.executable,
#         "utils/preprocess_netsim_to_tgn.py",
#         "--input_dir", log_dir,
#         "--out_dir", ".",
#         "--time_window", "1",
#         "--output", output_csv
#     ]

#     print("[STATE] Running preprocessing:\n    ", " ".join(cmd))
#     subprocess.check_call(cmd)

#     if not Path(output_csv).exists():
#         raise FileNotFoundError("❌ Preprocessing failed: CSV not generated")

#     df = pd.read_csv(output_csv)
#     print(f"[STATE] Preprocess OK: {len(df)} rows")
#     return df


# # -----------------------------------------------------------------------------
# # STEP 2 — Extract TGN embeddings (encoder_fn + AP averaging)
# # -----------------------------------------------------------------------------
# def extract_tgn_embeddings(df, encoder_fn, emb_dim):
#     """
#     encoder_fn : numpy -> numpy embedding function (from load_embedding_model)

#     Returns dict {AP_name : emb_vector}
#     """

#     feature_cols = [c for c in df.columns if c not in ["src", "dst", "timestamp"]]

#     # Detect APs from id_map.json created by preprocessing
#     if not Path("id_map.json").exists():
#         raise FileNotFoundError("id_map.json not found after preprocessing")

#     with open("id_map.json", "r") as f:
#         id_map = json.load(f)

#     ap_names = sorted([n for n in id_map.keys() if "access" in n.lower()])
#     ap_ids = [id_map[n] for n in ap_names]

#     print("[STATE] APs detected:", ap_names)

#     ap_emb = {}

#     for ap_name, ap_id in zip(ap_names, ap_ids):

#         sub = df[(df["src"] == ap_id) | (df["dst"] == ap_id)]
#         feats = sub[feature_cols].to_numpy(dtype=np.float32)

#         if len(feats) == 0:
#             ap_emb[ap_name] = np.zeros(emb_dim, dtype=np.float32)
#             continue

#         # main embedding step
#         z = encoder_fn(feats)        # numpy (N, D)
#         emb = z.mean(axis=0)         # vector (D,)

#         ap_emb[ap_name] = emb

#     return ap_emb


# # -----------------------------------------------------------------------------
# # MAIN
# # -----------------------------------------------------------------------------
# def main():
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--log_dir", required=True,
#                         help="Folder containing fresh NetSim logs")
#     parser.add_argument("--emb_dim", type=int, default=100)
#     args = parser.parse_args()

#     temp_csv = "ml_temp_state.csv"

#     # STEP A — PREPROCESS THE NEW LOGS
#     df = run_preprocess(args.log_dir, temp_csv)

#     # STEP B — LOAD TRAINED TGN ENCODER (FUNCTION)
#     encoder_path = Path("saved_models/wifi_run-mywifi.pth")
#     if not encoder_path.exists():
#         raise FileNotFoundError("❌ TGN encoder not found at saved_models/wifi_run-mywifi.pth")

#     print("[STATE] Loading TGN encoder (function)...")

#     feature_cols = [c for c in df.columns if c not in ["src", "dst", "timestamp"]]

#     encoder_fn = load_embedding_model(
#         checkpoint_path=str(encoder_path),
#         input_dim=len(feature_cols),
#         embedding_dim=args.emb_dim,
#         device="cpu"       # CPU only for RL loop
#     )

#     # STEP C — GET EMBEDDINGS
#     print("[STATE] Extracting AP embeddings...")
#     ap_emb = extract_tgn_embeddings(df, encoder_fn, args.emb_dim)

#     # STEP D — SAVE OUTPUT
#     out_path = "state_embeddings.npy"
#     np.save(out_path, ap_emb)

#     print("[STATE] Saved state embeddings →", out_path)
#     print("[STATE] Done.")


# if __name__ == "__main__":
#     main()

#!/usr/bin/env python3

# '''Version 2'''
# """
# get_state_embedding.py

# Quick end-to-end for a single new simulation iteration (debug mode).
# - Runs preprocessing (utils/preprocess_netsim_to_tgn.py) to produce ml_temp_state.csv + id_map.json
# - Loads trained encoder (saved_models/<prefix>-<data>.pth)
# - Extracts AP embeddings by mean pooling encoder outputs for each AP over events
# - Saves embeddings to embeddings_<data>.npy (dict of ap_name -> vector)

# Important: Uses the preprocess script in utils/.
# """

# import argparse
# import subprocess
# import json
# from pathlib import Path
# import numpy as np
# import pandas as pd
# import torch
# from modules.embedding_module import load_embedding_model

# def run_preprocess(log_dir, temp_csv, time_window=0.1):
#     cmd = [
#         "python", "utils/preprocess_netsim_to_tgn.py",
#         "--input_dir", log_dir,
#         "--out_dir", ".",
#         "--time_window", str(time_window),
#         "--output", temp_csv
#     ]
#     print("[STATE] Running preprocessing:")
#     print("   ", " ".join(cmd))
#     subprocess.check_call(cmd)
#     return temp_csv

# def build_ap_embeddings(csv_path, idmap_path, encoder_fn, emb_dim, device, max_timesteps=None):
#     print("[STATE] Loading CSV:", csv_path)
#     df = pd.read_csv(csv_path)
#     with open(idmap_path, "r") as f:
#         id_map = json.load(f)

#     # ap names from id_map where name looks like AP
#     ap_names = sorted([n for n in id_map.keys() if "access" in n.lower() or "ap_" in n.lower() or "access_point" in n.lower()])
#     if not ap_names:
#         # fallback: assume small-numbered node ids correspond to APs? then fallback to unique src/dst mapping
#         print("[WARN] No AP names detected in id_map by heuristics.")
#         ap_names = sorted(list(id_map.keys()))[:5]

#     print(f"[STATE] Found APs: {ap_names}")

#     # feature columns (all except src,dst,timestamp)
#     feature_cols = [c for c in df.columns if c not in ["src","dst","timestamp"]]
#     feature_dim = len(feature_cols)
#     print(f"[STATE] feature dim = {feature_dim}")

#     ap_embeddings = {}
#     for ap in ap_names:
#         # map ap name -> id
#         ap_id = id_map.get(ap, None)
#         if ap_id is None:
#             print(f"[WARN] AP {ap} not in id_map")
#             continue
#         mask = (df["src"] == ap_id) | (df["dst"] == ap_id)
#         sub = df.loc[mask, feature_cols].to_numpy(dtype=np.float32)
#         if len(sub) == 0:
#             emb = np.zeros(emb_dim, dtype=np.float32)
#         else:
#             # encoder_fn can be either a module or a function (handle both)
#             if hasattr(encoder_fn, "__call__") and not isinstance(encoder_fn, torch.nn.Module):
#                 # encode_fn returns numpy
#                 z = encoder_fn(sub)
#                 emb = z.mean(axis=0)
#             else:
#                 # encoder is a torch module (returns z,recon or z)
#                 x = torch.tensor(sub, dtype=torch.float32, device=device)
#                 with torch.no_grad():
#                     out = encoder_fn(x)
#                     if isinstance(out, tuple) or isinstance(out, list):
#                         z = out[0]
#                     else:
#                         z = out
#                     z = z.detach().cpu().numpy()
#                 emb = z.mean(axis=0)
#         ap_embeddings[ap] = emb.astype(np.float32)
#     return ap_embeddings

# def main():
#     p = argparse.ArgumentParser()
#     p.add_argument("--log_dir", required=True)
#     p.add_argument("--data", required=True, help="dataset name, e.g. mywifi")
#     p.add_argument("--save_prefix", default="wifi_run")
#     p.add_argument("--emb_dim", type=int, default=100)
#     p.add_argument("--device", default="cpu")
#     p.add_argument("--max_timesteps", type=int, default=None, help="not used in quick run")
#     args = p.parse_args()

#     device = torch.device(args.device if torch.cuda.is_available() else "cpu")

#     temp_csv = f"ml_temp_state.csv"
#     # 1) run preprocess
#     run_preprocess(args.log_dir, temp_csv, time_window=1.0)

#     # 2) check files
#     csv_path = Path(temp_csv)
#     idmap_path = Path("id_map.json")
#     encoder_path = Path(f"saved_models/{args.save_prefix}-{args.data}.pth")
#     if not csv_path.exists():
#         raise FileNotFoundError(f"CSV not found: {csv_path}")
#     if not idmap_path.exists():
#         raise FileNotFoundError("id_map.json not found in current dir (preprocess should write it).")
#     if not encoder_path.exists():
#         raise FileNotFoundError(f"encoder model not found: {encoder_path}")

#     # 3) load encoder (could return a callable or a module)
#     encoder_loaded = load_embedding_model(
#         checkpoint_path=encoder_path,
#         input_dim=len([c for c in pd.read_csv(csv_path, nrows=1).columns if c not in ["src","dst","timestamp"]]),
#         embedding_dim=args.emb_dim,
#         device=args.device
#     )

#     # If load_embedding_model returned (module, fn) or function, handle that
#     if isinstance(encoder_loaded, tuple) or isinstance(encoder_loaded, list):
#         # first element is module or encode_fn; try to find module
#         encoder_module = encoder_loaded[0]
#         encode_fn = encoder_loaded[1] if len(encoder_loaded) > 1 else None
#     else:
#         # could be module or function
#         if isinstance(encoder_loaded, torch.nn.Module):
#             encoder_module = encoder_loaded
#             encode_fn = None
#         else:
#             encoder_module = None
#             encode_fn = encoder_loaded

#     if encoder_module is not None:
#         encoder_module = encoder_module.to(device)
#         encoder_module.eval()
#         encoder_for_use = encoder_module
#     else:
#         encoder_for_use = encode_fn

#     # 4) build embeddings
#     ap_embeddings = build_ap_embeddings(csv_path, idmap_path, encoder_for_use, args.emb_dim, device, max_timesteps=args.max_timesteps)

#     # 5) save embeddings
#     out_path = Path(f"embeddings_{args.data}.npz")
#     # save as .npz: keys -> arrays
#     np.savez_compressed(out_path, **ap_embeddings)
#     print("[STATE] Saved embeddings ->", out_path)
#     # also print a small sanity check
#     keys = list(ap_embeddings.keys())
#     print("Keys found:", keys)
#     if keys:
#         k0 = keys[0]
#         print(f"Shape/Type of {k0}:", type(ap_embeddings[k0]))
#         print(ap_embeddings[k0][:10])

# if __name__ == "__main__":
#     main()

'''Version 3'''
import argparse
import subprocess
import json
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import sys

from modules.embedding_module import load_embedding_model


# -------------------------------------------------------------------------
# Preprocess (Using correct Python + correct time_window)
# -------------------------------------------------------------------------
def run_preprocess(log_dir, temp_csv, time_window=0.1):
    cmd = [
        sys.executable, "utils/preprocess_netsim_to_tgn.py",
        "--input_dir", log_dir,
        "--out_dir", ".",
        "--time_window", str(time_window),
        "--output", temp_csv
    ]
    print("[STATE] Running preprocessing:")
    print("   ", " ".join(cmd))
    subprocess.check_call(cmd)
    return temp_csv


# -------------------------------------------------------------------------
# Optional batched encoding for speed (GPU/CPU)
# -------------------------------------------------------------------------
def encode_in_batches(encoder_module, data, device, batch=1024):
    z_all = []
    for i in range(0, len(data), batch):
        x = torch.tensor(
            data[i:i+batch], dtype=torch.float32, device=device
        )
        with torch.no_grad():
            out = encoder_module(x)
            if isinstance(out, (list, tuple)):
                out = out[0]
            z_all.append(out.detach().cpu().numpy())
    return np.concatenate(z_all, axis=0)


# -------------------------------------------------------------------------
# Build AP embeddings
# -------------------------------------------------------------------------
def build_ap_embeddings(csv_path, idmap_path, encoder_fn, emb_dim, device, max_timesteps=None):
    print("[STATE] Loading CSV:", csv_path)
    df = pd.read_csv(csv_path)

    # apply timesteps limit here
    if max_timesteps is not None:
        df = df.iloc[:max_timesteps]

    with open(idmap_path, "r") as f:
        id_map = json.load(f)

    # Improved AP detection
    ap_names = [
        name for name in id_map
        if name.lower().startswith("ap")
        or "access" in name.lower()
    ]

    if not ap_names:
        print("[WARN] No AP names detected, falling back to first 5 nodes.")
        ap_names = sorted(list(id_map.keys()))[:5]

    print(f"[STATE] Found APs: {ap_names}")

    # feature columns are everything except src/dst/timestamp
    feature_cols = [c for c in df.columns if c not in ["src", "dst", "timestamp"]]
    feature_dim = len(feature_cols)
    print(f"[STATE] feature dim = {feature_dim}")

    ap_embeddings = {}

    for ap in ap_names:
        ap_id = id_map.get(ap, None)
        if ap_id is None:
            print(f"[WARN] AP {ap} not found in id_map")
            continue

        mask = (df["src"] == ap_id) | (df["dst"] == ap_id)
        sub = df.loc[mask, feature_cols].to_numpy(dtype=np.float32)

        if len(sub) == 0:
            emb = np.zeros(emb_dim, dtype=np.float32)
        else:
            # if encoder_fn is a module → batch it
            if isinstance(encoder_fn, torch.nn.Module):
                z = encode_in_batches(encoder_fn, sub, device)
            else:
                # callable returning numpy
                z = encoder_fn(sub)
            emb = z.mean(axis=0)

        ap_embeddings[ap] = emb.astype(np.float32)

    return ap_embeddings


# -------------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--log_dir", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--save_prefix", default="wifi_run")
    p.add_argument("--emb_dim", type=int, default=100)
    p.add_argument("--device", default="cpu")
    p.add_argument("--max_timesteps", type=int, default=None)
    args = p.parse_args()

    device = torch.device(args.device if torch.cuda.is_available() else "cpu")

    temp_csv = "ml_temp_state.csv"

    # Step 1: preprocess logs (uses window=0.1 now)
    run_preprocess(args.log_dir, temp_csv, time_window=0.1)

    # Check expected files
    csv_path = Path(temp_csv)
    idmap_path = Path("id_map.json")
    encoder_path = Path(f"saved_models/{args.save_prefix}-{args.data}.pth")

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    if not idmap_path.exists():
        raise FileNotFoundError("id_map.json not found (preprocessing should generate it)")
    if not encoder_path.exists():
        raise FileNotFoundError(f"Encoder model not found: {encoder_path}")

    # Load encoder
    encoder_loaded = load_embedding_model(
        checkpoint_path=encoder_path,
        input_dim=len([c for c in pd.read_csv(csv_path, nrows=1).columns if c not in ["src", "dst", "timestamp"]]),
        embedding_dim=args.emb_dim,
        device=args.device
    )

    # Determine if load returned (module, fn) or single object
    if isinstance(encoder_loaded, (tuple, list)):
        encoder_module = encoder_loaded[0]
        encode_fn = encoder_loaded[1] if len(encoder_loaded) > 1 else None
    else:
        encoder_module = encoder_loaded if isinstance(encoder_loaded, torch.nn.Module) else None
        encode_fn = encoder_loaded if encoder_module is None else None

    if encoder_module is not None:
        encoder_module = encoder_module.to(device)
        encoder_module.eval()
        encoder_for_use = encoder_module
    else:
        encoder_for_use = encode_fn

    # Step 4: build embeddings
    ap_embeddings = build_ap_embeddings(
        csv_path, idmap_path, encoder_for_use,
        args.emb_dim, device,
        max_timesteps=args.max_timesteps
    )

    # Step 5: save embeddings
    out_path = Path(f"embeddings_{args.data}.npz")
    np.savez_compressed(out_path, **ap_embeddings)
    print("[STATE] Saved embeddings ->", out_path)

    keys = list(ap_embeddings.keys())
    print("Keys:", keys)
    if keys:
        k0 = keys[0]
        print(f"Sample {k0}:", ap_embeddings[k0][:10])


if __name__ == "__main__":
    main()
