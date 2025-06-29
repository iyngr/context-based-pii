# Progress

This file tracks the project's progress using a task list format.
2025-06-03 12:58:02 - Log of updates made.

*

## Completed Tasks

*   Define the "end of call" signal mechanism.
*   Design the data structure for storing raw transcripts in `subscriber_service`.
*   Research Google Cloud Conversation Insights API for transcript ingestion requirements.
*   Develop a new service or enhance `subscriber_service` for post-call redaction and Insights API calls.
*   Implemented `transcript_aggregator_service` including architecture, Pub/Sub handlers, Firestore integration, CCAI integration, logging, and error handling.
*   Populated `Dockerfile` and `requirements.txt` for `transcript_aggregator_service`.
*   Outlined manual steps for GCP resource creation for `transcript_aggregator_service` (Pub/Sub subscriptions, Firestore instance, service account, IAM permissions).
*   Resolved all outstanding errors (`Location Mismatch` and `AlreadyExists`) in `transcript_aggregator_service`.
*   Resolved `400 InvalidArgument` error in `transcript_aggregator_service`.
*   Enhanced DLP template handling and error reporting in `main_service`.
*   Refactored `call_dlp_for_redaction` to use `GOOGLE_CLOUD_PROJECT` environment variable.
*   Resolved "project_id is not defined" errors in `main_service/main.py`.
*   Resolved "Invalid built-in info type name" error for custom info types in `main_service/main.py`.

## Current Tasks

*   Update `productContext.md` with new client requirements.
*   Update `decisionLog.md` with the architectural decision for post-call redaction.
*   Update `activeContext.md` with current focus and open questions.
*   Verify DLP template existence and permissions in GCP (if the error persists).
*   Instructing user to verify and grant necessary IAM permissions for the `main_service` service account to access DLP templates.
*   Investigating DLP template access permissions for the `main_service` Cloud Run service account.

## Next Steps

*   Configure Pub/Sub push subscriptions for `transcript_aggregator_service`.
*   Implement monitoring and alerting for `transcript_aggregator_service`.
[2025-06-15 20:21:51] - Successfully deployed `transcript_aggregator_service` to Google Cloud Run with min-instances=0 and max-instances=1.
2025-06-03 02:20:45 - **Updated `main_service` and Redeployed:** The `main_service/main.py` logic for DLP redaction has been refined to ensure comprehensive PII scanning even when a specific PII type is expected. The Docker image has been rebuilt and pushed to GCR, and the Cloud Run service is ready for re-testing.
2025-06-03 02:23:38 - **Image Naming Convention Update:** Adopting `context-manager-service-image` for GCR image tagging and deployment to align with existing repository names.
2025-06-03 02:40:11 - **Cloud Run Service Name Correction:** Decided to redeploy to the existing `context-manager` Cloud Run service instead of creating a new `context-manager-service` instance, to maintain a cleaner deployment environment.
2025-06-03 03:05:31 - **Next Steps for End-to-End Testing:** Configure Google Cloud Secret Manager secrets for `subscriber_service` (`SUBSCRIBER_CONTEXT_MANAGER_URL`, `SUBSCRIBER_REDACTED_TOPIC_NAME`, `SUBSCRIBER_GCP_PROJECT_ID`) and redeploy the `transcript-processor` Cloud Function.
[2025-06-15 03:58:40] - Debugged and resolved `SUBSCRIBER_CONTEXT_MANAGER_URL` secret loading issue in `subscriber-service`. Confirmed end-to-end flow is working.
[2025-06-15 03:47:28] - Storing the monitoring and alerting outline in `docs/resource-monitoring.md`.
[2025-06-16 02:39:25] - **Deployment Commands for Services:**
*   **`transcript_aggregator_service`**:
    ```bash
    cd transcript_aggregator_service && gcloud run deploy transcript-aggregator-service --source . --region us-central1 --project YOUR_GCP_PROJECT_ID --allow-unauthenticated --set-env-vars CONTEXT_TTL_SECONDS=3600 --set-env-vars GOOGLE_CLOUD_PROJECT=PROJECT_ID --set-env-vars AGGREGATED_TRANSCRIPTS_BUCKET=pg-transcript --min-instances=0 --max-instances=1
    ```
*   **`main_service` (Context Manager Service)**:
    ```bash
    cd main_service && gcloud run deploy context-manager --source . --region us-central1 --project PROJECT_ID --allow-unauthenticated --set-env-vars GOOGLE_CLOUD_PROJECT=PROJECT_ID --set-env-vars CONTEXT_TTL_SECONDS=90 --min-instances=0 --max-instances=1
    ```
*   **`subscriber_service`**:
    ```bash
    cd subscriber_service && gcloud run deploy subscriber-service --source . --region us-central1 --project PROJECT_ID --allow-unauthenticated --set-env-vars GCP_PROJECT_ID_FOR_SECRETS=PROJECT_ID --min-instances=0 --max-instances=1
    ```
2025-06-22 14:13:30 - Completed CI/CD setup: Created Artifact Registry repo, implemented service-specific Cloud Build files and triggers, connected GitHub, and configured service account permissions. Resolved build and deployment permission errors.