"""Build script for Cython extensions (used by setuptools)."""

import numpy as np
from Cython.Build import cythonize
from setuptools import Extension


def build(setup_kwargs: dict) -> None:  # type: ignore[type-arg]
    extensions = [
        Extension(
            "vibemol.analysis._nwdp_fast",
            ["vibemol/analysis/_nwdp_fast.pyx"],
            include_dirs=[np.get_include()],
        ),
    ]
    setup_kwargs["ext_modules"] = cythonize(extensions, language_level="3")
