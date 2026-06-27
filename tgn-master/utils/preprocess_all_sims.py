# #!/usr/bin/env python3
# """
# preprocess_all_sims.py
# Works with logs named like:

#     step_0_Application_Packet_Log.csv
#     step_0_Buffer_Occupancy_Log.csv
#     step_0_IEEE_802_11_Radio_Measurements_Log.csv
#     step_0_IEEE802_11_Backofflog.csv
#     step_0_Link_Packet_Log.csv

# Creates per-simulation temp folders with RENAMED logs:
#     Application_Packet_Log.csv
#     Buffer_Occupancy_Log.csv
#     Radio_Measurements_Log.csv
#     Backoff_Log.csv
#     Link_Packet_Log.csv

# Runs preprocess_netsim_to_tgn.py on each, then merges all outputs.
# """

# import argparse
# import shutil
# from pathlib import Path
# import subprocess
# import sys
# import re
# import pandas as pd
# import json


# # Mapping from your filenames → expected preprocess names
# RENAME_MAP = {
#     "Application_Packet_Log": "Application_Packet_Log.csv",
#     "Buffer_Occupancy_Log": "Buffer_Occupancy_Log.csv",
#     "IEEE_802_11_Radio_Measurements_Log": "IEEE_802_11_Radio_Measurements_Log.csv",
#     "Link_Packet_Log": "Link_Packet_Log.csv",
#     "IEEE802_11_Backofflog": "IEEE802_11_Backofflog.csv"   # ← FIX
# }



# def group_by_simulation(log_dir):
#     pattern = re.compile(r"step_(\d+)_")
#     groups = {}

#     for f in Path(log_dir).glob("*.csv"):
#         m = pattern.match(f.name)
#         if not m:
#             continue
#         sim_id = int(m.group(1))
#         groups.setdefault(sim_id, []).append(f)

#     return groups


# def resolve_target_name(src_file):
#     """Given: step_0_IEEE802_11_Backofflog.csv → Backoff_Log.csv"""
#     name = src_file.stem  # remove .csv
#     # strip "step_0_" prefix
#     parts = name.split("_", 2)  # ["step", "0", "Application_Packet_Log"]
#     core = parts[-1]            # Application_Packet_Log

#     for key in RENAME_MAP:
#         if key in core:
#             return RENAME_MAP[key]

#     raise ValueError(f"Could not map file {src_file.name} to known log type.")


# def run_preprocess_single_sim(sim_id, files, temp_root):
#     sim_temp = temp_root / f"sim_{sim_id}"
#     sim_temp.mkdir(parents=True, exist_ok=True)

#     # Copy + rename logs
#     for f in files:
#         target_name = resolve_target_name(f)
#         shutil.copy(f, sim_temp / target_name)

#     out_csv = sim_temp / f"{sim_id}.csv"

#     cmd = [
#         sys.executable,
#         "utils/preprocess_netsim_to_tgn.py",
#         "--input_dir", str(sim_temp),
#         "--out_dir", str(sim_temp),
#         "--time_window", "0.1",
#         "--output", out_csv.name
#     ]

#     print(f"[SIM {sim_id}] Running:", " ".join(cmd))
#     subprocess.check_call(cmd)

#     return out_csv, sim_temp / "id_map.json"


# def main():
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--input_dir", required=True)
#     parser.add_argument("--dataset", required=True)
#     args = parser.parse_args()

#     log_dir = Path(args.input_dir)
#     temp_root = Path("preprocess_temp")
#     temp_root.mkdir(exist_ok=True)

#     groups = group_by_simulation(log_dir)
#     print(f"[INFO] Found {len(groups)} simulations.")

#     Path("data").mkdir(exist_ok=True)
#     all_csvs = []
#     copied_map = False

#     for sim_id, files in sorted(groups.items()):
#         out_csv, idmap_path = run_preprocess_single_sim(sim_id, files, temp_root)
#         all_csvs.append(out_csv)

#         if not copied_map:
#             shutil.copy(idmap_path, f"data/{args.dataset}_id_map.json")
#             copied_map = True

#     print("[INFO] Concatenating outputs...")
#     df = pd.concat([pd.read_csv(c) for c in all_csvs], ignore_index=True)
#     df.to_csv(f"data/ml_{args.dataset}.csv", index=False)

#     print("[DONE] Combined dataset created:")
#     print(f" → data/ml_{args.dataset}.csv")
#     print(f" → data/{args.dataset}_id_map.json")


# if __name__ == "__main__":
#     main()
#!/usr/bin/env python3
import argparse
from pathlib import Path
import shutil
import subprocess
import pandas as pd
import multiprocessing as mp
import sys
import re

# ---------------------------------------------------------
# Correct mapping from YOUR input filenames to expected ones
# ---------------------------------------------------------
RENAME_MAP = {
    "Application_Packet_Log": "Application_Packet_Log.csv",
    "Buffer_Occupancy_Log": "Buffer_Occupancy_Log.csv",
    "IEEE_802_11_Radio_Measurements_Log": "IEEE_802_11_Radio_Measurements_Log.csv",
    "Link_Packet_Log": "Link_Packet_Log.csv",
    "IEEE802_11_Backofflog": "IEEE802_11_Backofflog.csv",
}

# ---------------------------------------------------------
# STEP 1 — Group files by simulation index
# ---------------------------------------------------------
def find_simulations(input_dir: Path):
    sims = {}
    pattern = re.compile(r"step_(\d+)_")

    for f in input_dir.glob("*.csv"):
        m = pattern.match(f.name)
        if not m:
            continue
        sim_id = int(m.group(1))
        sims.setdefault(sim_id, []).append(f)

    # -------------------------
    # FILTER: keep only simulations having all required logs
    # -------------------------
    REQUIRED_KEYS = [
        "Application_Packet_Log",
        "Buffer_Occupancy_Log",
        "IEEE_802_11_Radio_Measurements_Log",
        "Link_Packet_Log",
        "IEEE802_11_Backofflog"
    ]

    valid_sims = {}
    for sim_id, files in sims.items():
        names = [f.name for f in files]
        ok = True
        for key in REQUIRED_KEYS:
            if not any(key in n for n in names):
                ok = False
                break
        if ok:
            valid_sims[sim_id] = files
        else:
            print(f"[SKIP] step_{sim_id}: missing logs → skipping")

    return valid_sims


# ---------------------------------------------------------
# STEP 2 — Map step_* file → expected NetSim filename
# ---------------------------------------------------------
def resolve_target_name(src_file: Path):
    # remove prefix: step_2_Application_Packet_Log → Application_Packet_Log
    parts = src_file.stem.split("_", 2)
    if len(parts) < 3:
        raise ValueError(f"Unexpected filename format: {src_file.name}")
    name = parts[2]

    for key in RENAME_MAP:
        if key in name:
            return RENAME_MAP[key]

    raise ValueError(f"Unknown file type: {src_file.name}")


# ---------------------------------------------------------
# STEP 3 — Preprocess a single simulation
# ---------------------------------------------------------
def run_preprocess_single_sim(sim_id, files, temp_root):
    sim_dir = temp_root / f"sim_{sim_id}"
    # clear old folder if exists to avoid stale files
    if sim_dir.exists():
        shutil.rmtree(sim_dir)
    sim_dir.mkdir(parents=True, exist_ok=True)

    # Copy & rename logs
    for f in files:
        target = resolve_target_name(f)
        shutil.copy(f, sim_dir / target)

    out_csv = sim_dir / f"{sim_id}.csv"

    cmd = [
        sys.executable,
        "utils/preprocess_netsim_to_tgn.py",
        "--input_dir", str(sim_dir),
        "--out_dir", str(sim_dir),
        "--time_window", "0.1",
        "--output", f"{sim_id}.csv"
    ]

    print(f"[SIM {sim_id}] Running:", " ".join(cmd))
    subprocess.check_call(cmd)

    return out_csv, sim_dir / "id_map.json"


# ---------------------------------------------------------
# STEP 4 — Merge all per-simulation outputs (fast concat)
# ---------------------------------------------------------
def merge_all_preprocessed(temp_root, dataset):
    print("\n[INFO] Preprocessing complete. Merging results...")

    # ONLY include sim_X/<sim_id>.csv (processed output)
    csv_files = []
    for sim_dir in sorted(temp_root.glob("sim_*")):
        sim_id = sim_dir.name.split("_")[1]
        tgn_csv = sim_dir / f"{sim_id}.csv"
        if tgn_csv.exists():
            csv_files.append(tgn_csv)

    print(f"[INFO] Merging {len(csv_files)} processed TGN CSV files...")

    out_dir = Path("data")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"ml_{dataset}.csv"

    if len(csv_files) == 0:
        print("[ERR] No processed CSVs found.")
        return

    # Write header from FIRST processed CSV
    with open(out_path, "w", encoding="utf-8") as outf:
        with open(csv_files[0], "r", encoding="utf-8") as first:
            header = first.readline()
            outf.write(header)

    # Append data from all other processed CSVs
    for f in csv_files:
        print(f"[MERGE] appending {f} ...")
        with open(out_path, "a", encoding="utf-8") as outf:
            with open(f, "r", encoding="utf-8") as inf:
                next(inf)  # skip header
                shutil.copyfileobj(inf, outf)

    print(f"[DONE] Final merged CSV → {out_path}")

# ---------------------------------------------------------
# STEP 5 — Worker wrapper for multiprocessing
# ---------------------------------------------------------
def worker_process_single(args):
    sim_id, files, temp_root = args
    try:
        run_preprocess_single_sim(sim_id, files, temp_root)
        return sim_id, True, None
    except Exception as e:
        return sim_id, False, str(e)


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    inp = Path(args.input_dir)
    if not inp.exists():
        print(f"[ERROR] input_dir not found: {inp}")
        sys.exit(1)

    temp_root = Path("preprocess_temp")
    # clear stale temp folder to avoid merging old csvs
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(exist_ok=True)

    sims = find_simulations(inp)
    print(f"[INFO] Found {len(sims)} simulations.")

    jobs = [(sid, files, temp_root) for sid, files in sims.items()]

    print(f"[INFO] Starting parallel preprocessing using {args.workers} workers…")
    with mp.Pool(args.workers) as pool:
        results = pool.map(worker_process_single, jobs)

    for sid, ok, err in results:
        if not ok:
            print(f"[ERR] Simulation {sid} failed → {err}")

    print("\n[INFO] Preprocessing complete. Merging results...")
    merge_all_preprocessed(temp_root, args.dataset)


if __name__ == "__main__":
    main()
