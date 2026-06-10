#include <torch/extension.h>

// Forward declarations
void weighted_logit_cuda(torch::Tensor probs, torch::Tensor output,
                         float weight, float eps);
void sigmoid_bias_cuda(torch::Tensor input, torch::Tensor output, float bias);

// PyBind definition
PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
  m.def("weighted_logit", &weighted_logit_cuda,
        "Add weighted logits to output (CUDA)");
  m.def("sigmoid_bias", &sigmoid_bias_cuda, "Apply sigmoid with bias (CUDA)");
}
