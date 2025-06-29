import os
import json
import logging
from google.cloud import contact_center_insights_v1
from google.api_core.exceptions import AlreadyExists, GoogleAPICallError, DeadlineExceeded

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

        # The upload_conversation method returns a Long-Running Operation (LRO) object.
        # Calling .result() on this object blocks until the operation is complete.
        # It handles polling internally and raises an exception if the operation fails.
        # This is the recommended, idiomatic way to handle LROs synchronously.
        logger.info(f"Starting conversation upload for {gcs_uri}. Waiting for LRO to complete...")
        upload_operation = insights_client.upload_conversation(request=request)

        # Set a timeout for the LRO to complete.
        lro_timeout_seconds = 900  # 15 minutes
        response = upload_operation.result(timeout=lro_timeout_seconds)

        logger.info(f"Successfully uploaded conversation: {response.name}", extra={"json_fields": {"event": "ccai_upload_success", "conversation_id": conversation_id, "ccai_conversation_name": response.name}})

    except AlreadyExists:
        # This is raised by .result() if the LRO completes with an ALREADY_EXISTS status.
        logger.warning(f"Conversation with ID '{conversation_id}' already exists. Skipping upload.")
    except DeadlineExceeded:
        # This is raised by .result() if the timeout is reached.
        logger.error(f"LRO for conversation ID '{conversation_id}' timed out after {lro_timeout_seconds} seconds.", exc_info=True)
        # Re-raising is important to signal failure to Cloud Functions for potential retries.
        raise
    except GoogleAPICallError as e:
        logger.error(f"GoogleAPICallError during conversation upload for conversation ID: {conversation_id}. Error: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        raise
