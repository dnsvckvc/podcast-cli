# CLI Usage Examples

## Quick Start Examples

### Local Processing (Full Setup Required)
```bash
# Activate virtual environment
source .venv/bin/activate

# Process single YouTube video locally
python cli.py --url "https://www.youtube.com/watch?v=x1cybzlxqi0" --output ./podcasts

# Process RSS episode locally
python cli.py --rss "https://feeds.megaphone.fm/forwardguidance" \
              --episode "Threat to Fed Independence is Un-Anchoring Inflation Expectations | Jens Nordvig" \
              --output ./podcasts

# Batch processing with parallel workers
python cli.py --batch examples/batch_mixed.json --output ./podcasts --parallel 2
```

### Remote API Processing (Simple Setup)
```bash
# Activate virtual environment
source .venv/bin/activate

# Process single YouTube video via API
python cli.py --url "https://www.youtube.com/watch?v=x1cybzlxqi0" --output ./podcasts --remote

# Process RSS episode via API
python cli.py --rss "https://feeds.megaphone.fm/forwardguidance" \
              --episode "Threat to Fed Independence is Un-Anchoring Inflation Expectations | Jens Nordvig" \
              --output ./podcasts --remote

# Batch processing via API (sequential)
python cli.py --batch examples/batch_mixed.json --output ./podcasts --remote
```

## Environment Setup

### For Local Processing
Create `.env` file:
```bash
# Required for local processing
OPENAI_API_KEY=your_openai_key_here
SALAD_API_KEY=your_salad_key_here
SALAD_ORGANIZATION=your_salad_org_here
```

### For Remote API Processing
Create `.env` file:
```bash
# Required for remote processing
API_USERNAME=admin
API_PASSWORD=secure_password_here
```

## Output Structure (Same for Both Modes)

Both local and remote processing create identical output structure:

```
./podcasts/
├── youtube_x1cybzlxqi0/
│   ├── metadata.json          # Episode info + processing details
│   ├── audio.mp3              # Audio file (local only)
│   ├── transcript.txt         # Full transcript
│   └── summary.md             # Formatted summary
├── rss_threat_to_fed_independence.../
│   └── (same structure)
└── .cli_cache/
    └── processing_log.json    # Processing history
```

Note: Remote processing doesn't provide audio files, but creates the same folder structure with transcript and summary.

## Advanced Examples

### Local Processing with Custom Options
```bash
# Transcribe only (no summary)
python cli.py --url "https://youtube.com/watch?v=..." --output ./podcasts --transcribe-only

# Custom detail level (more detailed summary)
python cli.py --url "https://youtube.com/watch?v=..." --output ./podcasts --detail 0.8

# Use Whisper instead of Salad for transcription
python cli.py --url "https://youtube.com/watch?v=..." --output ./podcasts --transcriber whisper

# Verbose logging
python cli.py --url "https://youtube.com/watch?v=..." --output ./podcasts --verbose
```

### Remote Processing with Custom Options
```bash
# Custom detail level via API
python cli.py --url "https://youtube.com/watch?v=..." --output ./podcasts --remote --detail 0.8

# Custom API endpoint
python cli.py --url "https://youtube.com/watch?v=..." --output ./podcasts --remote --api-url "https://my-api.com"

# Force reprocess existing episodes
python cli.py --url "https://youtube.com/watch?v=..." --output ./podcasts --remote --force-reprocess
```

## Troubleshooting

### Local Processing Issues
```bash
# Check if environment variables are set
python -c "import os; print('OpenAI:', bool(os.getenv('OPENAI_API_KEY'))); print('Salad:', bool(os.getenv('SALAD_API_KEY')))"

# Test local processor initialization
python -c "from cli.cli_processor import CLIProcessor; from cli.output_manager import OutputManager; from utils.app_utils import load_config; CLIProcessor(load_config(), OutputManager('./test'), verbose=True)"
```

### Remote Processing Issues
```bash
# Check if API credentials are set
python -c "import os; print('API User:', bool(os.getenv('API_USERNAME'))); print('API Pass:', bool(os.getenv('API_PASSWORD')))"

# Test remote API connection
python -c "from cli.remote_api_client import RemoteAPIClient; client = RemoteAPIClient(); print('API Info:', client.get_api_info())"
```

### Common Issues
1. **Missing ffmpeg**: Install with `brew install ffmpeg` (macOS) or equivalent
2. **Python 3.9 compatibility**: Use `requirements-py39.txt` instead of `requirements.txt`
3. **Environment variables**: Make sure `.env` file is in project root
4. **API credentials**: Get credentials from the API administrator
5. **Network issues**: Remote processing requires stable internet connection