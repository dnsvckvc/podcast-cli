#!/usr/bin/env python3
"""
Podcast CLI entry point module.

This module provides the main() function that serves as the entry point
when podcast-cli is installed via pip.
"""

import argparse
import sys
import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from .utils.app_utils import load_config, setup_logger
from .output_manager import OutputManager
from .cli_processor import CLIProcessor
from .remote_processor import RemoteProcessor
from .hybrid_processor import HybridProcessor


def setup_cli_logger(verbose: bool = False) -> logging.Logger:
    """Setup CLI-specific logger."""
    logger = logging.getLogger("podcast_cli")

    # Set level based on verbosity
    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    # Only add handler if none exists
    if not logger.handlers:
        handler = logging.StreamHandler()
        if verbose:
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        else:
            formatter = logging.Formatter('%(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def load_cli_config(config_path: str = None) -> Dict[str, Any]:
    """Load configuration for CLI processing."""
    try:
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
        else:
            config = load_config()

        return config
    except Exception as e:
        raise RuntimeError(f"Failed to load configuration: {e}")


def parse_batch_file(batch_file: str) -> List[Dict[str, str]]:
    """
    Parse batch file containing URLs and processing instructions.

    Supported formats:
    - Simple: One URL per line
    - JSON: List of objects with url, platform, episode_name
    - CSV-like: url,platform,episode_name
    """
    if not os.path.exists(batch_file):
        raise FileNotFoundError(f"Batch file not found: {batch_file}")

    sources = []

    with open(batch_file, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    # Try to parse as JSON first
    try:
        json_data = json.loads(content)
        if isinstance(json_data, list):
            for item in json_data:
                if isinstance(item, dict) and "url" in item:
                    sources.append({
                        "url": item["url"],
                        "platform": item.get("platform", "youtube"),
                        "episode_name": item.get("episode_name")
                    })
                elif isinstance(item, str):
                    sources.append({
                        "url": item,
                        "platform": "youtube",
                        "episode_name": None
                    })
        return sources
    except json.JSONDecodeError:
        pass

    # Parse as simple text file (one URL per line)
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # Support CSV-like format: url,platform,episode_name
        parts = [p.strip() for p in line.split(',')]
        if len(parts) >= 1:
            sources.append({
                "url": parts[0],
                "platform": parts[1] if len(parts) > 1 else "youtube",
                "episode_name": parts[2] if len(parts) > 2 else None
            })

    return sources


def process_with_progress(processor: CLIProcessor, sources: List[Dict[str, str]],
                         options: Dict[str, Any], parallel: int = 1) -> List:
    """Process sources with progress indication."""
    try:
        from tqdm import tqdm
        use_tqdm = True
    except ImportError:
        use_tqdm = False
        print("Install tqdm for progress bars: pip install tqdm")

    results = []
    total = len(sources)

    if parallel == 1:
        # Sequential processing
        if use_tqdm:
            sources_iter = tqdm(sources, desc="Processing episodes", unit="episode")
        else:
            sources_iter = sources
            print(f"Processing {total} episodes...")

        for i, source in enumerate(sources_iter, 1):
            if not use_tqdm:
                print(f"Processing {i}/{total}: {source['url']}")

            result = processor.process_single(
                source_url=source["url"],
                platform=source["platform"],
                options={**options, "episode_name": source.get("episode_name")}
            )
            results.append(result)
    else:
        # Parallel processing
        print(f"Processing {total} episodes with {parallel} workers...")

        def process_single_wrapper(source_data):
            source, idx = source_data
            result = processor.process_single(
                source_url=source["url"],
                platform=source["platform"],
                options={**options, "episode_name": source.get("episode_name")}
            )
            return idx, result

        with ThreadPoolExecutor(max_workers=parallel) as executor:
            future_to_idx = {
                executor.submit(process_single_wrapper, (source, i)): i
                for i, source in enumerate(sources)
            }

            if use_tqdm:
                progress = tqdm(total=total, desc="Processing episodes", unit="episode")

            results = [None] * total

            for future in as_completed(future_to_idx):
                idx, result = future.result()
                results[idx] = result

                if use_tqdm:
                    progress.update(1)
                else:
                    completed = sum(1 for r in results if r is not None)
                    print(f"Completed {completed}/{total} episodes")

            if use_tqdm:
                progress.close()

    return results


def print_results_summary(results: List, output_manager: OutputManager, show_performance: bool = False):
    """Print summary of processing results."""
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    print(f"\n{'='*60}")
    print(f"PROCESSING SUMMARY")
    print(f"{'='*60}")
    print(f"Total episodes: {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")

    if successful:
        print(f"\nSuccessful episodes:")
        for result in successful:
            if result.episode_path:
                episode_name = result.episode_path.name
                if show_performance and result.performance_tracker:
                    summary = result.performance_tracker.get_performance_summary()
                    total_time = summary.get("total_time", "unknown")
                    print(f"  * {episode_name} ({total_time})")
                else:
                    print(f"  * {episode_name}")

    if failed:
        print(f"\nFailed episodes:")
        for result in failed:
            print(f"  X {result.error}")

    # Print output statistics
    stats = output_manager.get_processing_stats()
    print(f"\nOutput directory: {stats['output_directory']}")
    print(f"Total processed episodes: {stats['total_episodes']}")
    if stats['platforms']:
        print(f"Platforms: {', '.join(f'{k}: {v}' for k, v in stats['platforms'].items())}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Process podcast audio from YouTube or RSS feeds with AI transcription and summarization",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Input sources (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--url", help="YouTube URL to process")
    source_group.add_argument("--rss", help="RSS feed URL to process")
    source_group.add_argument("--batch", help="Batch file containing URLs to process")

    # Required arguments
    parser.add_argument("--output", required=True, help="Output directory for processed episodes")

    # Optional arguments
    parser.add_argument("--episode", help="Specific episode name (required for RSS feeds)")
    parser.add_argument("--detail", type=float, default=0.5, help="Summary detail level (0.0-1.0)")
    parser.add_argument("--transcriber", choices=["auto", "salad", "whisper", "local_whisper"],
                        help="Transcriber to use")
    parser.add_argument("--use-lite", action="store_true", help="Use Salad's lite transcription endpoint")
    parser.add_argument("--config", help="Custom configuration file path")
    parser.add_argument("--parallel", type=int, default=1, help="Number of parallel workers for batch processing")

    # Processing options
    parser.add_argument("--transcribe-only", action="store_true", help="Only transcribe, skip summarization")
    parser.add_argument("--summarize-only", action="store_true", help="Only summarize existing transcript")
    parser.add_argument("--force-reprocess", action="store_true", help="Force reprocessing of already processed episodes")
    parser.add_argument("--remote", action="store_true", help="Use remote API instead of local processing")
    parser.add_argument("--hybrid", action="store_true", help="Hybrid mode: download locally, transcribe remotely")
    parser.add_argument("--api-url", help="Custom API URL for remote processing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--no-performance-report", action="store_true", help="Disable performance reporting")

    args = parser.parse_args()

    # Setup logging
    logger = setup_cli_logger(args.verbose)

    try:
        # Validate detail level
        if not 0.0 <= args.detail <= 1.0:
            logger.error("Detail level must be between 0.0 and 1.0")
            sys.exit(1)

        # Validate mutually exclusive options
        if args.transcribe_only and args.summarize_only:
            logger.error("Cannot use --transcribe-only and --summarize-only together")
            sys.exit(1)

        if args.remote and args.hybrid:
            logger.error("Cannot use --remote and --hybrid together")
            sys.exit(1)

        if args.remote and args.summarize_only:
            logger.error("--summarize-only is not supported with remote processing")
            sys.exit(1)

        if args.rss and not args.episode:
            logger.error("RSS feeds require --episode parameter")
            sys.exit(1)

        # Initialize output manager
        logger.info("Initializing output manager...")
        output_manager = OutputManager(args.output)

        # Choose processor based on mode
        if args.hybrid:
            logger.info("Initializing hybrid processor...")
            config = load_cli_config(args.config)
            processor = HybridProcessor(config=config, output_manager=output_manager, verbose=args.verbose)
        elif args.remote:
            logger.info("Initializing remote API processor...")
            processor = RemoteProcessor(output_manager=output_manager, api_url=args.api_url, verbose=args.verbose)
        else:
            logger.info("Initializing local processor...")
            config = load_cli_config(args.config)
            if args.transcriber:
                config["transcriber"] = args.transcriber
            if args.use_lite:
                config.setdefault("salad", {})["use_lite"] = True
            processor = CLIProcessor(config, output_manager, args.verbose)

        # Prepare processing options
        processing_options = {
            "detail_level": args.detail,
            "transcribe": not args.summarize_only,
            "summarize": not args.transcribe_only,
            "transcribe_only": args.transcribe_only,
            "summarize_only": args.summarize_only,
            "force_reprocess": args.force_reprocess
        }

        # Process based on input type
        if args.batch:
            logger.info(f"Loading batch file: {args.batch}")
            sources = parse_batch_file(args.batch)
            logger.info(f"Found {len(sources)} episodes to process")
            results = process_with_progress(processor, sources, processing_options, args.parallel)
        else:
            if args.url:
                source_url = args.url
                platform = "youtube"
            else:
                source_url = args.rss
                platform = "rss"
                processing_options["episode_name"] = args.episode

            logger.info(f"Processing single episode: {source_url}")
            result = processor.process_single(source_url, platform, processing_options)
            results = [result]

        # Print results summary
        show_perf = args.verbose and not args.no_performance_report
        print_results_summary(results, output_manager, show_performance=show_perf)

        # Exit with appropriate code
        failed_count = sum(1 for r in results if not r.success)
        if failed_count > 0:
            logger.warning(f"{failed_count} episodes failed to process")
            sys.exit(1)
        else:
            logger.info("All episodes processed successfully!")
            sys.exit(0)

    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
