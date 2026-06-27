# sugar_model.py
import torch
import torch.nn as nn
import torch.nn.functional as F

class SubgraphPooler(nn.Module):
    """
    Trainable SUGAR subgraph pooling.
    Input:  H (N_ap, D)
    Output: pooled (k, D), attention (N_ap,)
    """

    def __init__(self, emb_dim=100, k=3):
        super().__init__()
        self.emb_dim = emb_dim
        self.k = k

        # score network
        self.scorer = nn.Sequential(
            nn.Linear(emb_dim, emb_dim),
            nn.ReLU(),
            nn.Linear(emb_dim, 1)
        )

    def forward(self, H):
        """
        H: (N_ap, D)
        Returns:
            pooled: (k, D)
            att:    (N_ap,)
        """
        scores = self.scorer(H).squeeze(-1)  # (N_ap,)
        att = torch.softmax(scores, dim=0)

        k = min(self.k, H.size(0))
        topk_idx = torch.topk(att, k=k, dim=0).indices

        pooled = H[topk_idx]  # (k, D)
        return pooled, att
