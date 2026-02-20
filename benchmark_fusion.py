import time
import torch
import math
import sys

# Try imports
try:
    import custom_ops
    CUDA_AVAILABLE = True
    print("✅ Custom CUDA extension loaded successfully")
except ImportError:
    CUDA_AVAILABLE = False
    print("⚠️  Custom CUDA extension NOT found (Running in Python-only mode)")

def py_logit(p, eps=1e-6):
    p = min(max(p, eps), 1.0 - eps)
    return math.log(p / (1.0 - p))

def python_fusion(probs, output, weight, eps=1e-6):
    # Simulate the loop in core/fusion.py
    for i in range(len(probs)):
        output[i] += weight * py_logit(probs[i], eps)

def run_benchmark():
    size = 1_000_000  # 1 Million elements
    weight = 0.7
    eps = 1e-6

    # Data prep
    print(f"\n🚀 Benchmarking Fusion Logic (Size: {size})")
    
    # Python CPU
    py_probs = [0.5] * size
    py_out = [0.0] * size
    
    t0 = time.time()
    python_fusion(py_probs, py_out, weight, eps)
    t_py = time.time() - t0
    print(f"   Python (CPU): {t_py:.4f} sec")

    # CUDA
    if CUDA_AVAILABLE and torch.cuda.is_available():
        gpu_probs = torch.full((size,), 0.5, device='cuda', dtype=torch.float32)
        gpu_out = torch.zeros((size,), device='cuda', dtype=torch.float32)
        
        # Warmup
        custom_ops.weighted_logit(gpu_probs, gpu_out, weight, eps)
        torch.cuda.synchronize()
        
        t0 = time.time()
        custom_ops.weighted_logit(gpu_probs, gpu_out, weight, eps)
        torch.cuda.synchronize()
        t_cuda = time.time() - t0
        
        print(f"   CUDA Kernel : {t_cuda:.4f} sec")
        print(f"⚡ Speedup: {t_py / t_cuda:.1f}x")
    else:
        print("   CUDA Kernel : Skipped (No GPU or Extension)")

if __name__ == "__main__":
    run_benchmark()
