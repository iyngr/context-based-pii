# CCAI Agent Assist Data Redaction System

## 1. System Overview

This system processes agent and customer transcripts from Google Cloud Contact Center AI (CCAI). Its primary purpose is to redact Personally Identifiable Information (PII) from these transcripts using Google Cloud Data Loss Prevention (DLP) and to manage conversation context using a Google Cloud Memorystore for Redis instance.

The system consists of two main components:

*   **`main_service`**: A Flask application deployed on Google Cloud Run. It is responsible for handling transcript utterances, interacting with Redis for conversation context, and invoking the Google Cloud DLP API for PII redaction.
*   **`subscriber_service`**: A Google Cloud Function triggered by Pub/Sub messages that contain raw transcripts. This service calls the `main_service` to process the transcripts and then publishes the redacted versions.

## 2. File Structure

```
.
├── .gcloudignore
├── Deployment-plan.md
├── Dockerfile  // Note: Purpose of this root Dockerfile? Builds target main_service/Dockerfile.
├── main_service/
│   ├── Dockerfile
│   ├── main.py       // Flask app, Redis, DLP logic
│   └── requirements.txt
└── subscriber_service/
    ├── main.py       // Cloud Function entry point (process_transcript_event)
    ├── requirements.txt
    └── subscriber.py // Note: Appears to be unused or duplicate of main.py?
```

## 3. Core Functionality

### `main_service/main.py`

*   A Flask application serving endpoints such as `/handle-agent-utterance` and `/handle-customer-utterance`.
*   Fetches essential configuration (e.g., Redis host/port, DLP Project ID) from Google Cloud Secret Manager.
*   Connects to a Google Cloud Memorystore for Redis (standalone instance) to store and retrieve conversation context. This context can include information like `expected_pii_type`.
*   Utilizes the Google Cloud DLP API to perform PII redaction on the transcript data.

### `subscriber_service/main.py`

*   A Google Cloud Function that is triggered by new messages published to the `raw-transcripts` Pub/Sub topic.
*   Parses incoming transcript data, expecting a `sessionId` within the `conversation_info` field.
*   Makes HTTP POST requests to the relevant endpoints exposed by the `main_service`.
*   Publishes the redacted transcript (specifically for customer utterances) to the `redacted-transcripts` Pub/Sub topic.
*   Fetches its configuration (e.g., `main_service` URL, output Pub/Sub topic name) from Google Cloud Secret Manager.

## 4. Google Cloud Resources Used (Production Configuration)

*   **Project ID:** `Project_ID`
*   **Region:** `us-central1` (for Cloud Run, Cloud Function, Memorystore, VPC Connector)
*   **Cloud Run Service (`main_service`):**
    *   Name: `context-manager`
    *   Deployed Image: `gcr.io/Project_ID/context-manager-image`
    *   Service Account: `context-manager-sa\1***\3`
*   **Cloud Function (`subscriber_service`):**
    *   Name: `transcript-processor`
    *   Runtime: `python311`
    *   Entry Point: `process_transcript_event` (in `subscriber_service/main.py`)
    *   Service Account: `transcript-processor-sa\1***\3`
*   **Pub/Sub Topics:**
    *   Input Topic (for raw transcripts): `raw-transcripts`
    *   Output Topic (for redacted transcripts): `redacted-transcripts`
*   **Memorystore for Redis (Standalone Instance):**
    *   Network: `default` VPC in `Project_ID`
    *   Private IP Address: `\1.***.\2.\3`
    *   Port: `6379`
    *   In-transit encryption: **Disabled**
*   **Serverless VPC Access Connector:**
    *   Name: `redis-connector`
    *   Network: `default`
    *   Region: `us-central1`
    *   IP Range: `\1.***.\2.\3/28` (Example, confirm actual if different)
*   **Secrets in Google Cloud Secret Manager:**
    *   `CONTEXT_MANAGER_REDIS_HOST`: Value `\1.***.\2.\3`
    *   `CONTEXT_MANAGER_REDIS_PORT`: Value `6379`
    *   `CONTEXT_MANAGER_DLP_PROJECT_ID`: Value `Project_ID`
    *   `SUBSCRIBER_CONTEXT_MANAGER_URL`: Value `https://context-manager-***.us-central1.run.app`
    *   `SUBSCRIBER_REDACTED_TOPIC_NAME`: Value `redacted-transcripts`
    *   `SUBSCRIBER_GCP_PROJECT_ID`: Value `Project_ID`

## 5. Build and Deployment Instructions

### Prerequisites

*   Google Cloud SDK installed and authenticated.
*   Target Google Cloud project (`Project_ID`) selected (`gcloud config set project Project_ID`).
*   Required APIs enabled:
    *   Cloud Run API (`run.googleapis.com`)
    *   Cloud Functions API (`cloudfunctions.googleapis.com`)
    *   Pub/Sub API (`pubsub.googleapis.com`)
    *   Cloud Build API (`cloudbuild.googleapis.com`)
    *   Compute Engine API (`compute.googleapis.com`) (for VPC Connector)
    *   Memorystore for Redis API (`redis.googleapis.com`)
    *   Cloud Data Loss Prevention (DLP) API (`dlp.googleapis.com`)
    *   Identity and Access Management (IAM) API (`iam.googleapis.com`)
    *   Secret Manager API (`secretmanager.googleapis.com`)
    *   Artifact Registry API (`artifactregistry.googleapis.com`) (if `gcr.io` is an alias or if using Artifact Registry directly)
*   Service accounts created with appropriate IAM roles:
    *   `context-manager-sa\1***\3`:
        *   Secret Manager Secret Accessor (`roles/secretmanager.secretAccessor`)
        *   Redis Client (`roles/redis.client`)
        *   DLP User (`roles/dlp.user`)
    *   `transcript-processor-sa\1***\3`:
        *   Secret Manager Secret Accessor (`roles/secretmanager.secretAccessor`)
        *   Pub/Sub Publisher (`roles/pubsub.publisher`)
        *   Cloud Run Invoker (`roles/run.invoker`) (to call `main_service`)
*   Pub/Sub topics created:
    *   `raw-transcripts`
    *   `redacted-transcripts`
*   Memorystore for Redis instance created in the `default` VPC, `us-central1` region, with in-transit encryption disabled. Note its private IP address.
*   Serverless VPC Access connector (`redis-connector`) created in the `default` VPC, `us-central1` region, connected to the appropriate network.
*   All secrets listed in the "Secrets in Google Cloud Secret Manager" section created and populated with their respective values.

### Build `main_service` Docker Image

```bash
# Ensure you are in the project root directory (where main_service/ directory exists)
gcloud builds submit --tag gcr.io/Project_ID/context-manager-image ./main_service --project=Project_ID
```

### Deploy `main_service` to Cloud Run

```bash
gcloud run deploy context-manager \
  --image gcr.io/Project_ID/context-manager-image \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --service-account context-manager-sa\1***\3 \
  --project=Project_ID \
  --vpc-connector redis-connector \
  --vpc-egress all
```
*Note: After deployment, if the service URL for `context-manager` changes (e.g., due to redeployment or a new revision becoming default), you **must** update the `SUBSCRIBER_CONTEXT_MANAGER_URL` secret in Secret Manager to reflect the new URL.*

### Deploy `subscriber_service` Cloud Function

```bash
# Ensure you are in the project root directory (where subscriber_service/ directory exists)
gcloud functions deploy transcript-processor \
  --runtime python311 \
  --trigger-topic raw-transcripts \
  --entry-point process_transcript_event \
  --region us-central1 \
  --service-account transcript-processor-sa\1***\3 \
  --source ./subscriber_service \
  --project=Project_ID \
  --clear-vpc-connector \
  --egress-settings all