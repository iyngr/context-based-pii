import os
import logging
from flask import Flask, request, jsonify
import redis
import json
import time
import yaml
from google.cloud import dlp_v2
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
# Sensitive values are fetched from Google Cloud Secret Manager
# CONTEXT_MANAGER_URL (secret: CONTEXT_MANAGER_URL)
# REDACTED_TOPIC_NAME (secret: SUBSCRIBER_REDACTED_TOPIC_NAME)
# SUBSCRIBER_GCP_PROJECT_ID (secret: SUBSCRIBER_GCP_PROJECT_ID)
# DLP_PROJECT_ID (secret: CONTEXT_MANAGER_DLP_PROJECT_ID)

# Non-sensitive configuration uses environment variables
# CONTEXT_TTL_SECONDS (environment variable)

# Example of how to fetch sensitive secrets (conceptual, as direct interaction is not in scope for this mode)
# CONTEXT_MANAGER_URL = get_secret("CONTEXT_MANAGER_URL")
# REDACTED_TOPIC_NAME = get_secret("SUBSCRIBER_REDACTED_TOPIC_NAME")
# SUBSCRIBER_GCP_PROJECT_ID = get_secret("SUBSCRIBER_GCP_PROJECT_ID")

REDIS_HOST_SECRET_ID = "CONTEXT_MANAGER_REDIS_HOST"
REDIS_PORT_SECRET_ID = "CONTEXT_MANAGER_REDIS_PORT"
DLP_PROJECT_ID_SECRET_ID = "CONTEXT_MANAGER_DLP_PROJECT_ID" # This is already fetched via get_secret below

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

CONTEXT_TTL_SECONDS = int(os.getenv('CONTEXT_TTL_SECONDS', 90)) # Non-sensitive, from environment variable

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

# Load DLP configuration from dlp_config.yaml
DLP_CONFIG = {}
try:
    with open('dlp_config.yaml', 'r') as f:
        DLP_CONFIG = yaml.safe_load(f)
    logger.info("Successfully loaded dlp_config.yaml.")
except FileNotFoundError:
    logger.error("dlp_config.yaml not found. DLP functionality might be impaired.")
    DLP_CONFIG = {} # Ensure it's a dict
except yaml.YAMLError as e:
    logger.error(f"Error decoding dlp_config.yaml: {str(e)}. DLP functionality might be impaired.")
    DLP_CONFIG = {} # Ensure it's a dict
except Exception as e:
    logger.error(f"An unexpected error occurred while loading dlp_config.yaml: {str(e)}")
    DLP_CONFIG = {} # Ensure it's a dict


# Initialize DLP client
# For Cloud Run, it's generally okay to initialize clients globally as the container instance
# stays warm between requests.
dlp_client = None
try:
    dlp_location = DLP_CONFIG.get("dlp_location")
    if dlp_location:
        logger.info(f"DLP location specified: {dlp_location}. Initializing regional client.")
        client_options = {"api_endpoint": f"{dlp_location}-dlp.googleapis.com"}
        dlp_client = dlp_v2.DlpServiceClient(client_options=client_options)
    else:
        logger.info("No DLP location specified. Initializing global DLP client.")
        dlp_client = dlp_v2.DlpServiceClient()
    logger.info("Successfully initialized DLP client.")
except Exception as e:
    logger.error(f"Could not initialize DLP client. Error: {str(e)}")
    # dlp_client remains None


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
    redacted_transcript = call_dlp_for_redaction(transcript, retrieved_context)

    return jsonify({"redacted_transcript": redacted_transcript, "context_used": retrieved_context is not None}), 200

# Placeholder functions - to be implemented
def extract_expected_pii(transcript: str) -> str | None:
    """
    Analyzes the agent's transcript to identify if it's asking for a specific PII
    by matching keywords from the 'context_keywords' section of DLP_CONFIG.
    Returns the PII type (e.g., "PHONE_NUMBER") or None.
    """
    transcript_lower = transcript.lower()
    
    context_keywords = DLP_CONFIG.get("context_keywords", {})
    if not context_keywords:
        logger.warning("No 'context_keywords' found in DLP_CONFIG. Cannot extract expected PII.")
        return None

    # Iterate through the configured PII types and their associated keywords
    for pii_type, keywords in context_keywords.items():
        for keyword in keywords:
            if keyword in transcript_lower:
                logger.info(f"Detected keyword '{keyword}' for PII type '{pii_type}'.")
                return pii_type
                
    return None

def call_dlp_for_redaction(transcript: str, context: dict | None) -> str:
    """
    Calls Google DLP to de-identify PII in the transcript.
    Uses context if available to tailor the DLP request.
    """
    if not dlp_client:
        logger.warning("DLP client not available. Returning original transcript.")
        return transcript
    
    # Use the globally available GCP_PROJECT_ID_FOR_SECRETS for DLP operations
    current_gcp_project_id = GCP_PROJECT_ID_FOR_SECRETS
    if not current_gcp_project_id or current_gcp_project_id == 'your-gcp-project-id': # Basic check for placeholder
        logger.warning("GOOGLE_CLOUD_PROJECT environment variable not configured correctly. Returning original transcript.")
        return transcript

    dlp_location = DLP_CONFIG.get("dlp_location")

    item = {"value": transcript}
    logger.info(f"Using GCP_PROJECT_ID_FOR_SECRETS: '{current_gcp_project_id}'")
    if dlp_location:
        parent = f"projects/{current_gcp_project_id}/locations/{dlp_location}"
    else:
        parent = f"projects/{current_gcp_project_id}"

    # Get template names from DLP_CONFIG
    dlp_templates = DLP_CONFIG.get("dlp_templates", {})
    inspect_template_name = dlp_templates.get("inspect_template_name", "").replace("${PROJECT_ID}", current_gcp_project_id)
    deidentify_template_name = dlp_templates.get("deidentify_template_name", "").replace("${PROJECT_ID}", current_gcp_project_id)

    if not inspect_template_name:
        logger.warning("DLP Inspect Template name not found in dlp_config.yaml. DLP inspection might be impaired.")
    if not deidentify_template_name:
        logger.warning("DLP De-identify Template name not found in dlp_config.yaml. DLP de-identification might be impaired.")

    # Prepare the base inspect_config from dlp_config.yaml, which will be used if no template is specified
    # or as a fallback if a template is not found.
    base_inspect_config_from_yaml = DLP_CONFIG.get("inspect_config", {})

    # Initialize dynamic_inspect_config to apply overrides/additions to the template or base config
    dynamic_inspect_config = {}

    if context and context.get("expected_pii_type"):
        expected_type = context.get("expected_pii_type")
        logger.info(f"Contextual PII type received: {expected_type}. Adjusting DLP scan dynamically.")

        # Boost likelihood for the expected type
        dynamic_inspect_config["min_likelihood"] = dlp_v2.Likelihood.LIKELY

        # Dynamically add the expected PII type to info_types if not already present
        if "info_types" not in dynamic_inspect_config:
            dynamic_inspect_config["info_types"] = []
        dynamic_inspect_config["info_types"].append({"name": expected_type})

        # Example: Add a hotword rule dynamically for PHONE_NUMBER
        if expected_type == "PHONE_NUMBER":
            if "rule_set" not in dynamic_inspect_config:
                dynamic_inspect_config["rule_set"] = []
            dynamic_inspect_config["rule_set"].append(
                {
                    "info_types": [{"name": "PHONE_NUMBER"}],
                    "rules": [
                        {
                            "hotword_rule": {
                                "hotword_regex": {"pattern": "(?i)call|contact|number"},
                                "proximity": {"window_before": 20, "window_after": 20},
                                "likelihood_adjustment": {"fixed_likelihood": dlp_v2.Likelihood.VERY_LIKELY},
                            }
                        }
                    ],
                }
            )
            logger.info("DLP inspection configured for PHONE_NUMBER context with increased sensitivity and hotword rule.")
        else:
            logger.info(f"DLP inspection configured to include {expected_type} with increased sensitivity.")

    # Merge dynamic adjustments into the base_inspect_config_from_yaml to create the final inspect_config
    # that will be used if no template is specified or as a fallback.
    final_inline_inspect_config = base_inspect_config_from_yaml.copy() # Start with a copy to avoid modifying original DLP_CONFIG
    if dynamic_inspect_config:
        if "info_types" in dynamic_inspect_config:
            if "info_types" not in final_inline_inspect_config:
                final_inline_inspect_config["info_types"] = []
            
            existing_info_type_names = {it["name"] for it in final_inline_inspect_config["info_types"]}
            for new_info_type in dynamic_inspect_config["info_types"]:
                if new_info_type["name"] not in existing_info_type_names:
                    final_inline_inspect_config["info_types"].append(new_info_type)
            
        if "rule_set" in dynamic_inspect_config:
            if "rule_set" not in final_inline_inspect_config:
                final_inline_inspect_config["rule_set"] = []
            final_inline_inspect_config["rule_set"].extend(dynamic_inspect_config["rule_set"])

        for key, value in dynamic_inspect_config.items():
            if key not in ["info_types", "rule_set"]:
                final_inline_inspect_config[key] = value
        
        logger.info("Merged dynamic_inspect_config into final_inline_inspect_config.")

    # Define the default deidentify_config for fallback
    default_deidentify_config = DLP_CONFIG.get("deidentify_config", {
        "info_type_transformations": {
            "transformations": [
                {
                    "primitive_transformation": {
                        "replace_with_info_type_config": {}
                    }
                }
            ]
        }
    })

    try:
        logger.info(f"Sending request to DLP API for project_id: {current_gcp_project_id}, transcript_preview: {transcript[:100]}")
        
        request = {
            "parent": parent,
            "item": item,
        }

        # Configure inspection: Prioritize template, supplement with dynamic config, or use full inline config.
        if inspect_template_name:
            request["inspect_template_name"] = inspect_template_name
            logger.info(f"Using inspect_template_name: {inspect_template_name}")
            # If there are dynamic adjustments, add them to supplement the template.
            if dynamic_inspect_config:
                request["inspect_config"] = dynamic_inspect_config
                logger.info("Supplementing inspect template with dynamic context-based config.")
        else:
            # No template specified, so use the fully merged inline config.
            request["inspect_config"] = final_inline_inspect_config
            logger.info("Using fully merged inline inspect_config (no template name provided).")

        # Configure de-identification: Prioritize template or use default inline config.
        if deidentify_template_name:
            request["deidentify_template_name"] = deidentify_template_name
            logger.info(f"Using deidentify_template_name: {deidentify_template_name}")
        else:
            request["deidentify_config"] = default_deidentify_config
            logger.info("Using inline deidentify_config (no template name provided).")

        response = dlp_client.deidentify_content(request=request)
        
        redacted_value = response.item.value
        logger.info(f"DLP De-identification successful. Redacted_transcript_preview: {redacted_value[:100]}")
        return redacted_value

    except NotFound as e:
        logger.warning(f"DLP API Error: Requested inspect/deidentify template not found ({inspect_template_name}, {deidentify_template_name}). Falling back to inline configuration. Error: {str(e)}")
        
        # Fallback attempt: retry without templates, forcing inline config
        try:
            fallback_request = {
                "parent": parent,
                "item": item,
                "inspect_config": final_inline_inspect_config, # Always use the prepared inline config for fallback
                "deidentify_config": default_deidentify_config # Always use the prepared inline config for fallback
            }
            logger.info("Attempting DLP with inline inspect_config and deidentify_config (fallback).")
            response = dlp_client.deidentify_content(request=fallback_request)
            redacted_value = response.item.value
            logger.info(f"DLP De-identification successful (fallback). Redacted_transcript_preview: {redacted_value[:100]}")
            return redacted_value
        except Exception as fallback_e:
            logger.error(f"An unexpected error occurred during DLP API fallback call: {str(fallback_e)}")
            return f"[DLP_FALLBACK_PROCESSING_ERROR] {transcript}"

    except PermissionDenied as e:
        logger.error(f"DLP API Error: Permission denied for project '{current_gcp_project_id}'. Ensure the service account has 'DLP User' role. Error: {str(e)}")
        return f"[DLP_PERMISSION_DENIED_ERROR] {transcript}"

    except Exception as e:
        logger.error(f"An unexpected error occurred during DLP API call: {str(e)}")
        return f"[DLP_PROCESSING_ERROR] {transcript}"

if __name__ == "__main__":
    # This block is for local development only.
    # For Cloud Run, Gunicorn (as specified in Dockerfile) will run the app.
    # app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
    pass # No action needed when run by Gunicorn