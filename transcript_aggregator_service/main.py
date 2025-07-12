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
import redis  # Added import for redis
# Removed redis and secretmanager imports as per user's request to revert to environment variables
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
    original_text = message_data.get('original_text')  # Also store original text if available
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
        utterance_data = {
            'text': redacted_transcript,
            'original_entry_index': original_entry_index,
            'participant_role': participant_role,
            'user_id': user_id,
            'start_timestamp_usec': start_timestamp_usec,
            'received_at': firestore.SERVER_TIMESTAMP
        }
        
        # Store original text if available
        if original_text:
            utterance_data['original_text'] = original_text
        
        doc_ref.set(utterance_data)
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

        # Introduce a delay to mitigate race condition between transcript persistence and conversation ended event.
        time.sleep(10)

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

            # The GCS payload must be a JSON object with an "entries" key.
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

@app.route('/conversation/<conversation_id>', methods=['GET'])
def get_conversation_realtime(conversation_id):
    """
    Retrieves conversation data directly from Firestore for real-time display.
    Returns both original and redacted transcripts in the same format as main_service.
    """
    try:
        # Retrieve all utterances from Firestore for this conversation
        utterances_ref = db.collection('conversations').document(conversation_id).collection('utterances')
        utterances = utterances_ref.order_by('original_entry_index').stream()
        
        utterances_data = []
        for utterance in utterances:
            data = utterance.to_dict()
            utterances_data.append(data)
        
        if not utterances_data:
            logger.info(f"No utterances found in Firestore for conversation {conversation_id}.", 
                       extra={"json_fields": {"event": "no_utterances_found", "conversation_id": conversation_id}})
            return jsonify({
                "status": "PROCESSING",
                "message": "No utterances found yet",
                "original_conversation": {"transcript": {"transcript_segments": []}},
                "redacted_conversation": {"transcript": {"transcript_segments": []}}
            }), 200
        
        # Try to get original transcripts from Redis if available
        original_transcript_segments = []
        redacted_transcript_segments = []
        
        # First try to build original transcript from Firestore data
        has_original_in_firestore = any(utterance_data.get('original_text') for utterance_data in utterances_data)
        
        if has_original_in_firestore:
            # Use original text from Firestore
            for utterance_data in utterances_data:
                speaker = "END_USER" if utterance_data.get('participant_role') == "END_USER" else "AGENT"
                original_transcript_segments.append({
                    "speaker": speaker,
                    "text": utterance_data.get('original_text', utterance_data.get('text', ''))
                })
            logger.info(f"Retrieved original transcript from Firestore for conversation {conversation_id}.")
        else:
            # Fallback to Redis for original transcripts
            if redis_client:
                try:
                    original_conversation_str = redis_client.get(f"original_conversation:{conversation_id}")
                    if original_conversation_str:
                        original_transcript_segments = json.loads(original_conversation_str)
                        logger.info(f"Retrieved original transcript from Redis for conversation {conversation_id}.")
                except Exception as e:
                    logger.warning(f"Could not retrieve original transcript from Redis for conversation {conversation_id}: {e}")
        
        # Build redacted transcript segments from Firestore data
        for utterance_data in utterances_data:
            speaker = "END_USER" if utterance_data.get('participant_role') == "END_USER" else "AGENT"
            redacted_transcript_segments.append({
                "speaker": speaker,
                "text": utterance_data.get('text', '')
            })
        
        # If we don't have original transcripts from either source, create placeholder structure
        if not original_transcript_segments:
            logger.warning(f"No original transcript found for conversation {conversation_id}. Using redacted as placeholder.")
            # Create a basic structure - in production you might want to store originals in Firestore too
            for utterance_data in utterances_data:
                speaker = "END_USER" if utterance_data.get('participant_role') == "END_USER" else "AGENT"
                original_transcript_segments.append({
                    "speaker": speaker,
                    "text": "[Original text not available]"
                })
        
        response_data = {
            "status": "PROCESSING" if len(utterances_data) == 0 else "PARTIAL",
            "conversation_id": conversation_id,
            "utterance_count": len(utterances_data),
            "original_conversation": {
                "transcript": {
                    "transcript_segments": original_transcript_segments
                }
            },
            "redacted_conversation": {
                "transcript": {
                    "transcript_segments": redacted_transcript_segments
                }
            }
        }
        
        logger.info(f"Retrieved {len(utterances_data)} utterances from Firestore for conversation {conversation_id}.", 
                   extra={"json_fields": {"event": "firestore_conversation_retrieved", "conversation_id": conversation_id, "utterance_count": len(utterances_data)}})
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error retrieving conversation {conversation_id} from Firestore: {e}", 
                    exc_info=True, 
                    extra={"json_fields": {"event": "firestore_conversation_error", "conversation_id": conversation_id, "error_details": str(e)}})
        return jsonify({'error': f'Failed to retrieve conversation: {e}'}), 500
