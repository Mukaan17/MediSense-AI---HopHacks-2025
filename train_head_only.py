# train_head_only.py

import os, argparse, json
import numpy as np
import pandas as pd
from PIL import Image

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from core.modeling_biomedclip import BiomedClipForCheXpert, DEFAULT_LABELS

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--img_root", required=True)
    ap.add_argument("--labels", nargs="*", default=DEFAULT_LABELS)
    ap.add_argument("--frontal_only", action="store_true")
    ap.add_argument("--u_policy", choices=["ignore","ones","zeros"], default="ignore")
    ap.add_argument("--val_split", type=float, default=0.1)
    ap.add_argument("--batch_size", type=int, default=24)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--weight_decay", type=float, default=1e-4)
    ap.add_argument("--num_workers", type=int, default=4)
    ap.add_argument("--mixed_precision", action="store_true")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--repo", default="microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224")
    ap.add_argument("--out", default="checkpoints/biovil_vit_chexpert.pt")
    return ap.parse_args()

def load_df(args):
    df = pd.read_csv(args.csv)
    assert "Path" in df.columns
    if args.frontal_only and "Frontal/Lateral" in df.columns:
        df = df[df["Frontal/Lateral"].str.lower() == "frontal"]
    exists = df["Path"].apply(lambda p: os.path.exists(os.path.join(args.img_root, p)))
    print(f"[CheXpert] Filtered missing files: kept {int(exists.sum())} / {len(df)} (dropped {len(df)-int(exists.sum())})")
    df = df[exists].reset_index(drop=True)
    for c in args.labels:
        if c not in df.columns:
            df[c] = np.nan
    return df

def apply_uncertain_policy(df, labels, policy):
    if policy == "ones":
        for c in labels: df.loc[df[c] == -1, c] = 1
    elif policy == "zeros":
        for c in labels: df.loc[df[c] == -1, c] = 0
    return df

class CheXpertDataset(Dataset):
    def __init__(self, df, root, labels, preprocess, u_ignore=True):
        self.df, self.root, self.labels = df, root, labels
        self.preprocess, self.u_ignore = preprocess, u_ignore

    def __len__(self): return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        path = os.path.join(self.root, row["Path"])
        img = Image.open(path).convert("RGB")
        x = self.preprocess(img)  # tensor [3,224,224] on CPU
        y = row[self.labels].astype("float32").values
        mask = ~np.isnan(y)
        y = np.nan_to_num(y, nan=0.0)
        if self.u_ignore:
            for i, c in enumerate(self.labels):
                if row[c] == -1:
                    mask[i] = False
        return x, torch.from_numpy(y), torch.from_numpy(mask.astype(np.float32))

def get_pos_weight(df, labels):
    y = df[labels]
    pos = (y == 1).sum().values
    neg = (y == 0).sum().values
    pos = np.where(pos == 0, 1, pos)
    return torch.tensor(neg/pos, dtype=torch.float32)

@torch.no_grad()
def eval_loop(model, loader, labels):
    model.eval()
    all_logits, all_y, all_m = [], [], []
    for x, y, m in loader:
        logits = model(x)               # model moves x to its own device
        all_logits.append(logits.cpu())
        all_y.append(y)
        all_m.append(m)
    logits = torch.cat(all_logits, 0)
    y = torch.cat(all_y, 0).numpy()
    m = torch.cat(all_m, 0).numpy()
    probs = torch.sigmoid(logits).numpy()
    aurocs = {}
    for i, lab in enumerate(labels):
        mask = m[:, i] > 0.5
        if mask.sum() > 1 and len(np.unique(y[mask, i])) > 1:
            aurocs[lab] = roc_auc_score(y[mask, i], probs[mask, i])
        else:
            aurocs[lab] = float("nan")
    macro = np.nanmean([v for v in aurocs.values() if not np.isnan(v)]) if len(aurocs) else float("nan")
    return float(macro), {k: (None if np.isnan(v) else float(v)) for k, v in aurocs.items()}

def main():
    args = parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    df = load_df(args)
    df = apply_uncertain_policy(df, args.labels, args.u_policy)
    tr, va = train_test_split(df, test_size=args.val_split, random_state=42, shuffle=True)

    # Build model (backbone frozen, head trainable) — model handles device internally
    model = BiomedClipForCheXpert(repo=args.repo, num_labels=len(args.labels), device=args.device)

    # Datasets / loaders
    train_ds = CheXpertDataset(tr, args.img_root, args.labels, model.preprocess, u_ignore=(args.u_policy=="ignore"))
    val_ds   = CheXpertDataset(va, args.img_root, args.labels, model.preprocess, u_ignore=(args.u_policy=="ignore"))

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,  num_workers=args.num_workers, pin_memory=True)
    val_loader   = DataLoader(val_ds,   batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers, pin_memory=True)

    # Loss only on head
    pos_weight = get_pos_weight(tr, args.labels).to(model.device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight, reduction="none")
    optim = torch.optim.AdamW(model.head.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    scaler = torch.cuda.amp.GradScaler(enabled=args.mixed_precision)

    best = -1.0
    for epoch in range(1, args.epochs+1):
        model.train()   # head is trainable; backbone still frozen
        total, steps = 0.0, 0
        for x, y, m in train_loader:
            y = y.to(model.device); m = m.to(model.device)
            optim.zero_grad(set_to_none=True)
            with torch.cuda.amp.autocast(enabled=args.mixed_precision):
                logits = model(x)                     # model moves x to device
                loss_mat = criterion(logits, y)       # [B, C]
                loss = (loss_mat * m).sum() / (m.sum() + 1e-6)
            scaler.scale(loss).backward()
            scaler.step(optim)
            scaler.update()
            total += loss.item(); steps += 1

        macro, per = eval_loop(model, val_loader, args.labels)
        print(f"Epoch {epoch:02d}  train_loss={total/max(1,steps):.4f}  val_macro_AUROC={macro:.4f}")
        print('  Key AUROCs:', {k: round(per.get(k, float('nan')) or float('nan'), 4)
               for k in ["Cardiomegaly","Edema","Consolidation","Atelectasis","Pneumonia","Pleural Effusion"]})

        if macro > best:
            best = macro
            payload = {
                "repo": args.repo,
                "labels": args.labels,
                "head_state_dict": model.head.state_dict(),   # save HEAD ONLY
            }
            torch.save(payload, args.out)
            with open(args.out + ".json", "w") as f:
                json.dump({"best_macro_auroc": best, "labels": args.labels, "repo": args.repo}, f, indent=2)
            print(f"  ✓ Saved checkpoint to {args.out}")

if __name__ == "__main__":
    main()
