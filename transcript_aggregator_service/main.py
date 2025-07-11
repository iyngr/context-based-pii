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
import redis # New import

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

# Configure TTL for conversation context
CONTEXT_TTL_SECONDS = int(os.getenv('CONTEXT_TTL_SECONDS', 3600)) # Default to 1 hour

# Multi-turn aggregation window size
UTTERANCE_WINDOW_SIZE = int(os.getenv('UTTERANCE_WINDOW_SIZE', 5)) # Keep last 5 utterances

# Main Service URL for sending aggregated transcripts
MAIN_SERVICE_URL = os.getenv('MAIN_SERVICE_URL')
if not MAIN_SERVICE_URL:
    logger.critical("MAIN_SERVICE_URL environment variable not set. Cannot forward aggregated transcripts.")
    # Depending on deployment strategy, you might want to exit here.
    # For now, we'll just log a critical error.

# Polling configuration for conversation completion
POLLING_INTERVAL_SECONDS = int(os.getenv('POLLING_INTERVAL_SECONDS', 5))
MAX_POLLING_ATTEMPTS = int(os.getenv('MAX_POLLING_ATTEMPTS', 12)) # 12 attempts * 5 seconds = 60 seconds max wait

app = Flask(__name__)

# Redis Configuration
REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379)) # Default to 6379

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

    # The participant_role is now guaranteed to be provided by the subscriber_service.
    # The fallback logic is no longer needed and has been removed to prevent incorrect role assignment.
    # Check for missing or empty required fields
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

    if not redis_client:
        logger.error("Redis client not initialized. Cannot buffer utterances for multi-turn context.", extra={"json_fields": {"event": "redis_not_initialized"}})
        return jsonify({'error': 'Redis client not available for buffering'}), 500

    if not MAIN_SERVICE_URL:
        logger.critical("MAIN_SERVICE_URL environment variable not set. Cannot forward aggregated transcripts.", extra={"json_fields": {"event": "configuration_error", "variable": "MAIN_SERVICE_URL"}})
        return jsonify({'error': 'Main service URL not configured'}), 500

    try:
        # Store the current utterance in Redis List
        # Use RPUSH to add to the right (end) of the list
        # Use LTRIM to keep only the last N elements (our window size)
        utterance_key = f"utterances:{conversation_id}"
        utterance_data_to_store = json.dumps({
            'text': redacted_transcript,
            'original_entry_index': original_entry_index,
            'participant_role': participant_role,
            'user_id': user_id,
            'start_timestamp_usec': start_timestamp_usec
        })
        
        # Add to list and trim to maintain window size
        redis_client.rpush(utterance_key, utterance_data_to_store)
        redis_client.ltrim(utterance_key, -UTTERANCE_WINDOW_SIZE, -1) # Keep only the last N elements
        redis_client.expire(utterance_key, CONTEXT_TTL_SECONDS) # Set TTL for the list

        logger.info(f"Redis: Stored utterance {original_entry_index} for conversation {conversation_id}. List size trimmed to {UTTERANCE_WINDOW_SIZE}.", extra={"json_fields": {"event": "redis_utterance_store", "conversation_id": conversation_id, "original_entry_index": original_entry_index}})

        # Retrieve the last N utterances
        raw_utterances_from_redis = redis_client.lrange(utterance_key, 0, -1)
        combined_transcript_parts = []
        
        for raw_utterance in raw_utterances_from_redis:
            try:
                utterance_dict = json.loads(raw_utterance)
                combined_transcript_parts.append(utterance_dict.get('text', ''))
            except json.JSONDecodeError as e:
                logger.error(f"Redis: Error decoding stored utterance for conversation {conversation_id}: {e}", extra={"json_fields": {"event": "redis_decode_error", "conversation_id": conversation_id, "error_details": str(e)}})
                continue # Skip malformed utterance

        combined_transcript = " ".join(combined_transcript_parts).strip()
        logger.info(f"Redis: Aggregated multi-turn transcript for {conversation_id}. Length: {len(combined_transcript)}", extra={"json_fields": {"event": "multi_turn_aggregation", "conversation_id": conversation_id, "combined_length": len(combined_transcript)}})

        # Forward the combined transcript to main_service for DLP processing
        main_service_payload = {
            "conversation_id": conversation_id,
            "transcript": combined_transcript,
            "context": { # Pass the context from the original message if available, or an empty dict
                "expected_pii_type": message_data.get('expected_pii_type') # Assuming subscriber might pass this
            }
        }
        
        # Make the HTTP POST request to main_service
        response = requests.post(f"{MAIN_SERVICE_URL}/handle-customer-utterance", json=main_service_payload)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        logger.info(f"Forwarded combined transcript to main_service for conversation {conversation_id}. Status: {response.status_code}", extra={"json_fields": {"event": "forward_to_main_service", "conversation_id": conversation_id, "status_code": response.status_code}})
        
        # The Firestore logic for storing individual utterances and then aggregating on conversation_ended
        # is no longer needed here, as main_service will handle the final DLP and storage.
        # We only use Firestore for conversation_ended event to trigger final GCS upload.
        # The existing Firestore logic in /conversation-ended will need to be updated to fetch from Redis.

        return jsonify({'status': 'success', 'message': 'Utterance buffered and combined transcript forwarded to main_service'}), 200

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to forward combined transcript to main_service for conversation {conversation_id}: {e}", exc_info=True, extra={"json_fields": {"event": "forward_to_main_service_error", "conversation_id": conversation_id, "error_details": str(e)}})
        return jsonify({'error': f'Failed to forward transcript to main service: {e}'}), 500
    except Exception as e:
        logger.error(f"An unexpected error occurred in /redacted-transcripts for conversation {conversation_id}: {e}", exc_info=True, extra={"json_fields": {"event": "unhandled_exception", "conversation_id": conversation_id, "error_details": str(e)}})
        return jsonify({'error': f'An unexpected error occurred: {e}'}), 500

@app.route('/conversation-ended', methods=['POST'])
def receive_conversation_ended_event():
    """
    Receives and processes Pub/Sub messages for conversation ended events.
    This function will now trigger the final aggregation and upload to GCS from Redis.
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
        total_utterance_count = message_data.get('total_utterance_count') # Get total count from conversation_ended event

        if not conversation_id:
            logger.error("Missing conversation_id in message data for conversation ended event.", extra={"json_fields": {"event": "missing_fields_error", "missing_fields": ["conversation_id"]}})
            return jsonify({'error': 'Missing conversation_id in message data'}), 400

        if event_type != 'conversation_ended':
            logger.info(f"Received lifecycle event with type: {event_type}. This handler only processes 'conversation_ended' events, skipping.", extra={"json_fields": {"event": "lifecycle_event_skipped", "conversation_id": conversation_id, "received_event_type": event_type}})
            return jsonify({'status': 'ignored', 'message': f'Event type {event_type} not processed by this handler.'}), 200

        logger.info(f"Received conversation ended event for Conversation ID: {conversation_id}. Total utterances expected: {total_utterance_count}", extra={"json_fields": {"event": "conversation_ended_event", "conversation_id": conversation_id, "expected_utterance_count": total_utterance_count}})

        if not redis_client:
            logger.error("Redis client not initialized. Cannot retrieve utterances for final aggregation.", extra={"json_fields": {"event": "redis_not_initialized"}})
            return jsonify({'error': 'Redis client not available for final aggregation'}), 500

        utterance_key = f"utterances:{conversation_id}"
        
        # Polling mechanism to wait for all utterances to be stored in Redis
        # We will poll until the number of utterances in Redis matches total_utterance_count
        # or until MAX_POLLING_ATTEMPTS is reached.
        polling_interval_seconds = int(os.getenv('POLLING_INTERVAL_SECONDS', 5))
        max_polling_attempts = int(os.getenv('MAX_POLLING_ATTEMPTS', 12)) # 12 attempts * 5 seconds = 60 seconds max wait

        all_utterances_received = False
        for attempt in range(max_polling_attempts):
            current_redis_utterance_count = redis_client.llen(utterance_key)
            logger.info(f"Polling Redis for conversation {conversation_id}. Attempt {attempt + 1}/{max_polling_attempts}. Current Redis count: {current_redis_utterance_count}, Expected: {total_utterance_count}", extra={"json_fields": {"event": "polling_redis", "conversation_id": conversation_id, "attempt": attempt + 1, "current_redis_count": current_redis_utterance_count, "expected_count": total_utterance_count}})

            if current_redis_utterance_count >= total_utterance_count:
                all_utterances_received = True
                logger.info(f"All expected utterances received for conversation {conversation_id}.", extra={"json_fields": {"event": "all_utterances_received", "conversation_id": conversation_id}})
                break
            
            time.sleep(polling_interval_seconds)
        
        if not all_utterances_received:
            logger.warning(f"Did not receive all expected utterances for conversation {conversation_id} after {max_polling_attempts} attempts. Proceeding with available utterances.", extra={"json_fields": {"event": "partial_utterances", "conversation_id": conversation_id, "final_redis_count": redis_client.llen(utterance_key), "expected_count": total_utterance_count}})

        # Retrieve all utterances from Redis for final aggregation
        raw_utterances_from_redis = redis_client.lrange(utterance_key, 0, -1)
        
        entries_for_gcs = []
        for raw_utterance in raw_utterances_from_redis:
            try:
                utterance_dict = json.loads(raw_utterance)
                entries_for_gcs.append(utterance_dict)
            except json.JSONDecodeError as e:
                logger.error(f"Redis: Error decoding stored utterance for conversation {conversation_id} during final aggregation: {e}", exc_info=True, extra={"json_fields": {"event": "redis_decode_error_final", "conversation_id": conversation_id, "error_details": str(e)}})
                continue # Skip malformed utterance

        if not entries_for_gcs:
            logger.warning(f"No utterances found in Redis for conversation ID: {conversation_id} during final aggregation. Skipping processing.", extra={"json_fields": {"event": "processing_skipped", "conversation_id": conversation_id, "reason": "no_utterances_in_redis"}})
            return jsonify({'status': 'skipped', 'message': 'No utterances found in Redis, skipping processing'}), 200

        # Sort entries by original_entry_index to ensure correct order
        entries_for_gcs.sort(key=lambda x: x.get('original_entry_index', 0))

        # 1. Store the final aggregated transcript in Redis for fast UI retrieval
        final_transcript_payload = {"transcript_segments": entries_for_gcs}
        final_transcript_key = f"final_transcript:{conversation_id}"
        try:
            redis_client.set(final_transcript_key, json.dumps(final_transcript_payload), ex=CONTEXT_TTL_SECONDS)
            logger.info(f"Stored final aggregated transcript in Redis for conversation {conversation_id}.", extra={"json_fields": {"event": "redis_store_final_transcript", "conversation_id": conversation_id}})
        except Exception as e:
            logger.error(f"Error storing final transcript in Redis for conversation {conversation_id}: {e}", exc_info=True)
            # Do not fail the whole process, GCS upload is still the primary goal.

        # 2. Upload Aggregated Transcript to GCS (background task)
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
            json_payload_for_gcs = json.dumps(gcs_payload_dict, indent=2)
            
            gcs_transcript_filename = f"{conversation_id}_transcript.json"
            
            _gcs_upload_with_retry(AGGREGATED_TRANSCRIPTS_BUCKET, gcs_transcript_filename, json_payload_for_gcs)
            gcs_transcript_uri = f"gs://{AGGREGATED_TRANSCRIPTS_BUCKET}/{gcs_transcript_filename}"
            logger.info(f"Uploaded final aggregated transcript to GCS: {gcs_transcript_uri}", extra={"json_fields": {"event": "gcs_upload_success_final", "conversation_id": conversation_id, "gcs_uri": gcs_transcript_uri}})

            # After successful upload, delete the temporary utterance list from Redis
            redis_client.delete(utterance_key)
            logger.info(f"Redis: Deleted temporary utterance list for conversation {conversation_id}.", extra={"json_fields": {"event": "redis_delete_utterance_list", "conversation_id": conversation_id}})

        except Exception as e:
            logger.error(f"Error during final GCS upload or Redis deletion. Exception: {e}", exc_info=True, extra={"json_fields": {"event": "gcs_upload_or_redis_delete_error_final", "conversation_id": conversation_id, "error_message": str(e)}})
            return jsonify({'error': f'Failed to process and upload final transcript: {e}'}), 500

        return jsonify({'status': 'success', 'message': 'Conversation ended event processed, final transcript stored in Redis and uploaded to GCS'}), 200
    except Exception as e:
        logger.error(f"Unhandled exception in /conversation-ended. Exception: {e}, Type: {type(e)}, Repr: {repr(e)}", exc_info=True, extra={"json_fields": {"event": "unhandled_exception", "error_message": str(e), "error_type": str(type(e)), "error_repr": repr(e)}})
        return jsonify({'error': f'An unexpected error occurred: {e}'}), 500
