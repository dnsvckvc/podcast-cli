"""
Podcast CLI - Command-line tool for podcast transcription.

A CLI tool for transcribing podcast audio from YouTube or RSS feeds
via Salad Cloud.
"""

__version__ = "1.0.0"

from .hybrid_processor import HybridProcessor
from .output_manager import OutputManager

__all__ = [
    "HybridProcessor",
    "OutputManager",
]
