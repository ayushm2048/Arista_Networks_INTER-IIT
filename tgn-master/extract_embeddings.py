# extract_embeddings.py
# Generate AP-wise embeddings from the trained autoencoder encoder.

import argparse
import pandas as pd
import numpy as np
import torch
from pathlib import Path
import json

from modules.embedding_module import load_embedding_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, required=True)   # dataset name (mywifi)
    parser.add_argument("--save_prefix", type=str, default="wifi_run")
    parser.add_argument("--embedding_dim", type=int, default=100)
    parser.add_argument("--device", type=str, default="cpu")
    args = parser.parse_args()

    # CSV and model paths
    csv_path = Path(f"./data/ml_{args.data}.csv")
    model_path = Path(f"./saved_models/{args.save_prefix}-{args.data}.pth")
    idmap_path = Path(f"./data/{args.data}/id_map.json")

    print("[extract] Loading data:", csv_path)
    df = pd.read_csv(csv_path)

    print("[extract] Loading id_map.json:", idmap_path)
    with open(idmap_path, "r") as f:
        id_map = json.load(f)          # dict: name → id

    # Reverse map: id → name
    id_to_name = {v: k for k, v in id_map.items()}

    # Identify AP nodes by *name*
    ap_node_ids = [
        nid for nid, name in id_to_name.items()
        if name.lower().startswith("ap") or "access" in name.lower()
    ]

    print(f"[extract] Found AP node IDs: {ap_node_ids}")

    # Collect feature columns (exclude src/dst/timestamp)
    feature_cols = [c for c in df.columns if c not in ["src", "dst", "timestamp"]]
    feature_dim = len(feature_cols)

    print(f"[extract] feature_dim = {feature_dim}")

    # Load trained encoder (from modules/embedding_module.py)
    encoder = load_embedding_model(
        checkpoint_path=model_path,
        input_dim=feature_dim,
        embedding_dim=args.embedding_dim,
        device=args.device
    )

    # Prepare output dict
    ap_embeddings = {}

    # Compute embedding for each AP
    for ap_id in ap_node_ids:
        ap_name = id_to_name[ap_id]

        mask = (df["src"] == ap_id) | (df["dst"] == ap_id)
        sub = df.loc[mask, feature_cols].to_numpy(dtype=np.float32)

        if len(sub) == 0:
            emb = np.zeros(args.embedding_dim, dtype=np.float32)
        else:
            with torch.no_grad():
                emb_events = encoder(sub)    # shape (N, emb_dim)
            emb = emb_events.mean(axis=0)    # pooled AP embedding

        ap_embeddings[ap_name] = emb

    # Save embeddings
    out_path = Path(f"./embeddings_{args.data}.npy")
    np.save(out_path, ap_embeddings)

    print(f"[extract] Saved AP embeddings to: {out_path}")


if __name__ == "__main__":
    main()
