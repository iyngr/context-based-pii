import os
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
            )
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

        logger.info(f"Starting conversation upload for {gcs_uri}. This will block until the LRO completes.")

        # The upload_conversation method returns a Long-Running Operation (LRO).
        # Calling .result() blocks until the LRO is complete, handling polling internally.
        # This is the standard synchronous method for handling LROs.
        upload_operation = insights_client.upload_conversation(request=request)

        max_poll_time_seconds = 900  # 15 minutes
        response = upload_operation.result(timeout=max_poll_time_seconds)

        logger.info(f"Successfully uploaded conversation: {response.name}", extra={"json_fields": {"event": "ccai_upload_success", "conversation_id": conversation_id, "ccai_conversation_name": response.name}})

    except AlreadyExists:
        logger.info(f"Conversation with ID '{conversation_id}' already exists. Skipping upload.")
    except DeadlineExceeded:
        logger.error(f"LRO for conversation ID '{conversation_id}' timed out after {max_poll_time_seconds} seconds.", exc_info=True)
    except GoogleAPICallError as e:
        logger.error(f"GoogleAPICallError during conversation upload for conversation ID: {conversation_id}. Error: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred for conversation ID '{conversation_id}': {e}", exc_info=True)
