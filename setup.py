from setuptools import setup
from setuptools import find_packages


setup(
    name="tourism-procedural-knowledge-mining",
    version="0.1.0",
    description="Reproducible tourism procedural-knowledge mining course experiments",
    packages=find_packages("src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
)
