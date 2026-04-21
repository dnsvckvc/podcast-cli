# Transcription Service — Integration Guide for PodBrief

This document responds to the requirements in `TRANSCRIPTION_INTEGRATION.md`. It
describes how to integrate with our transcription service end-to-end.

> **Heads-up on current shape.** Today the service ships as a Python CLI
> (`podcast-cli`) that wraps Salad Cloud's transcription endpoint. There is **no
> HTTP API yet**. We are happy to put a thin HTTP wrapper in front of the same
> pipeline for PodBrief — the contract below is what that wrapper will expose,
> and the underlying limits are what Salad enforces. If a CLI/library
> integration works for you in the interim, see the "Direct CLI usage" section
> at the end.

---

## 1. Integration shape — Option B (async with polling)

We confirm **Option B** from your requirements. The transcription job is
asynchronous because the underlying provider (Salad) is queue-based. Typical
turnaround for a 1-hour episode is 3–8 minutes. Synchronous responses (Option
A) are not offered because we cannot guarantee a single connection stays open
that long under load.

### 1.1 Submit a job

```
POST /v1/transcribe
Authorization: Bearer <api_key>
Content-Type: multipart/form-data

audio: <binary file>            # required
filename: episode.mp3           # optional, defaults to "audio.mp3"
language: en                    # optional ISO-639-1, default: auto-detect
diarization: true               # optional, default: true
sentence_timestamps: true       # optional, default: true
callback_url: https://...       # optional — see §1.3
metadata: {"podbrief_id": 1234} # optional, echoed back unchanged
```

**Response — 202 Accepted**
```json
{
  "job_id": "j_01HX9K2M4Z7Q8TXP3W5R6V8N1A",
  "status": "pending",
  "submitted_at": "2026-04-08T10:15:32Z"
}
```

### 1.2 Poll for completion

```
GET /v1/transcribe/{job_id}
Authorization: Bearer <api_key>
```

**Response while in flight — 200 OK**
```json
{
  "job_id": "j_01HX9K2M4Z7Q8TXP3W5R6V8N1A",
  "status": "processing"
}
```

`status` is one of `pending | processing | completed | failed`. Recommended
polling interval: **15 seconds**. You will rarely benefit from polling faster
than that.

**Response on success — 200 OK**
```json
{
  "job_id": "j_01HX9K2M4Z7Q8TXP3W5R6V8N1A",
  "status": "completed",
  "transcript": "Full plain-text transcript...",
  "duration_seconds": 3542,
  "word_count": 8421,
  "language": "en",
  "segments": [
    {
      "start": 19.66,
      "end": 19.90,
      "text": "Thank you.",
      "speaker": "SPEAKER_0"
    }
  ],
  "metadata": {"podbrief_id": 1234},
  "completed_at": "2026-04-08T10:21:48Z"
}
```

`segments` is included whenever you submit with `sentence_timestamps: true`
(the default). Speaker labels are populated when `diarization: true`.

### 1.3 Webhook callback (optional)

If you submit a `callback_url`, we will POST the same completion payload to it
once and stop. You should still expose the polling endpoint as a fallback. We
do **not** retry failed callback deliveries — please return 2xx promptly and
queue any heavy work behind the response.

---

## 2. Inputs

| Item | Value |
|---|---|
| Upload mechanism | `multipart/form-data`, `audio` field |
| Supported formats | MP3, M4A, WAV, FLAC, AIFF (audio); MP4, MOV, MKV, WEBM, WMA (video — we extract the audio track) |
| Max file size | **3 GB** per upload |
| Max audio duration | **2.5 hours** per file |
| Encoding | Any sample rate / bit depth Salad accepts; we do not transcode |

If your podcast episodes routinely exceed either limit, let us know and we will
add a chunked upload + stitching layer. For typical 30–100 MB episodes you
will not hit anything.

---

## 3. Outputs

**Always returned:**
- `transcript` — UTF-8 plain text
- `duration_seconds` — float, audio duration as reported by Salad
- `word_count` — integer
- `language` — ISO-639-1 code (echo of your input or detected value)

**Returned when requested:**
- `segments[]` — sentence-level objects with `start`, `end`, `text`, and
  `speaker` (when diarization is on)

**Not currently exposed** (available upstream from Salad if you need them
later — say the word and we'll surface them):
- Word-level timestamps with confidence scores
- SRT/VTT subtitle files
- LLM translation into other languages

---

## 4. Authentication

- **Scheme:** `Authorization: Bearer <api_key>`
- **Issuance:** We will provision one API key per environment (staging +
  production). Keys are rotatable on request.
- **Scope:** A key is scoped to a single tenant; quota and rate limits are
  enforced per key.

---

## 5. Errors

All non-2xx responses use the shape you proposed:

```json
{
  "error": "Audio file exceeds 3 GB upload limit",
  "code": "too_large"
}
```

| HTTP | `code` | Meaning |
|---|---|---|
| 400 | `unsupported_format` | File format not recognised by Salad |
| 400 | `too_large` | File exceeds 3 GB or 2.5 h |
| 401 | `unauthorized` | Missing/invalid API key |
| 404 | `job_not_found` | Unknown `job_id` on a polling request |
| 422 | `invalid_request` | Malformed body, missing `audio` field, etc. |
| 429 | `rate_limited` | See §6 |
| 500 | `internal_error` | Our wrapper failed before reaching Salad |
| 502 | `upstream_error` | Salad returned an error after job submission |

A successful job that ultimately failed inside Salad surfaces as a 200 with
`"status": "failed"` and an `error` field — not as a 5xx — because the job ID
existed and we want you to be able to inspect it.

Your existing 3-attempt exponential-backoff retry policy is fine. Idempotency
keys are not required.

---

## 6. Rate limits and quotas

| Limit | Default |
|---|---|
| Concurrent in-flight jobs per key | **20** |
| New jobs per minute per key | **120** |
| Polling requests per minute per key | **600** |

These are conservative starting values that comfortably cover your stated
"10–50 episodes per hour at peak" target. We can raise them on request once
real traffic is visible. There is no monthly cap; usage is metered by audio
minutes (we will share a usage dashboard URL once provisioning is done).

A 429 response includes `Retry-After` in seconds.

---

## 7. Server-side timeouts

- **Upload:** 30-minute server-side timeout. Use chunked transfer encoding for
  large files; do not buffer the whole upload client-side.
- **Polling:** Polling responses return in <1 s. There is no idle-connection
  timeout to worry about.
- **Job processing:** Jobs that have not reached `completed` or `failed` after
  **45 minutes** are auto-cancelled and surface as `failed` with
  `code: "timeout"`. This is generous — a 2.5-hour episode currently completes
  in well under 20 minutes.

Recommended client-side timeouts:
- Upload: 35 minutes
- Polling: 10 seconds, with retry

---

## 8. What we will deliver to you

Once you confirm you'd like to proceed:

1. **Base URLs:** `https://staging.podcast-cli.example.com` and
   `https://api.podcast-cli.example.com`
2. **API keys** for both environments (delivered out-of-band via 1Password
   share)
3. **OpenAPI 3.1 spec** mirroring this document — generated from the same
   wrapper, so it will not drift
4. **Postman collection** with example requests
5. **Status page URL** for incident comms

Lead time to stand the HTTP wrapper up in staging: **~1 week** from go-ahead.
The wrapper is a thin FastAPI service in front of the existing
`HybridProcessor` + `SaladTranscriber` code paths, so most of the work is
deployment plumbing (auth, quotas, observability), not transcription logic.

---

## 9. Direct CLI usage (interim option)

If you'd like to start integrating before the HTTP wrapper exists, the same
pipeline is available as a Python CLI you can vendor:

```bash
git clone https://github.com/yourusername/podcast-cli.git
cd podcast-cli
python -m venv .venv && source .venv/bin/activate
pip install -e .

export SALAD_API_KEY=...
export SALAD_ORGANIZATION=...

podcast-cli \
  --rss "https://feed.example.com/feed.xml" \
  --episode "Episode title" \
  --output ./output \
  --verbose
```

Each processed episode lands in `./output/<slug>/` with:

```
metadata.json     # episode info + processing options
audio.mp3         # the source audio
transcript.txt    # plain text (joined sentences)
transcript.json   # structured: sentences[], speakers, timestamps, duration
performance.json  # per-stage timing
```

`transcript.json` is the same structured payload that the HTTP wrapper will
return as the `segments` array — it is safe to build your downstream pipeline
against this shape today and switch to the HTTP endpoint when it ships.

The CLI's transcription behaviour is controlled by the `salad` block in
`config.json`:

```json
"salad": {
  "use_lite": false,
  "language_code": "en",
  "diarization": true,
  "sentence_level_timestamps": true
}
```

`use_lite: true` switches to Salad's cheaper `transcription-lite` endpoint,
which only returns plain text — no segments, no speaker labels. Leave it
`false` for the full feature set described above.

---

## 10. Open questions for PodBrief

1. Do you want speaker labels grouped by speaker across the whole episode
   (`SPEAKER_0`, `SPEAKER_1`, …) or are per-sentence labels enough? Salad gives
   us per-sentence labels for free; cross-episode speaker identity is a
   separate (paid) tier.
2. Will episodes ever arrive as URLs to a CDN instead of binary uploads? If
   yes we can save you the upload step entirely — Salad accepts presigned URLs
   natively.
3. Do you need translated transcripts (e.g. non-English podcasts surfaced in
   English) at launch, or is detected-language-only fine for v1?

Reach out on the shared Slack channel and we'll set up the call.
