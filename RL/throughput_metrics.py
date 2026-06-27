from helpers import infer_direction, edge_clients_from_radio,pd
import os
OUTPUT_DIR = "preprocessing_outputs"
def save_metric(df: pd.DataFrame, name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    if df.empty:
        print(f"[WARN] {name}: no data")
        return

    # Make a safe copy to avoid SettingWithCopyWarning
    df = df.copy()
    df.loc[:, "Metric"] = name

    for col in ["AP", "Client", "Throughput_Mbps"]:
        if col not in df.columns:
            df[col] = "" if col in ("AP", "Client") else 0.0

    df = df[["Metric", "AP", "Client", "Throughput_Mbps"]]

    path = os.path.join(OUTPUT_DIR, f"{name}.csv")
    df.to_csv(path, index=False)
    print(f"[INFO] Saved: {path}")



def _per_client_downlink_tput(link_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-client downlink throughput using:
       throughput = sum(packet_size_bytes * 8) / SIMULATION_TIME_MS

    Drops rows where throughput < THROUGHPUT_THRESHOLD.
    """

    # Hardcoded constants (modify as needed)
    SIMULATION_TIME_MS = 10000        # total simulation time in milliseconds
    THROUGHPUT_THRESHOLD = 0.05     # minimum throughput in Mbps allowed

    required_cols = {"Transmitter", "Receiver", "Packet Size(Bytes)"}
    missing = required_cols - set(link_df.columns)
    if missing:
        raise KeyError(f"Link log missing required columns: {missing}")

    df = link_df.copy(deep=True)
    df = infer_direction(df)

    # keep only downlink packets
    down = df[df["_dir"] == "downlink"].copy()
    if down.empty:
        return pd.DataFrame(columns=["AP", "Client", "Throughput_Mbps"])

    # Compute throughput per AP–Client:
    # sum(packet_bytes*8) / simulation_time(ms)
    grouped = (
        down.groupby(["Transmitter", "Receiver"], as_index=False)["Packet Size(Bytes)"]
        .sum()
        .rename(columns={"Packet Size(Bytes)": "TotalBytes"})
    )

    # Convert Bytes → bits
    grouped["TotalBits"] = grouped["TotalBytes"] * 8

    # Convert bits/ms → Mbps   (because 1 Mbps = 10^6 bps = 1000 bits/ms)
    grouped["Throughput_Mbps"] = (grouped["TotalBits"] / SIMULATION_TIME_MS) / 1000

    grouped = grouped.rename(columns={
        "Transmitter": "AP",
        "Receiver": "Client"
    })
    save_metric(grouped[["AP", "Client", "Throughput_Mbps"]],"pair_wise_downlink")
    # Apply threshold filter
    grouped = grouped[grouped["Throughput_Mbps"] >= THROUGHPUT_THRESHOLD]


    # Round final numbers
    grouped["Throughput_Mbps"] = grouped["Throughput_Mbps"].round(4)
    #save_metric(grouped[["AP", "Client", "Throughput_Mbps"]],"pair_wise_downlink")
    # Keep only required output columns
    return grouped[["AP", "Client", "Throughput_Mbps"]]



def median_downlink_throughput_edge(radio_df: pd.DataFrame, link_df: pd.DataFrame) -> pd.DataFrame:
    """Per-AP median downlink throughput for edge clients (RSSI -70 to -65)."""
    radio_df = radio_df.copy(deep=True)
    link_df = link_df.copy(deep=True)

    edge_map = edge_clients_from_radio(radio_df)   # dict: AP → list of edge clients
    per_client = _per_client_downlink_tput(link_df)
    # print(edge_map)

    if per_client.empty or not edge_map:
        return pd.DataFrame(columns=["Metric", "AP", "Client", "Value"])

    rows = []
    for ap, edges in edge_map.items():
        if not edges:
            continue
    # filter throughput df
        sub = per_client[(per_client["AP"] == ap) &
            (per_client["Client"].isin(edges))]

        if sub.empty:
            continue

        val = sub["Throughput_Mbps"].median()
        rows.append({"Metric": "median_downlink_throughput_edge",
            "AP": ap,
            "Client": "nil",
            "Value": round(val, 4)})

    return pd.DataFrame(rows)


    # per_client_edge = per_client[per_client["Client"].isin(edge_clients)]
    # if per_client_edge.empty:
    #     return pd.DataFrame(columns=["Metric", "AP", "Client", "Value"])

    # per_ap = (
    #     per_client_edge.groupby("AP", as_index=False)["Throughput_Mbps"]
    #     .median()
    #     .rename(columns={"Throughput_Mbps": "Value"})
    # )
    # per_ap["Metric"] = "median_downlink_throughput_edge"
    # per_ap["Client"] = "nil"
    # per_ap["Value"] = per_ap["Value"].round(4)
    # return per_ap[["Metric", "AP", "Client", "Value"]]


def p50_throughput_all_clients(link_df: pd.DataFrame) -> pd.DataFrame:
    """Per-AP P50 (median) throughput across all clients."""
    link_df = link_df.copy(deep=True)
    per_client = _per_client_downlink_tput(link_df)
    if per_client.empty:
        return pd.DataFrame(columns=["Metric", "AP", "Client", "Value"])

    per_ap = (
        per_client.groupby("AP", as_index=False)["Throughput_Mbps"]
        .median()
        .rename(columns={"Throughput_Mbps": "Value"})
    )
    per_ap["Metric"] = "p50_throughput_all_clients"
    per_ap["Client"] = "nil"
    per_ap["Value"] = per_ap["Value"].round(4)
    return per_ap[["Metric", "AP", "Client", "Value"]]

