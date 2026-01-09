# Minimal Setup Test Guide

## Test 1: Zero API Keys (Transcribe-Only)

No `.env` file needed!

```bash
# Activate environment
source .venv/bin/activate

# Test transcribe-only with no API keys
python cli.py --url "https://www.youtube.com/watch?v=x1cybzlxqi0" \
              --output ./test_minimal \
              --transcribe-only \
              --verbose

# Expected: Downloads Whisper model on first run, creates transcript
```

**Expected Output Structure:**
```
./test_minimal/
└── youtube_x1cybzlxqi0/
    ├── metadata.json
    ├── audio.mp3
    └── transcript.txt  # Only transcript, no summary
```

## Test 2: Single API Key (Full Processing)

Create `.env` with minimal content:
```bash
OPENAI_API_KEY=your_key_here
```

```bash
# Test full processing with minimal setup
python cli.py --url "https://www.youtube.com/watch?v=x1cybzlxqi0" \
              --output ./test_full \
              --verbose

# Expected: Local transcription + OpenAI summarization
```

**Expected Output Structure:**
```
./test_full/
└── youtube_x1cybzlxqi0/
    ├── metadata.json
    ├── audio.mp3
    ├── transcript.txt
    └── summary.md  # Both transcript and summary
```

## Test 3: Transcriber Selection

```bash
# Force specific transcriber types
python cli.py --url "https://youtube.com/watch?v=..." --output ./test --transcribe-only --transcriber local_whisper
python cli.py --url "https://youtube.com/watch?v=..." --output ./test --transcribe-only --transcriber auto
```

## Test 4: Batch Processing (Minimal)

```bash
# Batch transcribe-only (no API keys needed)
python cli.py --batch examples/batch_simple.txt \
              --output ./test_batch \
              --transcribe-only \
              --parallel 2
```

## Component Verification

```bash
# Check what gets initialized
python -c "
from cli.cli_processor import CLIProcessor
from cli.output_manager import OutputManager
from utils.app_utils import load_config

processor = CLIProcessor(load_config(), OutputManager('./test'), verbose=True)
print('Components:', processor.get_component_info())
print('Transcriber:', type(processor.transcriber).__name__)
print('Summarizer loaded:', processor.summarizer is not None)
"
```

Expected output:
- `LocalWhisperTranscriber` when no API keys present
- `SaladTranscriber` when SALAD_API_KEY found
- `WhisperTranscriber` when only OPENAI_API_KEY found
- Summarizer `None` until needed

## Model Download Info

First run will download Whisper model:
- **tiny**: ~39MB, fastest, lower accuracy
- **base**: ~140MB, good balance (default)
- **small**: ~240MB, better accuracy
- **medium**: ~760MB, high accuracy
- **large**: ~1.5GB, best accuracy

Subsequent runs use cached model and are much faster.