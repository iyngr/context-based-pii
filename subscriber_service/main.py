import base64
import json
import os
import requests
import logging
from flask import Flask, request, jsonify
from google.cloud import pubsub_v1
from google.cloud.secretmanager import SecretManagerServiceClient
from google.api_core.exceptions import NotFound, PermissionDenied

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
        payload = response.payload.data.decode("UTF-8")
        logger.info(f"Successfully fetched secret: {secret_id} (version: {version_id})")
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
        logger.critical(f"Critical: CONTEXT_MANAGER_URL secret ('{CONTEXT_MANAGER_URL_SECRET_ID}') could not be fetched. Function may not operate correctly.")

    REDACTED_TOPIC_NAME = get_secret(REDACTED_TOPIC_NAME_SECRET_ID, project_id=GCP_PROJECT_ID_FOR_SECRETS)
    if not REDACTED_TOPIC_NAME:
        logger.critical(f"Critical: REDACTED_TOPIC_NAME secret ('{REDACTED_TOPIC_NAME_SECRET_ID}') could not be fetched. Function may not operate correctly.")

    SUBSCRIBER_GCP_PROJECT_ID = get_secret(SUBSCRIBER_GCP_PROJECT_ID_SECRET_ID, project_id=GCP_PROJECT_ID_FOR_SECRETS)
    if not SUBSCRIBER_GCP_PROJECT_ID:
        logger.critical(f"Critical: SUBSCRIBER_GCP_PROJECT_ID secret ('{SUBSCRIBER_GCP_PROJECT_ID_SECRET_ID}') could not be fetched. Pub/Sub client may fail.")

load_secrets()


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
    
    logger.info("--- CORRECTED CODE (main.py) V1 --- ENTRY POINT ---")
    
    if not CONTEXT_MANAGER_URL:
        logger.error(f"--- CORRECTED CODE (main.py) V1 --- CONTEXT_MANAGER_URL secret ('{CONTEXT_MANAGER_URL_SECRET_ID}') was not loaded. Aborting function.")
        return "Internal Server Error", 500
    if not REDACTED_TOPIC_NAME:
        logger.error(f"--- CORRECTED CODE (main.py) V1 --- REDACTED_TOPIC_NAME secret ('{REDACTED_TOPIC_NAME_SECRET_ID}') was not loaded. Aborting function.")
        return "Internal Server Error", 500
    if not SUBSCRIBER_GCP_PROJECT_ID:
        logger.error(f"--- CORRECTED CODE (main.py) V1 --- SUBSCRIBER_GCP_PROJECT_ID secret ('{SUBSCRIBER_GCP_PROJECT_ID_SECRET_ID}') was not loaded. Aborting function.")
        return "Internal Server Error", 500

    initialize_publisher()

    try:
        if 'data' in pubsub_message:
            pubsub_message_data = base64.b64decode(pubsub_message['data']).decode('utf-8')
            message_payload = json.loads(pubsub_message_data)
            logger.info(f"--- CORRECTED CODE (main.py) V1 --- Decoded message payload: {json.dumps(message_payload)}")
        else:
            logger.error(f"--- DEBUG EARLY --- 'data' key missing in event or event is not a dict. Event: {pubsub_message}")
            return "Bad Request", 400

        conversation_info = message_payload.get('conversation_info', {})
        conversation_id = conversation_info.get('sessionId')

        if not conversation_id:
            logger.error("--- CORRECTED CODE (main.py) V1 --- Missing 'sessionId' in 'conversation_info'. Aborting.")
            return "Bad Request", 400

        entries = message_payload.get('entries', [])
        if not entries:
            logger.warning("--- CORRECTED CODE (main.py) V1 --- No 'entries' found. Nothing to process.")
            return "OK", 200

        headers = {'Content-Type': 'application/json'}

        for entry_index, entry in enumerate(entries):
            transcript = entry.get('text')
            participant_role_raw = entry.get('role')
            participant_role = participant_role_raw.upper() if participant_role_raw else ''

            if not transcript or not participant_role:
                logger.error(f"--- CORRECTED CODE (main.py) V1 --- Missing 'text' (transcript) or 'role' in entry {entry_index + 1}. Skipping.")
                continue

            service_payload = {
                "conversation_id": conversation_id,
                "transcript": transcript
            }

            try:
                if participant_role == 'AGENT':
                    endpoint = f"{CONTEXT_MANAGER_URL}/handle-agent-utterance"
                    response = requests.post(endpoint, json=service_payload, headers=headers, timeout=10)
                    response.raise_for_status()
                    logger.info(f"--- CORRECTED CODE (main.py) V1 --- Agent utterance (entry {entry_index + 1}) processed. Response: {response.text}")

                elif participant_role == 'END_USER' or participant_role == 'CUSTOMER':
                    endpoint = f"{CONTEXT_MANAGER_URL}/handle-customer-utterance"
                    response = requests.post(endpoint, json=service_payload, headers=headers, timeout=10)
                    response.raise_for_status()
                    
                    response_data = response.json()
                    logger.info(f"--- CORRECTED CODE (main.py) V1 --- Customer utterance (entry {entry_index + 1}) processed. Response data: {response_data}")

                    redacted_transcript = response_data.get('redacted_transcript')
                    if redacted_transcript is not None:
                        if publisher and REDACTED_TOPIC_NAME:
                            clean_redacted_topic_name = REDACTED_TOPIC_NAME.strip()
                            clean_subscriber_gcp_project_id = SUBSCRIBER_GCP_PROJECT_ID.strip()

                            full_redacted_topic_path = clean_redacted_topic_name
                            if not clean_redacted_topic_name.startswith("projects/"):
                                topic_name_only = clean_redacted_topic_name.split('/')[-1]
                                full_redacted_topic_path = f"projects/{clean_subscriber_gcp_project_id}/topics/{topic_name_only}"
                        
                            publish_payload = {
                                "conversation_id": conversation_id,
                                "original_entry_index": entry_index,
                                "redacted_transcript": redacted_transcript,
                                "original_transcript": transcript,
                                "participant_role": participant_role,
                                "user_id": entry.get('user_id'),
                                "start_timestamp_usec": entry.get('start_timestamp_usec'),
                                "language_code": message_payload.get("language_code")
                            }
                            message_bytes = json.dumps(publish_payload).encode('utf-8')
                            
                            try:
                                publish_future = publisher.publish(full_redacted_topic_path, data=message_bytes)
                                publish_future.result(timeout=10)
                                logger.info(f"--- CORRECTED CODE (main.py) V1 --- Published redacted transcript for entry {entry_index + 1} to topic: {full_redacted_topic_path}.")
                            except Exception as pub_e:
                                logger.error(f"--- CORRECTED CODE (main.py) V1 --- Error publishing for entry {entry_index + 1}. Error: {str(pub_e)}")
                        else:
                            logger.warning(f"--- CORRECTED CODE (main.py) V1 --- Publisher not init or topic name missing for entry {entry_index + 1}.")
                    else:
                        logger.info(f"--- CORRECTED CODE (main.py) V1 --- No redacted_transcript in response for entry {entry_index + 1}.")
                else:
                    logger.warning(f"--- CORRECTED CODE (main.py) V1 --- Unknown participant_role: '{participant_role}' in entry {entry_index + 1}. Skipping.")

            except requests.exceptions.HTTPError as http_err:
                logger.error(f"--- CORRECTED CODE (main.py) V1 --- HTTP error for entry {entry_index + 1}: {str(http_err)}, response: {http_err.response.text if http_err.response else 'No response text'}")
            except requests.exceptions.RequestException as req_err:
                logger.error(f"--- CORRECTED CODE (main.py) V1 --- Request error for entry {entry_index + 1}: {str(req_err)}")
            except json.JSONDecodeError as json_err_resp:
                 logger.error(f"--- CORRECTED CODE (main.py) V1 --- Error decoding JSON response from Context Manager for entry {entry_index + 1}: {str(json_err_resp)}")

        logger.info("--- CORRECTED CODE (main.py) V1 --- All entries processed ---")
        return "OK", 200

    except json.JSONDecodeError as json_err_msg:
        logger.error(f"--- CORRECTED CODE (main.py) V1 --- Error decoding initial JSON from Pub/Sub: {str(json_err_msg)}, data: {pubsub_message.get('data')}")
        return "Bad Request", 400
    except Exception as e:
        logger.error(f"--- CORRECTED CODE (main.py) V1 --- UNEXPECTED TOP LEVEL ERROR: {str(e)} ---", exc_info=True)
        return "Internal Server Error", 500

if __name__ == "__main__":
    # This block is for local development only.
    # For Cloud Run, Gunicorn (as specified in Dockerfile) will run the app.
    pass