import base64
import json
import os
import requests
import logging
import sys # Import sys for graceful exit
from flask import Flask, request, jsonify
from google.cloud import pubsub_v1
from google.cloud.secretmanager import SecretManagerServiceClient
from google.api_core.exceptions import NotFound, PermissionDenied
from google.auth.transport import requests as google_requests # Renamed to avoid conflict with 'requests'
from google.oauth2 import id_token

# Configure standard logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(module)s %(funcName)s %(lineno)d : %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Google Cloud Secret Manager Helper ---

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
        # Strip whitespace/newlines from the fetched secret
        payload = response.payload.data.decode("UTF-8").strip()
        logger.info(f"Successfully fetched secret: {secret_id}")
        return payload
    except NotFound:
        logger.error(f"Secret {secret_id} (version: {version_id}) not found in project {project_id}.")
        return None
    except PermissionDenied:
        logger.error(f"Permission denied when trying to access secret {secret_id} (version: {version_id}) in project {project_id}.")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching secret {secret_id} (version: {version_id}): {str(e)}")
        return None

# Configuration from Secret Manager
CONTEXT_MANAGER_URL_SECRET_ID = "SUBSCRIBER_CONTEXT_MANAGER_URL"
REDACTED_TOPIC_NAME_SECRET_ID = "SUBSCRIBER_REDACTED_TOPIC_NAME"
SUBSCRIBER_GCP_PROJECT_ID_SECRET_ID = "SUBSCRIBER_GCP_PROJECT_ID" # For PubSub client

CONTEXT_MANAGER_URL = None
REDACTED_TOPIC_NAME = None
SUBSCRIBER_GCP_PROJECT_ID = None # This will be used for PubSub client

# Fetch secrets at module load.
def load_secrets():
    global CONTEXT_MANAGER_URL, REDACTED_TOPIC_NAME, SUBSCRIBER_GCP_PROJECT_ID
    
    # Initialize GCP_PROJECT_ID_FOR_SECRETS within the function to ensure it's loaded from the environment
    global GCP_PROJECT_ID_FOR_SECRETS
    GCP_PROJECT_ID_FOR_SECRETS = os.getenv("GCP_PROJECT_ID_FOR_SECRETS")
    logger.info(f"--- DEBUG: GCP_PROJECT_ID_FOR_SECRETS from environment: {GCP_PROJECT_ID_FOR_SECRETS}")

    CONTEXT_MANAGER_URL = get_secret(CONTEXT_MANAGER_URL_SECRET_ID, project_id=GCP_PROJECT_ID_FOR_SECRETS)
    if not CONTEXT_MANAGER_URL:
        logger.critical(f"Critical: CONTEXT_MANAGER_URL secret ('{CONTEXT_MANAGER_URL_SECRET_ID}') could not be fetched. Exiting.")
        raise RuntimeError("Critical secret CONTEXT_MANAGER_URL could not be fetched. Application startup aborted.")

    REDACTED_TOPIC_NAME = get_secret(REDACTED_TOPIC_NAME_SECRET_ID, project_id=GCP_PROJECT_ID_FOR_SECRETS)
    if not REDACTED_TOPIC_NAME:
        logger.critical(f"Critical: REDACTED_TOPIC_NAME secret ('{REDACTED_TOPIC_NAME_SECRET_ID}') could not be fetched. Exiting.")
        sys.exit(1) # Exit if critical secret is missing

    SUBSCRIBER_GCP_PROJECT_ID = get_secret(SUBSCRIBER_GCP_PROJECT_ID_SECRET_ID, project_id=GCP_PROJECT_ID_FOR_SECRETS)
    if not SUBSCRIBER_GCP_PROJECT_ID:
        logger.critical(f"Critical: SUBSCRIBER_GCP_PROJECT_ID secret ('{SUBSCRIBER_GCP_PROJECT_ID_SECRET_ID}') could not be fetched. Exiting.")
        sys.exit(1) # Exit if critical secret is missing

load_secrets()

# --- Identity Token Generation Helper ---
_cached_id_tokens = {} # Cache for ID tokens to avoid re-fetching frequently

def get_id_token(audience: str) -> str:
    """
    Generates a Google-signed ID token for a given audience (Cloud Run service URL).
    Tokens are cached for efficiency.
    """
    if audience in _cached_id_tokens:
        # In a real-world scenario, you'd also check token expiration here.
        # For simplicity, we're assuming tokens are valid for the duration of the request.
        logger.info(f"Using cached ID token for audience: {audience}")
        return _cached_id_tokens[audience]

    try:
        # requests.Request() is used here as a placeholder for the actual HTTP request object
        # that id_token.fetch_id_token expects for its internal HTTP client.
        # It will use the default credentials available in the Cloud Run environment.
        auth_req = google_requests.Request()
        token = id_token.fetch_id_token(auth_req, audience)
        _cached_id_tokens[audience] = token
        logger.info(f"Successfully fetched new ID token for audience: {audience}")
        return token
    except Exception as e:
        logger.error(f"Error fetching ID token for audience {audience}: {str(e)}")
        return None

def get_full_topic_path(topic_name, project_id):
    """Constructs the full Pub/Sub topic path if not already provided."""
    if not topic_name or not project_id:
        return None
    
    # Clean up inputs just in case
    clean_topic_name = topic_name.strip()
    clean_project_id = project_id.strip()

    if clean_topic_name.startswith("projects/"):
        return clean_topic_name
    
    topic_name_only = clean_topic_name.split('/')[-1]
    return f"projects/{clean_project_id}/topics/{topic_name_only}"

publisher = None

def initialize_publisher():
    global publisher
    if publisher is None:
        if SUBSCRIBER_GCP_PROJECT_ID:
             logger.info(f"PubSub client will operate in project context: {SUBSCRIBER_GCP_PROJECT_ID} (used for topic path construction).")
        publisher = pubsub_v1.PublisherClient()


@app.route('/', methods=['POST'])
def process_transcript_event():
    """
    Cloud Run entry point. Triggered by a message on a Pub/Sub topic.
    Processes each entry in an Agent Assist transcript.
    """
    global CONTEXT_MANAGER_URL, REDACTED_TOPIC_NAME, SUBSCRIBER_GCP_PROJECT_ID
    global publisher

    envelope = request.get_json()
    if not envelope:
        msg = "no Pub/Sub message received"
        logger.error(f"error: {msg}")
        return f"Bad Request: {msg}", 400

    if not isinstance(envelope, dict) or "message" not in envelope:
        msg = "invalid Pub/Sub message format"
        logger.error(f"error: {msg}")
        return f"Bad Request: {msg}", 400

    pubsub_message = envelope["message"]
    
    logger.info("ENTRY POINT ---")
    
    if not CONTEXT_MANAGER_URL:
        logger.error(f"CONTEXT_MANAGER_URL secret ('{CONTEXT_MANAGER_URL_SECRET_ID}') was not loaded. Aborting function.")
        return "Internal Server Error", 500
    if not REDACTED_TOPIC_NAME:
        logger.error(f"REDACTED_TOPIC_NAME secret ('{REDACTED_TOPIC_NAME_SECRET_ID}') was not loaded. Aborting function.")
        return "Internal Server Error", 500
    if not SUBSCRIBER_GCP_PROJECT_ID:
        logger.error(f"SUBSCRIBER_GCP_PROJECT_ID secret ('{SUBSCRIBER_GCP_PROJECT_ID_SECRET_ID}') was not loaded. Aborting function.")
        return "Internal Server Error", 500

    initialize_publisher()

    try:
        if 'data' in pubsub_message:
            pubsub_message_data = base64.b64decode(pubsub_message['data']).decode('utf-8')
            message_payload = json.loads(pubsub_message_data)
            logger.info(f"Decoded message payload: {json.dumps(message_payload)}")
        else:
            logger.error(f"--- DEBUG EARLY --- 'data' key missing in event or event is not a dict. Event: {pubsub_message}")
            return "Bad Request", 400

        # Extract fields directly from the message_payload (individual utterance)
        conversation_id = message_payload.get('conversation_id')
        original_entry_index = message_payload.get('original_entry_index')
        participant_role_raw = message_payload.get('participant_role')
        transcript = message_payload.get('text')
        user_id = message_payload.get('user_id')
        start_timestamp_usec = message_payload.get('start_timestamp_usec')

        # Validate required fields for an individual utterance
        required_fields = {
            'conversation_id': conversation_id,
            'original_entry_index': original_entry_index,
            'participant_role': participant_role_raw,
            'text': transcript,
            'start_timestamp_usec': start_timestamp_usec
        }

        missing_fields = [field for field, value in required_fields.items() if value is None or (isinstance(value, str) and not value.strip())]
        if missing_fields:
            logger.error(f"Missing required fields in individual utterance payload: {', '.join(missing_fields)}. Aborting.", extra={"json_fields": {"event": "missing_fields_error", "missing_fields": missing_fields, "payload": message_payload}})
            return "Bad Request", 400

        participant_role = participant_role_raw.upper() if participant_role_raw else ''
        if not participant_role:
            logger.error(f"Participant role is empty after processing. Aborting.", extra={"json_fields": {"event": "empty_participant_role", "payload": message_payload}})
            return "Bad Request", 400

        headers = {'Content-Type': 'application/json'}
        
        # Add Authorization header with ID token
        if CONTEXT_MANAGER_URL:
            id_token_value = get_id_token(CONTEXT_MANAGER_URL)
            if id_token_value:
                headers['Authorization'] = f'Bearer {id_token_value}'
            else:
                logger.error(f"Could not obtain ID token for Context Manager URL: {CONTEXT_MANAGER_URL}. Proceeding without authentication.")
        else:
            logger.warning("CONTEXT_MANAGER_URL is not set. Cannot generate ID token for authentication.")
        service_payload = {
            "conversation_id": conversation_id,
            "transcript": transcript
        }

        try:
            if participant_role == 'AGENT':
                endpoint = f"{CONTEXT_MANAGER_URL}/handle-agent-utterance"
                response = requests.post(endpoint, json=service_payload, headers=headers, timeout=10)
                response.raise_for_status()
                response_data = response.json()
                logger.info(f"Agent utterance (entry {original_entry_index}) processed. Response data: {response_data}")
 
                redacted_transcript = response_data.get('redacted_transcript', transcript) # Fallback to original if not found
 
                if publisher and REDACTED_TOPIC_NAME:
                    full_redacted_topic_path = get_full_topic_path(REDACTED_TOPIC_NAME, SUBSCRIBER_GCP_PROJECT_ID)
 
                    publish_payload = {
                        "conversation_id": conversation_id,
                        "original_entry_index": original_entry_index,
                        "text": redacted_transcript,
                        "participant_role": participant_role,
                        "user_id": user_id,
                        "start_timestamp_usec": start_timestamp_usec
                    }
                    message_bytes = json.dumps(publish_payload).encode('utf-8')
                    
                    try:
                        publish_future = publisher.publish(full_redacted_topic_path, data=message_bytes)
                        publish_future.result(timeout=10)
                        logger.info(f"Published AGENT transcript for entry {original_entry_index} to topic: {full_redacted_topic_path}.")
                    except Exception as pub_e:
                        logger.error(f"Error publishing AGENT transcript for entry {original_entry_index}. Error: {str(pub_e)}")

            elif participant_role == 'END_USER' or participant_role == 'CUSTOMER':
                endpoint = f"{CONTEXT_MANAGER_URL}/handle-customer-utterance"
                response = requests.post(endpoint, json=service_payload, headers=headers, timeout=10)
                response.raise_for_status()
                
                response_data = response.json()
                logger.info(f"Customer utterance (entry {original_entry_index}) processed. Response data: {response_data}")

                redacted_transcript = response_data.get('redacted_transcript')
                if redacted_transcript is not None:
                    if publisher and REDACTED_TOPIC_NAME:
                        full_redacted_topic_path = get_full_topic_path(REDACTED_TOPIC_NAME, SUBSCRIBER_GCP_PROJECT_ID)

                        publish_payload = {
                            "conversation_id": conversation_id,
                            "original_entry_index": original_entry_index,
                            "text": redacted_transcript,
                            "participant_role": participant_role,
                            "user_id": user_id,
                            "start_timestamp_usec": start_timestamp_usec
                        }
                        message_bytes = json.dumps(publish_payload).encode('utf-8')
                        
                        try:
                            publish_future = publisher.publish(full_redacted_topic_path, data=message_bytes)
                            publish_future.result(timeout=10)
                            logger.info(f"Published redacted transcript for entry {original_entry_index} to topic: {full_redacted_topic_path}.")
                        except Exception as pub_e:
                            logger.error(f"Error publishing for entry {original_entry_index}. Error: {str(pub_e)}")
                    else:
                        logger.warning(f"Publisher not init or topic name missing for entry {original_entry_index}.")
                else:
                    logger.info(f"No redacted_transcript in response for entry {original_entry_index}.")
            else:
                logger.warning(f"Unknown participant_role: '{participant_role}' in entry {original_entry_index}. Skipping.")

        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error for entry {original_entry_index}: {str(http_err)}, response: {http_err.response.text if http_err.response else 'No response text'}")
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Request error for entry {original_entry_index}: {str(req_err)}")
        except json.JSONDecodeError as json_err_resp:
             logger.error(f"Error decoding JSON response from Context Manager for entry {original_entry_index}: {str(json_err_resp)}")

        logger.info(f"Entry {original_entry_index} processed successfully for conversation {conversation_id} ---")
        return "OK", 200

    except json.JSONDecodeError as json_err_msg:
        logger.error(f"Error decoding initial JSON from Pub/Sub: {str(json_err_msg)}, data: {pubsub_message.get('data')}")
        return "Bad Request", 400
    except Exception as e:
        logger.error(f"UNEXPECTED TOP LEVEL ERROR: {str(e)} ---", exc_info=True)
        return "Internal Server Error", 500

if __name__ == "__main__":
    # This block is for local development only.
    # For Cloud Run, Gunicorn (as specified in Dockerfile) will run the app.
    pass