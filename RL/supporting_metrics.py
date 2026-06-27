import os
import pandas as pd


def compute_average(df: pd.DataFrame, column: str, metric_name: str) -> pd.DataFrame:
    """
    Compute per-device (Receiver) average of a given column (RSSI or SNR).
    Output format:
        Metric, AP, Client, Value
    """

    results = []

    # ---- 1. Access Points ----
    ap_rows = df[df["Receiver Name"].str.upper().str.startswith("ACCESS_POINT")]
    if not ap_rows.empty:
        ap_avg = ap_rows.groupby("Receiver Name")[column].mean().reset_index()

        for _, row in ap_avg.iterrows():
            results.append({
                "Metric": metric_name,
                "AP": row["Receiver Name"],
                "Client": "nil",
                "Value": round(row[column], 4)
            })

    # ---- 2. Wireless Clients ----
    client_rows = df[df["Receiver Name"].str.upper().str.startswith("WIRELESS_NODE")]
    if not client_rows.empty:
        client_avg = client_rows.groupby("Receiver Name")[column].mean().reset_index()

        for _, row in client_avg.iterrows():
            results.append({
                "Metric": metric_name,
                "AP": "nil",
                "Client": row["Receiver Name"],
                "Value": round(row[column], 4)
            })

    return pd.DataFrame(results)


def save_supporting_metrics(radio_log_path: str, output_dir: str = "preprocessing_outputs"):
    """
    Generates:
       - metric_avg_rssi.csv
       - metric_avg_snr.csv
    """

    if not os.path.exists(radio_log_path):
        raise FileNotFoundError(f"[ERROR] Radio log not found: {radio_log_path}")

    os.makedirs(output_dir, exist_ok=True)

    df = pd.read_csv(radio_log_path)

    # Required columns
    required = {"Receiver Name", "Rx_Power(dBm)", "SNR(dB)"}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"[ERROR] Missing columns in radio log: {missing}")

    # ---- Compute metrics ----
    df_rssi = compute_average(df, "Rx_Power(dBm)", "avg_rssi")
    df_snr  = compute_average(df, "SNR(dB)",         "avg_snr")

    # ---- Save files ----
    out_rssi = os.path.join(output_dir, "metric_avg_rssi.csv")
    out_snr  = os.path.join(output_dir, "metric_avg_snr.csv")

    df_rssi.to_csv(out_rssi, index=False)
    df_snr.to_csv(out_snr, index=False)

    print(f"[INFO] Saved: {out_rssi}")
    print(f"[INFO] Saved: {out_snr}")

    return out_rssi, out_snr


# CLI support
# if __name__ == "__main__":
#     import argparse

#     parser = argparse.ArgumentParser(description="Generate RSSI + SNR supporting metrics.")
#     parser.add_argument("--radio", required=True, help="Path to radio measurement log CSV")
#     parser.add_argument("--output", default="preprocessing_outputs", help="Output directory")

#     args = parser.parse_args()
#     save_supporting_metrics(args.radio, args.output)
