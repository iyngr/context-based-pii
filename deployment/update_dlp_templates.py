import yaml
import os
from google.cloud import dlp_v2

def get_project_id():
    """Retrieves the Google Cloud Project ID from the environment variable."""
    project_id = os.environ.get("PROJECT_ID")
    if not project_id:
        raise ValueError("PROJECT_ID environment variable not set.")
    return project_id

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
    project_id = get_project_id()
    config_file = "main_service/dlp_config.yaml"
    create_or_update_dlp_templates(project_id, config_file)