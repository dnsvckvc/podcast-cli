Transcription API Reference
For more detailed instructions, please visit our Salad Docs Page or API Reference

Example cURL Post Transcript

Make sure to remove "translate": "to_eng" if you need transcription. To start transcription process send a POST request to the API URL:

curl -X POST https://api.salad.com/api/public/organizations/{my-organization}/inference-endpoints/transcribe/jobs \
   -H "Salad-Api-Key: {Your Salad API Key}" \
   -H "Content-Type: application/json" \
   -d '{
      "input": {
         "url": "https://example.com/path/to/file.mp3",
         "return_as_file": true,
         "language_code": "en",
         "translate": "to_eng",
         "sentence_level_timestamps": true,
         "word_level_timestamps": true,
         "diarization": true,
         "sentence_diarization": true,
         "multichannel": true,
         "srt": true,
         "summarize": 100,
         "llm_translation": "german, italian, french, spanish, english, portuguese, hindi, thai",
         "srt_translation": "german, italian, french, spanish, english, portuguese, hindi, thai",
         "custom_vocabulary": "terms devided by comma"
        }
      "webhook": {your webhook url},
      "metadata": {
        "my-job-id": 1234
      }
    }'
Example cURL Get Transcript

To get your transcription send a GET request to job specific URL:

curl https://api.salad.com/api/public/organizations/{my-organization}/inference-endpoints/transcribe/jobs/{job_id} \
   -H "Salad-Api-Key: {Your Salad API Key}"
Tutorial
Step 1

Configure you header to include your unique Salad API URL which can be found above as the variable “API URL”. Also include your unique Salad API key which can be found here as the variable "Salad-Api-Key".

Step 2

Update the JSON "input" parameters to customize your output and switch between transcription and translation.

"url"
URL has to be a downloadable link to a file. We recommend using a file service like S3 or Blob that offers secure presigned URLs. It should look like this https://bucketname.s3.us-east-2.amazonaws.com/filename.mp4?response-content-disposition=inline&X-Amz-Security-Token=IQoJb3JpZ2. You can't use YouTube links, Google Drive, or other file-sharing services if they do not provide downloadable url's.

Send media in any of these formats.

	*Audio:* AIFF, FLAC, M4A, MP3, WAV
	*Video:* MKV, MOV, WEBM, WMA, MP4
“return_as_file”
Set to "true" to receive the transcription output as a downloadable file URL, especially useful for large responses. Set to "false" (default) to receive the full transcription in the API response.

Note: If the response exceeds 1 MB in size, it will automatically be returned as a link to a file, regardless of the return_as_file setting.

“language_code”
Transcription is available in 97 languages. We automatically identify the source language. In order to make diarization more accurate, please provide your transcription language.

“sentence_level_timestamps”
Sentence level timestamps are returned on default. Set to false if not needed.

“word_level_timestamps”
Set to "true" for word level timestamps. Set to "false” on default.

“diarization”
Set to "true" for speaker separation and identification. Set to "false” on default.

Diarization requires the language_code to be defined. By default, it is set to "en" (English).

You can also diarize in "fr" (French), "de" (German), "es" (Spanish), "it" (Italian), "ja" (Japanese), "zh" (Chinese), "nl" (Dutch), "uk" (Ukrainian), "pt" (Portuguese), "ar" (Arabic), "cs” (Czech), "ru" (Russian), "pl" (Polish), "hu" (Hungarian), "fi" (Finnish), "fa" (Persian), "el" (Greek), "tr" (Turkish), "da" (Danish), "he" (Hebrew), "vi" (Vietnamese), "ko" (Korean), "ur" (Urdu), "te" (Telugu), "hi" (Hindi), "ca" (Catalan), "ml" (Malayalam).

“sentence_diarization”
Set to "true" to return speaker information at the sentence level. If several speakers are identified in one sentence, the most prominent one will be returned. Set to "false” by default.

“multichannel”
Set to "true" to transcribe audio with multiple speaker channels. Requires "diarization" or "sentence_diarization" to produce speaker/channel labels.
If the file contains only one audio channel, it will fall back to standard diarization.
Multichannel transcription is supported for all languages and incurs no additional cost, but may increase processing time by approximately 25%.

“srt”
Set to "true" to generate a .srt output for caption and subtitles. Set to "false” on default.

“translate”
We are excited to announce that we've added translation to English to our service. To enable translation, you need to specify the following parameter: "translate": "to_eng". When using translation, you can still add other features such as SRT generation, timestamps, and diarization. Note that if you use translation, the original transcription is not returned. Translation is currently available for translation from single language to English only.

"summarize"
Set to a positive integer to receive a summary of the transcription in the specified number of words or less. For example, "summarize": 100 will provide a summary of up to 100 words. Set to 0 (default) if summarization is not needed.

"llm_translation"
Leverage our new LLM integration to translate the transcription in between multiple languages. Provide a comma-separated list of target languages in English. For example:

"llm_translation": "german, italian, french, spanish, english, portuguese, hindi, thai"
Supported languages for LLM translation are: English, French, German, Italian, Portuguese, Hindi, Spanish, and Thai.

"srt_translation"
Use our LLM integration to translate the generated SRT captions into multiple languages. Provide a comma-separated list of target languages in English, similar to llm_translation. Same languages are supported.

"custom_vocabulary" (in preview)
Provide a comma-separated list of terms or phrases that are specific to your transcription context. This helps improve transcription accuracy for domain-specific terminology.

"custom_prompt"
Provide a custom instruction for the LLM to perform a specific task on the transcription, such as grammar improvement or text style change. For example:

"custom_prompt": "Correct all grammar mistakes"
"webhook"
*Optional. Webhook is a method that enables application to transmit data to another application immediately when process is finished. Specify your webhook url to use.

"my-job-id"
*Optional. If you need an identifier from your system you can the job id as desired.

Step 3

Make your POST transcript request. If successful, you will recieve a confirmation response that will include the job "id" *(ex: 00-681d01e03cec5f7122952100b66f2330-aa5b353301b6bc50-01).

Step 4

Make your GET transcript request. If successful, you will receive a JSON transcript output that will include the inputs you requested.

Note: If the response size exceeds 1 MB, the output will automatically be returned as a link to a file, even if "return_as_file" is set to false.

Example Transcript Output

{
  "id": "54e84442-3576-45ca-904c-a1d90bc77baf",
  "input": {
    "url": "https://example.com/path/to/file.mp3",
    "language_code": "en",
    "word_level_timestamps": true,
    "diarization": true,
    "srt": true,
    "summarize": 10,
    "llm_translation": "german, italian",
    "custom_prompt": "Provide a brief analysis of the following conversation."
  },
  "metadata": {
    "my-job-id": 1234
  },
  "status": "succeeded",
  "events": [
    {
      "action": "created",
      "time": "2024-05-15T23:49:37.9946816+00:00"
    },
    {
      "action": "started",
      "time": "2024-05-15T23:50:23.0483322+00:00"
    },
    {
      "action": "succeeded",
      "time": "2024-05-15T23:50:23.4688229+00:00"
    }
  ],
  "output": {
    "sentence_level_timestamps": [
            {
                "text": "Thank you.",
                "timestamp": [
                    19.66,
                    19.90
                ],
                "start": 19.66,
                "end": 19.90,
                "speaker": "SPEAKER_0",
                "channel": "0",
            }
        ],
    "word_segments": [
      {
        "word": "Thank",
        "start": 19.662,
        "end": 19.783,
        "score": 0.232,
        "speaker": "SPEAKER_0",
        "channel": "0"
      },
      {
        "word": "you.",
        "start": 19.803,
        "end": 19.903,
        "score": 0.545,
        "speaker": "SPEAKER_0",
        "channel": "0"
      }
    ],
    "srt_content": "1
00:00:19,2 --> 00:00:19,903
Thank you.",
  "summary": "This conversation expresses gratitude.",
  "llm_translations": {
      "German": "Danke.",
      "Italian": "Grazie."
    },
    "custom_prompt_result": "The conversation shows appreciation from one party to another.",
    "duration": 10.7795,
    "processing_time": 2.17370915412903
  },
  "create_time": "2024-05-15T23:49:37.9946816+00:00",
  "update_time": "2024-05-15T23:50:23.4688229+00:00"
}
If the response size exceeds 1 MB, the output will be provided as a link to a file:

{
  "id": "abcd1234-5678-90ab-cdef-1234567890ab",
  "input": {
    "url": "https://example.com/path/to/large_file.mp3",
    "language_code": "en",
    "word_level_timestamps": true,
    "diarization": true,
    "srt": true,
    "return_as_file": true
  },
  "metadata": {
    "my-job-id": 5678
  },
  "status": "succeeded",
  "events": [
    {
      "action": "created",
      "time": "2024-05-16T10:00:00.0000000+00:00"
    },
    {
      "action": "started",
      "time": "2024-05-16T10:01:00.0000000+00:00"
    },
    {
      "action": "succeeded",
      "time": "2024-05-16T10:30:00.0000000+00:00"
    }
  ],
  "output": {
    "url": "link to the result file",
    "duration": 0.62,
    "processing_time": 1702.6259961128235
  },
  "create_time": "2024-05-16T10:00:00.0000000+00:00",
  "update_time": "2024-05-16T10:30:00.0000000+00:00"
}
Status

“pending”, it has not yet been picked up for processing.

“created” the transcription job is now in our queue to be processed.

“running” the transcription is processing.

“failed” the transcript was not created. We will automatically re-try the transcription process until it fails three times. If we cannot transcribe your media, you will get a 200 error with one of the following messages. If this happens, send us a support request at support@salad.com.

"succeeded" the transcript is ready. If we were not able to pull your url, or there was another issue with the audio file you will see an "error" in the response and one of the reasons:

*File size is more than 3GB.

*The file can not be downloaded, or the duration is missing.

*File duration is more than 2.5 hours
