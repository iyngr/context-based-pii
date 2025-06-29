import os
import json
import logging
from google.cloud import contact_center_insights_v1
from google.api_core.exceptions import AlreadyExists, GoogleAPICallError
import time # Ensure time is imported for polling delays

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main(event, context):
    """
    Triggered by a change to a Cloud Storage bucket.
    Args:
         event (dict): Event payload.
         context (google.cloud.functions.Context): Metadata for the event.
    """
    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
    location = os.getenv('LOCATION', 'us-central1')
    bucket_name = event['bucket']
    file_name = event['name']
    gcs_uri = f"gs://{bucket_name}/{file_name}"
    conversation_id = os.path.splitext(file_name)[0].replace('_transcript', '')

    logger.info(f"Processing file: {file_name}.")
    logger.info(f"Conversation ID: {conversation_id}")

    if not project_id:
        logger.error("GOOGLE_CLOUD_PROJECT environment variable not set.")
        return

    try:
        client_options = {"api_endpoint": f"{location}-contactcenterinsights.googleapis.com"}
        insights_client = contact_center_insights_v1.ContactCenterInsightsClient(client_options=client_options)

        parent = f"projects/{project_id}/locations/{location}"

        conversation = contact_center_insights_v1.types.Conversation(
            data_source=contact_center_insights_v1.types.ConversationDataSource(
                gcs_source=contact_center_insights_v1.types.GcsSource(transcript_uri=gcs_uri)
            ),
        )

        redaction_config = contact_center_insights_v1.types.RedactionConfig(
            deidentify_template=f"projects/{project_id}/locations/{location}/deidentifyTemplates/deidentify",
            inspect_template=f"projects/{project_id}/locations/{location}/inspectTemplates/identify"
        )

        request = contact_center_insights_v1.types.UploadConversationRequest(
            parent=parent,
            conversation=conversation,
            conversation_id=conversation_id,
            redaction_config=redaction_config,
        )

        upload_operation = insights_client.upload_conversation(request=request)
        operation_name = upload_operation.operation.name
        logger.info(f"Upload operation started for {gcs_uri}, operation: {operation_name}")
        
        # Poll the LRO status using insights_client.transport.operations_client
        max_poll_time_seconds = 900 # 15 minutes, adjust as needed based on expected LRO duration
        poll_interval_seconds = 10 # Poll every 10 seconds
        start_time = time.time()

        while True:
            operation = insights_client.transport.operations_client.get_operation(name=operation_name)
            if operation.done:
                break
            
            if time.time() - start_time > max_poll_time_seconds:
                logger.error(f"LRO polling timed out after {max_poll_time_seconds} seconds for operation: {operation_name}", extra={"json_fields": {"event": "lro_polling_timeout", "operation_name": operation_name}})
                raise GoogleAPICallError(f"LRO polling timed out for operation: {operation_name}")
            
            time.sleep(poll_interval_seconds)
            logger.info(f"Polling LRO {operation_name}. Not yet done. Retrying in {poll_interval_seconds} seconds.")

        if operation.exception(): # Check if an exception occurred
            # Get the exception object
            lro_exception = operation.exception()
            error_message = str(lro_exception)
            error_code = getattr(lro_exception, 'code', 'UNKNOWN') # Get code if available
            
            if isinstance(lro_exception, AlreadyExists):
                logger.warning(f"Conversation with ID '{conversation_id}' already exists. Skipping upload. Operation: {operation_name}")
            else:
                logger.error(f"LRO failed for operation: {operation_name}. Error: {error_message}", exc_info=True, extra={"json_fields": {"event": "lro_failed", "operation_name": operation_name, "error_code": error_code, "error_message": error_message}})
                raise GoogleAPICallError(f"LRO failed: {error_message}")
        elif operation.error: # Fallback to operation.error if no exception object
            error_message = operation.error.message if operation.error.message else "Unknown LRO error"
            error_code = operation.error.code if operation.error.code else "UNKNOWN"
            
            if error_code == 6: # ALREADY_EXISTS (code 6)
                logger.warning(f"Conversation with ID '{conversation_id}' already exists. Skipping upload. Operation: {operation_name}")
            else:
                logger.error(f"LRO failed for operation: {operation_name}. Error: {error_message}", exc_info=True, extra={"json_fields": {"event": "lro_failed", "operation_name": operation_name, "error_code": error_code, "error_message": error_message}})
                raise GoogleAPICallError(f"LRO failed: {error_message}")
        else:
            # If operation is done and no error/exception, it must have a response
            if operation.response: # Ensure response object exists before deserializing
                response = contact_center_insights_v1.types.Conversation.deserialize(operation.response.value)
                logger.info(f"Successfully uploaded conversation: {response.name}", extra={"json_fields": {"event": "ccai_upload_success", "conversation_id": conversation_id, "ccai_conversation_name": response.name}})
            else:
                logger.error(f"LRO completed without error or response for operation: {operation_name}. This is an unexpected state.", extra={"json_fields": {"event": "lro_unexpected_state", "operation_name": operation_name}})
                raise GoogleAPICallError(f"LRO completed in unexpected state: {operation_name}")

    except AlreadyExists: # This catch is for the initial upload_conversation call, if it immediately returns AlreadyExists
        logger.warning(f"Conversation with ID '{conversation_id}' already exists. Skipping upload (initial check).")
    except GoogleAPICallError as e:
        logger.error(f"GoogleAPICallError during conversation upload for conversation ID: {conversation_id}. Error: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
