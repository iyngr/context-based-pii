import base64
import json
import logging
import time
from flask import Flask, request, jsonify
import os
from datetime import datetime, timedelta, timezone
from google.cloud import firestore, storage # Firestore is imported here
from google.cloud import contact_center_insights_v1
from google.protobuf.timestamp_pb2 import Timestamp as ProtoTimestamp # Alias the protobuf Timestamp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core.exceptions import InternalServerError, ServiceUnavailable, DeadlineExceeded, AlreadyExists, GoogleAPICallError

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
CONTEXT_TTL_SECONDS = int(os.getenv('CONTEXT_TTL_SECONDS', 3600))

# Polling configuration for conversation completion
POLLING_INTERVAL_SECONDS = int(os.getenv('POLLING_INTERVAL_SECONDS', 5))
MAX_POLLING_ATTEMPTS = int(os.getenv('MAX_POLLING_ATTEMPTS', 12)) # 12 attempts * 5 seconds = 60 seconds max wait

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

    # The participant_role is now guaranteed to be provided by the subscriber_service.
    # The fallback logic is no longer needed and has been removed to prevent incorrect role assignment.
    determined_role = participant_role



    # Check for missing or empty required fields
    required_fields = {
        'conversation_id': conversation_id,
        'text': redacted_transcript,
        'original_entry_index': original_entry_index,
        'participant_role': participant_role,
        'start_timestamp_usec': start_timestamp_usec # NEW: Add start_timestamp_usec to required fields check
    }

    missing_fields = []
    for field, value in required_fields.items():
        if value is None:
            missing_fields.append(field)
        elif isinstance(value, str) and not value.strip():
            missing_fields.append(field)

    if missing_fields:
        logger.error(f"Missing required fields: {', '.join(missing_fields)}", extra={"json_fields": {"event": "missing_fields_error", "missing_fields": missing_fields}})
        return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400

    # Calculate expiration timestamp
    expire_at = datetime.utcnow() + timedelta(seconds=CONTEXT_TTL_SECONDS)

    # Reference to the conversation document
    conversation_ref = db.collection('conversations_in_progress').document(conversation_id)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10),
           retry=retry_if_exception_type((InternalServerError, ServiceUnavailable, DeadlineExceeded)))
    def _firestore_set_with_retry(doc_ref, data):
        doc_ref.set(data)

    @firestore.transactional
    def update_conversation_document_in_transaction(transaction, conversation_ref, expire_at, current_utterance_timestamp_usec): # NEW PARAM
        snapshot = conversation_ref.get(transaction=transaction)
        
        current_utterance_count = 0
        current_last_utterance_timestamp = 0 # This should be in microseconds

        if snapshot.exists:
            data = snapshot.to_dict()
            current_utterance_count = data.get('utterance_count', 0)
            current_last_utterance_timestamp = data.get('last_utterance_timestamp', 0)

        new_utterance_count = current_utterance_count + 1
        # Update last_utterance_timestamp only if the current utterance's timestamp is newer
        new_last_utterance_timestamp = max(current_last_utterance_timestamp, current_utterance_timestamp_usec) # NEW LOGIC

        transaction.set(conversation_ref, {
            'expireAt': expire_at,
            'utterance_count': new_utterance_count,
            'last_utterance_timestamp': new_last_utterance_timestamp
        }, merge=True)
        
        return new_utterance_count, new_last_utterance_timestamp

    try:
        # Execute the transaction to update conversation document atomically
        new_count, new_timestamp = update_conversation_document_in_transaction(db.transaction(), conversation_ref, expire_at, start_timestamp_usec) # NEW PARAM
        logger.info(f"Firestore: Conversation document updated/created for ID: {conversation_id} with utterance_count={new_count}, last_utterance_timestamp={new_timestamp}", extra={"json_fields": {"event": "firestore_write", "conversation_id": conversation_id, "action": "update_create_atomic", "utterance_count": new_count, "last_utterance_timestamp": new_timestamp}})

        # Add the utterance to a sub-collection
        utterance_data = {
            'text': redacted_transcript,
            'original_entry_index': original_entry_index,
            'participant_role': determined_role, # Use the determined role here
            'user_id': user_id,
            'start_timestamp_usec': start_timestamp_usec
        }
        # Add the utterance to a sub-collection, using original_entry_index as document ID
        utterance_doc_ref = conversation_ref.collection('utterances').document(str(original_entry_index))
        _firestore_set_with_retry(utterance_doc_ref, utterance_data)
        logger.info(f"Firestore: Utterance stored for Conversation ID: {conversation_id}, Index: {original_entry_index}", extra={"json_fields": {"event": "firestore_write", "conversation_id": conversation_id, "original_entry_index": original_entry_index, "action": "add_utterance"}})

    except Exception as e:
        logger.error(f"Firestore operation failed: {e}", exc_info=True, extra={"json_fields": {"event": "firestore_error", "conversation_id": conversation_id, "error_details": str(e)}})
        return jsonify({'error': f'Firestore operation failed: {e}'}), 500

    return jsonify({'status': 'success', 'message': 'Transcript processed and stored in Firestore'}), 200

@app.route('/conversation-ended', methods=['POST'])
def receive_conversation_ended_event():
    """
    Receives and processes Pub/Sub messages for conversation ended events.
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

        # Pub/Sub message data is base64 encoded
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

        logger.info(f"Received conversation ended event for Conversation ID: {conversation_id}", extra={"json_fields": {"event": "conversation_ended_event", "conversation_id": conversation_id}})

        conversation_doc_ref = db.collection('conversations_in_progress').document(conversation_id)
        utterances_ref = conversation_doc_ref.collection('utterances')

        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10),
               retry=retry_if_exception_type((InternalServerError, ServiceUnavailable, DeadlineExceeded)))
        def _firestore_get_doc_with_retry(doc_ref):
            return doc_ref.get()

        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10),
               retry=retry_if_exception_type((InternalServerError, ServiceUnavailable, DeadlineExceeded)))
        def _firestore_get_collection_with_retry(query_ref):
            return query_ref.get()

        # Polling mechanism to wait for utterances to be stored
        transcript_ready = False
        for attempt in range(MAX_POLLING_ATTEMPTS):
            try:
                conversation_doc = _firestore_get_doc_with_retry(conversation_doc_ref)
                if conversation_doc.exists:
                    doc_data = conversation_doc.to_dict()
                    utterance_count = doc_data.get('utterance_count', 0)
                    last_utterance_timestamp = doc_data.get('last_utterance_timestamp', 0)

                    # Consider transcript ready if at least one utterance is present
                    # and the last utterance was received recently enough (e.g., within the polling interval)
                    # or if we've reached the max attempts and still have some utterances.
                    if utterance_count > 0:
                        # Simple heuristic: if we have utterances, assume they will eventually all arrive
                        # or that the last one has arrived.
                        transcript_ready = True
                        logger.info(f"Polling: Utterances found for {conversation_id}. Count: {utterance_count}, Last Timestamp: {last_utterance_timestamp}", extra={"json_fields": {"event": "polling_success", "conversation_id": conversation_id, "attempt": attempt + 1, "utterance_count": utterance_count}})
                        break
                
                logger.info(f"Polling: No utterances found for {conversation_id} yet. Attempt {attempt + 1}/{MAX_POLLING_ATTEMPTS}. Retrying in {POLLING_INTERVAL_SECONDS} seconds.", extra={"json_fields": {"event": "polling_wait", "conversation_id": conversation_id, "attempt": attempt + 1}})
                time.sleep(POLLING_INTERVAL_SECONDS)

            except Exception as e:
                logger.error(f"Polling Firestore for conversation {conversation_id} failed: {e}", exc_info=True, extra={"json_fields": {"event": "polling_error", "conversation_id": conversation_id, "error_details": str(e)}})
                # Continue polling even if there's a temporary Firestore error
                time.sleep(POLLING_INTERVAL_SECONDS)

        if not transcript_ready:
            logger.warning(f"Polling failed: No utterances found for conversation ID: {conversation_id} after {MAX_POLLING_ATTEMPTS} attempts. Skipping CCAI upload.", extra={"json_fields": {"event": "ccai_upload_skipped", "conversation_id": conversation_id, "reason": "polling_failed_no_utterances"}})
            return jsonify({'status': 'skipped', 'message': 'No transcript found after polling, skipping CCAI upload'}), 200

        # 1. Aggregate Full Transcript from Firestore
        try:
            utterances = _firestore_get_collection_with_retry(utterances_ref.order_by('original_entry_index'))
            logger.info(f"Firestore: Fetched {len(utterances)} utterances for conversation ID: {conversation_id}", extra={"json_fields": {"event": "firestore_read", "conversation_id": conversation_id, "utterance_count_fetched": len(utterances)}})
        except Exception as e:
            logger.error(f"Firestore read operation failed for utterances: {e}", exc_info=True, extra={"json_fields": {"event": "firestore_error", "conversation_id": conversation_id, "error_details": str(e)}})
            return jsonify({'error': f'Firestore read operation failed: {e}'}), 500

        full_transcript_parts = []
        entries_for_gcs = [] # This will hold the dictionaries for the "entries" list

        for i, utterance in enumerate(utterances):
            utterance_data = utterance.to_dict()
            full_transcript_parts.append(utterance_data.get('text', ''))

            logger.info(f"Processing utterance {i}: original_entry_index={utterance_data.get('original_entry_index')}, role={utterance_data.get('participant_role')}, user_id={utterance_data.get('user_id')}", extra={"json_fields": {"event": "processing_utterance", "conversation_id": conversation_id, "utterance_index": i, "original_entry_index": utterance_data.get('original_entry_index'), "participant_role": utterance_data.get('participant_role'), "user_id": utterance_data.get('user_id')}})

            entry_dict = {
                "text": utterance_data.get('text', ''),
                "role": utterance_data.get('participant_role'), # Use the role already determined and stored in Firestore
                "user_id": utterance_data.get('user_id') if utterance_data.get('user_id') is not None else 'default_user'
            }
            entries_for_gcs.append(entry_dict)

        full_transcript = " ".join(full_transcript_parts).strip()
        logger.info(f"Conversation aggregation: Aggregated transcript for {conversation_id}", extra={"json_fields": {"event": "conversation_aggregation", "conversation_id": conversation_id, "transcript_length": len(full_transcript)}})

        # 2. Integrate with Google CCAI Conversation Insights (UploadConversation API)
        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10),
               retry=retry_if_exception_type((InternalServerError, ServiceUnavailable, DeadlineExceeded)))
        def _upload_conversation_with_retry(client, request_obj):
            return client.upload_conversation(request=request_obj)

        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10),
               retry=retry_if_exception_type((InternalServerError, ServiceUnavailable, DeadlineExceeded)))
        def _firestore_delete_collection_docs_with_retry(collection_ref):
            for doc in collection_ref.stream():
                doc.reference.delete()

        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10),
               retry=retry_if_exception_type((InternalServerError, ServiceUnavailable, DeadlineExceeded)))
        def _firestore_delete_document_with_retry(doc_ref):
            doc_ref.delete()

        if full_transcript:
            project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
            if not project_id:
                logger.error("GOOGLE_CLOUD_PROJECT environment variable not set.", extra={"json_fields": {"event": "configuration_error", "variable": "GOOGLE_CLOUD_PROJECT"}})
                return jsonify({'error': 'GOOGLE_CLOUD_PROJECT environment variable not set'}), 500
            
            if not AGGREGATED_TRANSCRIPTS_BUCKET:
                logger.error("AGGREGATED_TRANSCRIPTS_BUCKET environment variable not set.", extra={"json_fields": {"event": "configuration_error", "variable": "AGGREGATED_TRANSCRIPTS_BUCKET"}})
                return jsonify({'error': 'AGGREGATED_TRANSCRIPTS_BUCKET environment variable not set'}), 500


            try:
                # Use the regional endpoint that matches your DLP location
                client_options = {"api_endpoint": "us-central1-contactcenterinsights.googleapis.com"}
                conversations_client = contact_center_insights_v1.ContactCenterInsightsClient(client_options=client_options)
                logger.info("CCAI Client initialized with regional endpoint us-central1")
            except Exception as e:
                logger.error(f"Failed to initialize CCAI Client: {e}")
                return jsonify({'error': f'Failed to initialize CCAI Client: {e}'}), 500

            # Use us-central1 for the parent (not global)
            parent = f"projects/{project_id}/locations/us-central1"

            try:
                logger.info("Starting GCS JSON preparation.", extra={"json_fields": {"event": "gcs_prep_start", "conversation_id": conversation_id}})


                # Construct the final JSON payload with the correct structure.
                # Construct the final JSON payload with the correct structure for the Conversation resource.
                logger.info(f"Preparing GCS payload with {len(entries_for_gcs)} entries.", extra={"json_fields": {"event": "gcs_payload_prep", "conversation_id": conversation_id, "entries_count": len(entries_for_gcs)}})
                json_payload_for_gcs_dict = {
                    "entries": entries_for_gcs  # Your list of conversation entry dictionaries
                }

                # Remove conversation_info and conversation_id from entries if present
                cleaned_entries = []
                for entry in entries_for_gcs:
                    entry_copy = dict(entry)
                    entry_copy.pop('conversation_id', None)
                    cleaned_entries.append(entry_copy)
                json_payload_for_gcs_dict = {
                    "entries": cleaned_entries
                }
                json_payload_for_gcs = json.dumps(json_payload_for_gcs_dict, indent=2)
                
                logger.info(f"Finished GCS JSON payload preparation for JsonConversationInput. Length: {len(json_payload_for_gcs)} bytes.", extra={"json_fields": {"event": "gcs_prep_json_payload_done", "conversation_id": conversation_id, "payload_length": len(json_payload_for_gcs)}})

                gcs_transcript_filename = f"{conversation_id}_transcript.json"
                logger.info(f"GCS transcript filename set to: {gcs_transcript_filename}", extra={"json_fields": {"event": "gcs_prep_filename", "conversation_id": conversation_id, "gcs_filename": gcs_transcript_filename}})

                bucket = storage_client.bucket(AGGREGATED_TRANSCRIPTS_BUCKET)
                logger.info(f"GCS bucket object obtained for bucket: {AGGREGATED_TRANSCRIPTS_BUCKET}", extra={"json_fields": {"event": "gcs_prep_bucket_obj", "conversation_id": conversation_id, "bucket_name": AGGREGATED_TRANSCRIPTS_BUCKET}})

                blob = bucket.blob(gcs_transcript_filename)
                logger.info(f"GCS blob object obtained for blob: {gcs_transcript_filename}", extra={"json_fields": {"event": "gcs_prep_blob_obj", "conversation_id": conversation_id, "blob_name": gcs_transcript_filename}})

                blob.upload_from_string(json_payload_for_gcs, content_type='application/json')
                gcs_transcript_uri = f"gs://{AGGREGATED_TRANSCRIPTS_BUCKET}/{gcs_transcript_filename}"
                logger.info(f"Uploaded aggregated transcript to GCS: {gcs_transcript_uri}", extra={"json_fields": {"event": "gcs_upload_success", "conversation_id": conversation_id, "gcs_uri": gcs_transcript_uri}})

                # Construct the Conversation object for the API call.
                # This object references the transcript in GCS via the data_source field.
                conversation_for_api_call = contact_center_insights_v1.types.Conversation(
                    data_source=contact_center_insights_v1.types.ConversationDataSource(
                        gcs_source=contact_center_insights_v1.types.GcsSource(transcript_uri=gcs_transcript_uri)
                    ),
                    # language_code is expected to be part of the GCS JSON for JsonConversationInput
                )

                # Construct the request object for upload_conversation
                # SpeechConfig is not needed when providing a transcript via GCS.
                # By providing an empty RedactionConfig, we disable the default redaction
                # that is implicitly and incorrectly triggered by the service.

                # Configure DLP-compatible redaction config with the correct location
                redaction_config = contact_center_insights_v1.types.RedactionConfig(
                    # Set the DLP configuration to use the same region as your resources
                    deidentify_template=f"projects/{project_id}/locations/us-central1/deidentifyTemplates/deidentify",
                    inspect_template=f"projects/{project_id}/locations/us-central1/inspectTemplates/identify"
                )

                upload_request = contact_center_insights_v1.types.UploadConversationRequest(
                    parent=parent,
                    conversation=conversation_for_api_call,
                    conversation_id=conversation_id,
                    redaction_config=redaction_config
                )

                try:
                    # Upload the conversation
                    response = _upload_conversation_with_retry(conversations_client, upload_request)
                    # Get the actual Conversation object from the operation result, with a 180-second timeout.
                    ccai_conversation = response.result(timeout=180)
                    logger.info(f"CCAI API: Conversation uploaded to CCAI: {ccai_conversation.name}", extra={"json_fields": {"event": "ccai_api_call", "conversation_id": conversation_id, "ccai_conversation_name": ccai_conversation.name}})
                except AlreadyExists:
                    logger.warning(f"CCAI API: Conversation with ID '{conversation_id}' already exists. Skipping upload.", extra={"json_fields": {"event": "ccai_upload_skipped_already_exists", "conversation_id": conversation_id}})
                except GoogleAPICallError as e:
                    # Handle the specific LRO state error to provide better logging, then re-raise
                    logger.error(f"GoogleAPICallError waiting for conversation upload LRO for conversation ID: {conversation_id}. Error: {e}", exc_info=True, extra={"json_fields": {"event": "ccai_upload_lro_error", "conversation_id": conversation_id, "error_details": str(e)}})
                    raise e

                # After successful upload, delete from Firestore
                # Delete utterances sub-collection
                _firestore_delete_collection_docs_with_retry(utterances_ref)
                # Delete conversation document
                _firestore_delete_document_with_retry(db.collection('conversations_in_progress').document(conversation_id))
                logger.info(f"Firestore: Deleted conversation {conversation_id} and its utterances from Firestore.", extra={"json_fields": {"event": "firestore_delete", "conversation_id": conversation_id}})

            except Exception as e:
                logger.error(f"Error during CCAI upload or Firestore deletion. Exception: {e}, Type: {type(e)}, Repr: {repr(e)}", exc_info=True, extra={"json_fields": {"event": "ccai_upload_or_firestore_delete_error", "conversation_id": conversation_id, "error_message": str(e), "error_type": str(type(e)), "error_repr": repr(e)}})
                return jsonify({'error': f'Failed to process conversation for insights: {e}'}), 500
        else:
            logger.warning(f"No transcript found for conversation ID: {conversation_id}. Skipping CCAI upload.", extra={"json_fields": {"event": "ccai_upload_skipped", "conversation_id": conversation_id, "reason": "no_transcript"}})

        return jsonify({'status': 'success', 'message': 'Conversation ended event processed and transcript uploaded to CCAI'}), 200
    except Exception as e:
        logger.error(f"Unhandled exception in /conversation-ended. Exception: {e}, Type: {type(e)}, Repr: {repr(e)}", exc_info=True, extra={"json_fields": {"event": "unhandled_exception", "error_message": str(e), "error_type": str(type(e)), "error_repr": repr(e)}})
        return jsonify({'error': f'An unexpected error occurred: {e}'}), 500
