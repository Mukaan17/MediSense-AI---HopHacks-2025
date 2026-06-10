# Cloud Infrastructure & Optimization Plan

## Goal
Migrate the local **Multimodal Clinical Copilot** to a production-grade, high-performance architecture using **AWS EC2**, **Kubernetes (EKS)**, **CUDA/Kernel optimizations**, and **AWS Titan** models.

## 1. Compute & Orchestration (EC2 & Kubernetes)

### **Kubernetes (Amazon EKS)**
We will containerize the application into microservices to ensure scalability and reliability.
*   **Cluster**: Amazon EKS (managed Kubernetes).
*   **Microservices**:
    *   `frontend-service`: React App (served via Nginx container).
    *   `backend-inference-service`: FastAPI server containing WhisperX and BioViL. **(Requires GPU)**
    *   `vector-store-service`: ChromaDB or centralized vector store (StatefulSet).

### **EC2 Instance Strategy (Node Groups)**
We need a mixed-instance cluster to optimize costs and performance.
*   **General Purpose Group** (for Frontend & System pods):
    *   **Instance**: `t3.medium` or `m6a.large`.
    *   **OS**: Amazon Linux 2023 or Ubuntu.
*   **GPU Inference Group** (for Backend/AI models):
    *   **Instance**: **`g5.xlarge`** (NVIDIA A10G Tensor Core GPU) or `g4dn.xlarge` (NVIDIA T4).
        *   *Why*: The "Titans" (AI models) and CUDA kernels need NVIDIA GPUs. `g5` provides A100-like features at a lower cost, perfect for inference.

## 2. Hardware Acceleration (CUDA & Kernels)

### **CUDA Integration**
The backend Docker image must be built on the official NVIDIA runtime to leverage the EC2 GPUs.
*   **Base Image**: `nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04`
*   **Application**:
    *   **WhisperX**: Uses `CTranslate2` (which uses CUDA) for rapid phoneme alignment and transcription.
    *   **BioViL**: PyTorch-based vision model running on CUDA.

### **Kernel Optimizations**
To maximize the "Titans" (hardware/models) performance, we will implement low-level kernel optimizations:
*   **FlashAttention-2**: Install/compile FlashAttention kernels for the Transformer layers in BioViL and Whisper. This reduces memory IO and speeds up inference by 2-4x.
*   **Torch.compile()**: Use PyTorch 2.0's compiler to fuse kernels for the vision encoder.
*   **Triton Inference Server (Optional)**: If latency is critical, we can export models to TensorRT/ONNX and serve them via Triton, but keeping them in Python (FastAPI) is easier for the current hackathon scope.

## 3. "Titans" (AWS Bedrock Models & Hardware)

Assuming "Titans" refers to **AWS Titan Models** (to replace external APIs like Groq/OpenAI) or **NVIDIA Titan-class performance**. Given the AWS context, we will integrate **AWS Bedrock**.

*   **AWS Titan Multimodal Embeddings G1**:
    *   *Usage*: Replace the local `sentence-transformers` or remote embeddings.
    *   *Benefit*: Native AWS integration, handles text/image natively for the RAG pipeline.
*   **AWS Titan Text Premier**:
    *   *Usage*: Replace Groq/Llama-3 for the Clinical Summary and Diagnosis generation.
    *   *Benefit*: HIPAA-eligible (potentially), lower latency within AWS VPC.

## 4. Architecture Diagram

```mermaid
graph TD
    User[Healthcare Professional] -->|HTTPS| ALB[AWS Load Balancer]
    
    subgraph "EKS Cluster (VPC)"
        ALB -->|/api| Backend[Backend Service\n(FastAPI + CUDA)]
        ALB -->|/*| Frontend[Frontend Service\n(React + Nginx)]
        
        subgraph "GPU Node (g5.xlarge)"
            Backend
        end
        
        Backend -->|Transcription| Whisper[WhisperX\n(FlashAttention)]
        Backend -->|Vision| BioViL[BioViL T\n(PyTorch 2.0)]
        Backend -->|RAG| VectorDB[(Vector Store)]
    end
    
    subgraph "AWS Bedrock"
        Backend -->|GenAI| TitanText[Amazon Titan Text]
        Backend -->|Embeddings| TitanEmbed[Amazon Titan Multimodal]
    end
```

## Implementation Roadmap

1.  **Containerization**:
    *   Create `Dockerfile.backend` with CUDA 12 + PyTorch + WhisperX.
    *   Create `Dockerfile.frontend` with Node build + Nginx alpine.
2.  **Infrastructure as Code (IaC)**:
    *   Use `eksctl` or Terraform to provision the EKS cluster with GPU nodegroups.
3.  **Code Adaptation**:
    *   Modify `llm_client.py` to support `boto3` (AWS Bedrock Titan) instead of `Groq`.
    *   Modify `api/server.py` to run specifically on `0.0.0.0` inside Docker.
4.  **Deployment**:
    *   Apply Kubernetes manifests (`deployment.yaml`, `service.yaml`).
