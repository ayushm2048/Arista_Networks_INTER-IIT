from __future__ import annotations
import pandas as pd

SHORT_RETRY_LIMIT = 7
LONG_RETRY_LIMIT  = 4

EDGE_RSSI_MIN = -70.0
EDGE_RSSI_MAX = -65.0

def is_ap(name: str) -> bool:
    return isinstance(name, str) and name.upper().startswith("ACCESS_POINT")

def is_client(name: str) -> bool:
    return isinstance(name, str) and name.upper().startswith("WIRELESS_NODE")

def infer_direction(link_df: pd.DataFrame) -> pd.DataFrame:
    """Add a '_dir' column safely (without mutating original)."""
    df = link_df.copy(deep=True)
    if "_dir" in df.columns:
        return df
    if "Transmitter" not in df.columns:
        raise KeyError("Link_Packet_Log must contain 'Transmitter'")

    df["_dir"] = df["Transmitter"].apply(
        lambda tx: "downlink" if isinstance(tx, str) and tx.upper().startswith("ACCESS_POINT")
        else ("uplink" if isinstance(tx, str) and tx.upper().startswith("WIRELESS_NODE")
              else "unknown")
    )
    return df


# def edge_clients_from_radio(radio_df: pd.DataFrame) -> list[str]:
#     df = radio_df.copy()

#     per = (
#         df.groupby("Receiver Name")["Rx_Power(dBm)"]
#         .mean()
#         .reset_index()
#     )

#     # keep only wireless clients
#     per = per[per["Receiver Name"].apply(is_client)]

#     # bottom 20% RSSI are edge clients
#     threshold = per["Rx_Power(dBm)"].quantile(0.2)

#     return per[per["Rx_Power(dBm)"] <= threshold]["Receiver Name"].tolist()
def edge_clients_from_radio(radio_df: pd.DataFrame) -> dict[str, list[str]]:
    """
    Compute edge clients *per AP*.
    For each AP:
        - Consider only packets where AP is the Transmitter AND client is Receiver.
        - Compute mean RSSI per client.
        - Select clients in bottom 20% RSSI bucket for that AP.
    Returns:
        dict: { AP_name : [client1, client2, ...] }
    """
    df = radio_df.copy()

    required_cols = {"Transmitter Name", "Receiver Name", "Rx_Power(dBm)"}
    missing = required_cols - set(df.columns)
    if missing:
        raise KeyError(f"Radio log missing: {missing}")

    # Only AP → client links
    df = df[df["Transmitter Name"].apply(is_ap) &
            df["Receiver Name"].apply(is_client)]

    if df.empty:
        return {}

    per_ap_edge = {}

    # group by AP
    for ap, sub in df.groupby("Transmitter Name"):
        # mean RSSI per client for this AP
        per = (
            sub.groupby("Receiver Name")["Rx_Power(dBm)"]
            .mean()
            .reset_index()
        )

        if per.empty:
            per_ap_edge[ap] = []
            continue

        # Define edge = bottom 20% RSSI **per-AP**
        threshold = per["Rx_Power(dBm)"].quantile(0.2)

        edges = per[per["Rx_Power(dBm)"] <= threshold]["Receiver Name"].tolist()
        per_ap_edge[ap] = edges

    return per_ap_edge


def map_client_to_ap(link_df: pd.DataFrame) -> pd.DataFrame:
    link_df = infer_direction(link_df.copy())
    pairs = []
    for _, row in link_df.iterrows():
        tx, rx, d = row["Transmitter"], row["Receiver"], row["_dir"]
        if d == "downlink":
            ap, client = tx, rx
        elif d == "uplink":
            ap, client = rx, tx
        else:
            continue
        if is_ap(ap) and is_client(client):
            pairs.append((client, ap))
    return pd.DataFrame(pairs, columns=["Client", "AP"]).drop_duplicates()