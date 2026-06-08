"""setup.py — needed so ``pip install -e .`` compiles Cython extensions."""

import numpy as np
from Cython.Build import cythonize
from setuptools import Extension, setup

extensions = [
    Extension(
        "vibemol.analysis._nwdp_fast",
        ["vibemol/analysis/_nwdp_fast.pyx"],
        include_dirs=[np.get_include()],
    ),
]

setup(ext_modules=cythonize(extensions, language_level="3"))
