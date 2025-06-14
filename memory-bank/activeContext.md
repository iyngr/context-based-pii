# Active Context

  This file tracks the project's current status, including recent changes, current goals, and open questions.
  2025-06-03 12:57:56 - Log of updates made.

*

## Current Focus

*   Designing the post-call PII redaction and Conversation Insights integration.

## Recent Changes

*   Updated `productContext.md` and `decisionLog.md` to reflect new client requirements for PII handling.

## Open Questions/Issues

*   How to reliably signal the "end of call" to trigger post-call processing?
*   What is the exact format required by the Conversation Insights API for transcript ingestion, especially regarding message ordering?
*   How to ensure the `subscriber_service` can store and retrieve full conversation transcripts efficiently for post-call processing?
2025-06-03 03:05:04 - **Cloud Function `transcript-processor` Details:**
    *   **Entry Point:** `process_transcript_event`
    *   **Trigger Topic:** `projects/Project_ID/topics/raw-transcripts`
    *   **Service Account:** `transcript-processor-sa\1***\3`
2025-06-15 03:14:20 - User reported "Method Not Allowed" when accessing `subscriber-service` URL directly. This is expected behavior as it's a Pub/Sub subscriber, not a web server.
2025-06-15 03:15:04 - User re-iterated concern about "Method Not Allowed" error for `subscriber-service` URL. Need to re-confirm expected behavior and deployment success.