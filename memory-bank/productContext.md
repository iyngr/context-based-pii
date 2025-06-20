# Product Context

This file provides a high-level overview of the project and the expected product that will be created. Initially it is based upon projectBrief.md (if provided) and all other available project-related information in the working directory. This file is intended to be updated as the project evolves, and should be used to inform all other modes of the project's goals and context.
2025-06-03 12:57:45 - Log of updates made will be appended as footnotes to the end of this file.

*

## Project Goal

*   Enable real-time raw transcript flow to Agent Assist for PII verification.
*   Ensure redacted PII information is sent to Conversation Insights for analytics.
*   Implement post-call PII redaction.
*   Maintain chronological order of transcripts in Conversation Insights.

## Key Features

*   Real-time transcript streaming to Agent Assist.
*   Automated PII redaction service.
*   Integration with Google Cloud Conversation Insights API.
*   Robust transcript aggregation and ordering using Firestore.
*   End-of-call detection via CCAI lifecycle notifications.

## Overall Architecture

*   A Pub/Sub-driven architecture for real-time transcript processing.
*   `main_service`: Handles PII redaction and conversation context management using Redis.
*   `subscriber_service`: Cloud Function triggered by raw transcript Pub/Sub messages, calls `main_service`, and publishes redacted transcripts.
*   `transcript_aggregator_service`: Subscribes to redacted transcripts, aggregates conversations using Firestore, detects end-of-call via CCAI lifecycle events, and ingests full transcripts into Google Cloud Conversation Insights.
*   Direct API integration with Google Cloud Conversation Insights.
2025-06-03 01:10:20 - Updated project goal, key features, and overall architecture based on new client requirements for PII handling.
2025-06-03 01:53:25 - **Deployment Strategy Update:** Both `main_service` and `subscriber_service` are intended to be deployed to Google Cloud Run or Cloud Functions. Redis (Valkey) is configured to be accessible only via Serverless VPC Access, restricting direct access from outside the GCP environment.