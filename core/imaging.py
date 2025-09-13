# core/imaging.py
import io
import os
from typing import List, Dict, Any

import torch
from PIL import Image
from core.modeling_biomedclip import BiomedClipForCheXpert

class ImagingModel:
    """
    Loads head-only BiomedCLIP checkpoint:
      {
        "repo": "<hf repo id>",
        "labels": [...],
        "head_state_dict": {"weight": <Tensor>, "bias": <Tensor>}
      }
    """
    def __init__(self, ckpt_path: str):
        if not os.path.exists(ckpt_path):
            raise FileNotFoundError(f"Checkpoint not found: {ckpt_path}")

        # device & top-k
        dev = os.getenv("CXR_DEVICE")
        if dev in ("cpu", "cuda"):
            self.device = torch.device(dev)
        else:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.top_k = int(os.getenv("CXR_TOPK", "6"))

        # load checkpoint
        payload = torch.load(ckpt_path, map_location="cpu")
        repo   = payload.get("repo") or payload.get("model_id") or payload.get("biomedclip_repo")
        labels = payload.get("labels")
        head_sd = payload.get("head_state_dict")

        if not repo:
            raise RuntimeError("Checkpoint missing 'repo'.")
        if not labels:
            raise RuntimeError("Checkpoint missing 'labels'.")
        if not isinstance(head_sd, dict) or ("weight" not in head_sd) or ("bias" not in head_sd):
            raise RuntimeError("Checkpoint missing 'head_state_dict' with 'weight' and 'bias'.")

        self.labels = list(labels)

        # build backbone + head skeleton
        self.model = BiomedClipForCheXpert(repo=repo, num_labels=len(self.labels), device=str(self.device))
        # load head weights EXACTLY as provided
        self.model.head.load_state_dict(head_sd, strict=True)
        self.model.eval()

    @torch.no_grad()
    def predict(self, img_bytes: bytes) -> List[Dict[str, Any]]:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        x = self.model.get_preprocess()(img).unsqueeze(0).to(self.model.device)
        logits = self.model(x)                                   # [1, C]
        probs  = torch.sigmoid(logits).squeeze(0).float().cpu()  # [C]
        vals, idxs = torch.topk(probs, k=min(self.top_k, len(self.labels)))
        return [{"label": self.labels[i], "score": float(p)} for p, i in zip(vals.tolist(), idxs.tolist())]

    def get_labels(self) -> List[str]:
        return list(self.labels)
