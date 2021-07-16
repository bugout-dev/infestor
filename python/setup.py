import os
from setuptools import find_packages, setup

from infestor.version import INFESTOR_VERSION

long_description = ""
README_PATH = os.path.join(os.path.dirname(__file__), "..", "README.md")
with open(README_PATH) as ifp:
    long_description = ifp.read()

setup(
    name="bugout-infestor",
    version=INFESTOR_VERSION,
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=["atomicwrites", "humbug", "libcst", "pygit2", "pydantic"],
    extras_require={
        "dev": ["black", "mypy", "wheel", "types-atomicwrites"],
        "distribute": ["setuptools", "twine", "wheel"],
    },
    description="Humbug Infestor: Manage Humbug reporting over your code base",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Bugout.dev",
    author_email="engineering@bugout.dev",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python",
        "License :: OSI Approved :: Apache Software License",
        "Topic :: Software Development :: Libraries",
    ],
    url="https://github.com/bugout-dev/infestor",
    entry_points={"console_scripts": ["infestor=infestor.cli:main"]},
    include_package_data=True,
)
