# Project Brief: Context Manager Service with PII Redaction

## 1. main_service/main.py (Context Manager Service)

This Flask application serves as the core context manager and PII redaction engine.

### Key Functionality:
*   **Secret Management:** Securely fetches configuration values (Redis host/port, Google Cloud DLP project ID) using Google Cloud Secret Manager.
*   **Redis Integration:** Connects to a Redis (or Valkey) instance to store and retrieve conversational context, specifically `expected_pii_type`, with a configurable TTL.
*   **Google Cloud DLP Integration:** Initializes a Google Cloud DLP client for PII de-identification.

### API Endpoints:
*   `/handle-agent-utterance`:
    *   Receives transcripts from an "agent" (chatbot or human).
    *   Analyzes the transcript using `extract_expected_pii()` to identify if the agent is requesting specific PII (e.g., phone number, email).
    *   If an expected PII type is found, stores this context in Redis, associated with the `conversation_id`.
*   `/handle-customer-utterance`:
    *   Receives transcripts from a "customer" (end-user).
    *   Retrieves any previously stored context from Redis for the given `conversation_id`.
    *   Calls `call_dlp_for_redaction()` to de-identify PII in the customer's transcript.
    *   DLP call can be tailored based on retrieved context (e.g., more sensitive to phone numbers if expected).
    *   Returns the redacted transcript.

### PII Logic:
*   `extract_expected_pii`: Placeholder function using keyword matching to infer expected PII type from agent requests.
*   `call_dlp_for_redaction`: Handles calls to Google Cloud DLP API, scanning for built-in InfoTypes (PHONE_NUMBER, EMAIL_ADDRESS, CREDIT_CARD_NUMBER, etc.) and dynamically adjusting inspection based on context. Replaces identified PII with its InfoType name (e.g., "[PHONE_NUMBER]").

## 2. subscriber_service/main.py (or subscriber_service/subscriber.py)

This Python script functions as a Google Cloud Function (or similar serverless function) triggered by Pub/Sub messages, processing Agent Assist transcripts.

### Key Functionality:
*   **Secret Management:** Fetches configuration (Context Manager URL, Redacted Pub/Sub Topic Name, GCP Project ID for Pub/Sub) from Google Cloud Secret Manager.
*   **Pub/Sub Integration:** Initializes a Google Cloud Pub/Sub Publisher client to publish redacted transcripts.

### Event Processing (`process_transcript_event`):
*   Main entry point for the Cloud Function.
*   Decodes incoming Pub/Sub messages containing Agent Assist transcript data.
*   Iterates through transcript entries, identifying 'AGENT' or 'END_USER'/'CUSTOMER' utterances.
*   For 'AGENT' utterances: Calls `main_service`'s `/handle-agent-utterance` to store potential PII request context.
*   For 'END_USER'/'CUSTOMER' utterances: Calls `main_service`'s `/handle-customer-utterance` to get a PII-redacted transcript.
*   If a redacted transcript is received, publishes this data (redacted transcript, conversation ID, original transcript, role, etc.) to a configured Pub/Sub topic.

### Error Handling:
*   Includes robust logging and error handling for secret fetching, HTTP requests to the context manager, and Pub/Sub publishing.

## Overall Project Summary

The project establishes a secure and scalable system for managing conversational context and redacting sensitive PII from customer interactions within a Google Cloud environment.

### Workflow:
1.  **Transcript Ingestion:** Agent Assist (or similar) publishes conversation transcripts to a Pub/Sub topic.
2.  **Subscriber Processing:** The `subscriber_service` (Cloud Function) is triggered by these Pub/Sub messages.
3.  **Context Management & PII Detection (Agent):** If an agent's utterance suggests a PII request, the `subscriber_service` sends it to the `main_service`. The `main_service` identifies the expected PII type and stores this context in Redis.
4.  **PII Redaction (Customer):** If a customer's utterance contains PII, the `subscriber_service` sends it to the `main_service`. The `main_service` retrieves relevant context from Redis (e.g., "agent asked for phone number"), then uses Google Cloud DLP to redact PII, potentially using context for improved accuracy.
5.  **Redacted Transcript Publication:** The `main_service` returns the redacted transcript to the `subscriber_service`, which publishes it to another Pub/Sub topic for downstream consumption (e.g., analytics, storage).

This architecture ensures sensitive customer data is de-identified before further storage or processing, enhancing privacy and compliance.