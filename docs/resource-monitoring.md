# Monitoring and Alerting for `transcript_aggregator_service`

This document outlines the steps for setting up robust monitoring and alerting for the `transcript_aggregator_service` deployed on Google Cloud Run. These steps are to be performed manually via the GCP Console or using the `gcloud` CLI.

## 1. Cloud Monitoring Dashboards for Service Health (`transcript_aggregator_service` - Cloud Run)

### Metrics to Monitor:
*   `run.googleapis.com/request_count`: Total number of requests.
*   `run.googleapis.com/request_latencies`: Latency of requests.
*   `run.googleapis.com/container/cpu/utilizations`: CPU utilization of service instances.
*   `run.googleapis.com/container/memory/utilizations`: Memory utilization of service instances.
*   `run.googleapis.com/container/instance_count`: Number of running instances.
*   `run.googleapis.com/container/billable_instance_time`: Billable instance time.
*   `logging.googleapis.com/log_entry_count` (filtered by severity: `ERROR` or `CRITICAL`): Count of error logs.

### Dashboard Setup (GCP Console):
1.  Navigate to **Monitoring > Dashboards**.
2.  Click **+ CREATE DASHBOARD**.
3.  Add charts for each of the above metrics. Use appropriate aggregations (e.g., `SUM` for request count, `MEAN` or `P99` for latencies) and group by relevant labels (e.g., `service_name`, `revision_name`).
4.  Configure time ranges and refresh intervals as needed.

## 2. Cloud Monitoring Dashboards for Pub/Sub Message Backlog

### Metrics to Monitor:
*   `pubsub.googleapis.com/subscription/num_undelivered_messages`: Number of messages in the subscription backlog.
*   `pubsub.googleapis.com/subscription/oldest_unacked_message_age`: Age of the oldest unacknowledged message.
*   `pubsub.googleapis.com/subscription/pull_request_count`: Number of pull requests.
*   `pubsub.googleapis.com/subscription/push_request_count`: Number of push requests (if using push subscriptions).

### Dashboard Setup (GCP Console):
1.  Navigate to **Monitoring > Dashboards**.
2.  Add charts for the `redacted-transcripts` subscription (and any other relevant Pub/Sub subscriptions used by the service).
3.  Focus on `num_undelivered_messages` and `oldest_unacked_message_age` to identify processing bottlenecks.

## 3. Cloud Monitoring Dashboards for Firestore Read/Write Metrics

### Metrics to Monitor:
*   `firestore.googleapis.com/document/read_count`: Number of document reads.
*   `firestore.googleapis.com/document/write_count`: Number of document writes.
*   `firestore.googleapis.com/document/delete_count`: Number of document deletes.
*   `firestore.googleapis.com/document/indexed_document_count`: Number of indexed documents.
*   `firestore.googleapis.com/network/sent_bytes_count`: Bytes sent from Firestore.
*   `firestore.googleapis.com/network/received_bytes_count`: Bytes received by Firestore.

### Dashboard Setup (GCP Console):
1.  Navigate to **Monitoring > Dashboards**.
2.  Add charts for the `redacted-transcript-db` Firestore database.
3.  Monitor read/write operations to understand usage patterns and potential performance issues.

## 4. Cloud Monitoring Dashboards for CCAI API Call Metrics

### Metrics to Monitor (assuming `transcript_aggregator_service` makes direct CCAI API calls):
*   `logging.googleapis.com/log_entry_count` (filtered by `resource.type="cloud_run_revision"` and `jsonPayload.api_method="google.cloud.contactcenterinsights.v1.ConversationInsights.CreateConversation"` or similar CCAI methods, and `severity="ERROR"`): Count of failed CCAI API calls.
*   Custom metrics (if implemented in `transcript_aggregator_service` to track successful/failed CCAI calls or latency).

### Dashboard Setup (GCP Console):
1.  Navigate to **Monitoring > Dashboards**.
2.  Create charts based on log-based metrics for CCAI API call success/failure rates and latency.
3.  If custom metrics are implemented, add charts for those.

## 5. Configure Alerts for Critical Errors or Performance Degradation

### Alerting Policy Setup (GCP Console):
1.  Navigate to **Monitoring > Alerting**.
2.  Click **+ CREATE POLICY**.

### Suggested Alerting Policies:
*   **Cloud Run Error Rate:**
    *   **Metric:** `logging.googleapis.com/log_entry_count` (filter by `severity=ERROR` or `CRITICAL`, `resource.type="cloud_run_revision"`, `resource.labels.service_name="transcript_aggregator_service"`).
    *   **Condition:** Threshold for error count (e.g., > 5 errors in 5 minutes).
    *   **Notification Channel:** Email, PagerDuty, Slack, etc.
*   **Cloud Run High Latency:**
    *   **Metric:** `run.googleapis.com/request_latencies` (P99).
    *   **Condition:** Threshold for latency (e.g., > 500ms for 5 minutes).
*   **Pub/Sub Backlog Growth:**
    *   **Metric:** `pubsub.googleapis.com/subscription/num_undelivered_messages` for `redacted-transcripts` subscription.
    *   **Condition:** Threshold for backlog size (e.g., > 1000 messages for 10 minutes).
*   **Pub/Sub Oldest Unacked Message Age:**
    *   **Metric:** `pubsub.googleapis.com/subscription/oldest_unacked_message_age` for `redacted-transcripts` subscription.
    *   **Condition:** Threshold for age (e.g., > 5 minutes).
*   **Firestore High Write/Read Latency or Errors:**
    *   **Metric:** `firestore.googleapis.com/api/request_latencies` or `logging.googleapis.com/log_entry_count` (filtered for Firestore errors).
    *   **Condition:** Define appropriate thresholds.
*   **CCAI API Call Failures:**
    *   **Metric:** Log-based metric for failed CCAI API calls.
    *   **Condition:** Threshold for failure rate or count.

### Notification Channels:
Ensure appropriate notification channels (e.g., email groups, PagerDuty, Slack webhooks) are configured in Cloud Monitoring to receive alerts.