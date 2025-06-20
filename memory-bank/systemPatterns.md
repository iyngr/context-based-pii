# System Patterns *Optional*

This file documents recurring patterns and standards used in the project.
It is optional, but recommended to be updated as the project evolves.
2025-06-03 12:58:18 - Log of updates made.

*

## Coding Patterns

*   

## Architectural Patterns

*   

## Testing Patterns

*
[2025-06-03 01:11:40] - **Post-Call PII Redaction and Conversation Insights Integration:**
    *   **Pattern:** Raw transcripts flow to Agent Assist for real-time PII verification. Post-call, a dedicated process redacts PII and sends the full, ordered transcript to Google Cloud Conversation Insights.
    *   **Components:**
        *   **Agent Assist:** Configured to *not* send data to Conversation Insights directly. Publishes raw transcripts to Pub/Sub.
        *   **`subscriber_service`:** Subscribes to raw transcript Pub/Sub. Temporarily stores raw utterances (e.g., in Redis) per `conversation_id`. Upon "end of call" signal, retrieves, aggregates, and orders the full raw transcript.
        *   **`main_service`:** Provides a new endpoint for comprehensive, post-call PII redaction of entire conversation transcripts.
        *   **Conversation Insights Ingestion Component (within `subscriber_service` or new service):** Calls Google Cloud Conversation Insights API with the fully redacted and chronologically ordered transcript.
    *   **Rationale:** Addresses client requirement for raw transcripts in Agent Assist while ensuring PII redaction for Conversation Insights.
    *   **Implications:** Requires robust "end of call" detection, efficient temporary storage, and careful handling of transcript ordering for Insights API.
2025-06-03 01:58:18 - **Command Compatibility Pattern:** All CLI commands generated for execution must be compatible with Windows PowerShell and CMD. This means avoiding multi-line commands or characters that are not interpreted correctly by these shells, and properly escaping special characters (e.g., double quotes within JSON payloads).
2025-06-03 02:00:05 - **Complex Payload Handling Pattern:** For `curl` commands involving complex JSON payloads, create a temporary `.json` file containing the payload. Use `curl -d @filename.json` to send the content, which is more robust across different shell environments (e.g., Windows PowerShell/CMD) than inline escaping.
2025-06-03 02:05:54 - **Windows `curl` File Payload Workaround:** When using `curl.exe` with file-based payloads (`-d @filename.json`) on Windows, especially in PowerShell, wrap the `curl` command within `cmd /c "..."` to ensure correct interpretation of the `@` symbol and prevent PowerShell's splatting operator interference.
2025-06-03 02:26:12 - **Container Registry Pattern:** Using Google Artifact Registry (GAR) for Docker image storage. Images will be tagged and pushed to `[REGION]-docker.pkg.dev/YOUR_GCP_PROJECT_ID/[REPOSITORY_NAME]/[IMAGE_NAME]:[TAG]`.
2025-06-03 02:33:25 - **Preferred Docker Build Method:** Exclusively use `gcloud builds submit` for building and pushing Docker images to Google Artifact Registry (GAR). `docker build` and `docker push` commands should NOT be suggested. This method performs builds in the cloud, eliminating the need for a local Docker daemon and directly pushing the image to the specified registry.