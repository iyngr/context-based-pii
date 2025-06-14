import json
import logging
import subprocess
import os

# Configure logging for the test script
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(module)s %(funcName)s %(lineno)d : %(message)s')
logger = logging.getLogger(__name__)

# GCP Project ID and Pub/Sub Topic for raw transcripts
GCP_PROJECT_ID = 'trans-market-458313-u3'
RAW_TRANSCRIPTS_TOPIC = 'raw-transcripts'

def run_e2e_test(conversation_filename):
    # Construct the absolute path to the conversation file
    # This assumes the script is run from the project root (context_manager_service)
    full_conversation_path = os.path.join(os.getcwd(), 'synthetic_conversations', conversation_filename)
    
    logger.info(f"--- Running E2E test for: {conversation_filename} ---")
    
    try:
        logger.info(f"Attempting to open file: {full_conversation_path}")
        with open(full_conversation_path, 'r') as f:
            conversation_data = json.load(f)
        
        # Convert conversation data to a JSON string for the gcloud command
        message_payload = json.dumps(conversation_data)
        
        # Construct the gcloud pubsub publish command
        command = [
            'gcloud', 'pubsub', 'topics', 'publish', RAW_TRANSCRIPTS_TOPIC,
            '--project', GCP_PROJECT_ID,
            '--message', message_payload
        ]
        
        logger.info(f"Publishing message from '{conversation_filename}' to Pub/Sub topic '{RAW_TRANSCRIPTS_TOPIC}' in project '{GCP_PROJECT_ID}'...")
        
        # Execute the gcloud command
        result = subprocess.run(command, capture_output=True, text=True, check=True, shell=True)
        
        logger.info(f"Pub/Sub publish command output for {conversation_filename}:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"Pub/Sub publish command stderr for {conversation_filename}:\n{result.stderr}")
            
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
        'account_access_issue.json',
        'international_order_support.json',
        'order_cancellation_request.json',
        'refund_inquiry.json',
        'shipping_address_update.json'
    ]

    for file_path in conversation_files:
        run_e2e_test(file_path)