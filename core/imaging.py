from typing import List, Dict, Any
import io

try:
    import torchvision.transforms as T
    from PIL import Image
    TORCH_AVAILABLE = True
except Exception:
    TORCH_AVAILABLE = False

class ImagingModel:
    def __init__(self, labels=None, device: str = "cpu"):
        self.labels = labels or ["cardiomegaly","pleural_effusion","consolidation","pneumothorax","edema","atelectasis"]
        self.device = device
        self.model = None
        if TORCH_AVAILABLE:
            self.tx = T.Compose([T.Resize(512), T.CenterCrop(512), T.ToTensor(), T.Normalize(mean=[0.5], std=[0.5])])

    def _prep(self, image_bytes: bytes):
        img = Image.open(io.BytesIO(image_bytes)).convert("L")
        return self.tx(img).unsqueeze(0) if TORCH_AVAILABLE else None

    def predict(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        return [{"label": lab, "prob": 0.05, "heatmap": None} for lab in self.labels]


