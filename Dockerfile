# ---------------------------------------------------------------
# Production Backend Dockerfile
# Base: NVIDIA CUDA 12.1 (Ubuntu 22.04)
# Features: Python 3.10, PyTorch 2.1 (GPU), Custom CUDA Kernels
# ---------------------------------------------------------------
FROM --platform=linux/amd64 nvidia/cuda:12.1.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HUGGINGFACE_HUB_CACHE=/app/cache/huggingface \
    TORCH_HOME=/app/cache/torch \
    CUDA_HOME=/usr/local/cuda-12.1 \
    PATH="/usr/local/cuda-12.1/bin:${PATH}" \
    TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;9.0"

# 1. System Dependencies (including build tools for CUDA)
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    python3-dev \
    python3-setuptools \
    git \
    ninja-build \
    build-essential \
    libsndfile1 \
    ffmpeg \
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# Symlink python
RUN ln -s /usr/bin/python3.10 /usr/bin/python

WORKDIR /app

# 2. Python Dependencies
# Upgrade pip and install essential build packages
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel

# Install PyTorch with CUDA support FIRST
RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Copy requirements and install
COPY requirements.txt .
# Exclude only torch/vision/audio packages already installed with CUDA wheels.
RUN awk '!/^(torch|torchvision|torchaudio)==/' requirements.txt > requirements_filtered.txt && \
    pip3 install --no-cache-dir --no-build-isolation -r requirements_filtered.txt

# install CUDA specific build deps
COPY requirements_cuda.txt .
RUN pip3 install --no-cache-dir -r requirements_cuda.txt

# 3. Application Code & Kernel Build
COPY . .

# Build and Install the Custom CUDA Extension
RUN CUDA_HOME=/usr/local/cuda-12.1 python3 setup.py install

# Create cache dirs
RUN mkdir -p /app/cache/huggingface /app/cache/torch

EXPOSE 8000

# Run the integrated server (which can now use custom_ops)
CMD ["python", "run_integrated_server.py"]


