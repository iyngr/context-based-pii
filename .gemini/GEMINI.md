# Gemini Code Assist - Project Context

This document provides context for Gemini Code Assist to understand the project structure, goals, and key components.

## Project Overview

This project is a real-time PII (Personally Identifiable Information) redaction service for contact center transcripts. It integrates with Google Cloud services like Agent Assist, Pub/Sub, Cloud Functions, Cloud Run, Redis, Firestore, and Contact Center AI (CCAI) Insights.

The primary goal is to ensure that raw, unredacted transcripts are available to agents in real-time via Agent Assist, while only fully redacted transcripts are stored for post-call analysis in CCAI Insights.

## Key Services

The project is composed of three main services:

1.  **`main_service`**: A Flask application deployed on Cloud Run that acts as the central context manager and PII redaction engine. It uses Redis to store conversational context (e.g., if an agent is expecting a specific type of PII) and Google Cloud DLP to perform the redaction.

2.  **`subscriber_service`**: A Cloud Function (or Cloud Run service) that is triggered by raw transcript messages from Agent Assist (via Pub/Sub). It orchestrates the redaction process by calling the `main_service` and then publishes the redacted transcripts to another Pub/Sub topic.

3.  **`transcript_aggregator_service`**: A Cloud Run service that subscribes to the redacted transcripts topic. It aggregates all the utterances for a given conversation using Firestore as a temporary store. When it receives a "conversation ended" event from CCAI's lifecycle notifications, it assembles the full, ordered, redacted transcript and uploads it to Google Cloud Conversation Insights for analysis.

## High-Level Workflow

1.  **Ingestion**: Agent Assist publishes raw conversation transcripts to a `raw-transcripts` Pub/Sub topic.
2.  **Subscription & Orchestration**: The `subscriber_service` receives these messages.
3.  **Context Handling (Agent Utterances)**: For agent messages, it calls the `main_service`'s `/handle-agent-utterance` endpoint. The `main_service` analyzes the text for keywords (e.g., "what is your email?") and stores the expected PII type (e.g., `EMAIL_ADDRESS`) in Redis, associated with the `conversation_id`. The original agent utterance is then published to the `redacted-transcripts` topic.
4.  **Redaction (Customer Utterances)**: For customer messages, it calls the `main_service`'s `/handle-customer-utterance` endpoint. The `main_service` retrieves any context from Redis and uses it to perform a more accurate PII redaction using the Cloud DLP API.
5.  **Publication of Redacted Transcripts**: The `main_service` returns the redacted text to the `subscriber_service`, which then publishes it to the `redacted-transcripts` topic.
6.  **Aggregation**: The `transcript_aggregator_service` receives all messages (both original agent text and redacted customer text) from the `redacted-transcripts` topic and stores them in Firestore, ordered by their original timestamp, under a document for the `conversation_id`.
7.  **Final Upload**: Upon receiving a `conversation_ended` event from a separate CCAI lifecycle Pub/Sub topic, the `transcript_aggregator_service` retrieves all utterances for that conversation from Firestore, assembles them into a single transcript file, uploads it to a GCS bucket, and then calls the CCAI Insights API to ingest the conversation from that GCS file.
8.  **Cleanup**: After a successful upload to CCAI, the corresponding conversation data is deleted from Firestore.

## Architectural Patterns

*   **Pub/Sub-Driven**: The entire workflow is asynchronous and driven by messages on Pub/Sub topics.
*   **Microservices**: The logic is separated into distinct services, each with a clear responsibility.
*   **Serverless**: The services are deployed on Cloud Run and Cloud Functions, allowing for scalability and managed infrastructure.
*   **Externalized State**: Redis is used for short-lived conversational context, and Firestore is used for the temporary aggregation of in-progress conversations.
*   **CI/CD**: The project uses Google Cloud Build for continuous integration and deployment, with separate build configurations and triggers for each service.

## How to Help

When I ask for help, please consider the context of the entire project. For example:

*   If I'm working on the `main_service`, remember that it needs to interact with Redis and DLP, and that its configuration is stored in `dlp_config.yaml` and fetched from Secret Manager.
*   If I'm working on the `subscriber_service`, remember its role is to call the `main_service` and publish to Pub/Sub.
*   If I'm working on the `transcript_aggregator_service`, remember its job is to collect transcripts from Firestore and upload them to CCAI Insights after an end-of-call event.
*   Changes in one service might require changes in another. For example, if an API in `main_service` changes, the `subscriber_service` will likely need to be updated.
*   All services rely on secrets from Google Cloud Secret Manager for configuration.
*   Pay attention to the IAM roles and permissions required for each service to interact with other Google Cloud services.