"""Setup script for podcast-cli."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="podcast-cli",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Command-line tool for transcribing podcast audio via Salad Cloud",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/podcast-cli",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "podcast-cli=podcast_cli.cli:main",
        ],
    },
    include_package_data=True,
)
