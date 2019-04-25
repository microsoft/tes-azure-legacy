# TES API Server for Azure Compute <!-- omit in toc -->

## Table of Contents <!-- omit in toc -->
<!--
Generated with the Markdown All in One extension by Yu Zhang.
https://marketplace.visualstudio.com/items?itemName=yzhang.markdown-all-in-one
-->
- [1. Deployment](#1-deployment)
  - [a. Terraform](#a-terraform)
  - [b. Initialize the app](#b-initialize-the-app)
  - [c. Provision resources for the backend](#c-provision-resources-for-the-backend)
  - [Troubleshooting](#troubleshooting)
- [2. Configuration](#2-configuration)
  - [a. Compute backends](#a-compute-backends)
  - [b. Authentication](#b-authentication)
- [3. Backend Resource Provisioner](#3-backend-resource-provisioner)
  - [a. Submit a backend resource provision request](#a-submit-a-backend-resource-provision-request)
    - [Azure Batch](#azure-batch)
  - [b. Query status](#b-query-status)
- [4. Authoring a TES task](#4-authoring-a-tes-task)
- [Appendix A - Workflow engine details](#appendix-a---workflow-engine-details)
  - [Cromwell](#cromwell)
- [Appendix B - Backend details](#appendix-b---backend-details)
  - [Azure Batch](#azure-batch-1)

## 1. Deployment
### a. Terraform
Deployment of the TES on Azure API server is performed through [Terraform](http://terraform.io/). Terraform is authenticated to Azure via the [Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli?view=azure-cli-latest) and thus the Azure CLI is also required. Ensure you are logged into the Azure CLI first with `az login` before attempting deployment with Terraform. To deploy, navigate to the `api-server/terraform` directory in this repository in a shell and run the below commands.

```bash
terraform init

# Pass the username and password as the container registry is private
terraform plan -var 'resource_group_name=<rg_name>' -var 'resource_group_location=<rg_location>' -var 'acr_login_username=<username>' -var 'acr_login_password=<password>' -out=plan

terraform apply "plan"
```

Terraform will automatically provision the API server as a web app on Azure App service along with its dependencies (Azure Container Registry, App Insights, Redis, Azure DB for PostgreSQL, Key Vault) and place the connection secrets in Key Vault for you. The deployment takes approximately 20 minutes to complete.

Resource information (including URL) to the App Service instance created will be printed by Terraform upon completion, for example:
```
app_service_default_hostname = https://tesazure-RANDOMID.azurewebsites.net
app_service_name = tesazure-RANDOMID
resource_group = tesazure
```

NOTE: Currently, there is a bug in the PostgreSQL firewall rule API for Azure which should be fixed in June. You may see an error during provisioning related to the firewall rule ([more information here](https://github.com/MicrosoftDocs/azure-docs/issues/20758)).


### b. Initialize the app
App Service will pull the configured Docker images upon first request, which can take some time. To initialize the app, use curl or Postman to issue a GET request against `/v1/tasks/service-info`, for example:
```bash
curl https://tesazure-RANDOMID.azurewebsites.net/v1/tasks/service-info
```

The first few requests may return a 5xx HTTP status as it initializes. It should return a 200 HTTP status after a few minutes which indicates the API is now running.


### c. Provision resources for the backend
The API server provides a REST API for provisioning resources specific to the chosen backend.

After configuring the backend, restart the app service via the [Azure Portal](https://portal.azure.com) and initialize the web app again (see above) to reload its updated configuration.


### Troubleshooting
If the web endpoint does not come online, you may use the Log Stream feature from the App Service resource in the [Azure Portal](https://portal.azure.com) to view diagnostic information about the app initialization. Log Stream requires that you enable filesystem logging first, which you can do from the Diagnostic Logs blade on the same App Service resource.


## 2. Configuration
Application configuration may be performed by setting environment variables. On Azure App Service, these variables are configurable in the [Azure Portal](https://portal.azure.com) under the web app resource's *App Settings* blade.

The API server will automatically override a configuration parameter named `CONFVAR` if it finds a corresponding environment variable with the `APP_` prefix (i.e., named `APP_CONFVAR`).

Configuration parameters may also be performed by adding values to Azure Key Vault. Once setup, the TES API will automaticall override a configuration parameter named `CONFVAR` if it finds a corresponding secret with the `TESAZURE-` prefix (i.e., named `TESAZURE-CONFVAR`). Since Key Vault doesn't support underscores, any secret name with a dash will be set in configuration with an underscore instead to match Flask configuration standards.

The provisioners below take care of this initial configuration for you; but if manually setting up an instance of the Docker image, to connect a Key Vault the `KEYVAULT_URL` configuration value must be set at a minumum. Since using a Managed Service Identity is not yet supported, you also need to set the `AZURE_CLIENT_ID`, `AZURE_SECRET`, and `AZURE_TENANT` configuration values for a service principle with access to the Key Vault.

There are more configuration parameters than listed here; **see [`config.py`](/tesazure/config.py) for the full list of supported configuration parameters.**


### a. Compute backends
The `COMPUTE_BACKEND` configuration variable determines which Azure Compute backend is used. At this time, only the `batch` backend is supported and used by default.

Support for Azure Kubernetes Service (AKS) and possibly others is planned for the future.

The provisioning REST API (see below) will automatically adjust the API server's configuration parameters as resources are provisioned. If you wish to configure manually, see the *Appendix - Backend details* section below for details.


### b. Authentication
By default, the TES endpoint will be unprotected and task information is visible to all users. However, you may optionally configure Bearer authentication backed by AAD to restrict access to the APIs and limit task visibility between users or tenants. [Create your AAD application](https://docs.microsoft.com/en-us/azure/active-directory/develop/quickstart-v1-add-azure-ad-app) and configure the following config parameters:
```python
AAD_VERIFY = True
AAD_AUDIENCE = 'your-aad-app-client-id'
AAD_TENANT_ID = 'your-aad-app-tenant-id'

# Choices among [None, 'per-user', 'per-tenant'], defaults to None
TASK_ACCESS_RESTRICTIONS = 'per-user'
```
The configuration above ensures that only tokens for users originating from the indicated `AAD_TENANT_ID` will be accepted, and that tasks from one user are not visible by another.

## 3. Backend Resource Provisioner
While the TES specification does not include a compute provisioner, in order to reduce spin-up friction, a compute provisioner is included in the API server outside of the TES API schema.

Since infrastructure provisioning takes longer than appropriate for a REST request, the request returns immediately (after initial validation) with a unique id that the client may pass to the status endpoint to query the provisioning progress.

The provisioner will attempt to provision resources for the configured backend as specified in the `COMPUTE_BACKEND` setting.

### a. Submit a backend resource provision request
The backend resource provision request consists of a POST payload to the provisioner with your request body, making sure to keep the `guid` value the call returns:
```
POST '/provision/initialize'
{
  backend-specific json body here (see below)
}
```

Different compute backends require different body parameters for provisioning since the underlying infrastructure is different. Each of the payload formats are defined below.

#### Azure Batch
Required fields are `service_principal` and `subscription_id`. The service principal must have access in the specified subscription to create resources. The other fields are populated with defaults and names are populated using a random number generator to avoid conflicts with other Azure resoruces. Default logic is defined in the [batch backend models](tesazure/backends/batch/models.py).

```json
 {
	"service_principal": {
		"client_id": "<client-id>",
		"secret": "<secret>",
		"tenant": "<tenant>"
	},
    "subscription_id": "<subscription_id>",
    "resource_group": "<resource_group_name>",
    "location": "<az_region_name>",
    "storage_account_name": "<storage_account_name>",
    "storage_sku": "<storage_sku>",
    "batch_account_name": "<batch_account_name>"
}
```


### b. Query status
Query the status of the provisioning, replacing `<guid>` with the GUID returned in Step 1.
```
GET '/provision/query/<guid>'
```


## 4. Authoring a TES task
No matter which compute backend is selected, the TES API ensures a consistent runtime environment for executors. Two directories are made available on all tasks:
* `/tes-wd`: An backend-specific volume mount, possibly only available to the specific executor
* `/tes-wd/shared`: A volume shared by all executors within a TES task
* `/tes-wd/shared-global`: A globally-shared volume for all TES tasks

Any TES task inputs are marshalled into the `/tes-wd/shared` prior to execution of the tasks' executors, and TES task outputs are read from there as well after executor execution. It is intended to be used as a working directory for output data. Its contents can be considered private, as each TES task will have its own volume.

Note that because this folder is shared between executors of a TES task, any tools with intermediary outputs should take care not to overwrite input files; modified input files will remain that way as files are downloaded onto the backend compute only once, not once per executor.

The `/tes-wd/shared-global` volume is shared by **all tasks** and so one task may introspect the data written to this directory by another task. This has specific advantages for some workflow engines (see below), but use with caution.


## Appendix A - Workflow engine details
### Cromwell
Cromwell has a TES backend, however only local filesystem is supported - that is, that after tasks run in the cloud the `stdout`, `stderr` and `rc` files are expected to be present locally in the `cromwell-executions` folder.

To achieve this behavior, Azure Files can be leveraged to create a shared filesystem over SMB. By default, a Azure Files share is mounted at `/tes-wd/shared-global`. Create a Cromwell configuration to ensure the remote compute outputs to that folder:
```
include required(classpath("application"))

backend {
  default = "TES"
  providers {
    TES {
      actor-factory = "cromwell.backend.impl.tes.TesBackendLifecycleActorFactory"
      config {
        temporary-directory = "$(mktemp -d \"/$AZ_BATCH_TASK_DIR\"/tmp.XXXXXX)"
        endpoint = "http://TESAZURE_FQDN/v1/tasks"
        root = "/tes-wd/shared-global"
        dockerRoot = "/tes-wd/shared-global"
        glob-link-command = "ls -L GLOB_PATTERN 2> /dev/null | xargs -I ? ln -s ? GLOB_DIRECTORY"
      }
    }
  }
}
```

Then mount the Azure Files share as the `cromwell-executions` folder:
```bash
mkdir cromwell-executions
sudo mount -t cifs //ACCOUNT_NAME.file.core.windows.net/batchtmp cromwell-executions dir_mode=0777,file_mode=0777,serverino
```
For more information, see [Using Azure Files](https://docs.microsoft.com/en-us/azure/storage/files/storage-how-to-use-files-linux).

**Important**: note that due to the nature of shared filesystems, the result of **any** Cromwell executions will be visible to anyone who has mounted the Azure File share.

## Appendix B - Backend details
Backend-specific details about configuring or using the compute backends are listed below. For additional detail, you may wish to read the [design documentation](DESIGN.md).


### Azure Batch
On the batch backend, `/tes-wd` maps to the job directory on the node the particular task is executing on, i.e. `$AZ_BATCH_TASK_DIR/../` (see [here](https://docs.microsoft.com/en-us/azure/batch/batch-compute-node-environment-variables#command-line-expansion-of-environment-variables) for details).

At a minimum, the following information must be configured to use the batch backend:
* `BATCH_ACCOUNT_NAME`: Azure Batch account name (e.g. `foo`)
* `BATCH_ACCOUNT_KEY`: Azure Batch account key (e.g. `asd...==`)
* `BATCH_ACCOUNT_URL`: Azure Batch account URL (e.g. `https://ACCOUNT_NAME.REGION.batch.azure.com`)
