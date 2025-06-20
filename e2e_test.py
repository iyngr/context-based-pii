import json
import logging
import subprocess
import os

# Configure logging for the test script
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(module)s %(funcName)s %(lineno)d : %(message)s')
logger = logging.getLogger(__name__)

# GCP Project ID and Pub/Sub Topic for raw transcripts
GCP_PROJECT_ID = os.environ.get("PROJECT_ID")
if not GCP_PROJECT_ID:
    raise ValueError("PROJECT_ID environment variable not set. Please set it before running the tests.")
RAW_TRANSCRIPTS_TOPIC = 'raw-transcripts'
AA_LIFECYCLE_TOPIC = 'aa-lifecycle-event-notification'

def run_e2e_test(conversation_filename):
    # Construct the absolute path to the conversation file
    # This assumes the script is run from the project root (context_manager_service)
    full_conversation_path = os.path.join(os.getcwd(), 'synthetic_conversations', conversation_filename)
    
    logger.info(f"--- Running E2E test for: {conversation_filename} ---")
    
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
        start_command = [
            'gcloud', 'pubsub', 'topics', 'publish', AA_LIFECYCLE_TOPIC,
            '--project', GCP_PROJECT_ID,
            '--message', start_message_payload
        ]
        logger.info(f"Publishing 'conversation_started' message for '{conversation_id}' to Pub/Sub topic '{AA_LIFECYCLE_TOPIC}'...")
        subprocess.run(start_command, capture_output=True, text=True, check=True, shell=True)
        logger.info(f"Published 'conversation_started' for {conversation_id}.")

        # 2. Publish raw transcript messages from 'entries'
        # No longer add or require 'conversation_info'
        message_payload = json.dumps(conversation_data)
        publish_raw_command = [
            'gcloud', 'pubsub', 'topics', 'publish', RAW_TRANSCRIPTS_TOPIC,
            '--project', GCP_PROJECT_ID,
            '--message', message_payload
        ]
        logger.info(f"Publishing entire conversation data for '{conversation_id}' to Pub/Sub topic '{RAW_TRANSCRIPTS_TOPIC}'...")
        subprocess.run(publish_raw_command, capture_output=True, text=True, check=True, shell=True)
        logger.info(f"Published entire conversation data for {conversation_id}.")

        # 3. Send 'conversation_ended' message
        end_message_payload = json.dumps({
            "conversation_id": conversation_id,
            "event_type": "conversation_ended",
            "end_time": current_time # Using current_time as end_time for simplicity
        })
        end_command = [
            'gcloud', 'pubsub', 'topics', 'publish', AA_LIFECYCLE_TOPIC,
            '--project', GCP_PROJECT_ID,
            '--message', end_message_payload
        ]
        logger.info(f"Publishing 'conversation_ended' message for '{conversation_id}' to Pub/Sub topic '{AA_LIFECYCLE_TOPIC}'...")
        subprocess.run(end_command, capture_output=True, text=True, check=True, shell=True)
        logger.info(f"Published 'conversation_ended' for {conversation_id}.")
            
        logger.info(f"--- E2E test completed for: {conversation_filename} ---")

    except FileNotFoundError:
        logger.error(f"Error: Conversation file not found at {conversation_filename}")
    except json.JSONDecodeError:
        logger.error(f"Error: Invalid JSON in {conversation_filename}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error executing gcloud command for {conversation_filename}: {e}")
        logger.error(f"Command stdout: {e.stdout}")
        logger.error(f"Command stderr: {e.stderr}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during E2E test for {conversation_filename}: {str(e)}", exc_info=True)

if __name__ == "__main__":
    # List of synthetic conversation files to test
    conversation_files = [
        'refund_inquiry_v1_extended.json'
    ]

    for file_path in conversation_files:
        run_e2e_test(file_path)