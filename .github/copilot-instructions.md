# GitHub Copilot Instructions

This document provides instructions for GitHub Copilot to ensure consistency, quality, and adherence to best practices when generating code for this project.

## General Instructions

- **Follow Official Documentation**: Always adhere to the official documentation for Google Cloud Platform (GCP) services. Do not invent or hallucinate APIs, library methods, or classes that do not exist.
- **GCP-Centric Responses**: The entire project is built on Google Cloud Services. All code generation, responses, and solutions must be relevant to and compatible with the GCP ecosystem.
- **PowerShell Compatibility**: The development environment is Windows-based. All terminal commands must be compatible with PowerShell, especially concerning multi-line commands and syntax. Use backticks (`) for line continuation where necessary.

## Project Context

This project is a data redaction system for Contact Center AI (CCAI) transcripts. It uses a microservices architecture to process, redact PII using Google Cloud DLP, and store transcripts for analysis.

- **`subscriber_service`**: Ingests raw transcripts from Pub/Sub.
- **`main_service`**: Handles PII redaction using DLP and manages context with Redis.
- **`transcript_aggregator_service`**: Manages multi-turn context and aggregates final transcripts.
- **`ccai_insights_function`**: Uploads final transcripts to the CCAI Insights API.
- **`frontend`**: A React-based web interface for interacting with the system.

The primary technologies used are:
- **Backend**: Python, Flask, Docker
- **Frontend**: JavaScript, React
- **Cloud**: Google Cloud Run, Cloud Functions, Pub/Sub, Cloud Storage, Redis (Memorystore), Cloud DLP
- **CI/CD**: Google Cloud Build

## Development Standards

### Design
- **Microservices Architecture**: When adding new functionality, consider if it should be a new microservice or part of an existing one. Follow the existing pattern of single-responsibility services.
- **Stateless Services**: Services should be stateless whenever possible, with state managed externally in Redis or Cloud Storage.
- **Asynchronous Communication**: Use Pub/Sub for communication between services to ensure loose coupling and scalability.

### Code
- **Python**:
    - Follow PEP 8 style guidelines.
    - Use type hints for all function signatures.
    - Use a logging library for all output; do not use `print()`.
    - All API endpoints should have clear error handling and return meaningful JSON responses.
- **JavaScript/React**:
    - Follow standard React best practices.
    - Use functional components with Hooks.
    - Keep components small and focused on a single responsibility.
    - Use a consistent styling approach (e.g., CSS Modules, styled-components).
- **Security**:
    - All Cloud Run services and Cloud Functions should be deployed with the principle of least privilege.
    - Avoid using `--allow-unauthenticated` for services that should not be publicly accessible. Use IAM to control access.
    - Sanitize all user inputs to prevent injection attacks.

### Review
- **Code Reviews**:
    - Ensure all new code has corresponding unit or integration tests.
    - Verify that code adheres to the standards outlined in this document.
    - Check for potential security vulnerabilities.
    - Ensure that changes are well-documented, both in code comments and in relevant documentation files.
- **Pull Requests**:
    - Pull requests should be small and focused on a single feature or bug fix.
    - The PR description should clearly explain the changes and the reasoning behind them.
