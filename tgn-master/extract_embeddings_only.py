# extract_embeddings_only.py
import argparse
import numpy as np
import pandas as pd
import torch
from pathlib import Path

from modules.embedding_module import load_embedding_model
from modules.sugar_model import SugarPoolingMLP   # FIXED IMPORT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--save_prefix", default="wifi_run")
    parser.add_argument("--emb_dim", type=int, default=100)
    parser.add_argument("--k", type=int, default=6)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    csv_path = Path(f"./data/ml_{args.data}.csv")
    df = pd.read_csv(csv_path)

    feature_cols = [c for c in df.columns if c not in ["src", "dst", "timestamp"]]
    feature_dim = len(feature_cols)

    encoder = load_embedding_model(
        checkpoint_path=Path(f"./saved_models/{args.save_prefix}-{args.data}.pth"),
        input_dim=feature_dim,
        embedding_dim=args.emb_dim,
        device=args.device
    )

    sugar_path = Path(f"./saved_models/sugar-{args.save_prefix}-{args.data}.pth")

    sugar_model = SugarPoolingMLP(embed_dim=args.emb_dim, k=args.k)
    sugar_model.load_state_dict(torch.load(sugar_path, map_location=args.device))
    sugar_model.eval()

    ap_names = sorted(x for x in df["src"].unique() if "ACCESS_POINT" in str(x))
    timestamps = sorted(df["timestamp"].unique())

    output = {
        "ap_names": ap_names,
        "timestamps": timestamps,
        "pooled": {}
    }

    for ts in timestamps:
        sub = df[df["timestamp"] == ts]

        per_ap = []
        for ap in ap_names:
            rows = sub[(sub["src"] == ap) | (sub["dst"] == ap)]
            feats = rows[feature_cols].to_numpy(dtype=np.float32)

            if len(feats) == 0:
                per_ap.append(np.zeros(args.emb_dim))
                continue

            with torch.no_grad():
                emb = encoder(feats)
                per_ap.append(emb.mean(axis=0))

        per_ap = torch.tensor(per_ap, dtype=torch.float32)

        with torch.no_grad():
            pooled = sugar_model(per_ap)

        output["pooled"][ts] = pooled.numpy()

    np.save(f"embeddings_sugar_{args.data}.npy", output)
    print("[extract] Saved embeddings → embeddings_sugar_%s.npy" % args.data)


if __name__ == "__main__":
    main()
