import yaml
import os
import subprocess # New import
import logging # New import
from google.cloud import dlp_v2

# Configure logging for the script
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

def create_or_update_dlp_templates(project_id, config_file):
    """
    Creates or updates DLP inspect and de-identify templates based on a YAML configuration.
    """
    client = dlp_v2.DlpServiceClient()
    parent = f"projects/{project_id}/locations/us-central1"

    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    # Create or update Inspect Template
    inspect_template_name = config['dlp_templates']['inspect_template_name'].replace("${PROJECT_ID}", project_id)
    inspect_template_id = inspect_template_name.split('/')[-1]
    inspect_config = config['inspect_config']

    try:
        # Try to get the template to check if it exists
        client.get_inspect_template(name=inspect_template_name)
        print(f"Updating existing inspect template: {inspect_template_name}")
        template = dlp_v2.InspectTemplate(inspect_config=inspect_config)
        client.update_inspect_template(name=inspect_template_name, inspect_template=template)
    except Exception as e:
        print(f"Creating new inspect template: {inspect_template_name}")
        template = dlp_v2.InspectTemplate(inspect_config=inspect_config)
        client.create_inspect_template(parent=parent, inspect_template_id=inspect_template_id, inspect_template=template)

    # Create or update De-identify Template
    deidentify_template_name = config['dlp_templates']['deidentify_template_name'].replace("${PROJECT_ID}", project_id)
    deidentify_template_id = deidentify_template_name.split('/')[-1]
    deidentify_config = config['deidentify_config']

    try:
        # Try to get the template to check if it exists
        client.get_deidentify_template(name=deidentify_template_name)
        print(f"Updating existing de-identify template: {deidentify_template_name}")
        template = dlp_v2.DeidentifyTemplate(deidentify_config=deidentify_config)
        client.update_deidentify_template(name=deidentify_template_name, deidentify_template=template)
    except Exception as e:
        print(f"Creating new de-identify template: {deidentify_template_name}")
        template = dlp_v2.DeidentifyTemplate(deidentify_config=deidentify_config)
        client.create_deidentify_template(parent=parent, deidentify_template_id=deidentify_template_id, deidentify_template=template)

if __name__ == "__main__":
    project_id = get_gcp_project_id()
    config_file = "main_service/dlp_config.yaml"
    create_or_update_dlp_templates(project_id, config_file)