# Google Cloud DLP Permission Troubleshooting

The error message "DLP API Error: Requested inspect/deidentify template not found" (Error: 404 Requested deidentify template not found) often indicates a permission issue, even if the templates exist. The service account running your `main_service` (likely a Cloud Run service) needs specific IAM roles to access and use Google Cloud DLP templates.

## 1. Identify the Service Account

For a Cloud Run service, the default service account is typically `[PROJECT_NUMBER]-compute@developer.gserviceaccount.com` unless a custom service account was specified during deployment.

To find the exact service account used by your `main_service` Cloud Run instance:

1.  Go to the [Cloud Run page](https://console.cloud.google.com/run) in the Google Cloud Console.
2.  Select your `main_service` (or `context-manager` as per `progress.md`).
3.  Go to the **Details** tab.
4.  Look for the **Service account** field. Note down its email address.

## 2. Grant Necessary IAM Permissions

The service account needs permissions to read DLP templates and de-identify content.

### Recommended Role: `DLP User` (`roles/dlp.user`)

This role grants broad permissions for DLP operations, including viewing and using templates.

1.  Go to the [IAM & Admin page](https://console.cloud.google.com/iam-admin/iam) in the Google Cloud Console.
2.  Click **+ GRANT ACCESS**.
3.  In the **New principals** field, paste the service account email address you identified in step 1.
4.  In the **Select a role** dropdown, search for and select `DLP User`.
5.  Click **SAVE**.

### More Granular Permissions (if `DLP User` is too broad):

If you prefer more fine-grained control, you can grant the following individual permissions:

*   `dlp.inspectTemplates.get`
*   `dlp.deidentifyTemplates.get`
*   `dlp.content.deidentify`

To grant these:

1.  Follow steps 1-3 above.
2.  Instead of selecting a predefined role, click on the **Roles** dropdown and then **Add another role**.
3.  Search for and add each of the permissions listed above.
4.  Click **SAVE**.

## 3. Verify Template Location and Project ID

Double-check that the templates referenced in your `main_service/dlp_config.yaml` (e.g., `us-central1/inspectTemplates/identify`) exactly match the actual location and project ID where your DLP templates are created.

*   **Project ID:** Ensure is indeed your correct project ID.
*   **Location:** Confirm that your templates are in `us-central1`. If they are in a different region (e.g., `us-east1`), you must update `main_service/dlp_config.yaml` and redeploy `main_service`.

## 4. Redeploy `main_service` (Optional but Recommended)

Although IAM changes are usually propagated quickly, it's good practice to redeploy your `main_service` after updating permissions to ensure it picks up the latest IAM policies.

After granting the necessary permissions, re-test your application. If the issue persists, please provide any new error messages.