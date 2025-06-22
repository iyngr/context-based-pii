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
[2025-06-15 03:36:17] - **Decision:** Google Cloud Firestore instance `redacted-transcript-db` created.
**Rationale:** To provide temporary storage for utterances for the `transcript_aggregator_service`.
**Implementation Details:**
    *   **Database ID:** `redacted-transcript-db`
    *   **Edition:** Standard Edition
    *   **Mode:** Firestore Native
    *   **Security Rules:** Open (for now, to be restricted later)
    *   **Region:** `us-central1`
[2025-06-15 04:01:37] - **Decision:** `transcript_aggregator_service` has been fully implemented.
**Rationale:** This service centralizes conversation aggregation, end-of-call detection, and ingestion into Google Cloud Conversation Insights, improving maintainability, scalability, and separation of concerns.
**Implementation Details:**
    *   Subscribes to `redacted-transcripts` Pub/Sub topic.
    *   Utilizes Google Cloud Firestore (`redacted-transcript-db`) for persistent temporary storage of utterances, grouped by `conversation_id` and ordered by timestamp.
    *   Detects conversation end using CCAI lifecycle notifications (specifically "conversation ended" messages) from a dedicated Pub/Sub topic.
    *   Upon conversation completion, retrieves all associated utterances from Firestore, assembles the full redacted transcript, and calls the Google Cloud Conversation Insights API.
    *   Includes robust logging and error handling.
    *   `Dockerfile` and `requirements.txt` are configured for deployment.
[2025-06-15 20:23:17] - **Decision:** Resolved `gunicorn: not found` error and `app.run()` conflict in `transcript_aggregator_service` deployment.
**Rationale:** The `gunicorn: not found` error indicated that the `gunicorn` package was not installed in the container. The `app.run()` call in `main.py` was conflicting with Gunicorn's startup process.
**Implementation Details:**
    *   Added `gunicorn` to `transcript_aggregator_service/requirements.txt`.
    *   Removed the `if __name__ == '__main__':` block and `app.run()` call from `transcript_aggregator_service/main.py`.
    *   Modified `transcript_aggregator_service/Dockerfile` to use the array form for `CMD` and directly specify the port for Gunicorn.
[2025-06-18 07:32:31] - **Decision:** Resolved `400 Error redacting conversation: com.google.cloud.privacy.dlp.common.exceptions.InvalidInputException: location must be set to the region's name when calling regional instance us-central1` in `transcript_aggregator_service`.
**Note:** The explicit project ID for DLP templates was later removed from the code and replaced with a placeholder in `dlp_config.yaml` for security and reusability.
**Rationale:** The Contact Center AI (CCAI) service was not being explicitly configured with the DLP region, causing its internal DLP calls to fail.
**Implementation Details:**
    *   Added a `dlp_config.json` to the `transcript_aggregator_service`.
    *   Modified `transcript_aggregator_service/main.py` to:
        *   Initialize the Google Cloud DLP client with the correct regional endpoint.
        *   Load the DLP configuration from `dlp_config.json`.
        *   Create persistent DLP inspection and de-identification templates if they don't already exist.
        *   Pass the resource names of these templates in the `redaction_config` of the `UploadConversationRequest`.
        *   **Note:** The explicit project ID for DLP templates was later removed from the code and replaced with a placeholder in `dlp_config.yaml` for security and reusability.
[2025-06-18 08:00:58] - **Decision:** Added a 60-second timeout to the `deidentify_content` DLP API call in `main_service`.
**Rationale:** The service was experiencing 300-second timeouts when calling the DLP API, indicating a network connectivity issue. Adding a shorter timeout prevents the service from hanging and allows it to fail faster.
**Implementation Details:**
    *   Modified the `call_dlp_for_redaction` function in `main_service/main.py` to include a `timeout=60` parameter in the `dlp_client.deidentify_content` call.
[2025-06-18 08:20:05] - **Decision:** Rolled back all DLP-related changes in `main_service` and `transcript_aggregator_service`.
**Rationale:** The user requested to revert all DLP changes to restore the services to their previous state before further debugging.
**Implementation Details:**
    *   Reverted changes in `main_service/main.py` to remove the DLP client location logic and timeout.
    *   Removed `google-api-core` from `main_service/requirements.txt`.
    *   Reverted changes in `transcript_aggregator_service/main.py` to remove the DLP client, config loading, and redaction logic.
    *   Deleted `transcript_aggregator_service/dlp_config.json`.
    *   Confirmed `google-cloud-dlp` was removed from `transcript_aggregator_service/requirements.txt`.
[2025-06-18 08:53:25] - **Decision:** Resolved `400 InvalidArgument` error in `transcript_aggregator_service` by explicitly setting the client endpoint for the Contact Center Insights API.
**Rationale:** The error `location must be set to the region's name when calling regional instance` indicated that the CCAI client was not using the correct regional endpoint, causing a mismatch when the service internally called the DLP API. The user confirmed that their resources are in `us-east1`.
**Implementation Details:**
    *   Modified `transcript_aggregator_service/main.py` to initialize the `contact_center_insights_v1.ContactCenterInsightsClient` with `client_options` that specify the regional API endpoint (e.g., `us-central1-contactcenterinsights.googleapis.com`).
    *   Updated the default location to `us-central1`, while still allowing it to be overridden by the `CCAI_LOCATION` environment variable.
[2025-06-18 09:24:21] - **Decision:** Implemented a definitive fix for the recurring `Location Mismatch` and `409 AlreadyExists` errors in `transcript_aggregator_service`.
**Rationale:** The root cause of the location error was a conflicting client initialization that overwrote the correctly configured global client. The `AlreadyExists` error was caused by non-idempotent processing of re-delivered Pub/Sub messages.
**Implementation Details:**
    *   Removed the conflicting local `ContactCenterInsightsClient` initialization from the `receive_conversation_ended_event` function.
    *   Standardized on a single, correctly configured client initialization within the function, ensuring the `us-central1` endpoint is always used.
    *   Wrapped the CCAI upload call in a `try...except AlreadyExists` block. If a conversation already exists, the error is logged as a warning, and the process continues to the Firestore cleanup step, ensuring idempotency.
[2025-06-20 06:08:00] - **Decision:** Enhanced DLP template handling in `main_service` and improved error reporting for `NotFound` exceptions.
**Rationale:** The `404 Requested inspect template not found` error indicated that the `main_service` was failing when DLP inspect/de-identify templates were not found or configured incorrectly. The previous rollback of DLP changes likely contributed to this. This change makes the service more resilient and provides clearer debugging information.
**Implementation Details:**
   *   Modified `main_service/main.py` to ensure that if `inspect_template_name` is not provided in `dlp_config.yaml`, the `inspect_config` defined directly in `dlp_config.yaml` is used as a fallback.
   *   Implemented logic to merge dynamic `inspect_config` adjustments (from `context`) with the base `inspect_config` (either from a template or the YAML file), specifically handling `info_types` and `rule_set` to avoid duplicates and extend existing configurations.
   *   Added specific `try...except NotFound` block around the `dlp_client.deidentify_content` call in `main_service/main.py` to catch `404 Not Found` errors and provide a more informative log message, explicitly mentioning the missing templates and project ID.
[2025-06-20 06:10:00] - **Decision:** Refactored `call_dlp_for_redaction` in `main_service/main.py` to directly use the `GOOGLE_CLOUD_PROJECT` environment variable for DLP operations instead of passing `project_id` as a function parameter.
**Rationale:** This aligns with the user's feedback and best practices for Cloud Run services, where the `GOOGLE_CLOUD_PROJECT` environment variable is automatically provided and should be the authoritative source for the project ID. It simplifies the function signature and reduces potential for inconsistencies.
**Implementation Details:**
   *   Removed the `project_id` parameter from the `call_dlp_for_redaction` function signature.
   *   Updated the function to use the globally available `GCP_PROJECT_ID_FOR_SECRETS` (which is derived from `GOOGLE_CLOUD_PROJECT`) for constructing the DLP parent path and replacing the `${PROJECT_ID}` placeholder in DLP template names.
   *   Modified the call to `call_dlp_for_redaction` in `handle_customer_utterance` to no longer pass the `DLP_PROJECT_ID` argument.
[2025-06-20 06:12:15] - **Decision:** Resolved "project_id is not defined" errors in `main_service/main.py`.
**Rationale:** After refactoring `call_dlp_for_redaction` to use the global `GCP_PROJECT_ID_FOR_SECRETS` (derived from `GOOGLE_CLOUD_PROJECT`), some log messages and error messages within the function still incorrectly referenced the removed `project_id` parameter, leading to `reportUndefinedVariable` errors.
**Implementation Details:**
   *   Updated `logger.info` message at line 339 to use `current_gcp_project_id` instead of `project_id`.
   *   Updated the `NotFound` exception log message at line 407 to use `current_gcp_project_id` instead of `project_id`.
[2025-06-20 08:03:00] - **Decision:** The `DLP API Error: Requested inspect/deidentify template not found` error is likely a permission issue, not a missing template issue.
**Rationale:** The user confirmed that the DLP templates already exist. The `NotFound` error from the DLP API when called by `main_service` indicates that the service account running `main_service` does not have the necessary permissions to access or use these templates.
**Implementation Details:**
    *   The service account associated with the `main_service` Cloud Run instance has the following roles:
        *   `roles/artifactregistry.createOnPushWriter`
        *   `roles/artifactregistry.writer`
        *   `roles/cloudbuild.builds.editor`
        *   `roles/developerconnect.readTokenAccessor`
        *   `roles/dlp.admin`
        *   `roles/dlp.deidentifyTemplatesEditor`
        *   `roles/dlp.inspectTemplatesEditor`
        *   `roles/dlp.reader`
        *   `roles/dlp.user`
        *   `roles/iam.serviceAccountUser`
        *   `roles/logging.logWriter`
        *   `roles/memorystore.admin`
        *   `roles/redis.admin`
        *   `roles/redis.dbConnectionUser`
        *   `roles/run.admin`
        *   `roles/secretmanager.secretAccessor`
    *   Given these roles, the service account has more than sufficient permissions for DLP operations, including `dlp.user`, `dlp.admin`, and specific editor/reader roles for templates.
2025-06-22 14:13:38 - **Decision:** Implemented a comprehensive CI/CD pipeline using Google Cloud Build.
**Rationale:** To automate the build and deployment process for each service, ensuring faster iterations and reliable deployments. This includes setting up a new Artifact Registry, service-specific Cloud Build configurations, and triggers integrated with GitHub.
**Implementation Details:**
    *   Created `ccai-services` Artifact Registry repository in `us-central1`.
    *   Developed separate `cloudbuild.yaml` files for `main_service`, `subscriber_service`, and `transcript_aggregator_service`.
    *   Configured three Cloud Build triggers, each monitoring a specific service folder and using "Included files filter" for precise triggering.
    *   Connected Developer Connect GitHub to the project's GitHub repository to enable automatic triggers on `master` branch commits.
    *   Ensured each trigger is associated with a dedicated service account possessing the necessary `Artifact Registry Writer` and `Service Account User` (on itself) permissions to handle image pushes and Cloud Run deployments.
[2025-06-22 15:33:00] - **Decision:** Enhanced error handling in `main_service/main.py` to specifically catch `google.api_core.exceptions.MethodNotImplemented` for DLP API calls.
**Rationale:** The log indicated `501 Received http2 header with status: 404` which maps to `MethodNotImplemented` in `google.api_core.exceptions`. Explicitly catching this exception provides a more precise error message and debugging guidance.
**Implementation Details:**
    *   Added `MethodNotImplemented` to the import list from `google.api_core.exceptions`.
    *   Introduced a specific `except MethodNotImplemented as e:` block in `call_dlp_for_redaction` to handle this error, providing a detailed message about enabling the DLP API, checking service account roles, and verifying template existence.
[2025-06-22 19:06:53] - **Decision:** Resolved `NameError: name 'item' is not defined` in `main_service/main.py`.
**Rationale:** The `item` field in the DLP API request was not correctly populated, leading to a `NameError`.
**Implementation Details:**
    *   Modified `main_service/main.py` at line 376 to change `"item": item` to `"item": {"value": transcript}`. This correctly passes the transcript content to the DLP API.
[2025-06-22 19:06:53] - **Decision:** Confirmed and reinforced the use of global DLP client with regional parent paths for templates in `main_service`.
**Rationale:** To ensure DLP API calls are correctly routed and utilize templates, even when the client is initialized globally. This addresses previous issues related to location mismatches and template access.
**Implementation Details:**
    *   The `dlp_client` is initialized globally without a specific region.
    *   The `parent` parameter for DLP API calls is constructed using `projects/{current_gcp_project_id}/locations/{dlp_location}`, where `dlp_location` is fetched from `dlp_config.yaml` (defaulting to `us-central1`). This ensures that templates are referenced correctly within their respective regions.
[2025-06-22 19:10:52] - **Decision:** Modified DLP inspection configuration logic in `main_service/main.py` to prioritize templates and supplement with dynamic configuration.
**Rationale:** The previous logic for configuring DLP inspection was not optimally prioritizing templates when dynamic context was available. This change ensures that if an `inspect_template_name` is provided, it is used as the primary configuration, and any dynamic `inspect_config` (e.g., for boosting specific infoTypes) is applied as a supplement, rather than overwriting the template. If no template is specified, the fully merged inline configuration is used.
**Implementation Details:**
    *   Modified `main_service/main.py` at lines 379-389 to adjust the conditional logic for setting `request["inspect_template_name"]` and `request["inspect_config"]`.
    *   The new logic checks for `inspect_template_name` first. If present, it sets the template name and then, if `dynamic_inspect_config` exists, it also sets `request["inspect_config"]` to `dynamic_inspect_config` to supplement the template.
    *   If `inspect_template_name` is not present, it falls back to using `final_inline_inspect_config`.
[2025-06-22 19:22:18] - **Decision:** Reverted DLP inspection configuration logic in `main_service/main.py` to ensure all configured `info_types` are considered for redaction.
**Rationale:** The previous modification to prioritize templates and supplement with dynamic configuration was found to be problematic. When both `inspect_template_name` and `inspect_config` are provided in the DLP API request, the API prioritizes the template, effectively ignoring the `inspect_config` which contains the full list of `info_types` from `dlp_config.yaml` and any dynamic rules. This led to missed redactions for `CREDIT_CARD_NUMBER` and `CVV_NUMBER`. The reverted logic ensures that if dynamic adjustments are made, or if no template is specified, the comprehensive `final_inline_inspect_config` (which merges `base_inspect_config_from_yaml` and `dynamic_inspect_config`) is always used as the `inspect_config` parameter.
**Implementation Details:**
    *   Reverted `main_service/main.py` at lines 379-389 to the previous logic:
        *   If `dynamic_inspect_config` is present, `request["inspect_config"]` is set to `final_inline_inspect_config`.
        *   If `inspect_template_name` is present (and no dynamic config), `request["inspect_template_name"]` is used.
        *   Otherwise, `request["inspect_config"]` falls back to `base_inspect_config_from_yaml`.
[2025-06-22 19:38:34] - **Decision:** Refined DLP inspection configuration logic in `main_service/main.py` to ensure explicit inclusion of `expected_pii_type` and correct precedence.
**Rationale:** Despite templates and `dlp_config.yaml` being in sync, redaction for `CREDIT_CARD_NUMBER` and `CVV_NUMBER` was missed. This was due to the DLP API prioritizing `inspect_template_name` over `inspect_config` when both are present, and the `dynamic_inspect_config` not explicitly adding the `expected_pii_type` to its `info_types` list. The `rule_set` for boosting likelihood only works on already considered `info_types`.
**Implementation Details:**
    *   **Reverted `inspect_config` precedence logic:** Modified `main_service/main.py` at lines 386-395 to ensure that if `dynamic_inspect_config` is present (indicating an `expected_pii_type`), the `final_inline_inspect_config` (which is a comprehensive merge of base config and dynamic rules) is always used as `request["inspect_config"]`. The `inspect_template_name` is only used if no dynamic configuration is present.
    *   **Explicitly added `expected_pii_type` to `info_types`:** Inserted logic at line 338 in `main_service/main.py` to explicitly add the `expected_pii_type` (e.g., `CREDIT_CARD_NUMBER`) to the `info_types` list within `final_inline_inspect_config` if it's not already present. This guarantees that DLP is explicitly instructed to look for that specific PII type, in addition to any likelihood boosting rules.
[2025-06-22 19:44:01] - **Decision:** Modified DLP inspection configuration logic in `main_service/main.py` to correctly handle custom info types like `SOCIAL_HANDLE`.
**Rationale:** The previous implementation for dynamically adding `expected_pii_type` to the DLP inspection configuration treated all `expected_type` values as built-in info types. This caused an "Invalid built-in info type name" error when a custom info type like `SOCIAL_HANDLE` was encountered, as custom info types require their full definition (including regex pattern) to be provided under `custom_info_types` in the `inspect_config`.
**Implementation Details:**
    *   Modified `main_service/main.py` at lines 343-352 to differentiate between built-in and custom info types.
    *   The updated logic now checks if the `expected_type` is present in the `custom_info_types` section of `DLP_CONFIG`.
    *   If it's a custom info type, its full definition is added to `final_inline_inspect_config["custom_info_types"]`.
    *   If it's a built-in info type, its name is added to `final_inline_inspect_config["info_types"]`, as before.