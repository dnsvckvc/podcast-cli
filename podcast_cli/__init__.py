"""
Podcast CLI - Command-line tool for podcast processing.

A CLI tool for processing podcast audio from YouTube or RSS feeds
with AI transcription and summarization.
"""

__version__ = "1.0.0"

from .cli_processor import CLIProcessor
from .remote_processor import RemoteProcessor
from .hybrid_processor import HybridProcessor
from .output_manager import OutputManager

__all__ = [
    "CLIProcessor",
    "RemoteProcessor",
    "HybridProcessor",
    "OutputManager",
]