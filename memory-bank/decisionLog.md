# Decision Log

This file records architectural and implementation decisions using a list format.
2025-06-03 12:58:10 - Log of updates made.

*

## Decision

*

## Rationale

*

## Implementation Details

*
[2025-06-03 01:11:00] - **Decision:** Implement post-call PII redaction and direct integration with Google Cloud Conversation Insights API, bypassing Agent Assist's built-in "Send to Insights" and "Export conversations to insights" options.
**Rationale:** Client requirement to allow raw transcripts for Agent Assist PII verification during the call, while ensuring only redacted PII flows to Conversation Insights for analytics. This necessitates a custom redaction and ingestion pipeline.
**Implementation Details:**
    *   The `subscriber_service` will be enhanced to temporarily store raw utterances for a conversation.
    *   Upon call termination (signal to be determined), the aggregated raw transcript will be sent to the `main_service` for comprehensive PII redaction.
    *   A new component within the `subscriber_service` (or a new dedicated service) will be responsible for calling the Google Cloud Conversation Insights API with the fully redacted and chronologically ordered transcript.
2025-06-03 01:53:37 - **Decision:** Deploy `main_service` and `subscriber_service` to Google Cloud Run/Functions.
**Rationale:** This deployment strategy enables access to Redis (Valkey) from the Cloud Run environment.
**Implementation Details:**
    *   Service accounts for Cloud Run services must have appropriate permissions to access Secret Manager (for Redis host/port/DLP project ID) and Google Cloud DLP.
    *   Redis connectivity does not require a Serverless VPC Access connector.
2025-06-03 03:40:16 - Established Pub/Sub Topic Names:
- Raw Transcripts Topic: `raw-transcripts`
- Redacted Transcripts Topic: `redacted-transcripts`
[2025-06-08 02:14:08] - **Decision:** Introduce a new `transcript_aggregator_service` to handle conversation aggregation, end-of-call detection, and ingestion into Google Cloud Conversation Insights.
**Rationale:** To improve maintainability, scalability, and separation of concerns by offloading complex aggregation and ingestion logic from the `subscriber_service`.
**Implementation Details:**
    *   The `subscriber_service` will publish individual redacted utterances to the `redacted-transcripts` Pub/Sub topic.
    *   The `transcript_aggregator_service` will subscribe to `redacted-transcripts`.
    *   It will use a persistent temporary store (e.g., Firestore or Redis) to group utterances by `conversation_id` and order them by timestamp.
    *   Conversation end detection will be implemented using strategies like timeouts or explicit end signals.
    *   Upon conversation completion, it will assemble the full redacted transcript and call the Google Cloud Conversation Insights API.
[2025-06-08 02:24:05] - **Decision:** Utilize Google Cloud Contact Center AI (CCAI) lifecycle notifications (specifically "conversation ended" messages) as the definitive trigger for conversation aggregation and ingestion into Conversation Insights.
**Rationale:** Provides a more robust and reliable "end of conversation" signal compared to timeout-based mechanisms.
**Implementation Details:**
    *   The `transcript_aggregator_service` will subscribe to the Pub/Sub topic where CCAI publishes lifecycle events.
    *   Individual redacted utterances will continue to be published by `subscriber_service` to `redacted-transcripts` and stored by `transcript_aggregator_service` in a temporary, queryable store (e.g., Redis or Firestore) keyed by `conversation_id`.
    *   Upon receiving a "conversation ended" notification for a `conversation_id`, the `transcript_aggregator_service` will retrieve all associated utterances from temporary storage, sort them, assemble the full transcript, and then call the Conversation Insights API.
    *   Relying solely on Pub/Sub's message backlog for aggregation is not recommended due to inefficiency in querying and managing acknowledged messages.
[2025-06-15 03:55:00] - Resolved `SUBSCRIBER_CONTEXT_MANAGER_URL` secret loading issue in `subscriber-service`.

## Decision
The `GCP_PROJECT_ID_FOR_SECRETS` environment variable was not being correctly loaded by the Cloud Run service, leading to the failure to fetch secrets.

## Rationale
The problem was multi-faceted:
1.  **`gcloud run deploy` command:** Initially, `--set-env-vars` with comma-separated values for multiple variables sometimes caused parsing issues. Separating them into individual `--set-env-vars` flags resolved this.
2.  **`subscriber_service/main.py` initialization:** The `GCP_PROJECT_ID_FOR_SECRETS` was being retrieved at the global scope, which meant it was evaluated before the Cloud Run environment variables were fully available. Moving the `os.getenv()` call into the `load_secrets()` function and explicitly passing this value to `get_secret()` calls ensured correct retrieval at runtime.

## Implementation Details
- Modified `deployment_plan.md` to use separate `--set-env-vars` flags for `PUBSUB_TOPIC` and `GCP_PROJECT_ID_FOR_SECRETS`.
- Modified `subscriber_service/main.py`:
    - Moved `GCP_PROJECT_ID_FOR_SECRETS = os.getenv("GCP_PROJECT_ID_FOR_SECRETS")` inside the `load_secrets()` function.
    - Updated `get_secret()` calls within `load_secrets()` to explicitly pass `project_id=GCP_PROJECT_ID_FOR_SECRETS`.