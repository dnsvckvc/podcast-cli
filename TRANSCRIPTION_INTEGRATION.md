# Transcription Service Integration — Requirements

## Context

We're building **PodBrief**, a SaaS that subscribes to podcast RSS feeds, transcribes new episodes, and produces AI summaries. The transcription step is delegated to your existing service. This document outlines what we need to integrate.

To simplify your operational footprint, **we will handle audio downloading on our side** and upload the audio file directly to your transcription endpoint. You won't need to maintain a downloader VPS or fetch audio from third-party CDNs.

## Required endpoint

A single HTTP endpoint that accepts an audio file and returns a transcript.

### Option A — Synchronous (acceptable for ~1 hour audio)

```
POST /transcribe
Content-Type: multipart/form-data
Authorization: Bearer <api_key>

audio: <binary file>
filename: episode.mp3
```

**Response:**
```json
{
  "transcript": "Full transcript text...",
  "duration_seconds": 3542,
  "word_count": 8421,
  "language": "en"
}
```

A 1-hour episode currently takes 3-5 minutes — synchronous is fine if you can keep the connection open. Please set a generous server-side timeout (10+ minutes).

### Option B — Asynchronous with polling (preferred if jobs may exceed ~5 min)

```
POST /transcribe              → returns { "job_id": "..." }
GET  /transcribe/{job_id}     → returns { "status": "pending|processing|completed|failed", "transcript": "...", ... }
```

We'll poll every 10-30 seconds until completion.

### Option C — Webhook callback (also acceptable)

```
POST /transcribe
audio: <binary file>
callback_url: https://podbrief.example.com/internal/transcription-callback
```

You POST the result to our callback when done. We'll handle authentication on our side.

## Inputs

- **Audio source:** We always upload the binary audio file directly (multipart form data). We do **not** ask you to fetch from external URLs.
- **Audio formats:** Whatever podcasts use in the wild — MP3, M4A, occasionally OGG. Please confirm what's supported.
- **File size:** Typical podcast episodes are 30-100 MB. Please confirm any upload size limits.

## Outputs

**Required:**
- Plain text transcript (UTF-8)

**Nice to have:**
- Word count
- Detected language
- Audio duration in seconds
- Optional: timestamped segments (start/end per sentence or paragraph) — useful later for the "highlights with timestamps" feature

## Auth

- API key via `Authorization: Bearer <key>` header is preferred
- Or any other scheme you prefer — just let us know

## Error handling

When something fails (unsupported format, internal error, timeout), please return:

```json
{
  "error": "human-readable message",
  "code": "unsupported_format|internal_error|too_large"
}
```

with an appropriate HTTP status. We'll surface failures in our UI and retry up to 3 times.

## Scale and rate limits

- **Initial scale:** A few hundred to low thousands of users
- **Volume:** Roughly 10-50 episodes per hour at peak, mostly off-peak
- **Concurrency:** We can throttle from our side if needed — please share any rate limits

## Reliability expectations

- We'll retry failed jobs 3 times with exponential backoff
- Idempotency is not required since we upload fresh on each retry

## What we'd like from you

1. **Endpoint URL** for our environment
2. **Auth credentials** (API key or equivalent)
3. **OpenAPI/Swagger spec** if available, or a simple example request/response
4. **Confirmation of** which integration shape (A/B/C above) fits your service
5. **Supported audio formats** and upload size limits
6. **Rate limits or quotas** we need to respect
7. **Server-side timeout settings** so we can configure our client accordingly

Once we have this, we can wire it into our worker and start processing episodes end-to-end. Happy to jump on a call to clarify anything.
