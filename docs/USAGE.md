# TES API Server for Azure Compute <!-- omit in toc -->

## Table of Contents <!-- omit in toc -->
<!--
Generated with the Markdown All in One extension by Yu Zhang.
https://marketplace.visualstudio.com/items?itemName=yzhang.markdown-all-in-one
-->
- [1. Deployment](#1-deployment)
  - [a. Deploy ACR](#a-deploy-acr)
  - [b. Terraform](#b-terraform)
  - [c. Initialize the app](#c-initialize-the-app)
  - [d. Provision resources for the backend](#d-provision-resources-for-the-backend)
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
    - [Block Blobs](#block-blobs)
    - [Azure Files](#azure-files)
    - [Deployment on App Service](#deployment-on-app-service)
- [Azure Blob Storage](#azure-blob-storage)
- [Azure Files](#azure-files-1)
- [Appendix B - Backend details](#appendix-b---backend-details)
  - [Azure Batch](#azure-batch-1)

## 1. Deployment
### a. Deploy ACR
Use the [Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli?view=azure-cli-latest) to setup a private container registry. To get started, login and pick your subscription:
```bash
az login
az account list -o table
az account set --subscription subscription-id-here
```

An Azure Container Registry is expected to be available and populated with the images necessary to start the solution. Replace the `<variables>` as you see fit:
```bash
az group create -n <rg_name> -l <rg_location>
az acr create -g <rg_name> -l <rg_location> -n <acr_name>
az acr login -n <acr_name>

pushd api-server
docker build -f Dockerfile_publish -t <acr_name>.azurecr.io/tesazure/api:latest .
docker push <acr_name>.azurecr.io/tesazure/api:latest
popd

pushd container-filetransfer
docker build -t <acr_name>.azurecr.io/tesazure/container-filetransfer:latest .
docker push <acr_name>.azurecr.io/tesazure/container-filetransfer:latest
popd

pushd local-forwarder
docker build -t <acr_name>.azurecr.io/tesazure/local-forwarder:latest .
docker push <acr_name>.azurecr.io/tesazure/local-forwarder:latest
popd
```

Lastly, edit `api-server/api-server.env` and set `APP_FILETRANSFER_CONTAINER_IMAGE` to `<acr_name>.azurecr.io/tesazure/container-filetransfer:latest`.

### b. Terraform
Deployment of the TES on Azure API server is performed through [Terraform](http://terraform.io/). Terraform is authenticated to Azure via the Azure CLI and will piggyback on our earlier login. To start deployment, run the below commands from the repo root:

```bash
cd api-server/terraform
terraform init

# Pass the username and password as the container registry is private
terraform plan -var 'resource_group_name=<rg_name>' -var 'resource_group_location=<rg_location>' -var 'acr_login_server=http://yourname.azurecr.io' -var 'acr_login_username=<username>' -var 'acr_login_password=<password>' -out=plan

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


### c. Initialize the app
App Service will pull the configured Docker images upon first request, which can take some time. To initialize the app, use curl or Postman to issue a GET request against `/v1/tasks/service-info`, for example:
```bash
curl https://tesazure-RANDOMID.azurewebsites.net/v1/tasks/service-info
```

The first few requests may return a 5xx HTTP status as it initializes. It should return a 200 HTTP status after a few minutes which indicates the API is now running.


### d. Provision resources for the backend
The API server provides a REST API for provisioning resources specific to the chosen backend.

After configuring the backend, restart the app service via the [Azure Portal](https://portal.azure.com) and initialize the web app again (see above) to reload its updated configuration.


### Troubleshooting
If the web endpoint does not come online, you may use the Log Stream feature from the App Service resource in the [Azure Portal](https://portal.azure.com) to view diagnostic information about the app initialization. Log Stream requires that you enable filesystem logging first, which you can do from the *Diagnostic Logs* blade on the same App Service resource.


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
Cromwell has a TES backend, however only local filesystem is supported - that is, that after tasks run in the cloud the `stdout`, `stderr` and `rc` files are expected to be present locally in the `cromwell-executions` folder on the Cromwell server.

To achieve this behavior, either an Azure Blob container (via [azure-storage-fuse](https://github.com/Azure/azure-storage-fuse)) or an Azure Files share (via SMB/CIFS) can be mounted to create shared filesystem from Azure cloud storage:
* Block Blocks achieve a higher performance at lower cost but cannot stream portions of files
* Azure Files is simpler and supports partial file reads, but is less performant than block blob and more costly for long-term data storage.

The TES API server has automatic detection for tasks submitted by Cromwell and applies workarounds to make implementing one of the two above approaches easy.

#### Block Blobs
When Cromwell is detected as the task submitter and local paths leverage the shared execution environment `/tes-wd/shared`, the files are automatically mapped to the configured storage container in the TES API server. For example, an output generated by Cromwell:
When Cromwell is detected, the TES input and output URL fields are mangled to use a blob SAS URI instead - for example:
```json
{
  "outputs": [
    {
      ...
      "path": "/tes-wd/shared-global/MultiStep/bded96bd-8d21-45c5-b956-2089ed4996ec/call-Merge/execution/rc"
    },
...
```
becomes:
```json
{
  "outputs": [
    {
      ...
      "path": "https://myaccount.blob.core.windows.net/CONTAINER/shared-global/MultiStep/bded96bd-8d21-45c5-b956-2089ed4996ec/call-Merge/execution/rc?SAS_TOKEN_PARAMS"
    },
...
```

The same transformations are performed on input files. This ensures that the Cromwell outputs, exit status (`rc`), standard output log (`stdout`) and standard error log (`stderr`) are captured to the blob storage account (globally in the TES API server).

If you wish to use Cromwell but avoid the auto-mapping of inputs and outputs to Azure blob, simply use paths outside of the shared prefix (`/tes-wd/shared`).

#### Azure Files
To use Azure Files, your workflow input files will need to exist in the Azure Files share name configured in the TES API server. The Azure Files mountpoint is `/tes-wd/shared-global` on remote compute, so your WDL workflow can be developed using local file paths under from that directory.

#### Deployment on App Service
Deployment of a Cromwell container on App Service provides a simple way to run Cromwell and also mount an Azure Files share or Blob Blob container to create a shared filesystem:
1. Visit the Azure portal and deploy a new [App Service - Web App for Linux Containers](https://azure.microsoft.com/en-us/services/app-service/containers/)
2. Under the *Container Settings* blade, choose *Docker Compose* and then *Docker Hub*. Enter the following `docker-compose` configuration under the *Configuration* text entry:
    ```
    version: '3'
    services:
      cromwell:
        image: "broadinstitute/cromwell:prod"
        entrypoint: "/bin/sh"
        command: ["-c", "java -Dconfig.file=/tes-wd/cromwell-tes.conf -jar /app/cromwell.jar server"]
        volumes:
          - cromwell-outputs:/tes-wd
          - shared-global:/tes-wd/shared-global
        ports:
          - "80:8000"
    ```
3. Navigate to the *Configuration* blade and under *Path Mappings*, configure the following mappings:
    1. Name=`cromwell-tes-blob`, Configuration options=*Basic*, Storage accounts=*<TES-deployed storage account>*, Storage Type=*Azure Blob*, Storage Container=`cromwell`, mount path=`cromwell-tes-blob`
    2. Name=`cromwell-tes-files`, Configuration options=*Basic*, Storage accounts=*<TES-deployed storage account>*, Storage Type=*Azure Files*, Storage Container=`batchfiles`, mount path=`cromwell-tes-files`
4. Edit the `backend.providers.TES.config.endpoint` configuration key of the reference [cromwell-tes.conf](cromwell-tes.conf) provided with this repo to point to your API server URI, and upload it to the `cromwell-tes-blob` container in your storage account.
5. Restart the Cromwell web app

## Azure Blob Storage
The blob implementation works by having App Service mount the container specified by the `CROMWELL_STORAGE_CONTAINER_NAME` configuration parameter and transforming Cromwell's local paths on the fly to blob URIs.

When the TES API server detects Cromwell is submitting tasks, inputs and outputs whose path begins with `/tes-wd/shared` are automatically remapped to a blob URL using the configured storage account and container (with the `/tes-wd` prefix removed). Therefore it is assumed that the WDL workflow will be configured with local paths that, by convention, mirror the cloud storage's container.

For example, given the following overrides:
```
APP_CROMWELL_STORAGE_CONTAINER_NAME='CROMWELL'
APP_STORAGE_ACCOUNT_NAME = 'TESONAZURE'
APP_STORAGE_ACCOUNT_KEY = 'AjR$Hbs ... =='
```

If a blob `https://TESONAZURE.blob.core.windows.net/CROMWELL/shared/inputs/large_file.cram` is uploaded, a hypothetical MultiStep workflow could specify as its WDL inputs file:
```
{
  "MultiStep.input_file": "/tes-wd/shared/inputs/large_file.cram",
}
```

Because the blob path and file path match (i.e. `shared/inputs/large_file.cram`), the TES server takes care of the mapping between the two.

The same applies for outputs as well - for example the `rc` output Cromwell produces would ordinarily be specified as a local path:
```
/tes-wd/shared/wf_hello/0911c1c7-de5d-442f-94e8-31814a035f8c/call-hello/execution/rc
```
which would be dynamically transformed to a blob URI in the provided account and container name, using the same path but with `/tes-wd` removed:
```
https://TESONAZURE.blob.core.windows.net/CROMWELL-OUTPUTS/shared/wf_hello/0911c1c7-de5d-442f-94e8-31814a035f8c/call-hello/execution/rc?sas_token_here
```

To use Azure Blob Storage with Cromwell, be sure to set the roots to `/tes-wd/shared`:
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
        root = "/tes-wd/shared
        dockerRoot = "/tes-wd/shared
        glob-link-command = "ls -L GLOB_PATTERN 2> /dev/null | xargs -I ? ln -s ? GLOB_DIRECTORY"
      }
    }
  }
}
```


## Azure Files
An Azure Files share is mounted at `/tes-wd/shared-global`. All that needs to be doen is to set the execution root to that folder:
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

**Important**: note that due to the nature of shared filesystems, the result of **any** Cromwell executions will be visible to anyone who has mounted the Azure File share.

## Appendix B - Backend details
Backend-specific details about configuring or using the compute backends are listed below. For additional detail, you may wish to read the [design documentation](DESIGN.md).


### Azure Batch
On the batch backend, `/tes-wd` maps to the job directory on the node the particular task is executing on, i.e. `$AZ_BATCH_TASK_DIR/../` (see [here](https://docs.microsoft.com/en-us/azure/batch/batch-compute-node-environment-variables#command-line-expansion-of-environment-variables) for details).

At a minimum, the following information must be configured to use the batch backend:
* `BATCH_ACCOUNT_NAME`: Azure Batch account name (e.g. `foo`)
* `BATCH_ACCOUNT_KEY`: Azure Batch account key (e.g. `asd...==`)
* `BATCH_ACCOUNT_URL`: Azure Batch account URL (e.g. `https://ACCOUNT_NAME.REGION.batch.azure.com`)
