#!/usr/bin/env python3
# train_sugar.py — Robust SUGAR trainer (handles multiple encoder return types)

import argparse
import torch
import torch.optim as optim
import pandas as pd
import numpy as np
import json
import sys
import traceback
from pathlib import Path

from modules.embedding_module import load_embedding_model
from modules.sugar_model import SubgraphPooler
from modules.mi_loss import info_nce_loss


class FuncEncoderWrapper(torch.nn.Module):
    """
    Wrap a callable encoder (function) into an nn.Module so SUGAR can call .to(device) and .eval().
    The callable may accept either a torch.Tensor or numpy array and may return:
      - torch.Tensor z
      - numpy.ndarray z
      - (z, recon) tuple where z is tensor/ndarray
    Forward returns (z_tensor, recon_tensor) where recon is a zeros placeholder.
    """
    def __init__(self, fn, in_feat_dim, device):
        super().__init__()
        self.fn = fn
        self.in_feat_dim = in_feat_dim
        self.device = device

    def forward(self, x):
        # x is a torch.Tensor (N_events, feat_dim)
        try:
            # Try calling the function with tensor first (some wrappers accept tensors)
            out = self.fn(x)
        except Exception:
            # fallback: convert to numpy and call
            arr = x.detach().cpu().numpy()
            out = self.fn(arr)

        # Normalize outputs to (z_tensor, recon_tensor)
        if isinstance(out, (list, tuple)):
            z = out[0]
        else:
            z = out

        if isinstance(z, np.ndarray):
            z_t = torch.tensor(z, dtype=torch.float32, device=self.device)
        elif isinstance(z, torch.Tensor):
            z_t = z.to(self.device)
        else:
            # try convertable
            z_t = torch.tensor(np.array(z), dtype=torch.float32, device=self.device)

        # recon placeholder: zeros sized (N_events, in_feat_dim)
        recon_t = torch.zeros((z_t.size(0), self.in_feat_dim), dtype=torch.float32, device=self.device)
        return z_t, recon_t


def build_H_per_timestep(df, id_map, encoder, emb_dim, device,
                         max_timesteps=None, debug_every=1000):
    """
    Build per-timestep AP embedding matrices:
      returns: dict ts -> (ap_names, H tensor (N_ap, D))
    encoder: nn.Module (callable) that returns (z, recon) or z
    """
    ap_names = sorted([n for n in id_map.keys()
                       if n.lower().startswith("access")
                       or n.lower().startswith("ap")
                       or "access_point" in n.lower()])

    ap_ids = [id_map[n] for n in ap_names]
    ts_bins = sorted(df["timestamp"].unique())
    if max_timesteps is not None:
        ts_bins = ts_bins[:max_timesteps]

    feature_cols = [c for c in df.columns if c not in ["src", "dst", "timestamp"]]
    ts_to_H = {}

    print(f"[SUGAR] building H: timesteps={len(ts_bins)}  APs={len(ap_ids)}  feat_dim={len(feature_cols)}")
    sys.stdout.flush()

    # Pre-calc mapping from timestamp -> subframe for speed (pandas groupby may be slower repeatedly)
    groups = {ts: grp for ts, grp in df.groupby("timestamp")}

    for i, ts in enumerate(ts_bins, start=1):
        g = groups.get(ts, pd.DataFrame(columns=df.columns))
        H_rows = []
        for ap_name, ap_id in zip(ap_names, ap_ids):
            sub = g[(g["src"] == ap_id) | (g["dst"] == ap_id)]
            feats = sub[feature_cols].to_numpy(dtype=np.float32)
            if feats.shape[0] == 0:
                H_rows.append(torch.zeros(emb_dim, device=device))
            else:
                x = torch.tensor(feats, dtype=torch.float32, device=device)
                with torch.no_grad():
                    out = encoder(x)
                    # encoder may return (z, recon) or z directly
                    if isinstance(out, (tuple, list)):
                        z = out[0]
                    else:
                        z = out
                    # ensure z is tensor
                    if isinstance(z, np.ndarray):
                        z = torch.tensor(z, dtype=torch.float32, device=device)
                    elif isinstance(z, torch.Tensor):
                        z = z.to(device)
                    else:
                        z = torch.tensor(np.array(z), dtype=torch.float32, device=device)
                # average events
                H_rows.append(z.mean(dim=0))
        H = torch.stack(H_rows, dim=0)  # (N_ap, D)
        ts_to_H[ts] = (ap_names, H)

        if (i % debug_every) == 0:
            print(f"[SUGAR] built {i}/{len(ts_bins)} timesteps")
            sys.stdout.flush()

    return ts_to_H


def main():
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--data", required=True)
        parser.add_argument("--save_prefix", default="wifi_run")
        parser.add_argument("--emb_dim", type=int, default=100)
        parser.add_argument("--k", type=int, default=3)
        parser.add_argument("--epochs", type=int, default=5)
        parser.add_argument("--batch", type=int, default=16)
        parser.add_argument("--device", default="cpu")
        parser.add_argument("--max_timesteps", type=int, default=None,
                            help="If set, limit number of timesteps (useful for fast tests)")
        args = parser.parse_args()

        device = torch.device(args.device if torch.cuda.is_available() else "cpu")
        print(f"[SUGAR] device = {device}")
        sys.stdout.flush()

        csv_path = Path(f"data/ml_{args.data}.csv")
        idmap_path = Path(f"data/{args.data}_id_map.json")
        encoder_path = Path(f"saved_models/{args.save_prefix}-{args.data}.pth")

        print("[SUGAR] checking paths...")
        print("  csv:   ", csv_path)
        print("  idmap: ", idmap_path)
        print("  encoder:", encoder_path)
        sys.stdout.flush()

        if not csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")
        if not idmap_path.exists():
            raise FileNotFoundError(f"id_map not found: {idmap_path}")
        if not encoder_path.exists():
            raise FileNotFoundError(f"encoder model not found: {encoder_path}")

        print("[SUGAR] loading CSV (pandas) ...")
        df = pd.read_csv(csv_path)
        print(f"[SUGAR] events: {len(df)}  columns: {df.shape[1]}")
        sys.stdout.flush()

        with open(idmap_path, "r") as f:
            id_map = json.load(f)

        print("[SUGAR] loading encoder model (frozen encoder)...")
        loaded = load_embedding_model(
            checkpoint_path=encoder_path,
            input_dim=len([c for c in df.columns if c not in ["src", "dst", "timestamp"]]),
            embedding_dim=args.emb_dim,
            device=args.device
        )

        # Normalize `loaded` into an nn.Module encoder_module
        if isinstance(loaded, torch.nn.Module):
            encoder_module = loaded
        elif isinstance(loaded, (tuple, list)) and isinstance(loaded[0], torch.nn.Module):
            encoder_module = loaded[0]
        elif callable(loaded):
            # wrap callable into module
            in_feat = len([c for c in df.columns if c not in ["src", "dst", "timestamp"]])
            encoder_module = FuncEncoderWrapper(loaded, in_feat_dim=in_feat, device=device)
        else:
            # try tuple first element
            if isinstance(loaded, (tuple, list)):
                candidate = loaded[0]
                if isinstance(candidate, torch.nn.Module):
                    encoder_module = candidate
                elif callable(candidate):
                    in_feat = len([c for c in df.columns if c not in ["src", "dst", "timestamp"]])
                    encoder_module = FuncEncoderWrapper(candidate, in_feat_dim=in_feat, device=device)
                else:
                    raise RuntimeError("Unsupported encoder type returned by load_embedding_model")
            else:
                raise RuntimeError("Unsupported encoder type returned by load_embedding_model")

        encoder = encoder_module.to(device)
        encoder.eval()

        print("[SUGAR] building timestep embeddings (use --max_timesteps to speed up)...")
        ts_to_H = build_H_per_timestep(df, id_map, encoder, args.emb_dim, device,
                                       max_timesteps=args.max_timesteps)
        ts_list = list(ts_to_H.keys())

        pooler = SubgraphPooler(emb_dim=args.emb_dim, k=args.k).to(device)
        opt = optim.Adam(pooler.parameters(), lr=1e-3)

        save_path = Path("saved_models") / f"sugar-{args.save_prefix}-{args.data}.pth"
        best_loss = float("inf")

        print(f"[SUGAR] training pooler (epochs={args.epochs}, batch={args.batch}, k={args.k}) ...")
        sys.stdout.flush()

        for epoch in range(1, args.epochs + 1):
            pooler.train()
            epoch_loss = 0.0
            steps = max(1, len(ts_list) // args.batch)

            for step in range(steps):
                sel = np.random.choice(ts_list, size=args.batch, replace=False)
                H_batch = []
                G_batch = []
                for ts in sel:
                    _, H = ts_to_H[ts]
                    H_batch.append(H)                  # (N_ap, D)
                    G_batch.append(H.mean(dim=0))      # (D,)

                H_batch = torch.stack(H_batch, dim=0)   # (B, N, D)
                G_batch = torch.stack(G_batch, dim=0)   # (B, D)
                B = H_batch.size(0)

                pooled_list = []
                for i in range(B):
                    pooled, _ = pooler(H_batch[i])      # (k, D)
                    pooled_list.append(pooled)

                pooled = torch.stack(pooled_list, dim=0)  # (B, k, D)
                # ensure pooled participates in gradient graph
                pooled = pooled.requires_grad_()

                # negatives: other globals in batch (for each sample)
                negs = []
                for i in range(B):
                    other_idx = [j for j in range(B) if j != i]
                    if len(other_idx) == 0:
                        other_idx = [i]
                    negs.append(G_batch[other_idx].unsqueeze(0))
                negs = torch.cat(negs, dim=0)  # (B, Nneg, D)

                loss = info_nce_loss(pooled, G_batch, negs)
                opt.zero_grad()
                loss.backward()
                opt.step()

                epoch_loss += loss.item()

            print(f"[SUGAR] Epoch {epoch}/{args.epochs}  loss={epoch_loss:.6f}")
            sys.stdout.flush()

            if epoch_loss < best_loss:
                best_loss = epoch_loss
                torch.save(pooler.state_dict(), save_path)
                print("[SUGAR] saved best pooler ->", save_path)
                sys.stdout.flush()

        print("[SUGAR] Training finished. best_loss =", best_loss)

    except Exception:
        print("=== EXCEPTION in train_sugar.py ===")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
