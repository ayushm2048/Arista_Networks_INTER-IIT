# extract_sugar_embeddings.py  (FAST + COMPATIBLE WITH YOUR embedding_module)
import argparse
import json
import numpy as np
import pandas as pd
import torch
from pathlib import Path

from modules.embedding_module import AutoEncoder   # you DO have this
from modules.sugar_model import SubgraphPooler


# -------------------------------------------------------------------
# LOCAL LOADER FOR AUTOENCODER  (matches your training)
# -------------------------------------------------------------------
@torch.no_grad()
def load_encoder_for_sugar(checkpoint_path, input_dim, emb_dim, device):
    model = AutoEncoder(input_dim=input_dim,
                        embedding_dim=emb_dim,
                        hidden=128).to(device)
    model.load_state_dict(torch.load(checkpoint_path, map_location=device))
    model.eval()
    return model.encoder   # return encoder module


# -------------------------------------------------------------------
# FAST AP TIMESTEP EMBEDDING BUILDER
# -------------------------------------------------------------------
def build_H_per_timestep_fast(df, id_map, encoder, emb_dim, device, max_ts=None):
    ap_names = sorted([
        n for n in id_map.keys()
        if n.lower().startswith("access") or n.lower().startswith("ap")
    ])
    ap_ids = [id_map[n] for n in ap_names]

    timestamps = df["timestamp"].unique()
    timestamps.sort()

    if max_ts:
        timestamps = timestamps[:max_ts]

    feat_cols = [c for c in df.columns if c not in ["src", "dst", "timestamp"]]
    grouped = {ts: g for ts, g in df.groupby("timestamp")}

    print(f"[FAST-EXTRACT] timesteps={len(timestamps)}  APs={len(ap_ids)}  feat_dim={len(feat_cols)}")

    ts_to_H = {}

    for idx, ts in enumerate(timestamps, 1):
        g = grouped[ts]
        H_rows = []

        for ap_id in ap_ids:
            sub = g[(g["src"] == ap_id) | (g["dst"] == ap_id)]
            feats = sub[feat_cols].to_numpy(dtype=np.float32)

            if len(feats) == 0:
                H_rows.append(torch.zeros(emb_dim, device=device))
            else:
                x = torch.tensor(feats, dtype=torch.float32, device=device)
                z = encoder(x)  # returns tensor (N,D)
                H_rows.append(z.mean(dim=0))

        H = torch.stack(H_rows, dim=0)
        ts_to_H[ts] = (ap_names, H)

        if idx % 1000 == 0:
            print(f"[FAST-EXTRACT] built {idx}/{len(timestamps)} timesteps")

    return ts_to_H


# -------------------------------------------------------------------
# MAIN EXTRACTION
# -------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--save_prefix", required=True)
    parser.add_argument("--emb_dim", type=int, default=100)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--max_timesteps", type=int, default=None)
    args = parser.parse_args()

    device = torch.device("cpu")

    csv_path = Path(f"data/ml_{args.data}.csv")
    idmap_path = Path(f"data/{args.data}_id_map.json")
    encoder_path = Path(f"saved_models/{args.save_prefix}-{args.data}.pth")
    sugar_path = Path(f"saved_models/sugar-{args.save_prefix}-{args.data}.pth")

    print("[EXTRACT] checking files:")
    for p in [csv_path, idmap_path, encoder_path, sugar_path]:
        print("  ", p, "OK" if p.exists() else "MISSING")

    # Load CSV + id map
    df = pd.read_csv(csv_path)
    with open(idmap_path, "r") as f:
        id_map = json.load(f)

    # -------- load encoder (your real autoencoder) --------
    encoder = load_encoder_for_sugar(
        checkpoint_path=encoder_path,
        input_dim=len([c for c in df.columns if c not in ["src", "dst", "timestamp"]]),
        emb_dim=args.emb_dim,
        device=device
    )

    # -------- load SUGAR pooler --------
    pooler = SubgraphPooler(emb_dim=args.emb_dim, k=args.k).to(device)
    pooler.load_state_dict(torch.load(sugar_path, map_location=device))
    pooler.eval()

    # -------- build timestep AP matrices --------
    ts_to_H = build_H_per_timestep_fast(
        df=df,
        id_map=id_map,
        encoder=encoder,
        emb_dim=args.emb_dim,
        device=device,
        max_ts=args.max_timesteps
    )

    # -------- aggregate pooled embeddings --------
    ap_names = sorted([
        n for n in id_map.keys()
        if n.lower().startswith("access") or n.lower().startswith("ap")
    ])
    ap_emb_list = {ap: [] for ap in ap_names}

    print("[EXTRACT] applying SUGAR pooling…")

    for ts, (names, H) in ts_to_H.items():
        with torch.no_grad():
            pooled, _ = pooler(H)
            pooled_vec = pooled.mean(dim=0).cpu().numpy()

        for ap in ap_names:
            ap_emb_list[ap].append(pooled_vec)

    # Final averaged vectors
    final = {ap: np.mean(np.stack(v, axis=0), axis=0) for ap, v in ap_emb_list.items()}

    out_path = Path(f"embeddings_sugar_{args.data}.npy")
    np.save(out_path, final)

    print("[EXTRACT] saved:", out_path)


if __name__ == "__main__":
    main()
