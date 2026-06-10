#!/bin/bash
#SBATCH --partition=gpuq
#SBATCH --qos=gpu
#SBATCH --job-name=chexpert-train
#SBATCH --output=/scratch/vnandak/%x-%N-%j.out
#SBATCH --error=/scratch/vnandak/%x-%N-%j.err
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=4
#SBATCH --gres=gpu:A100.80gb:1
#SBATCH --mem=32gb
#SBATCH --time=0-01:00:00

set -e
umask 0027

echo "=== GPU Info ==="
nvidia-smi

echo "=== Loading modules ==="
module load cuda/12.3.1
module load gnu10
module load python

echo "=== Activating venv ==="
source ~/venv/bin/activate
which python
python --version

echo "=== Working directory ==="
cd /scratch/vnandak
ls -la train/ | head -5
echo "..."
ls train/ | wc -l

echo "=== Installing dependencies ==="
pip install --quiet open_clip_torch torchvision pandas scikit-learn pillow transformers

echo "=== Pre-flight checks ==="
python -c "
import torch, open_clip, pandas, sklearn, PIL, os
print(f'PyTorch: {torch.__version__}')
print(f'CUDA: {torch.cuda.is_available()} — {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')

# Verify images exist
df = pandas.read_csv('train.csv')
sample = df['Path'].iloc[0]
print(f'CSV sample path: {sample}')

# Check with and without prefix
for prefix in ['CheXpert-v1.0-small/', 'CheXpert-v1.0/', '']:
    test = sample.replace(prefix, '', 1) if prefix else sample
    full = os.path.join('.', test)
    if os.path.exists(full):
        print(f'Resolved path: {full} — EXISTS (size: {os.path.getsize(full)} bytes)')
        break
else:
    print(f'ERROR: Could not resolve image path')

# Count reachable
count = sum(1 for p in df['Path'][:1000] if os.path.exists(os.path.join('.', p)) or 
    os.path.exists(os.path.join('.', p.replace('CheXpert-v1.0-small/', ''))))
print(f'Reachable (first 1000): {count}/1000')
if count < 10:
    raise RuntimeError(f'Only {count} images reachable — check extraction!')
print('Pre-flight PASSED')
"

echo "=== Starting training ==="
python train_head_only.py \
  --csv train.csv \
  --img_root . \
  --epochs 10 \
  --batch_size 64 \
  --mixed_precision \
  --num_workers 4 \
  --device cuda \
  --out /scratch/vnandak/checkpoints/biovil_vit_chexpert.pt

echo "=== Training complete! ==="
ls -la /scratch/vnandak/checkpoints/
