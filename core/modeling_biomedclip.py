import torch
import torch.nn as nn
import open_clip

DEFAULT_LABELS = [
    "No Finding","Enlarged Cardiomediastinum","Cardiomegaly","Lung Opacity",
    "Lung Lesion","Edema","Consolidation","Pneumonia","Atelectasis",
    "Pneumothorax","Pleural Effusion","Pleural Other","Fracture","Support Devices"
]

class BiomedClipForCheXpert(nn.Module):
    """
    OpenCLIP BiomedCLIP visual tower (ViT-B/16) + linear head for multi-label CheXpert.
    Backbone is frozen; only the head trains (head-only fine-tune).
    """
    def __init__(self, repo: str, num_labels: int, device: str = None):
        super().__init__()
        self.repo = repo
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))

        # ✅ Correct loader for BiomedCLIP HF repo (your open_clip expects this form)
        # Returns (model, preprocess) or (model, preprocess, meta) depending on version.
        ret = open_clip.create_model_from_pretrained(f"hf-hub:{self.repo}")
        if isinstance(ret, tuple):
            if len(ret) >= 2:
                self.backbone, self.preprocess = ret[0], ret[1]
            else:
                self.backbone, self.preprocess = ret[0], None
        else:
            self.backbone, self.preprocess = ret, None

        # Derive feature dim robustly
        feat_dim = getattr(getattr(self.backbone, "visual", None), "output_dim", None)
        if feat_dim is None:
            # fallback for older variants
            feat_dim = getattr(self.backbone, "embed_dim", None)
        if feat_dim is None:
            # last-resort: dummy forward
            with torch.no_grad():
                dummy = torch.randn(1, 3, 224, 224)
                feats = self.backbone.encode_image(dummy)
                feat_dim = feats.shape[-1]

        # Linear head for CheXpert labels
        self.head = nn.Linear(feat_dim, num_labels)

        # Freeze backbone (head-only training)
        for p in self.backbone.parameters():
            p.requires_grad = False
        self.backbone.eval()

        # Move modules to device
        self.backbone.to(self.device)
        self.head.to(self.device)

    @torch.no_grad()
    def encode_images(self, x: torch.Tensor) -> torch.Tensor:
        return self.backbone.encode_image(x)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # keep everything on the same device
        x = x.to(self.device, non_blocking=True)
        with torch.no_grad():
            feats = self.encode_images(x)      # [B, D]
        logits = self.head(feats)              # [B, C]
        return logits

    def parameters_to_optimize(self):
        return self.head.parameters()

    def get_preprocess(self):
        return self.preprocess
import torch
import torch.nn as nn
import open_clip

DEFAULT_LABELS = [
    "No Finding","Enlarged Cardiomediastinum","Cardiomegaly","Lung Opacity",
    "Lung Lesion","Edema","Consolidation","Pneumonia","Atelectasis",
    "Pneumothorax","Pleural Effusion","Pleural Other","Fracture","Support Devices"
]

class BiomedClipForCheXpert(nn.Module):
    """
    OpenCLIP BiomedCLIP visual tower (ViT-B/16) + linear head for multi-label CheXpert.
    Backbone is frozen; only the head trains (head-only fine-tune).
    """
    def __init__(self, repo: str, num_labels: int, device: str = None):
        super().__init__()
        self.repo = repo
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))

        # ✅ Correct loader for BiomedCLIP HF repo (your open_clip expects this form)
        # Returns (model, preprocess) or (model, preprocess, meta) depending on version.
        ret = open_clip.create_model_from_pretrained(f"hf-hub:{self.repo}")
        if isinstance(ret, tuple):
            if len(ret) >= 2:
                self.backbone, self.preprocess = ret[0], ret[1]
            else:
                self.backbone, self.preprocess = ret[0], None
        else:
            self.backbone, self.preprocess = ret, None

        # Derive feature dim robustly
        feat_dim = getattr(getattr(self.backbone, "visual", None), "output_dim", None)
        if feat_dim is None:
            # fallback for older variants
            feat_dim = getattr(self.backbone, "embed_dim", None)
        if feat_dim is None:
            # last-resort: dummy forward
            with torch.no_grad():
                dummy = torch.randn(1, 3, 224, 224)
                feats = self.backbone.encode_image(dummy)
                feat_dim = feats.shape[-1]

        # Linear head for CheXpert labels
        self.head = nn.Linear(feat_dim, num_labels)

        # Freeze backbone (head-only training)
        for p in self.backbone.parameters():
            p.requires_grad = False
        self.backbone.eval()

        # Move modules to device
        self.backbone.to(self.device)
        self.head.to(self.device)

    @torch.no_grad()
    def encode_images(self, x: torch.Tensor) -> torch.Tensor:
        return self.backbone.encode_image(x)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # keep everything on the same device
        x = x.to(self.device, non_blocking=True)
        with torch.no_grad():
            feats = self.encode_images(x)      # [B, D]
        logits = self.head(feats)              # [B, C]
        return logits

    def parameters_to_optimize(self):
        return self.head.parameters()

    def get_preprocess(self):
        return self.preprocess
