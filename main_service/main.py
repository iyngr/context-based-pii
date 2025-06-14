import os
import logging
from flask import Flask, request, jsonify
import redis
import json # Added for JSON serialization
import time # For a better timestamp
from google.cloud import dlp_v2 # Added for Google Cloud DLP
from google.cloud.secretmanager import SecretManagerServiceClient
from google.api_core.exceptions import NotFound, PermissionDenied

# --- Google Cloud Secret Manager Helper ---
GCP_PROJECT_ID_FOR_SECRETS = os.getenv("GOOGLE_CLOUD_PROJECT")

def get_secret(secret_id, version_id="latest", project_id=None):
    """
    Fetches a secret from Google Cloud Secret Manager.
    Args:
        secret_id (str): The ID of the secret.
        version_id (str): The version of the secret (default is "latest").
        project_id (str): The GCP project ID. If None, uses GCP_PROJECT_ID_FOR_SECRETS.
    Returns:
        str: The secret value, or None if an error occurs.
    """
    if not project_id:
        project_id = GCP_PROJECT_ID_FOR_SECRETS

    if not project_id:
        logger.error("GCP_PROJECT_ID_FOR_SECRETS is not set. Cannot fetch secrets.")
        return None
    if not secret_id:
        logger.error("secret_id not provided to get_secret function.")
        return None

    try:
        client = SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(name=name)
        payload = response.payload.data.decode("UTF-8")
        # Strip whitespace/newlines from the fetched secret
        cleaned_payload = payload.strip()
        logger.info(f"Successfully fetched secret: {secret_id} (version: {version_id}). Raw length: {len(payload)}, Cleaned length: {len(cleaned_payload)}")
        if payload != cleaned_payload:
            logger.warning(f"Secret '{secret_id}' had leading/trailing whitespace removed. Original: '{repr(payload)}', Cleaned: '{repr(cleaned_payload)}'")
        return cleaned_payload
    except NotFound:
        logger.error(f"Secret {secret_id} (version: {version_id}) not found in project {project_id}.")
        return None
    except PermissionDenied:
        logger.error(f"Permission denied when trying to access secret {secret_id} (version: {version_id}) in project {project_id}.")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching secret {secret_id} (version: {version_id}): {str(e)}")
        return None

app = Flask(__name__)

# Configure standard logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(module)s %(funcName)s %(lineno)d : %(message)s')
logger = logging.getLogger(__name__)

# Configuration
REDIS_HOST_SECRET_ID = "CONTEXT_MANAGER_REDIS_HOST" # Updated from VALKEY
REDIS_PORT_SECRET_ID = "CONTEXT_MANAGER_REDIS_PORT" # Updated from VALKEY
DLP_PROJECT_ID_SECRET_ID = "CONTEXT_MANAGER_DLP_PROJECT_ID"

REDIS_HOST = get_secret(REDIS_HOST_SECRET_ID)
if not REDIS_HOST:
    logger.critical(f"Critical: REDIS_HOST secret ('{REDIS_HOST_SECRET_ID}') could not be fetched. Exiting.")
    exit(1)

REDIS_PORT_STR = get_secret(REDIS_PORT_SECRET_ID)
if not REDIS_PORT_STR:
    logger.warning(f"REDIS_PORT secret ('{REDIS_PORT_SECRET_ID}') not found. Using default port 6379.")
    REDIS_PORT = 6379
else:
    try:
        REDIS_PORT = int(REDIS_PORT_STR)
    except ValueError:
        logger.critical(f"Critical: REDIS_PORT secret ('{REDIS_PORT_SECRET_ID}') is not a valid integer: '{REDIS_PORT_STR}'. Exiting.")
        exit(1)

DLP_PROJECT_ID = get_secret(DLP_PROJECT_ID_SECRET_ID)
if not DLP_PROJECT_ID:
    # Depending on strictness, you might exit or allow fallback if DLP is optional at startup
    logger.warning(f"DLP_PROJECT_ID secret ('{DLP_PROJECT_ID_SECRET_ID}') could not be fetched. DLP functionality might be impaired.")
    # If DLP_PROJECT_ID is absolutely critical for any operation before a request, consider exiting:
    # logger.critical(f"Critical: DLP_PROJECT_ID secret ('{DLP_PROJECT_ID_SECRET_ID}') could not be fetched. Exiting.")
    # exit(1)

CONTEXT_TTL_SECONDS = int(os.environ.get('CONTEXT_TTL_SECONDS', 90)) # This one remains as env var per instructions

# Initialize Redis client
redis_client = None
try:
    logger.info(f"Attempting to connect to Redis host:{REDIS_HOST} port:{REDIS_PORT} ssl:True")
    # Ensure your managed Redis instance is configured to accept SSL connections on this port.
    # For IAM auth, no username/password needed here.
    redis_client = redis.StrictRedis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=0,
        decode_responses=True,
        ssl=False,  # Updated to False based on Memorystore config
        ssl_cert_reqs=None,
        socket_connect_timeout=10 # Added connection timeout (10 seconds)
        # username=None # Try removing username parameter entirely for IAM auth with redis-py
    )
    logger.info("Redis client configured. Attempting ping...") # Added log
    redis_client.ping()
    logger.info("Redis ping successful.") # Added log
    logger.info("Successfully connected to Redis.")
except redis.exceptions.AuthenticationError as auth_err: # More specific
    logger.error(f"Redis AuthenticationError during client initialization. Error: {str(auth_err)}")
    # redis_client remains None
except redis.exceptions.TimeoutError as timeout_err: # Added specific TimeoutError handling
    logger.error(f"Redis TimeoutError during client initialization or ping. Error: {str(timeout_err)}")
    # redis_client remains None
except redis.exceptions.ConnectionError as conn_err: # For other connection issues
    logger.error(f"Redis ConnectionError during client initialization or ping. Error: {str(conn_err)}")
    # redis_client remains None
except Exception as e: # Catch any other unexpected errors during initialization
    logger.error(f"An UNEXPECTED error occurred during Redis client initialization or ping. Error: {str(e)}")
    # redis_client remains None
    # Consider if the app should exit(1) here if Redis is absolutely critical for startup


# Initialize DLP client
# For Cloud Run, it's generally okay to initialize clients globally as the container instance
# stays warm between requests.
try:
    dlp_client = dlp_v2.DlpServiceClient()
    logger.info("Successfully initialized DLP client.")
except Exception as e:
    logger.error(f"Could not initialize DLP client. Error: {str(e)}")
    dlp_client = None


@app.route('/')
def hello_world():
    """A simple hello world endpoint."""
    return "Hello, World! This is the Context Manager Service."

@app.route('/handle-agent-utterance', methods=['POST'])
def handle_agent_utterance():
    """
    Handles the agent's utterance, extracts potential PII requests,
    and stores context in Redis.
    """
    data = request.get_json()
    if not data or 'conversation_id' not in data or 'transcript' not in data:
        return jsonify({"error": "Missing conversation_id or transcript"}), 400

    conversation_id = data['conversation_id']
    transcript = data['transcript']

    # Placeholder for PII request extraction logic
    # This function would analyze the transcript and return an expected PII type
    # e.g., "PHONE_NUMBER", "EMAIL_ADDRESS", or None
    expected_pii_type = extract_expected_pii(transcript)

    if expected_pii_type and redis_client:
        try:
            context_key = f"context:{conversation_id}"
            # Use time.time() for a standard Unix timestamp
            context_value = {"expected_pii_type": expected_pii_type, "timestamp": time.time()}
            redis_client.setex(context_key, CONTEXT_TTL_SECONDS, json.dumps(context_value)) # Store as JSON string
            logger.info(f"Stored context in Redis for conversation_id: {conversation_id}, context_value: {context_value}")
            return jsonify({"message": "Agent utterance processed, context stored.", "expected_pii": expected_pii_type}), 200
        except redis.exceptions.RedisError as e: # redis-py library still raises redis.exceptions
            logger.error(f"Redis error during context storage for conversation_id: {conversation_id}. Error: {str(e)}")
            return jsonify({"error": "Failed to store context in Redis"}), 500
    elif not redis_client:
        return jsonify({"error": "Redis client not available"}), 503

    return jsonify({"message": "Agent utterance processed, no specific PII context to store."}), 200

@app.route('/handle-customer-utterance', methods=['POST'])
def handle_customer_utterance():
    """
    Handles the customer's utterance, retrieves context from Redis,
    and calls DLP for PII redaction.
    """
    data = request.get_json()
    if not data or 'conversation_id' not in data or 'transcript' not in data:
        return jsonify({"error": "Missing conversation_id or transcript"}), 400

    conversation_id = data['conversation_id']
    transcript = data['transcript']
    retrieved_context = None

    if redis_client:
        try:
            context_key = f"context:{conversation_id}"
            context_data_str = redis_client.get(context_key)
            if context_data_str:
                retrieved_context = json.loads(context_data_str) # Use json.loads
                logger.info(f"Retrieved context from Redis for conversation_id: {conversation_id}, retrieved_context: {retrieved_context}")
        except redis.exceptions.RedisError as e: # redis-py library still raises redis.exceptions
            logger.error(f"Redis error while retrieving context for conversation_id: {conversation_id}. Error: {str(e)}")
            retrieved_context = None # Ensure context is None if Redis fails
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from Redis for conversation_id: {conversation_id}, context_data_str: {context_data_str}. Error: {str(e)}")
            retrieved_context = None # Ensure context is None if JSON is malformed
        except Exception as e: # Catch other potential errors
            logger.error(f"Error processing retrieved context from Redis for conversation_id: {conversation_id}. Error: {str(e)}")
            retrieved_context = None # Ensure context is None for any other error
    elif not redis_client:
        logger.warning("Redis client not available for customer utterance.")


    # Placeholder for DLP invocation logic
    # This function would take the transcript and optional context
    # to call Google DLP and return the redacted transcript.
    redacted_transcript = call_dlp_for_redaction(transcript, DLP_PROJECT_ID, retrieved_context)

    return jsonify({"redacted_transcript": redacted_transcript, "context_used": retrieved_context is not None}), 200

# Placeholder functions - to be implemented
def extract_expected_pii(transcript: str) -> str | None:
    """
    Analyzes the agent's transcript to identify if it's asking for a specific PII.
    Returns the PII type (e.g., "PHONE_NUMBER") or None.
    This is a simplified placeholder.
    """
    transcript_lower = transcript.lower()
    # Order can matter if keywords overlap; more specific checks can come first.
    if "social security" in transcript_lower or "ssn" in transcript_lower:
        return "US_SOCIAL_SECURITY_NUMBER" # Matches DLP InfoType name
    if "credit card" in transcript_lower or "card number" in transcript_lower:
        return "CREDIT_CARD_NUMBER"
    if "phone number" in transcript_lower or "your number" in transcript_lower or "contact number" in transcript_lower:
        return "PHONE_NUMBER"
    if "email address" in transcript_lower or "your email" in transcript_lower:
        return "EMAIL_ADDRESS"
    if "date of birth" in transcript_lower or "dob" in transcript_lower:
        return "DATE_OF_BIRTH"
    if "address" in transcript_lower or "live" in transcript_lower and "where do you" in transcript_lower: # Basic address detection
        return "STREET_ADDRESS" # Matches DLP InfoType name
    if "account number" in transcript_lower or "member id" in transcript_lower:
        return "FINANCIAL_ACCOUNT_NUMBER"
    if "full name" in transcript_lower or "your name" in transcript_lower:
        return "PERSON_NAME" # Matches DLP InfoType name
    if "passport number" in transcript_lower or "passport no" in transcript_lower:
        return "PASSPORT" # Matches DLP InfoType name
    # Add more PII types and keywords as needed. Consider regex for more complex patterns.
    return None

def call_dlp_for_redaction(transcript: str, project_id: str, context: dict | None) -> str:
    """
    Calls Google DLP to de-identify PII in the transcript.
    Uses context if available to tailor the DLP request.
    """
    global dlp_client # Ensure we are using the globally initialized client
    if not dlp_client:
        logger.warning("DLP client not available. Returning original transcript.")
        return transcript
    if not project_id or project_id == 'your-gcp-project-id': # Basic check for placeholder
        logger.warning("DLP Project ID not configured correctly. Returning original transcript.")
        return transcript

    item = {"value": transcript}
    logger.info(f"--- DEBUG DLP PARENT --- project_id (raw value): '{project_id}'")
    logger.info(f"--- DEBUG DLP PARENT --- project_id (repr value): {repr(project_id)}")
    parent = f"projects/{project_id}"

    # Define InfoTypes to scan for by default
    info_types_to_scan = [
        {"name": "PHONE_NUMBER"},
        {"name": "EMAIL_ADDRESS"},
        {"name": "CREDIT_CARD_NUMBER"},
        {"name": "US_SOCIAL_SECURITY_NUMBER"},
        {"name": "PERSON_NAME"},
        {"name": "STREET_ADDRESS"},
        {"name": "DATE_OF_BIRTH"},
        {"name": "PASSPORT"},
        {"name": "IBAN_CODE"},
        {"name": "SWIFT_CODE"},
        # Add other relevant built-in or custom info_types here.
        # Consider creating custom info types for domain-specific PII like "ACCOUNT_NUMBER".
    ]

    # Start with default broad inspection configuration
    inspect_config = {
        "info_types": info_types_to_scan,
        "min_likelihood": dlp_v2.Likelihood.POSSIBLE,
        "include_quote": True,
    }

    custom_info_types = []

    if context and context.get("expected_pii_type"):
        expected_type = context.get("expected_pii_type")
        logger.info(f"Contextual PII type received: {expected_type}. Adjusting DLP scan.")

        # Always include the expected type with higher likelihood if it's a standard InfoType
        found_in_default = False
        for info_type_dict in inspect_config["info_types"]:
            if info_type_dict["name"] == expected_type:
                found_in_default = True
                break
        
        if not found_in_default:
            # Add the expected type if it's not already in the default list
            inspect_config["info_types"].append({"name": expected_type})

        # Boost likelihood for the expected type
        inspect_config["min_likelihood"] = dlp_v2.Likelihood.LIKELY

        if expected_type == "PHONE_NUMBER":
            custom_phone_regex_infotype_name = "CUSTOM_PHONE_REGEX_CTX"
            custom_info_types.append(
                {
                    "info_type": {"name": custom_phone_regex_infotype_name},
                    "regex": {"pattern": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"},
                }
            )
            logger.info("DLP inspection configured for PHONE_NUMBER context with built-in and custom regex (more sensitive).")
        else:
            logger.info(f"DLP inspection configured to include {expected_type} with increased sensitivity, alongside general scan.")

    if custom_info_types:
        inspect_config["custom_info_types"] = custom_info_types

    # Configure de-identification: Redact all matched PII by replacing with the InfoType name
    deidentify_config = {
        "info_type_transformations": {
            "transformations": [
                {
                    "primitive_transformation": {
                        "replace_with_info_type_config": {}
                    }
                }
            ]
        }
    }

    try:
        logger.info(f"Sending request to DLP API for project_id: {project_id}, transcript_preview: {transcript[:100]}")
        request_body = {
            "parent": parent,
            "deidentify_config": deidentify_config,
            "inspect_config": inspect_config,
            "item": item,
        }
        response = dlp_client.deidentify_content(request=request_body)
        
        redacted_value = response.item.value
        logger.info(f"DLP De-identification successful. Redacted_transcript_preview: {redacted_value[:100]}")
        return redacted_value
    except Exception as e:
        logger.error(f"An error occurred during DLP API call: {str(e)}")
        # Fallback: return original transcript or a transcript with a generic error message
        return f"[DLP_PROCESSING_ERROR] {transcript}"

if __name__ == "__main__":
    # This block is for local development only.
    # For Cloud Run, Gunicorn (as specified in Dockerfile) will run the app.
    # app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
    pass # No action needed when run by Gunicorn