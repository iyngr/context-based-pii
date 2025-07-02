import json
import logging
import subprocess
import os
import time
from google.cloud import pubsub_v1

# Configure logging for the test script
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(module)s %(funcName)s %(lineno)d : %(message)s')
logger = logging.getLogger(__name__)

def get_gcp_project_id():
    """Gets the current GCP project ID from the gcloud configuration."""
    try:
        command = ['gcloud', 'config', 'get-value', 'project']
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            shell=True  # Use shell=True for consistency and Windows compatibility
        )
        project_id = result.stdout.strip()
        if not project_id:
            raise ValueError("gcloud config returned an empty project ID. Please run 'gcloud config set project YOUR_PROJECT_ID'.")
        logger.info(f"Successfully retrieved GCP Project ID via gcloud: {project_id}")
        return project_id
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error(
            "Failed to get GCP Project ID using 'gcloud config get-value project'. "
            "Please ensure the gcloud CLI is installed, you are authenticated ('gcloud auth login'), "
            "and a default project is set ('gcloud config set project YOUR_PROJECT_ID')."
        )
        if isinstance(e, subprocess.CalledProcessError):
            logger.error(f"gcloud stderr: {e.stderr}")
        raise SystemExit("Could not determine GCP Project ID. Aborting test.") from e

# GCP Project ID and Pub/Sub Topic for raw transcripts
GCP_PROJECT_ID = get_gcp_project_id()
RAW_TRANSCRIPTS_TOPIC = 'raw-transcripts'
AA_LIFECYCLE_TOPIC = 'aa-lifecycle-event-notification'

def run_e2e_test(conversation_filename):
    # Construct the absolute path to the conversation file
    # This assumes the script is run from the project root (context_manager_service)
    full_conversation_path = os.path.join(os.getcwd(), 'synthetic_conversations', conversation_filename)
    
    logger.info(f"--- Running E2E test for: {conversation_filename} ---")
    
    publisher = pubsub_v1.PublisherClient()
    raw_topic_path = publisher.topic_path(GCP_PROJECT_ID, RAW_TRANSCRIPTS_TOPIC)
    lifecycle_topic_path = publisher.topic_path(GCP_PROJECT_ID, AA_LIFECYCLE_TOPIC)

    try:
        logger.info(f"Attempting to open file: {full_conversation_path}")
        with open(full_conversation_path, 'r') as f:
            conversation_data = json.load(f)
        
        # Extract conversation_id from conversation_info or from entries
        conversation_id = None
        if 'conversation_info' in conversation_data and 'conversation_id' in conversation_data['conversation_info']:
            conversation_id = conversation_data['conversation_info']['conversation_id']
        elif 'entries' in conversation_data and len(conversation_data['entries']) > 0:
            # Try to infer conversation_id from the first entry if present
            first_entry = conversation_data['entries'][0]
            conversation_id = first_entry.get('conversation_id')
            if not conversation_id:
                # Fallback: use a default or raise error
                conversation_id = 'test_conversation_id'
                logger.warning(f"No conversation_id found in entries; using default: {conversation_id}")
        if not conversation_id:
            logger.error(f"Error: Missing conversation_id in both 'conversation_info' and 'entries' for {conversation_filename}")
            return

        # Get current time for start_time and end_time
        from datetime import datetime, timezone
        current_time = datetime.now(timezone.utc).isoformat(timespec='seconds') + 'Z'

        # 1. Send 'conversation_started' message
        start_message_payload = json.dumps({
            "conversation_id": conversation_id,
            "event_type": "conversation_started",
            "start_time": current_time
        })
        logger.info(f"Publishing 'conversation_started' message for '{conversation_id}' to Pub/Sub topic '{AA_LIFECYCLE_TOPIC}'...")
        future = publisher.publish(lifecycle_topic_path, start_message_payload.encode("utf-8"))
        future.result()
        logger.info(f"Published 'conversation_started' for {conversation_id}.")

        # 2. Publish individual raw transcript messages from 'entries'
        total_utterance_count = len(conversation_data.get('entries', []))
        logger.info(f"Publishing {total_utterance_count} individual utterances for '{conversation_id}' to Pub/Sub topic '{RAW_TRANSCRIPTS_TOPIC}'...")
        
        publish_futures = []
        for i, entry in enumerate(conversation_data.get('entries', [])):
            # Ensure each entry has conversation_id, original_entry_index, participant_role, text, start_timestamp_usec
            # The subscriber_service expects these fields.
            # For simplicity in test, we'll ensure they are present or add placeholders.
            entry_payload = {
                "conversation_id": conversation_id,
                "original_entry_index": entry.get('original_entry_index', i), # Use existing or generate
                "participant_role": entry.get('role', 'UNKNOWN'), # Use 'role' from synthetic data
                "text": entry.get('text', ''),
                "user_id": entry.get('user_id', 'test_user'),
                "start_timestamp_usec": entry.get('start_timestamp_usec', int(time.time() * 1_000_000)) # Use existing or generate
            }
            
            message_payload = json.dumps(entry_payload)
            future = publisher.publish(raw_topic_path, message_payload.encode("utf-8"))
            publish_futures.append(future)
        
        logger.info(f"Waiting for {len(publish_futures)} utterances to publish...")
        for i, future in enumerate(publish_futures):
            future.result()
            logger.info(f"Published utterance {i+1}/{total_utterance_count} for '{conversation_id}'.")


        logger.info(f"Finished publishing all individual utterances for {conversation_id}.")

        # 3. Send 'conversation_ended' message with total_utterance_count
        end_message_payload = json.dumps({
            "conversation_id": conversation_id,
            "event_type": "conversation_ended",
            "end_time": current_time, # Using current_time as end_time for simplicity
            "total_utterance_count": total_utterance_count # Pass the total count for aggregator to wait for
        })
        logger.info(f"Publishing 'conversation_ended' message for '{conversation_id}' to Pub/Sub topic '{AA_LIFECYCLE_TOPIC}'...")
        future = publisher.publish(lifecycle_topic_path, end_message_payload.encode("utf-8"))
        future.result()
        logger.info(f"Published 'conversation_ended' for {conversation_id}.")
            
        logger.info(f"--- E2E test completed for: {conversation_filename} ---")

    except FileNotFoundError:
        logger.error(f"Error: Conversation file not found at {conversation_filename}")
    except json.JSONDecodeError:
        logger.error(f"Error: Invalid JSON in {conversation_filename}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during E2E test for {conversation_filename}: {str(e)}", exc_info=True)

if __name__ == "__main__":
    # List of synthetic conversation files to test
    conversation_files = [
        'refund_inquiry_v1_extended.json'
    ]

    for file_path in conversation_files:
        run_e2e_test(file_path)