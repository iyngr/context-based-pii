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
[2025-06-03 01:11:40] - **Multi-Turn Context-Based PII Redaction and Conversation Insights Integration:**
    *   **Pattern:** Raw transcripts flow to Agent Assist for real-time PII verification. A multi-service pipeline handles PII redaction and ingestion into Google Cloud Conversation Insights.
    *   **Components:**
        *   **Agent Assist:** Publishes raw transcripts to Pub/Sub.
        *   **`subscriber_service`:** Subscribes to raw transcript Pub/Sub, calls `main_service` for redaction, and publishes redacted transcripts.
        *   **`main_service`:** Handles PII redaction using Google Cloud DLP. It maintains multi-turn context in Redis by identifying "expected PII types" from agent utterances, which dynamically influences DLP's likelihood boosting for customer utterances.
        *   **`transcript_aggregator_service`:** Subscribes to redacted transcripts, aggregates conversations using Firestore, detects end-of-call via CCAI lifecycle events, and prepares full transcripts for ingestion.
        *   **`ccai_insights_function`:** A dedicated service responsible for ingesting aggregated transcripts into Google Cloud Conversation Insights.
    *   **Rationale:** Addresses client requirement for raw transcripts in Agent Assist while ensuring only redacted PII flows to Conversation Insights. The multi-turn context in `main_service` improves redaction accuracy.
    *   **Implications:** Requires robust "end of call" detection, efficient temporary storage (Redis for context, Firestore for aggregation), and careful handling of transcript ordering for Insights API.
2025-06-03 01:58:18 - **Command Compatibility Pattern:** All CLI commands generated for execution must be compatible with Windows PowerShell and CMD. This means avoiding multi-line commands or characters that are not interpreted correctly by these shells, and properly escaping special characters (e.g., double quotes within JSON payloads).
2025-06-03 02:00:05 - **Complex Payload Handling Pattern:** For `curl` commands involving complex JSON payloads, create a temporary `.json` file containing the payload. Use `curl -d @filename.json` to send the content, which is more robust across different shell environments (e.g., Windows PowerShell/CMD) than inline escaping.
2025-06-03 02:05:54 - **Windows `curl` File Payload Workaround:** When using `curl.exe` with file-based payloads (`-d @filename.json`) on Windows, especially in PowerShell, wrap the `curl` command within `cmd /c "..."` to ensure correct interpretation of the `@` symbol and prevent PowerShell's splatting operator interference.
2025-06-03 02:26:12 - **Container Registry Pattern:** Using Google Artifact Registry (GAR) for Docker image storage. Images will be tagged and pushed to `[REGION]-docker.pkg.dev/YOUR_GCP_PROJECT_ID/[REPOSITORY_NAME]/[IMAGE_NAME]:[TAG]`.
2025-06-03 02:33:25 - **Preferred Docker Build Method:** Exclusively use `gcloud builds submit` for building and pushing Docker images to Google Artifact Registry (GAR). `docker build` and `docker push` commands should NOT be suggested. This method performs builds in the cloud, eliminating the need for a local Docker daemon and directly pushing the image to the specified registry.
[2025-06-20 09:15:00] - **Monorepo CI/CD Pattern:** Adopted a service-specific CI/CD pipeline using separate Cloud Build triggers for each service (`main_service`, `subscriber_service`, `transcript_aggregator_service`).
    *   **Pattern:** Each service directory contains its own `cloudbuild.yaml`. A dedicated Cloud Build trigger is configured for each service, using an "Included files filter" (e.g., `main_service/**`) to ensure a build is only initiated when code within that specific service's directory is modified.
    *   **Rationale:** This approach optimizes build times and costs by avoiding unnecessary rebuilds of unchanged services. It improves the maintainability of build configurations by keeping them co-located with the service code.
    *   **Implications:** Requires creating and managing multiple triggers instead of a single one. Shared library changes would require a separate strategy if they need to trigger builds for all dependent services.
[2025-06-20 09:18:00] - **Artifact Registry Repository Mode:** All Docker images are stored in a **Standard** Artifact Registry repository.
    *   **Pattern:** A single, regional (`us-central1`) Artifact Registry repository with the "Standard" mode is used as the central storage for all custom-built container images.
    *   **Rationale:** The "Standard" mode is the correct choice for directly pushing and managing first-party artifacts created by the CI/CD pipeline. It provides a secure, private registry. Remote and Virtual repositories can be added later to optimize third-party image caching and simplify client configuration.
[2025-06-20 09:20:00] - **Coding and Dependency Standardization:**
    *   **Pattern:** All services (`main_service`, `subscriber_service`, `transcript_aggregator_service`) are standardized to use the `python:3.12-slim` base Docker image. All Python dependencies in `requirements.txt` files are pinned to specific versions (e.g., `Flask==2.3.2`).
    *   **Rationale:** Using a consistent Python version simplifies the development environment and avoids runtime inconsistencies. Pinning dependencies ensures reproducible builds, preventing unexpected failures caused by upstream library updates.
[2025-06-20 09:22:00] - **Regional Google Cloud Client Initialization Pattern:**
    *   **Pattern:** When interacting with regionalized Google Cloud services like Cloud DLP or Contact Center AI (CCAI), the client library must be initialized with the specific regional API endpoint (e.g., `us-central1-dlp.googleapis.com`).
    *   **Rationale:** Failure to specify the regional endpoint when resources (like DLP templates or CCAI conversations) reside in a specific region can lead to `404 Not Found` or `400 InvalidArgument` errors, even if permissions are correct. The global endpoint (e.g., `dlp.googleapis.com`) cannot access regionalized resources. This pattern was applied to fix errors in both `main_service` (DLP) and `transcript_aggregator_service` (CCAI).