# import numpy as np
# import random
# import pandas as pd


# class Data:
#   def __init__(self, sources, destinations, timestamps, edge_idxs, labels):
#     self.sources = sources
#     self.destinations = destinations
#     self.timestamps = timestamps
#     self.edge_idxs = edge_idxs
#     self.labels = labels
#     self.n_interactions = len(sources)
#     self.unique_nodes = set(sources) | set(destinations)
#     self.n_unique_nodes = len(self.unique_nodes)


# def get_data_node_classification(dataset_name, use_validation=False):
#   ### Load data and train val test split
#   graph_df = pd.read_csv('./data/ml_{}.csv'.format(dataset_name))
#   edge_features = np.load('./data/ml_{}.npy'.format(dataset_name))
#   node_features = np.load('./data/ml_{}_node.npy'.format(dataset_name))

#   val_time, test_time = list(np.quantile(graph_df.ts, [0.70, 0.85]))

#   sources = graph_df.u.values
#   destinations = graph_df.i.values
#   edge_idxs = graph_df.idx.values
#   labels = graph_df.label.values
#   timestamps = graph_df.ts.values

#   random.seed(2020)

#   train_mask = timestamps <= val_time if use_validation else timestamps <= test_time
#   test_mask = timestamps > test_time
#   val_mask = np.logical_and(timestamps <= test_time, timestamps > val_time) if use_validation else test_mask

#   full_data = Data(sources, destinations, timestamps, edge_idxs, labels)

#   train_data = Data(sources[train_mask], destinations[train_mask], timestamps[train_mask],
#                     edge_idxs[train_mask], labels[train_mask])

#   val_data = Data(sources[val_mask], destinations[val_mask], timestamps[val_mask],
#                   edge_idxs[val_mask], labels[val_mask])

#   test_data = Data(sources[test_mask], destinations[test_mask], timestamps[test_mask],
#                    edge_idxs[test_mask], labels[test_mask])

#   return full_data, node_features, edge_features, train_data, val_data, test_data


# def get_data(dataset_name, different_new_nodes_between_val_and_test=False, randomize_features=False):
#   ### Load data and train val test split
#   graph_df = pd.read_csv('./data/ml_{}.csv'.format(dataset_name))
#   edge_features = np.load('./data/ml_{}.npy'.format(dataset_name))
#   node_features = np.load('./data/ml_{}_node.npy'.format(dataset_name)) 
    
#   if randomize_features:
#     node_features = np.random.rand(node_features.shape[0], node_features.shape[1])

#   val_time, test_time = list(np.quantile(graph_df.ts, [0.70, 0.85]))

#   sources = graph_df.u.values
#   destinations = graph_df.i.values
#   edge_idxs = graph_df.idx.values
#   labels = graph_df.label.values
#   timestamps = graph_df.ts.values

#   full_data = Data(sources, destinations, timestamps, edge_idxs, labels)

#   random.seed(2020)

#   node_set = set(sources) | set(destinations)
#   n_total_unique_nodes = len(node_set)

#   # Compute nodes which appear at test time
#   test_node_set = set(sources[timestamps > val_time]).union(
#     set(destinations[timestamps > val_time]))
#   # Sample nodes which we keep as new nodes (to test inductiveness), so than we have to remove all
#   # their edges from training
#   new_test_node_set = set(random.sample(test_node_set, int(0.1 * n_total_unique_nodes)))

#   # Mask saying for each source and destination whether they are new test nodes
#   new_test_source_mask = graph_df.u.map(lambda x: x in new_test_node_set).values
#   new_test_destination_mask = graph_df.i.map(lambda x: x in new_test_node_set).values

#   # Mask which is true for edges with both destination and source not being new test nodes (because
#   # we want to remove all edges involving any new test node)
#   observed_edges_mask = np.logical_and(~new_test_source_mask, ~new_test_destination_mask)

#   # For train we keep edges happening before the validation time which do not involve any new node
#   # used for inductiveness
#   train_mask = np.logical_and(timestamps <= val_time, observed_edges_mask)

#   train_data = Data(sources[train_mask], destinations[train_mask], timestamps[train_mask],
#                     edge_idxs[train_mask], labels[train_mask])

#   # define the new nodes sets for testing inductiveness of the model
#   train_node_set = set(train_data.sources).union(train_data.destinations)
#   assert len(train_node_set & new_test_node_set) == 0
#   new_node_set = node_set - train_node_set

#   val_mask = np.logical_and(timestamps <= test_time, timestamps > val_time)
#   test_mask = timestamps > test_time

#   if different_new_nodes_between_val_and_test:
#     n_new_nodes = len(new_test_node_set) // 2
#     val_new_node_set = set(list(new_test_node_set)[:n_new_nodes])
#     test_new_node_set = set(list(new_test_node_set)[n_new_nodes:])

#     edge_contains_new_val_node_mask = np.array(
#       [(a in val_new_node_set or b in val_new_node_set) for a, b in zip(sources, destinations)])
#     edge_contains_new_test_node_mask = np.array(
#       [(a in test_new_node_set or b in test_new_node_set) for a, b in zip(sources, destinations)])
#     new_node_val_mask = np.logical_and(val_mask, edge_contains_new_val_node_mask)
#     new_node_test_mask = np.logical_and(test_mask, edge_contains_new_test_node_mask)


#   else:
#     edge_contains_new_node_mask = np.array(
#       [(a in new_node_set or b in new_node_set) for a, b in zip(sources, destinations)])
#     new_node_val_mask = np.logical_and(val_mask, edge_contains_new_node_mask)
#     new_node_test_mask = np.logical_and(test_mask, edge_contains_new_node_mask)

#   # validation and test with all edges
#   val_data = Data(sources[val_mask], destinations[val_mask], timestamps[val_mask],
#                   edge_idxs[val_mask], labels[val_mask])

#   test_data = Data(sources[test_mask], destinations[test_mask], timestamps[test_mask],
#                    edge_idxs[test_mask], labels[test_mask])

#   # validation and test with edges that at least has one new node (not in training set)
#   new_node_val_data = Data(sources[new_node_val_mask], destinations[new_node_val_mask],
#                            timestamps[new_node_val_mask],
#                            edge_idxs[new_node_val_mask], labels[new_node_val_mask])

#   new_node_test_data = Data(sources[new_node_test_mask], destinations[new_node_test_mask],
#                             timestamps[new_node_test_mask], edge_idxs[new_node_test_mask],
#                             labels[new_node_test_mask])

#   print("The dataset has {} interactions, involving {} different nodes".format(full_data.n_interactions,
#                                                                       full_data.n_unique_nodes))
#   print("The training dataset has {} interactions, involving {} different nodes".format(
#     train_data.n_interactions, train_data.n_unique_nodes))
#   print("The validation dataset has {} interactions, involving {} different nodes".format(
#     val_data.n_interactions, val_data.n_unique_nodes))
#   print("The test dataset has {} interactions, involving {} different nodes".format(
#     test_data.n_interactions, test_data.n_unique_nodes))
#   print("The new node validation dataset has {} interactions, involving {} different nodes".format(
#     new_node_val_data.n_interactions, new_node_val_data.n_unique_nodes))
#   print("The new node test dataset has {} interactions, involving {} different nodes".format(
#     new_node_test_data.n_interactions, new_node_test_data.n_unique_nodes))
#   print("{} nodes were used for the inductive testing, i.e. are never seen during training".format(
#     len(new_test_node_set)))

#   return node_features, edge_features, full_data, train_data, val_data, test_data, \
#          new_node_val_data, new_node_test_data


# def compute_time_statistics(sources, destinations, timestamps):
#   last_timestamp_sources = dict()
#   last_timestamp_dst = dict()
#   all_timediffs_src = []
#   all_timediffs_dst = []
#   for k in range(len(sources)):
#     source_id = sources[k]
#     dest_id = destinations[k]
#     c_timestamp = timestamps[k]
#     if source_id not in last_timestamp_sources.keys():
#       last_timestamp_sources[source_id] = 0
#     if dest_id not in last_timestamp_dst.keys():
#       last_timestamp_dst[dest_id] = 0
#     all_timediffs_src.append(c_timestamp - last_timestamp_sources[source_id])
#     all_timediffs_dst.append(c_timestamp - last_timestamp_dst[dest_id])
#     last_timestamp_sources[source_id] = c_timestamp
#     last_timestamp_dst[dest_id] = c_timestamp
#   assert len(all_timediffs_src) == len(sources)
#   assert len(all_timediffs_dst) == len(sources)
#   mean_time_shift_src = np.mean(all_timediffs_src)
#   std_time_shift_src = np.std(all_timediffs_src)
#   mean_time_shift_dst = np.mean(all_timediffs_dst)
#   std_time_shift_dst = np.std(all_timediffs_dst)

#   return mean_time_shift_src, std_time_shift_src, mean_time_shift_dst, std_time_shift_dst

# utils/data_processing.py
# Patched get_data() to load combined CSV ml_<dataset>.csv
# (Replaces the original get_data behavior that required .npy files.)
#
# Based on original file in your repo. :contentReference[oaicite:3]{index=3}

import numpy as np
import pandas as pd
import random

class Data:
    def __init__(self, sources, destinations, timestamps, edge_idxs=None, labels=None):
        self.sources = sources
        self.destinations = destinations
        self.timestamps = timestamps
        self.edge_idxs = edge_idxs
        self.labels = labels
        self.n_interactions = len(sources)
        self.unique_nodes = set(sources) | set(destinations)
        self.n_unique_nodes = len(self.unique_nodes)

def compute_time_statistics(sources, destinations, timestamps):
    last_timestamp_sources = dict()
    last_timestamp_dst = dict()
    all_timediffs_src = []
    all_timediffs_dst = []
    for k in range(len(sources)):
        source_id = sources[k]
        dest_id = destinations[k]
        c_timestamp = timestamps[k]
        if source_id not in last_timestamp_sources:
            last_timestamp_sources[source_id] = 0
        if dest_id not in last_timestamp_dst:
            last_timestamp_dst[dest_id] = 0
        all_timediffs_src.append(c_timestamp - last_timestamp_sources[source_id])
        all_timediffs_dst.append(c_timestamp - last_timestamp_dst[dest_id])
        last_timestamp_sources[source_id] = c_timestamp
        last_timestamp_dst[dest_id] = c_timestamp
    assert len(all_timediffs_src) == len(sources)
    assert len(all_timediffs_dst) == len(sources)
    mean_time_shift_src = np.mean(all_timediffs_src)
    std_time_shift_src = np.std(all_timediffs_src)
    mean_time_shift_dst = np.mean(all_timediffs_dst)
    std_time_shift_dst = np.std(all_timediffs_dst)

    return mean_time_shift_src, std_time_shift_src, mean_time_shift_dst, std_time_shift_dst

def get_data(dataset_name, val_ratio=0.15, test_ratio=0.15, randomize_features=False):
    """
    Load data from ./data/ml_<dataset_name>.csv
    Returns:
      dict with:
        src, dst, ts, features, train_mask, val_mask, test_mask, feature_dim
    Assumptions:
      - CSV columns: src,dst,timestamp,<feature_1>,...,<feature_K>
      - src/dst are integers (node ids matching id_map.json)
    """
    csv_path = f'./data/ml_{dataset_name}.csv'
    print(f"[data_processing] Loading CSV: {csv_path}")
    df = pd.read_csv(csv_path)

    # required columns
    if not set(['src','dst','timestamp']).issubset(set(df.columns)):
        raise RuntimeError("CSV must contain 'src','dst','timestamp' columns")

    df = df.sort_values('timestamp').reset_index(drop=True)

    src = df['src'].astype(np.int64).values
    dst = df['dst'].astype(np.int64).values
    ts  = df['timestamp'].astype(np.float64).values

    # feature columns = all other columns
    feature_cols = [c for c in df.columns if c not in ('src','dst','timestamp')]
    features = df[feature_cols].astype(np.float32).values

    if randomize_features:
        rng = np.random.RandomState(2020)
        features = rng.rand(*features.shape).astype(np.float32)

    # train/val/test time split by quantiles
    val_time = np.quantile(ts, 1 - (val_ratio + test_ratio))
    test_time = np.quantile(ts, 1 - test_ratio)

    num_events = len(ts)
    train_mask = ts <= val_time
    val_mask = np.logical_and(ts > val_time, ts <= test_time)
    test_mask = ts > test_time

    print(f"[data_processing] Events: {num_events}, feature_dim: {features.shape[1]}")
    print(f"[data_processing] Train/Val/Test masks: {train_mask.sum()}/{val_mask.sum()}/{test_mask.sum()}")

    return {
        "src": src,
        "dst": dst,
        "ts": ts,
        "features": features,
        "train_mask": train_mask,
        "val_mask": val_mask,
        "test_mask": test_mask,
        "feature_cols": feature_cols,
        "feature_dim": features.shape[1]
    }
