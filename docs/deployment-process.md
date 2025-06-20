# Deployment Plan: CCAI Agent Assist Data Redaction System

This document outlines the steps to deploy the Python-based data redaction system, which comprises a Cloud Run service (`main_service`) and a Cloud Function (`subscriber_service`). This plan emphasizes a "secrets-first" approach using Google Cloud Secret Manager.

**Replace `Project_ID` (formerly `YOUR_PROJECT_ID`) with your actual Google Cloud Project ID if different. This plan uses `Project_ID`.**
Other placeholders (e.g., `us-central1` for region, `ccai-redis-instance` for Redis instance) should also be replaced if your specific values differ from the ones used in this updated plan.

## I. Pre-Deployment Setup

### 1. Enable Necessary Google Cloud APIs
Ensure all required APIs are enabled for your project.
Command:
```bash
gcloud services enable run.googleapis.com \
  cloudfunctions.googleapis.com \
  pubsub.googleapis.com \
  cloudbuild.googleapis.com \
  compute.googleapis.com \
  redis.googleapis.com \
  dlp.googleapis.com \
  iam.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  --project=Project_ID
```

### 2. Plan Resource Names and Configurations
Before creating resources, decide on consistent names and configurations (values used in this plan are specified):
*   **VPC Network:** `default`
*   **Serverless VPC Access Connector Name:** `redis-connector`
*   **Memorystore for Redis (Standalone) Instance:**
    *   Name: `ccai-redis-instance`
    *   Region: `us-central1`
    *   Internal IP Address: This will be `CONTEXT_MANAGER_REDIS_HOST` (Value: `\1.***.\2.\3`).
    *   Port: `6379` (This will be `CONTEXT_MANAGER_REDIS_PORT`).
*   **Pub/Sub Topics:**
    *   Input Raw Transcripts Topic: `raw-transcripts` (This will be `SUBSCRIBER_INPUT_TRANSCRIPT_TOPIC`).
    *   Output Redacted Transcripts Topic: `redacted-transcripts` (This will be `SUBSCRIBER_REDACTED_TOPIC_NAME`).
*   **Service Accounts:**
    *   Cloud Run (`main_service`): `context-manager-sa`
    *   Cloud Function (`subscriber_service`): `transcript-processor-sa`
*   **Cloud Run Service Name (`main_service`):** `context-manager`
*   **Cloud Function Name (`subscriber_service`):** `transcript-processor`
*   **DLP Project ID:** `Project_ID`. This will be `CONTEXT_MANAGER_DLP_PROJECT_ID`.
*   **GCP Project ID (for Secret Manager access):** `Project_ID`. This will be `SUBSCRIBER_GCP_PROJECT_ID`.

### 3. Create Core Infrastructure
*   **VPC Network & Serverless VPC Access Connector:**
    *   Ensure your chosen VPC network exists (`default`).
    *   Create a Serverless VPC Access Connector if one doesn't exist, linking it to this VPC.
    *   Name: `redis-connector`
    *   Region: `us-central1`
    *   IP Range: `\1.***.\2.\3/28` (ensure it's an unused range in your VPC)
    ```bash
    gcloud compute networks vpc-access connectors create redis-connector \
      --network default \
      --region us-central1 \
      --range \1.***.\2.\3/28 \
      --project=Project_ID
    ```
*   **Memorystore for Redis (Standalone) Instance:**
    *   Provision your standalone Memorystore for Redis instance.
    *   Name: `ccai-redis-instance`
    *   Region: `us-central1`
    *   Tier: BASIC (or choose based on needs)
    *   Connect Mode: `DIRECT_PEERING`
    *   Transit Encryption: **DISABLED**
    *   Auth enabled: (Optional, if IAM auth is used, ensure SA has `roles/redis.client`)
    *   Network: `default`
    *   The instance will get a private IP address (e.g., `\1.***.\2.\3`) accessible via the VPC connector.
*   **Pub/Sub Topics:**
    *   Input Topic:
      ```bash
      gcloud pubsub topics create raw-transcripts --project=Project_ID
      ```
    *   Output Topic:
      ```bash
      gcloud pubsub topics create redacted-transcripts --project=Project_ID
      ```
*   **Pub/Sub Subscription (for Cloud Function Trigger):**
    *   Create a subscription to the Input Topic (`raw-transcripts`). The Cloud Function will use this as its trigger.
    ```bash
    gcloud pubsub subscriptions create raw-transcripts-sub \
      --topic=raw-transcripts \
      --project=Project_ID
      # Add other flags like --ack-deadline or dead-letter policy as needed.
    ```

### 4. Create Service Accounts & Grant IAM Permissions

*   **Service Account for Cloud Run (`main_service`):**
    *   Name: `context-manager-sa`
    ```bash
    gcloud iam service-accounts create context-manager-sa \
      --display-name="Context Manager Service Account" \
      --project=Project_ID
    ```
    *   Grant Roles:
        *   Secret Manager Secret Accessor (to access its configuration secrets):
          ```bash
          gcloud projects add-iam-policy-binding Project_ID \
            --member="serviceAccount:context-manager-sa\1***\3" \
            --role="roles/secretmanager.secretAccessor"
          ```
        *   Redis Client (for Memorystore for Redis):
          Grants "Cloud Memorystore Redis Db Connection User" access.
          ```bash
          gcloud memorystore instances add-iam-policy-binding ccai-redis-instance \
            --region=us-central1 \
            --member="serviceAccount:context-manager-sa\1***\3" \
            --role="roles/redis.client" \
            --project=Project_ID
          ```
        *   DLP User:
          ```bash
          gcloud projects add-iam-policy-binding Project_ID \
            --member="serviceAccount:context-manager-sa\1***\3" \
            --role="roles/dlp.user"
          ```

*   **Service Account for Cloud Function (`subscriber_service`):**
    *   Name: `transcript-processor-sa`
    ```bash
    gcloud iam service-accounts create transcript-processor-sa \
      --display-name="Transcript Processor Service Account" \
      --project=Project_ID
    ```
    *   Grant Roles:
        *   Secret Manager Secret Accessor (to access its configuration secrets):
          ```bash
          gcloud projects add-iam-policy-binding Project_ID \
            --member="serviceAccount:transcript-processor-sa\1***\3" \
            --role="roles/secretmanager.secretAccessor"
          ```
        *   Pub/Sub Publisher (for the `redacted-transcripts` topic):
          ```bash
          gcloud pubsub topics add-iam-policy-binding redacted-transcripts \
            --member="serviceAccount:transcript-processor-sa\1***\3" \
            --role="roles/pubsub.publisher" \
            --project=Project_ID
          ```
        *   (Cloud Run Invoker role will be granted after `context-manager` service is deployed).

### 5. Create and Populate Secrets in Google Cloud Secret Manager
Create the following secrets. The application code will fetch these values at runtime.
*   `CONTEXT_MANAGER_REDIS_HOST`: Set to the internal IP address of your Memorystore for Redis instance (`\1.***.\2.\3`).
*   `CONTEXT_MANAGER_REDIS_PORT`: Set to your Redis port (`6379`).
*   `CONTEXT_MANAGER_DLP_PROJECT_ID`: Set to your Google Cloud Project ID (`Project_ID`).
*   `SUBSCRIBER_REDACTED_TOPIC_NAME`: Set to the name of your output Pub/Sub topic (`redacted-transcripts`).
*   `SUBSCRIBER_GCP_PROJECT_ID`: Set to your Google Cloud Project ID (`Project_ID`).
*   `SUBSCRIBER_INPUT_TRANSCRIPT_TOPIC`: Set to the name of your input Pub/Sub topic (`raw-transcripts`).
*   `SUBSCRIBER_CONTEXT_MANAGER_URL`: This will be set to the URL of the deployed `context-manager` service (e.g., `https://context-manager-***.us-central1.run.app`).

Example for creating a secret (repeat for each):
```bash
echo "ACTUAL_SECRET_VALUE" | gcloud secrets create SECRET_NAME_HERE \
    --project="Project_ID" \
    --replication-policy="automatic" \
    --data-file="-"
```
**Note:** The `SUBSCRIBER_CONTEXT_MANAGER_URL` secret will be created/updated *after* `context-manager` service is deployed with its actual URL.

## II. Application Deployment

### 6. Build and Deploy `main_service` (Cloud Run)
*   Navigate to the project root directory.
*   Build the Docker image for `context-manager` service:
    ```bash
    gcloud builds submit --tag gcr.io/Project_ID/context-manager-image ./main_service \
      --project=Project_ID
    ```
*   Deploy to Cloud Run:
    ```bash
    gcloud run deploy context-manager \
      --image gcr.io/Project_ID/context-manager-image \
      --platform managed \
      --region us-central1 \
      --allow-unauthenticated \ # Or configure IAM for invocation
      --service-account context-manager-sa\1***\3 \
      --vpc-connector redis-connector \
      --vpc-egress all \
      --project=Project_ID
      # Note: The application fetches configuration (like Redis host/port) from Secret Manager.
      # Ensure GOOGLE_CLOUD_PROJECT is available if get_secret relies on it,
      # or configure secrets to be mounted as environment variables or files.
    ```

### 7. Obtain `main_service` URL
After successful deployment, Cloud Run will provide a service URL (e.g., `https://context-manager-***.us-central1.run.app`).
You can also retrieve it using:
```bash
gcloud run services describe context-manager \
  --platform managed \
  --region us-central1 \
  --format="value(status.url)" \
  --project=Project_ID
```

### 8. Update `SUBSCRIBER_CONTEXT_MANAGER_URL` Secret
Create or update the `SUBSCRIBER_CONTEXT_MANAGER_URL` secret in Secret Manager with the URL of the `context-manager` service (e.g., `https://context-manager-***.us-central1.run.app`).
If creating for the first time:
```bash
echo "https://context-manager-***.us-central1.run.app" | gcloud secrets create SUBSCRIBER_CONTEXT_MANAGER_URL \
    --project="Project_ID" \
    --replication-policy="automatic" \
    --data-file="-"
```
If updating an existing version:
```bash
echo "https://context-manager-***.us-central1.run.app" | gcloud secrets versions add SUBSCRIBER_CONTEXT_MANAGER_URL \
    --project="Project_ID" \
    --data-file="-"
```

### 9. Grant Cloud Run Invoker Role to `transcript-processor-sa`
Now that `context-manager` service is deployed, grant the `transcript-processor-sa` service account permission to invoke it.
```bash
gcloud run services add-iam-policy-binding context-manager \
  --region=us-central1 \
  --member="serviceAccount:transcript-processor-sa\1***\3" \
  --role="roles/run.invoker" \
  --platform=managed \
  --project=Project_ID
```

### 10. Deploy `subscriber_service` (Cloud Function)
*   Navigate to the project root directory.
*   Deploy the Cloud Function:
    ```bash
    gcloud functions deploy transcript-processor \
      --runtime python311 # Or your preferred Python runtime \
      --trigger-topic raw-transcripts \ # Or --trigger-subscription raw-transcripts-sub
      --entry-point process_transcript_event \
      --region us-central1 \
      --service-account transcript-processor-sa\1***\3 \
      --source ./subscriber_service \
      --clear-vpc-connector \
      --egress-settings all \
      --project=Project_ID
      # Note: The application fetches configuration (like the Context Manager URL) from Secret Manager.
      # Ensure GOOGLE_CLOUD_PROJECT is available if get_secret relies on it,
      # or configure secrets to be mounted as environment variables or files.
    ```

## III. Post-Deployment

### 11. Testing and Verification
*   Send a test message to the `raw-transcripts` Pub/Sub topic.
*   Verify that the `context-manager` (Cloud Run) logs show requests for agent and customer utterances.
*   Verify that the `transcript-processor` (Cloud Function) logs show it processes the message and calls the `context-manager` service.
*   Check for redacted messages on the `redacted-transcripts` Pub/Sub topic.
*   Monitor logs in Cloud Logging for any errors related to secret access, Redis connection, DLP processing, or Pub/Sub publishing.
