from __future__ import annotations
import pandas as pd
import os
from helpers import map_client_to_ap, infer_direction, SHORT_RETRY_LIMIT,is_client,is_ap
OUTPUT_DIR = "preprocessing_outputs"
OUTPUT_DIR = "preprocessing_outputs"

def save_metric(df: pd.DataFrame, name: str):
    """Flexible saver — works for KPI tables AND raw logs like link_df."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if df is None or df.empty:
        print(f"[WARN] {name}: no data")
        return

    df = df.copy()   # avoid SettingWithCopyWarning

    # -------------------------------
    # CASE 1: KPI-style dataframe
    # -------------------------------
    required_cols = {"Metric", "AP", "Client", "Value"}

    if required_cols.issubset(df.columns):
        # reorder columns
        df = df[["Metric", "AP", "Client", "Value"]]
        path = os.path.join(OUTPUT_DIR, f"{name}.csv")
        df.to_csv(path, index=False)
        print(f"[INFO] Saved KPI table: {path}")
        return

    # -------------------------------
    # CASE 2: Raw / arbitrary dataframe (e.g., link_df)
    # -------------------------------
    path = os.path.join(OUTPUT_DIR, f"{name}.csv")
    df.to_csv(path, index=False)
    print(f"[INFO] Saved RAW table: {path}")


def _per_device_retry(backoff_df: pd.DataFrame) -> pd.DataFrame:
    req = {"Device Name","RetryCount"}
    missing = req - set(backoff_df.columns)
    if missing:
        raise KeyError(f"Backoff log missing columns: {missing}")
    return (backoff_df.groupby("Device Name")["RetryCount"].mean()
            .reset_index().rename(columns={"Device Name":"Client","RetryCount":"Retry_Rate"}))

def p95_retry_rate(backoff_df: pd.DataFrame, link_df: pd.DataFrame) -> pd.DataFrame:
    per_dev = _per_device_retry(backoff_df)
    pairs = map_client_to_ap(link_df)
    df = per_dev.merge(pairs, on="Client", how="inner")
    if df.empty:
        return pd.DataFrame(columns=["Metric","AP","Client","Value"])
    per_ap = df.groupby("AP")["Retry_Rate"].quantile(0.95).reset_index().rename(columns={"Retry_Rate":"Value"})
    per_ap["Metric"] = "p95_retry_rate"
    per_ap["Client"] = "nil"
    per_ap["Value"] = per_ap["Value"].round(4)
    return per_ap[["Metric","AP","Client","Value"]]

def uplink_per_p95(backoff_df: pd.DataFrame, link_df: pd.DataFrame) -> pd.DataFrame:
    """
    Optimized uplink p95 PER per AP, without merge().
    Each (AP, PacketId) has exactly one client in link_df,
    so build a mapping and inject 'AP' column directly in backoff_df.
    """

    # ------------------------------------------------------------
    # 1. Identify uplink packets
    # ------------------------------------------------------------
    link_df = infer_direction(link_df.copy())
    uplink = link_df[link_df["_dir"] == "uplink"][["Packet Id", "Transmitter", "Receiver"]]

    if uplink.empty:
        print("[WARN] uplink_per_p95: no uplink packets found")
        return pd.DataFrame(columns=["Metric","AP","Client","Value"])

    # ------------------------------------------------------------
    # 2. Build mapping: (Client, PacketId) -> AP
    #    Transmitter = client (wireless_node)
    #    Receiver    = AP
    # ------------------------------------------------------------
    uplink["key"] = list(zip(uplink["Transmitter"], uplink["Packet Id"]))
    map_client_pid_to_ap = dict(zip(uplink["key"], uplink["Receiver"]))

    # ------------------------------------------------------------
    # 3. Add AP column to backoff_df using the mapping
    # ------------------------------------------------------------
    back = backoff_df.copy()
    back["key"] = list(zip(back["Device Name"], back["PacketId"]))
    back["AP"] = back["key"].map(map_client_pid_to_ap)

    # Keep only rows where mapping succeeded (i.e., real uplink packets)
    back = back.dropna(subset=["AP"])

    if back.empty:
        print("[WARN] uplink_per_p95: no backoff rows matched uplink mapping")
        return pd.DataFrame(columns=["Metric","AP","Client","Value"])

    # ------------------------------------------------------------
    # 4. Retry rate computation
    # ------------------------------------------------------------
    
    back["Retry_Rate"] = back["RetryCount"].astype(float)
    back = back.dropna(subset=["Retry_Rate"])

    # ------------------------------------------------------------
    # 5. Compute average retry rate per AP–Client
    # ------------------------------------------------------------
    per_client = (
        back.groupby(["AP", "Device Name"])["Retry_Rate"]
        .mean()
        .reset_index()
        .rename(columns={
            "Device Name": "Client",
            "Retry_Rate": "AvgRetry"
        })
    )

    if per_client.empty:
        return pd.DataFrame(columns=["Metric","AP","Client","Value"])

    # ------------------------------------------------------------
    # 6. Compute p95 AvgRetry per AP
    # ------------------------------------------------------------
    per_ap = (
        per_client.groupby("AP")["AvgRetry"]
        .quantile(0.95)
        .reset_index()
        .rename(columns={"AvgRetry": "Value"})
    )

    # ------------------------------------------------------------
    # 7. Formatting
    # ------------------------------------------------------------
    per_ap["Metric"] = "uplink_per_p95"
    per_ap["Client"] = "nil"
    per_ap["Value"] = per_ap["Value"].round(4)

    return per_ap[["Metric", "AP", "Client", "Value"]]


def retry_asymmetry(backoff_df: pd.DataFrame, link_df: pd.DataFrame) -> pd.DataFrame:
    per_dev = _per_device_retry(backoff_df)
    pairs = map_client_to_ap(link_df)

    ap_means = (
        backoff_df[backoff_df["Device Name"].apply(
            lambda x: isinstance(x, str) and x.upper().startswith("ACCESS_POINT")
        )]
        .groupby("Device Name")["RetryCount"].mean().reset_index()
        .rename(columns={"Device Name": "AP", "RetryCount": "AP_Retry"})
    )

    # Merge pairs with per-device and AP retry means
    df = pairs.merge(per_dev, on="Client", how="left").merge(ap_means, on="AP", how="left")

    # Drop rows with missing client retry rates
    df = df.dropna(subset=["Retry_Rate"])

    # Fill missing AP retry rates with 0
    df["AP_Retry"] = df["AP_Retry"].fillna(0.0)

    # Compute asymmetry and round
    df["Value"] = (df["Retry_Rate"] - df["AP_Retry"]).round(4)
    df["Metric"] = "retry_asymmetry"

    return df[["Metric", "AP", "Client", "Value"]]


def drop_rate(backoff_df: pd.DataFrame, link_df: pd.DataFrame) -> pd.DataFrame:
    pairs = map_client_to_ap(link_df)
    rows = []
    for _, row in pairs.iterrows():
        client, ap = row["Client"], row["AP"]
        sub = backoff_df[backoff_df["Device Name"] == client]
        total = len(sub)
        if total == 0:
            val = 0.0
        else:
            val = float((sub["RetryCount"] >= SHORT_RETRY_LIMIT).sum()) / total
        rows.append({"Metric":"drop_rate", "AP": ap, "Client": client, "Value": round(val,4)})
    return pd.DataFrame(rows)