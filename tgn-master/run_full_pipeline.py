# import argparse
# import subprocess
# from pathlib import Path
# import json
# import os
# import sys
# import shutil

# ###############################################################################
# # run_full_pipeline.py  (FINAL VERSION)
# #
# # 1. Preprocessing (logs → dataset.csv + id_map.json)
# # 2. Copy into TGN directory (ml_<dataset>.csv + <dataset>_id_map.json)
# # 3. Train autoencoder (train_self_supervised.py)
# # 4. Train SUGAR (train_sugar.py)
# # 5. Extract pooled embeddings (extract_sugar_embeddings.py)
# ###############################################################################


# def run_preprocessing(args):
#     print("\n==============================")
#     print(" STEP 1 — PREPROCESSING LOGS ")
#     print("==============================\n")

#     preprocess_script = Path("utils/preprocess_netsim_to_tgn.py")
#     if not preprocess_script.exists():
#         print("[ERROR] preprocess_netsim_to_tgn.py not found in utils/")
#         sys.exit(1)

#     Path(args.out_dir).mkdir(parents=True, exist_ok=True)

#     out_csv = f"{args.dataset}.csv"

#     cmd = [
#         sys.executable, str(preprocess_script),
#         "--input_dir", args.input_dir,
#         "--out_dir", args.out_dir,
#         "--time_window", str(args.window_s),
#         "--output", out_csv,
#         "--app", "Application_Packet_Log.csv"
#     ]

#     print("[INFO] Running preprocessing script:")
#     print(" ", " ".join(cmd), "\n")
#     subprocess.check_call(cmd)

#     print("[INFO] Preprocessing completed.")
#     print(f"[INFO] Created: {args.out_dir}/{out_csv}")
#     print(f"[INFO] Created: {args.out_dir}/id_map.json\n")


# def run_autoencoder_training(args):
#     print("\n==============================")
#     print(" STEP 2 — TRAIN AUTOENCODER ")
#     print("==============================\n")

#     train_script = Path("train_self_supervised.py")
#     if not train_script.exists():
#         print("[ERROR] train_self_supervised.py not found!")
#         sys.exit(1)

#     cmd = [
#         sys.executable, str(train_script),
#         "--data", args.dataset,
#         "--save_prefix", args.prefix,
#         "--n_epoch", str(args.epochs)
#     ]

#     print("[INFO] Running autoencoder training:")
#     print(" ", " ".join(cmd), "\n")
#     subprocess.check_call(cmd)


# def run_sugar_training(args):
#     print("\n==============================")
#     print(" STEP 3 — TRAIN SUGAR ")
#     print("==============================\n")

#     cmd = [
#         sys.executable, "train_sugar.py",
#         "--data", args.dataset,
#         "--save_prefix", args.prefix,
#         "--emb_dim", "100",
#         "--k", "6",
#         "--epochs", "30",
#         "--batch", "64",
#         "--lr", "0.001"
#     ]

#     print("[INFO] Running SUGAR training:")
#     print(" ", " ".join(cmd), "\n")
#     subprocess.check_call(cmd)


# def run_sugar_extract(args):
#     print("\n==============================")
#     print(" STEP 4 — EXTRACT SUGAR EMBEDDINGS ")
#     print("==============================\n")

#     cmd = [
#         sys.executable, "extract_sugar_embeddings.py",
#         "--data", args.dataset,
#         "--save_prefix", args.prefix,
#         "--emb_dim", "100",
#         "--k", "6"
#     ]

#     print("[INFO] Extracting pooled embeddings:")
#     print(" ", " ".join(cmd), "\n")
#     subprocess.check_call(cmd)


# def main():
#     parser = argparse.ArgumentParser()

#     parser.add_argument("--input_dir", required=True)
#     parser.add_argument("--out_dir", required=True)
#     parser.add_argument("--dataset", required=True)
#     parser.add_argument("--window_s", type=float, default=0.1)
#     parser.add_argument("--epochs", type=int, default=50)
#     parser.add_argument("--prefix", default="run")

#     args = parser.parse_args()

#     # --- Step 1 ---
#     run_preprocessing(args)

#     # --- Step 2: Copy output to data/ ---
#     print("\n[INFO] Copying preprocessed outputs to TGN directory...")

#     dst_csv = Path("data") / f"ml_{args.dataset}.csv"
#     dst_idmap = Path("data") / f"{args.dataset}_id_map.json"
#     Path("data").mkdir(exist_ok=True)

#     shutil.copy(Path(args.out_dir) / f"{args.dataset}.csv", dst_csv)
#     shutil.copy(Path(args.out_dir) / "id_map.json", dst_idmap)

#     print(f"[INFO] Dataset ready: {dst_csv}")
#     print(f"[INFO] ID map ready: {dst_idmap}\n")

#     # --- Step 3 ---
#     run_autoencoder_training(args)

#     # --- Step 4 ---
#     run_sugar_training(args)

#     # --- Step 5 ---
#     run_sugar_extract(args)


# if __name__ == "__main__":
#     main()

# import argparse
# import subprocess
# from pathlib import Path
# import shutil
# import sys


# def run_preprocessing(args):
#     print("\n==============================")
#     print(" STEP 1 — PREPROCESSING LOGS ")
#     print("==============================\n")

#     preprocess_script = Path("utils/preprocess_netsim_to_tgn.py")
#     if not preprocess_script.exists():
#         print("ERROR: preprocess_netsim_to_tgn.py not found!")
#         sys.exit(1)

#     out = Path(args.out_dir)
#     out.mkdir(parents=True, exist_ok=True)

#     cmd = [
#         sys.executable, str(preprocess_script),
#         "--input_dir", args.input_dir,
#         "--out_dir", args.out_dir,
#         "--time_window", str(args.time_window),
#         "--output", f"{args.dataset}.csv"
#     ]

#     print("[INFO] Running:", " ".join(cmd))
#     subprocess.check_call(cmd)

#     print("\n[INFO] Preprocessing DONE.\n")


# def copy_to_tgn(args):
#     print("\n==============================")
#     print(" STEP 2 — COPYING FOR TGN    ")
#     print("==============================\n")

#     src_csv = Path(args.out_dir) / f"{args.dataset}.csv"
#     src_idmap = Path(args.out_dir) / "id_map.json"

#     dst_csv = Path("data") / f"ml_{args.dataset}.csv"
#     dst_idmap = Path("data") / f"{args.dataset}_id_map.json"

#     Path("data").mkdir(exist_ok=True)

#     shutil.copy(src_csv, dst_csv)
#     shutil.copy(src_idmap, dst_idmap)

#     print("[INFO] Copied:")
#     print("  →", dst_csv)
#     print("  →", dst_idmap)


# def run_tgn_training(args):
#     print("\n==============================")
#     print(" STEP 3 — TRAIN TGN          ")
#     print("==============================\n")

#     cmd = [
#         sys.executable, "train_self_supervised.py",
#         "--data", args.dataset,
#         "--save_prefix", args.save_prefix,
#         "--n_epoch", str(args.tgn_epochs)
#     ]

#     print("[INFO] Running:", " ".join(cmd))
#     subprocess.check_call(cmd)

#     print("[INFO] TGN training DONE.\n")


# def run_sugar_training(args):
#     print("\n==============================")
#     print(" STEP 4 — TRAIN SUGAR        ")
#     print("==============================\n")

#     cmd = [
#         sys.executable, "train_sugar.py",
#         "--data", args.dataset,
#         "--save_prefix", args.save_prefix,
#         "--emb_dim", str(args.emb_dim),
#         "--k", str(args.k),
#         "--epochs", str(args.sugar_epochs),
#         "--batch", "16",
#         "--device", args.device,
#         "--max_timesteps", str(args.max_timesteps)
#     ]

#     print("[INFO] Running:", " ".join(cmd))
#     subprocess.check_call(cmd)

#     print("[INFO] SUGAR training DONE.\n")


# def run_sugar_extract(args):
#     print("\n==============================")
#     print(" STEP 5 — EXTRACT EMBEDDINGS ")
#     print("==============================\n")

#     cmd = [
#         sys.executable, "extract_sugar_embeddings.py",
#         "--data", args.dataset,
#         "--save_prefix", args.save_prefix,
#         "--emb_dim", str(args.emb_dim),
#         "--k", str(args.k),
#         "--device", args.device,
#         "--max_timesteps", str(args.max_timesteps)
#     ]

#     print("[INFO] Running:", " ".join(cmd))
#     subprocess.check_call(cmd)

#     print("[INFO] SUGAR embeddings extracted.\n")


# def main():
#     parser = argparse.ArgumentParser()

#     parser.add_argument("--input_dir", required=True)
#     parser.add_argument("--out_dir", default="tgn_output")
#     parser.add_argument("--dataset", default="mywifi")

#     parser.add_argument("--time_window", type=float, default=1.0)
#     parser.add_argument("--save_prefix", default="wifi_run")

#     parser.add_argument("--tgn_epochs", type=int, default=20)
#     parser.add_argument("--sugar_epochs", type=int, default=5)
#     parser.add_argument("--emb_dim", type=int, default=100)
#     parser.add_argument("--k", type=int, default=3)
#     parser.add_argument("--max_timesteps", type=int, default=500)

#     parser.add_argument("--device", default="cpu")

#     args = parser.parse_args()

#     run_preprocessing(args)
#     copy_to_tgn(args)
#     run_tgn_training(args)
#     run_sugar_training(args)
#     run_sugar_extract(args)

#     print("\n==============================")
#     print(" FULL PIPELINE COMPLETED 🎉   ")
#     print("==============================\n")


# if __name__ == "__main__":
#     main()

import argparse
import subprocess
from pathlib import Path
import shutil
import sys


def run_preprocessing(args):
    print("\n==============================")
    print(" STEP 1 — PREPROCESSING LOGS ")
    print("==============================\n")

    preprocess_script = Path("utils/preprocess_netsim_to_tgn.py")
    if not preprocess_script.exists():
        print("ERROR: preprocess_netsim_to_tgn.py not found!")
        sys.exit(1)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, str(preprocess_script),
        "--input_dir", args.input_dir,
        "--out_dir", args.out_dir,
        "--time_window", str(args.time_window),
        "--output", f"{args.dataset}.csv"
    ]

    print("[INFO] Running:", " ".join(cmd))
    subprocess.check_call(cmd)

    print("\n[INFO] Preprocessing DONE.\n")


def copy_to_tgn(args):
    print("\n==============================")
    print(" STEP 2 — COPYING FOR TGN    ")
    print("==============================\n")

    src_csv = Path(args.out_dir) / f"{args.dataset}.csv"
    src_idmap = Path(args.out_dir) / "id_map.json"

    dst_csv = Path("data") / f"ml_{args.dataset}.csv"
    dst_idmap = Path("data") / f"{args.dataset}_id_map.json"

    Path("data").mkdir(exist_ok=True)

    shutil.copy(src_csv, dst_csv)
    shutil.copy(src_idmap, dst_idmap)

    print("[INFO] Copied:")
    print("  →", dst_csv)
    print("  →", dst_idmap)


def run_tgn_training(args):
    print("\n==============================")
    print(" STEP 3 — TRAIN TGN          ")
    print("==============================\n")

    # ❗ PATCH: Removed --emb_dim (TGN does NOT accept this argument)
    cmd = [
    sys.executable, "train_self_supervised.py",
    "--data", args.dataset,
    "--save_prefix", args.save_prefix,
    "--n_epoch", str(args.tgn_epochs),
    "--device", args.device          # << ADD THIS
]

    print("[INFO] Running:", " ".join(cmd))
    subprocess.check_call(cmd)

    print("[INFO] TGN training DONE.\n")


def run_sugar_training(args):
    print("\n==============================")
    print(" STEP 4 — TRAIN SUGAR        ")
    print("==============================\n")

    cmd = [
        sys.executable, "train_sugar.py",
        "--data", args.dataset,
        "--save_prefix", args.save_prefix,
        "--emb_dim", str(args.emb_dim),
        "--k", str(args.k),
        "--epochs", str(args.sugar_epochs),
        "--batch", "16",
        "--device", args.device,
        "--max_timesteps", str(args.max_timesteps)
    ]

    print("[INFO] Running:", " ".join(cmd))
    subprocess.check_call(cmd)

    print("[INFO] SUGAR training DONE.\n")


def run_sugar_extract(args):
    print("\n==============================")
    print(" STEP 5 — EXTRACT EMBEDDINGS ")
    print("==============================\n")

    cmd = [
        sys.executable, "extract_sugar_embeddings.py",
        "--data", args.dataset,
        "--save_prefix", args.save_prefix,
        "--emb_dim", str(args.emb_dim),
        "--k", str(args.k),
        "--device", args.device,
        "--max_timesteps", str(args.max_timesteps)
    ]

    print("[INFO] Running:", " ".join(cmd))
    subprocess.check_call(cmd)

    print("[INFO] SUGAR embeddings extracted.\n")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--input_dir", required=False)
    parser.add_argument("--out_dir", default="tgn_output")
    parser.add_argument("--dataset", default="mywifi")

    parser.add_argument("--time_window", type=float, default=1.0)
    parser.add_argument("--save_prefix", default="wifi_run")

    parser.add_argument("--tgn_epochs", type=int, default=20)
    parser.add_argument("--sugar_epochs", type=int, default=5)
    parser.add_argument("--emb_dim", type=int, default=100)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--max_timesteps", type=int, default=500)

    parser.add_argument("--device", default="cpu")

    parser.add_argument("--use_combined_dataset", action="store_true")

    args = parser.parse_args()

    # -----------------------------
    # STEP 1 — preprocessing OR skip
    # -----------------------------
    if args.use_combined_dataset:
        print("\n[INFO] Skipping preprocessing — using combined dataset from data/ directory\n")
    else:
        if not args.input_dir:
            print("[ERROR] --input_dir is required unless --use_combined_dataset is used")
            sys.exit(1)

        run_preprocessing(args)
        copy_to_tgn(args)

    # -----------------------------
    # Training steps
    # -----------------------------
    run_tgn_training(args)
    run_sugar_training(args)
    run_sugar_extract(args)

    print("\n==============================")
    print(" FULL PIPELINE COMPLETED 🎉   ")
    print("==============================\n")


if __name__ == "__main__":
    main()
