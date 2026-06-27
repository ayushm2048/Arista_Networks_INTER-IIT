import torch
import torch.nn.functional as F


def info_nce_loss(local_pooled, global_vec, negative_globs, temperature=0.2):
    """
    local_pooled: (B, k, D)
    global_vec:   (B, D)
    negative_globs: (B, Nneg, D)
    """

    B, k, D = local_pooled.shape

    # mean local pooled => (B, D)
    pooled = local_pooled.mean(dim=1)   

    # positive similarities
    pos = torch.sum(pooled * global_vec, dim=-1) / temperature   # (B)

    # negative similarities (each sample has Nneg negatives)
    neg = torch.bmm(pooled.unsqueeze(1), negative_globs.transpose(1,2)).squeeze(1)  # (B, Nneg)
    neg = neg / temperature

    # logits = [positive | negatives]
    logits = torch.cat([pos.unsqueeze(1), neg], dim=1)   # (B, 1+Nneg)

    labels = torch.zeros(B, dtype=torch.long, device=local_pooled.device)

    loss = F.cross_entropy(logits, labels)

    return loss
