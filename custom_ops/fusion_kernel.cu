#include <cmath>
#include <cuda.h>
#include <cuda_runtime.h>
#include <torch/extension.h>

// Helper for logit
__device__ float logit_func(float p, float eps) {
  // Clamp p
  if (p < eps)
    p = eps;
  if (p > 1.0f - eps)
    p = 1.0f - eps;
  return logf(p / (1.0f - p));
}

// -------------------------------------------------------------
// KERNEL: Weighted Logit Accumulation
// Calculates: output[i] += weight * logit(probs[i])
// -------------------------------------------------------------
__global__ void weighted_logit_kernel(const float *__restrict__ probs,
                                      float *__restrict__ output, float weight,
                                      float eps, int size) {
  int idx = blockIdx.x * blockDim.x + threadIdx.x;
  if (idx < size) {
    float p = probs[idx];
    float val = logit_func(p, eps);
    // Atomic add is safer if multiple threads write to same output,
    // but here we map 1:1, so direct add is fine if shapes match.
    // Assuming 1:1 mapping for simplicity in this demo.
    output[idx] += weight * val;
  }
}

// C++ Wrapper
void weighted_logit_cuda(torch::Tensor probs, torch::Tensor output,
                         float weight, float eps) {
  // Safety Checks (Best Practice)
  TORCH_CHECK(probs.device().is_cuda(), "probs must be a CUDA tensor");
  TORCH_CHECK(output.device().is_cuda(), "output must be a CUDA tensor");
  TORCH_CHECK(probs.is_contiguous(), "probs must be contiguous");
  TORCH_CHECK(output.is_contiguous(), "output must be contiguous");
  TORCH_CHECK(probs.dtype() == torch::kFloat32, "probs must be float32");

  const auto size = probs.numel();
  const int threads = 256;
  const int blocks = (size + threads - 1) / threads;

  weighted_logit_kernel<<<blocks, threads>>>(
      probs.data_ptr<float>(), output.data_ptr<float>(), weight, eps, size);
}

// -------------------------------------------------------------
// KERNEL: Sigmoid + Bias (Activation)
// Calculates: output[i] = 1 / (1 + exp(-(input[i] + bias)))
// -------------------------------------------------------------
__global__ void sigmoid_bias_kernel(const float *__restrict__ input,
                                    float *__restrict__ output, float bias,
                                    int size) {
  int idx = blockIdx.x * blockDim.x + threadIdx.x;
  if (idx < size) {
    float val = input[idx] + bias;
    output[idx] = 1.0f / (1.0f + expf(-val));
  }
}

void sigmoid_bias_cuda(torch::Tensor input, torch::Tensor output, float bias) {
  TORCH_CHECK(input.device().is_cuda(), "input must be a CUDA tensor");
  TORCH_CHECK(output.device().is_cuda(), "output must be a CUDA tensor");
  TORCH_CHECK(input.is_contiguous(), "input must be contiguous");
  TORCH_CHECK(output.is_contiguous(), "output must be contiguous");
  TORCH_CHECK(input.dtype() == torch::kFloat32, "input must be float32");

  const auto size = input.numel();
  const int threads = 256;
  const int blocks = (size + threads - 1) / threads;

  sigmoid_bias_kernel<<<blocks, threads>>>(
      input.data_ptr<float>(), output.data_ptr<float>(), bias, size);
}
