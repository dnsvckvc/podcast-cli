# Podcast CLI

A command-line tool for processing podcast audio from YouTube or RSS feeds with AI transcription and summarization.

## Features

- **Three Processing Modes**:
  - **Local**: Full local processing (download, transcribe, summarize)
  - **Remote**: Use remote API endpoint
  - **Hybrid**: Local download + remote transcription

- Batch processing with parallel workers
- Progress tracking with tqdm
- Structured output with metadata
- Performance reporting
- Support for YouTube and RSS sources

## Installation

### From PyPI (when published)

```bash
pip install podcast-cli
```

### From Source

```bash
git clone https://github.com/yourusername/podcast-cli.git
cd podcast-cli
pip install -e .
```

### With Local Whisper Support

```bash
pip install -e ".[local-whisper]"
```

## Configuration

Create a `.env` file with your API keys:

```env
# Required for summarization
OPENAI_API_KEY=your_openai_api_key

# Required for Salad transcription (remote/hybrid modes)
SALAD_API_KEY=your_salad_api_key
SALAD_ORGANIZATION=your_salad_org

# Required for remote mode
API_USERNAME=your_api_username
API_PASSWORD=your_api_password
API_URL=https://your-api-endpoint.com
```

## Usage

### Basic Usage

```bash
# Process a YouTube video (local mode)
podcast-cli --url "https://youtube.com/watch?v=..." --output ./podcasts

# Process an RSS episode
podcast-cli --rss "https://feeds.example.com/feed.xml" --episode "Episode Name" --output ./podcasts
```

### Processing Modes

```bash
# Local processing (default)
podcast-cli --url "https://youtube.com/watch?v=..." --output ./podcasts

# Remote API processing
podcast-cli --url "https://youtube.com/watch?v=..." --output ./podcasts --remote

# Hybrid mode (local download + Salad Cloud transcription)
podcast-cli --url "https://youtube.com/watch?v=..." --output ./podcasts --hybrid
```

### Batch Processing

```bash
# Process multiple URLs from a file
podcast-cli --batch urls.txt --output ./podcasts

# Parallel processing with 4 workers
podcast-cli --batch urls.txt --output ./podcasts --parallel 4
```

### Additional Options

```bash
# Transcription only (skip summarization)
podcast-cli --url "..." --output ./podcasts --transcribe-only

# Summarization only (existing transcript)
podcast-cli --url "..." --output ./podcasts --summarize-only

# Custom detail level (0.0-1.0)
podcast-cli --url "..." --output ./podcasts --detail 0.75

# Verbose mode with performance reporting
podcast-cli --url "..." --output ./podcasts --verbose

# Force reprocessing of already processed episodes
podcast-cli --url "..." --output ./podcasts --force-reprocess

# Choose specific transcriber
podcast-cli --url "..." --output ./podcasts --transcriber salad
```

## Output Structure

```
./podcasts/
├── <podcast_name>/
│   └── <episode_date>/
│       ├── metadata.json    # Episode info, processing stats
│       ├── transcript.txt   # Raw transcript
│       ├── summary.md       # AI summary
│       └── README.md        # Episode documentation
└── processing_stats.json    # Overall stats
```

## Batch File Formats

### Simple (one URL per line)
```
https://youtube.com/watch?v=...
https://youtube.com/watch?v=...
```

### JSON
```json
[
  {
    "url": "https://youtube.com/watch?v=...",
    "platform": "youtube"
  },
  {
    "url": "https://feeds.example.com/feed.xml",
    "platform": "rss",
    "episode_name": "Episode Title"
  }
]
```

### CSV-like
```
https://youtube.com/watch?v=...,youtube
https://feeds.example.com/feed.xml,rss,Episode Name
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black podcast_cli
isort podcast_cli
```

## License

MIT License
