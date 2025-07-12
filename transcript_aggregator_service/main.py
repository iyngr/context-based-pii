import base64
import json
import logging
import time
from flask import Flask, request, jsonify
import os
from datetime import datetime, timedelta, timezone
from google.cloud import firestore, storage # Firestore is imported here
from google.protobuf.timestamp_pb2 import Timestamp as ProtoTimestamp # Alias the protobuf Timestamp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core.exceptions import InternalServerError, ServiceUnavailable, DeadlineExceeded, AlreadyExists, GoogleAPICallError
import requests # New import for making HTTP requests
# Removed redis and secretmanager imports as per user's request to revert to environment variables
# import redis
# from google.cloud.secretmanager import SecretManagerServiceClient
# from google.api_core.exceptions import NotFound, PermissionDenied

# Configure structured logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "serviceContext": {
                "service": "transcript-aggregator-service",
                "version": os.getenv("GAE_VERSION", "local")
            }
        }
        if hasattr(record, 'json_fields'):
            log_record.update(record.json_fields)
        
        if record.exc_info:
            # Format the exception information
            log_record["exception_info"] = self.formatException(record.exc_info)
        elif record.exc_text:
            log_record["exception_info"] = record.exc_text
            
        return json.dumps(log_record)

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# Initialize Firestore client
db = firestore.Client(database="redacted-transcript-db")

# Initialize GCS Client
storage_client = storage.Client()
AGGREGATED_TRANSCRIPTS_BUCKET = os.getenv('AGGREGATED_TRANSCRIPTS_BUCKET')

# Reverted to reading directly from environment variables
REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379)) # Default to 6379

# --- Custom JSON Encoder ---
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super(DateTimeEncoder, self).default(obj)
 
redis_client = None
if REDIS_HOST:
    try:
        redis_client = redis.StrictRedis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=0,
            decode_responses=True,
            socket_connect_timeout=10
        )
        redis_client.ping()
        logger.info("Successfully connected to Redis for utterance buffering.")
    except Exception as e:
        logger.error(f"Could not connect to Redis for utterance buffering: {e}", exc_info=True)
else:
    logger.warning("REDIS_HOST environment variable not set. Multi-turn context buffering will be inactive.")
 
# Configure TTL for conversation context
CONTEXT_TTL_SECONDS = int(os.getenv('CONTEXT_TTL_SECONDS', 3600)) # Default to 1 hour
 
# Main Service URL for sending aggregated transcripts
MAIN_SERVICE_URL = os.getenv('MAIN_SERVICE_URL')
if not MAIN_SERVICE_URL:
    logger.critical("MAIN_SERVICE_URL environment variable not set. Cannot forward aggregated transcripts.")
    # Depending on deployment strategy, you might want to exit here.
    # For now, we'll just log a critical error.
 
app = Flask(__name__)
 
@app.route('/redacted-transcripts', methods=['POST'])
def receive_redacted_transcripts():
    """
    Receives and processes Pub/Sub messages for redacted transcripts.
    """
    envelope = request.get_json()
    if not envelope:
        logger.error("No Pub/Sub message received.", extra={"json_fields": {"event": "message_reception_error", "reason": "no_envelope"}})
        return jsonify({'error': 'No Pub/Sub message received'}), 400

    if not isinstance(envelope, dict) or 'message' not in envelope:
        logger.error("Invalid Pub/Sub message format.", extra={"json_fields": {"event": "message_reception_error", "reason": "invalid_format"}})
        return jsonify({'error': 'Invalid Pub/Sub message format'}), 400

    pubsub_message = envelope['message']

    if 'data' not in pubsub_message:
        logger.error("No data in Pub/Sub message.", extra={"json_fields": {"event": "message_reception_error", "reason": "no_data"}})
        return jsonify({'error': 'No data in Pub/Sub message'}), 400

    try:
        # Pub/Sub message data is base64 encoded
        data = base64.b64decode(pubsub_message['data']).decode('utf-8')
        message_data = json.loads(data)
        logger.info("Message received from 'redacted-transcripts' topic.", extra={"json_fields": {"event": "message_received", "topic": "redacted-transcripts", "message_id": pubsub_message.get('message_id')}})
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Could not decode or parse message data: {e}", extra={"json_fields": {"event": "message_parsing_error", "error_details": str(e)}})
        return jsonify({'error': f'Could not decode or parse message data: {e}'}), 400

    # Extract required fields
    conversation_id = message_data.get('conversation_id')
    redacted_transcript = message_data.get('text')
    original_entry_index = message_data.get('original_entry_index')
    participant_role = message_data.get('participant_role')
    user_id = message_data.get('user_id')
    start_timestamp_usec = message_data.get('start_timestamp_usec')

    required_fields = {
        'conversation_id': conversation_id,
        'text': redacted_transcript,
        'original_entry_index': original_entry_index,
        'participant_role': participant_role,
        'start_timestamp_usec': start_timestamp_usec
    }

    missing_fields = [field for field, value in required_fields.items() if value is None or (isinstance(value, str) and not value.strip())]

    if missing_fields:
        logger.error(f"Missing required fields: {', '.join(missing_fields)}", extra={"json_fields": {"event": "missing_fields_error", "missing_fields": missing_fields}})
        return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400

    try:
        # Store the utterance in Firestore
        doc_ref = db.collection('conversations').document(conversation_id).collection('utterances').document(str(original_entry_index))
        doc_ref.set({
            'text': redacted_transcript,
            'original_entry_index': original_entry_index,
            'participant_role': participant_role,
            'user_id': user_id,
            'start_timestamp_usec': start_timestamp_usec,
            'received_at': firestore.SERVER_TIMESTAMP
        })
        logger.info(f"Firestore: Stored utterance {original_entry_index} for conversation {conversation_id}.", extra={"json_fields": {"event": "firestore_utterance_store", "conversation_id": conversation_id, "original_entry_index": original_entry_index}})
        return jsonify({'status': 'success', 'message': 'Utterance stored in Firestore'}), 200

    except Exception as e:
        logger.error(f"An unexpected error occurred in /redacted-transcripts for conversation {conversation_id}: {e}", exc_info=True, extra={"json_fields": {"event": "unhandled_exception", "conversation_id": conversation_id, "error_details": str(e)}})
        return jsonify({'error': f'An unexpected error occurred: {e}'}), 500

@app.route('/conversation-ended', methods=['POST'])
def receive_conversation_ended_event():
    """
    Receives and processes Pub/Sub messages for conversation ended events.
    This function will now trigger the final aggregation and upload to GCS from Firestore.
    """
    envelope = request.get_json()
    if not envelope:
        logger.error("No Pub/Sub message received for conversation ended event.", extra={"json_fields": {"event": "message_reception_error", "reason": "no_envelope"}})
        return jsonify({'error': 'No Pub/Sub message received'}), 400

    if not isinstance(envelope, dict) or 'message' not in envelope:
        logger.error("Invalid Pub/Sub message format for conversation ended event.", extra={"json_fields": {"event": "message_reception_error", "reason": "invalid_format"}})
        return jsonify({'error': 'Invalid Pub/Sub message format'}), 400

    pubsub_message = envelope['message']

    try:
        if 'data' not in pubsub_message:
            logger.error("No data in Pub/Sub message for conversation ended event.", extra={"json_fields": {"event": "message_reception_error", "reason": "no_data"}})
            return jsonify({'error': 'No data in Pub/Sub message'}), 400

        data = base64.b64decode(pubsub_message['data']).decode('utf-8')
        message_data = json.loads(data)
        logger.info("Message received from 'aa-lifecycle-event-notification' topic.", extra={"json_fields": {"event": "message_received", "topic": "aa-lifecycle-event-notification", "message_id": pubsub_message.get('message_id')}})
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Could not decode or parse message data for conversation ended event: {e}", extra={"json_fields": {"event": "message_parsing_error", "error_details": str(e)}})
        return jsonify({'error': f'Could not decode or parse message data: {e}'}), 400

    try:
        conversation_id = message_data.get('conversation_id')
        event_type = message_data.get('event_type')

        if not conversation_id:
            logger.error("Missing conversation_id in message data for conversation ended event.", extra={"json_fields": {"event": "missing_fields_error", "missing_fields": ["conversation_id"]}})
            return jsonify({'error': 'Missing conversation_id in message data'}), 400

        if event_type != 'conversation_ended':
            logger.info(f"Received lifecycle event with type: {event_type}. This handler only processes 'conversation_ended' events, skipping.", extra={"json_fields": {"event": "lifecycle_event_skipped", "conversation_id": conversation_id, "received_event_type": event_type}})
            return jsonify({'status': 'ignored', 'message': f'Event type {event_type} not processed by this handler.'}), 200

        logger.info(f"Received conversation ended event for Conversation ID: {conversation_id}.", extra={"json_fields": {"event": "conversation_ended_event", "conversation_id": conversation_id}})

        # Retrieve all utterances from Firestore for final aggregation
        utterances_ref = db.collection('conversations').document(conversation_id).collection('utterances')
        utterances = utterances_ref.order_by('original_entry_index').stream()

        entries_for_gcs = [utterance.to_dict() for utterance in utterances]

        if not entries_for_gcs:
            logger.warning(f"No utterances found in Firestore for conversation ID: {conversation_id} during final aggregation. Skipping GCS upload.", extra={"json_fields": {"event": "gcs_upload_skipped", "conversation_id": conversation_id, "reason": "no_utterances_in_firestore"}})
            return jsonify({'status': 'skipped', 'message': 'No utterances found in Firestore, skipping GCS upload'}), 500 # Changed to 500 as it's a critical failure for the batch process

        # Upload Aggregated Transcript to GCS
        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10),
               retry=retry_if_exception_type((InternalServerError, ServiceUnavailable, DeadlineExceeded)))
        def _gcs_upload_with_retry(bucket_name, filename, content):
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(filename)
            blob.upload_from_string(content, content_type='application/json')

        if not AGGREGATED_TRANSCRIPTS_BUCKET:
            logger.error("AGGREGATED_TRANSCRIPTS_BUCKET environment variable not set.", extra={"json_fields": {"event": "configuration_error", "variable": "AGGREGATED_TRANSCRIPTS_BUCKET"}})
            return jsonify({'error': 'AGGREGATED_TRANSCRIPTS_BUCKET environment variable not set'}), 500

        try:
            logger.info("Starting GCS JSON preparation for final aggregation.", extra={"json_fields": {"event": "gcs_prep_start_final", "conversation_id": conversation_id}})

            gcs_payload_dict = {"entries": entries_for_gcs}
            json_payload_for_gcs = json.dumps(gcs_payload_dict, indent=2, cls=DateTimeEncoder)
            
            gcs_transcript_filename = f"{conversation_id}_transcript.json"
            
            _gcs_upload_with_retry(AGGREGATED_TRANSCRIPTS_BUCKET, gcs_transcript_filename, json_payload_for_gcs)
            gcs_transcript_uri = f"gs://{AGGREGATED_TRANSCRIPTS_BUCKET}/{gcs_transcript_filename}"
            logger.info(f"Uploaded final aggregated transcript to GCS: {gcs_transcript_uri}", extra={"json_fields": {"event": "gcs_upload_success_final", "conversation_id": conversation_id, "gcs_uri": gcs_transcript_uri}})

        except Exception as e:
            logger.error(f"Error during final GCS upload. Exception: {e}", exc_info=True, extra={"json_fields": {"event": "gcs_upload_error_final", "conversation_id": conversation_id, "error_message": str(e)}})
            return jsonify({'error': f'Failed to process and upload final transcript: {e}'}), 500

        return jsonify({'status': 'success', 'message': 'Conversation ended event processed and final transcript uploaded to GCS'}), 200
    except Exception as e:
        logger.error(f"Unhandled exception in /conversation-ended. Exception: {e}, Type: {type(e)}, Repr: {repr(e)}", exc_info=True, extra={"json_fields": {"event": "unhandled_exception", "error_message": str(e), "error_type": str(type(e)), "error_repr": repr(e)}})
        return jsonify({'error': f'An unexpected error occurred: {e}'}), 500
