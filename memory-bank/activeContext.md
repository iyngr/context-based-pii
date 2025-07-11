# Active Context

  This file tracks the project's current status, including recent changes, current goals, and open questions.
  2025-06-03 12:57:56 - Log of updates made.

*

## Current Focus

*   Ensuring accurate multi-turn context-based PII redaction using Google Cloud DLP.

## Recent Changes

*   Refined DLP configuration in `main_service/dlp_config.yaml` for custom info types and likelihood boosting.
*   Updated `productContext.md` to reflect the `ccai_insights_function`'s role in Conversation Insights integration.

## Open Questions/Issues

*   None currently identified based on recent source code analysis.
2025-07-07 01:10:23 - **Current Focus:** Implementing a secure server-side proxy for frontend-to-backend communication using Node.js.
2025-07-07 04:54:23 - **Current Focus:** Diagnosing blank screen issue in frontend by adding console logs to React component lifecycle.
2025-07-07 04:56:11 - **Recent Changes:** Rebuilt frontend application after reinstalling dependencies.
2025-07-07 01:10:23 - **Recent Changes:** Modified `frontend/Dockerfile` to use Node.js for serving static files and proxying API requests, created `frontend/server.js`, and updated `frontend/package.json` with new dependencies and scripts.
2025-07-12 01:32:41 - **Clarification on Multi-Turn Context:** The proposed real-time redaction for the UI will leverage the *current* context available in Redis for immediate feedback. However, the existing `subscriber_service` and `transcript_aggregator_service` pipeline will continue to handle the comprehensive, multi-turn context-aware redaction (which catches PII revealed across multiple turns) when the "Analyze Conversation" button is clicked. This ensures that PII revealed later in the conversation, or across multiple turns, is still accurately redacted for final archival. The real-time UI redaction acts as a "preview" while the robust backend process handles the full context.