# Podcast CLI

A command-line tool for transcribing podcast audio from YouTube or RSS feeds via Salad Cloud.

## Features

- Local download of YouTube videos and RSS-feed episodes
- Direct transcription via Salad Cloud (lite or full endpoint)
- Optional speaker diarization and sentence-level timestamps (full endpoint)
- Batch processing with parallel workers
- Progress tracking with `tqdm`
- Structured output with metadata + per-episode performance reports

## Installation

### From source

```bash
git clone https://github.com/yourusername/podcast-cli.git
cd podcast-cli
pip install -e .
```

## Configuration

Create a `.env` file with your Salad credentials:

```env
SALAD_API_KEY=your_salad_api_key
SALAD_ORGANIZATION=your_salad_org
```

The runtime config lives in `config.json`. The `salad` block selects the
endpoint and toggles transcription features:

```json
"salad": {
  "use_lite": false,
  "language_code": "en",
  "diarization": true,
  "sentence_level_timestamps": true
}
```

- `use_lite`: when `true`, uses Salad's `transcription-lite` endpoint
  (URL + plain text only). When `false` (default), uses the full
  `transcribe` endpoint and the options below take effect.
- `language_code`: ISO language code (e.g. `"en"`). Required for
  diarization to work reliably.
- `diarization`: when `true`, enables speaker separation. Sentence-level
  speaker labels are also enabled automatically (Salad requires
  `sentence_diarization` for that).
- `sentence_level_timestamps`: keep `true` so the structured
  `transcript.json` is populated.

## Usage

```bash
# YouTube
podcast-cli --url "https://youtube.com/watch?v=..." --output ./podcasts

# RSS episode
podcast-cli --rss "https://feeds.example.com/feed.xml" \
            --episode "Episode Name" \
            --output ./podcasts

# Batch
podcast-cli --batch urls.txt --output ./podcasts --parallel 4

# Force reprocess of an already-processed episode
podcast-cli --url "..." --output ./podcasts --force-reprocess

# Verbose with per-episode performance report
podcast-cli --url "..." --output ./podcasts --verbose
```

## Output structure

When the full Salad endpoint is in use, each episode folder contains:

```
./podcasts/
├── youtube_VIDEOID/
│   ├── metadata.json     # episode info + processing options
│   ├── audio.mp3
│   ├── transcript.txt    # plain text (joined sentences)
│   ├── transcript.json   # structured: sentences, timestamps, speakers
│   └── performance.json
└── .cli_cache/
    └── processing_log.json
```

When `use_lite` is `true`, only `transcript.txt` is produced.

## Batch file formats

### Plain text (one URL per line)
```
https://youtube.com/watch?v=...
https://youtube.com/watch?v=...
```

### JSON
```json
[
  {"url": "https://youtube.com/watch?v=...", "platform": "youtube"},
  {"url": "https://feeds.example.com/feed.xml", "platform": "rss", "episode_name": "Episode Title"}
]
```

### CSV-like
```
https://youtube.com/watch?v=...,youtube
https://feeds.example.com/feed.xml,rss,Episode Name
```

## Development

```bash
pip install -e ".[dev]"
pytest
black podcast_cli
isort podcast_cli
```

## License

MIT License
