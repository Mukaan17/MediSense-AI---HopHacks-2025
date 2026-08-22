from setuptools import setup
from torch.utils.cpp_extension import BuildExtension, CUDAExtension

setup(
    name='custom_ops',
    ext_modules=[
        CUDAExtension(
            name='custom_ops',
            sources=[
                'custom_ops/bindings.cpp',
                'custom_ops/fusion_kernel.cu',
            ],
            extra_compile_args={
                'cxx': ['-O3'],
                'nvcc': ['-O3']
            }
        )
    ],
    cmdclass={
        'build_ext': BuildExtension
    }
)
