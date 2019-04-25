# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import contextlib
import datetime
import posixpath
import shlex
import uuid
from marshmallow import ValidationError

import azure.batch as azbatch
import azure.batch.batch_auth as azbatch_auth
import azure.storage.blob as azblob
import azure.mgmt.resource as azresource_mgmt
import azure.mgmt.storage as azstorage_mgmt
import azure.mgmt.batch as azbatch_mgmt
import azure.common.credentials as azcredentials
import azure.storage.file as azfiles
from msrestazure.azure_exceptions import CloudError as AzCloudError

from flask import current_app
from flask_celeryext.app import current_celery_app
from flask_celeryext import RequestContextTask

from .. import common as backend_common
from ... import models as tesmodels
from . import models as batchbackendmodels


@contextlib.contextmanager
def _handle_batch_error(should_raise=True):
    try:
        yield
    except azbatch.models.BatchErrorException as e:
        details = "N/A"
        if e.error.values:
            details = ', '.join([f"{detail.key}='{detail.value}'" for detail in e.error.values])
        current_app.logger.exception(f"Batch error {e.error.code}: {e.error.message}. Details: {details}")
        if should_raise:
            raise


class AzureBatchEngine(backend_common.AbstractComputeBackend):
    """
    A lightweight class for working with Azure Batch.

    Attributes:
        credentials: An Azure Batch client credentials object.
        batch_client_pool: An instance of the Azure Batch client.
    """

    @property
    def provision_request_schema(self):
        """MarshmallowSchema for backend specific provision request"""
        return batchbackendmodels.ProvisionRequestSchema()

    def __init__(self):
        """Return a new AzureBatchEngine object."""
        self.credentials = azbatch_auth.SharedKeyCredentials(
            current_app.config['BATCH_ACCOUNT_NAME'],
            current_app.config['BATCH_ACCOUNT_KEY'])

        self.batch_client = azbatch.batch_service_client.BatchServiceClient(
            self.credentials,
            current_app.config['BATCH_ACCOUNT_URL']
        )

    def _initializePoolKeywordArgs(self, vm_size):
        """Returns kwargs used for pool initialization."""
        admin_user = None
        if current_app.config['BATCH_NODE_ADMIN_USERNAME'] and current_app.config['BATCH_NODE_ADMIN_PASSWORD']:
            # Add a debug admin user if requested
            current_app.logger.debug(f"Adding user {current_app.config['BATCH_NODE_ADMIN_USERNAME']} to pool")
            admin_user = [azbatch.models.UserAccount(elevation_level=azbatch.models.ElevationLevel.admin, name=current_app.config['BATCH_NODE_ADMIN_USERNAME'], password=current_app.config['BATCH_NODE_ADMIN_PASSWORD'])]

        pool_start_task = None
        if 'BATCH_STORAGE_FILESHARE_NAME' in current_app.config and current_app.config['BATCH_STORAGE_FILESHARE_NAME'] is not None:
            current_app.logger.info(f"Creating pool with Azure files share '{current_app.config['BATCH_STORAGE_FILESHARE_NAME']}'")
            share_name = current_app.config['BATCH_STORAGE_FILESHARE_NAME']
            file_service = azfiles.FileService(account_name=current_app.config['STORAGE_ACCOUNT_NAME'], account_key=current_app.config['STORAGE_ACCOUNT_KEY'])
            file_service.create_share(share_name)

            azfiles_mountpoint = "/mnt/batch/tasks/shared-azfiles"
            # FIXME: core.windows.net suffix could theoretically vary
            azfiles_endpoint = f"//{file_service.account_name}.file.core.windows.net/{share_name}"
            node_start_command = f'/bin/bash -c "mkdir -p {shlex.quote(azfiles_mountpoint)} && mount -t cifs {shlex.quote(azfiles_endpoint)} {shlex.quote(azfiles_mountpoint)} -o vers=3.0,username={shlex.quote(current_app.config["STORAGE_ACCOUNT_NAME"])},password={current_app.config["STORAGE_ACCOUNT_KEY"]},dir_mode=0777,file_mode=0777,serverino,mfsymlinks"'

            pool_start_task = azbatch.models.StartTask(
                command_line=node_start_command,
                wait_for_success=True,
                user_identity=azbatch.models.UserIdentity(
                    auto_user=azbatch.models.AutoUserSpecification(
                        scope=azbatch.models.AutoUserScope.pool,
                        elevation_level=azbatch.models.ElevationLevel.admin
                    )
                )
            )

        acr_registry = None
        if current_app.config['PRIVATE_DOCKER_REGISTRY_URL']:
            # Check if we need to add a private registry to the pool
            # Note images are only downloaded upon creation, never updated later
            current_app.logger.debug(f"Adding private Docker registry {current_app.config['PRIVATE_DOCKER_REGISTRY_URL']} to pool")
            acr_registry = azbatch.models.ContainerRegistry(
                registry_server=current_app.config['PRIVATE_DOCKER_REGISTRY_URL'],
                user_name=current_app.config['PRIVATE_DOCKER_REGISTRY_USERNAME'],
                password=current_app.config['PRIVATE_DOCKER_REGISTRY_PASSWORD']
            )

        container_conf = azbatch.models.ContainerConfiguration(
            container_image_names=['alpine'],
            container_registries=[acr_registry] if acr_registry else None)

        image = azbatch.models.VirtualMachineConfiguration(
            image_reference=azbatch.models.ImageReference(
                publisher="microsoft-azure-batch",
                offer="ubuntu-server-container",
                sku="16-04-lts",
                version="latest"
            ),
            container_configuration=container_conf,
            node_agent_sku_id="batch.node.ubuntu 16.04"
        )

        return {
            'vm_size': vm_size,
            'target_dedicated_nodes': current_app.config['BATCH_POOL_DEDICATED_NODE_COUNT'],
            'target_low_priority_nodes': current_app.config['BATCH_POOL_LOW_PRIORITY_NODE_COUNT'],
            'user_accounts': admin_user,
            'start_task': pool_start_task,
            'virtual_machine_configuration': image
        }

    def _initializePool(self, vm_size):
        """Initialize a new Azure Batch pool."""
        # create a new unique Azure Batch pool id
        pool_id = str(uuid.uuid4())
        current_app.logger.info(f"Attempting to create new pool {pool_id}")

        pool = azbatch.models.PoolAddParameter(id=pool_id, **self._initializePoolKeywordArgs(vm_size))
        self.batch_client.pool.add(pool)
        return pool

    def _initializePoolSpec(self, vm_size):
        """Initialize a Azure Batch auto-pool spec for use when a job is submitted."""
        return azbatch.models.PoolSpecification(**self._initializePoolKeywordArgs(vm_size))

    def createJob(self, task):
        """Create new job and execute workflow."""
        # check Azure Batch jobs list to see if a job with the same id exists
        job_id = str(uuid.uuid4())
        existing_job_ids = [j.id for j in self.batch_client.job.list()]
        if job_id in existing_job_ids:
            current_app.logger.warning(f"Batch job {job_id} already exists!")
            return False

        current_app.logger.info(f'Creating Azure Batch job {job_id}')

        # TODO: Make a script in the container and pass inputs instead of command line
        download_commands = backend_common.commands.generate_input_download_commands(task)
        upload_commands = backend_common.commands.generate_output_upload_commands(task)

        # Upload TES inputs passed as 'content' to blob, then download them into
        # the containers during prep. FIXME: Need a cleanup routine for this
        container_name = current_app.config['BATCH_STORAGE_TMP_CONTAINER_NAME']
        blob_service = azblob.BlockBlobService(account_name=current_app.config['STORAGE_ACCOUNT_NAME'], account_key=current_app.config['STORAGE_ACCOUNT_KEY'])
        blob_service.create_container(container_name)
        for input in task.inputs:
            if input.content is None:
                continue

            blob_filename = str(uuid.uuid4())
            blob_service.create_blob_from_text(container_name, blob_filename, input.content)
            token = blob_service.generate_blob_shared_access_signature(
                container_name,
                blob_filename,
                azblob.BlobPermissions.READ,
                datetime.datetime.utcnow() + datetime.timedelta(hours=1),
            )
            url = blob_service.make_blob_url(container_name, blob_filename, sas_token=token)
            download_commands.append(backend_common.commands.generate_input_download_command(url, input.path))

        # Pick an appropriate VM size and create the pool as necessary
        vm_size = backend_common.determine_azure_vm_for_task(task.resources)
        override_pool_id = current_app.config.get('BATCH_OVERRIDE_POOL_ID', None)
        if override_pool_id:
            current_app.logger.info(f"Using pool override {override_pool_id} for batch job {job_id}")
            pool_info = azbatch.models.PoolInformation(pool_id=override_pool_id)
        else:
            current_app.logger.info(f"Auto-pool to be created with batch job {job_id}")
            pool_info = azbatch.models.PoolInformation(

                auto_pool_specification=azbatch.models.AutoPoolSpecification(
                    auto_pool_prefix='tes-',
                    pool_lifetime_option='job',
                    keep_alive=False,
                    pool=self._initializePoolSpec(vm_size)
                )
            )

        job = azbatch.models.JobAddParameter(
            id=job_id,
            pool_info=pool_info,
            on_all_tasks_complete=azbatch.models.OnAllTasksComplete.terminate_job,
            on_task_failure=azbatch.models.OnTaskFailure.perform_exit_options_job_action
        )

        current_app.logger.info(f'Adding preparation task for job {job_id}')
        task_container_run_options = '-v "$AZ_BATCH_TASK_DIR/../:/tes-wd"'
        if 'BATCH_STORAGE_FILESHARE_NAME' in current_app.config and current_app.config['BATCH_STORAGE_FILESHARE_NAME'] is not None:
            azfiles_path = f"/mnt/batch/tasks/shared-azfiles"
            task_container_run_options += f' -v "{azfiles_path}:/tes-wd/shared-global"'
        fileprep_task_container_run_options = '--entrypoint=/bin/sh ' + task_container_run_options
        download_commands_shell = ';'.join(download_commands) if download_commands else 'true'

        job.job_preparation_task = azbatch.models.JobPreparationTask(
            container_settings=azbatch.models.TaskContainerSettings(
                # FIXME: change this to the public version when available
                image_name='tesazure.azurecr.io/tesazure/container-filetransfer',
                container_run_options=fileprep_task_container_run_options
            ),
            # mkdir is required to ensure permissions are right on folder
            # if created by Docker from -v syntax, owned by root and permissions
            # errors ensue
            command_line=f""" -c "set -e; set -o pipefail; mkdir -p /tes-wd/shared; {download_commands_shell}; wait" """,
        )

        if upload_commands:
            # prep task is always used for mkdir above at a minimum, but if
            # changing this logic later, recall that release task cannot be
            # specified without prep task
            current_app.logger.info(f'Adding release task for job {job_id}')
            job.job_release_task = azbatch.models.JobReleaseTask(
                container_settings=azbatch.models.TaskContainerSettings(
                    # FIXME: change this to the public version when available
                    image_name='tesazure.azurecr.io/tesazure/container-filetransfer',
                    container_run_options=fileprep_task_container_run_options
                ),
                command_line=f""" -c "set -e; set -o pipefail; {';'.join(upload_commands)}; wait" """
            )

        with _handle_batch_error():
            self.batch_client.job.add(job)

        for executor in task.executors:
            task_id = str(uuid.uuid4())
            current_app.logger.info(f'Creating Azure Batch task {task_id} for executor')

            batch_task_env = [azbatch.models.EnvironmentSetting(name=k, value=v) for k, v in executor.env.items()]

            commands = [' '.join(executor.command)]
            if executor.stdout:
                # currently the source path isn't quoted; we should map the workdir into /tes-wd explicitly
                # to avoid having to use the shell expansion here
                commands += backend_common.commands.generate_copy_commands(posixpath.join("/tes-wd/$AZ_BATCH_TASK_ID/stdout.txt"), executor.stderr)
            if executor.stderr:
                commands += backend_common.commands.generate_copy_commands(posixpath.join("/tes-wd/$AZ_BATCH_TASK_ID/stderr.txt"), executor.stderr)

            # TODO: Handle 'workdir' parameter from TES
            task = azbatch.models.TaskAddParameter(
                id=task_id,
                environment_settings=batch_task_env,
                command_line=f"""/bin/sh -c "set -e; {';'.join(commands)}; wait" """,
                container_settings=azbatch.models.TaskContainerSettings(
                    image_name=executor.image,
                    container_run_options=task_container_run_options
                )
            )
            self.batch_client.task.add(job_id=job_id, task=task)

        return job_id

    def create_task(self, task):
        """Create a new Azure Batch task."""
        task_id = self.createJob(task)
        return task_id

    def get_task(self, task_id):
        try:
            batch_job = self.batch_client.job.get(task_id)
        except azbatch.models.BatchErrorException as e:
            if e.error.code == "JobNotFound":
                return False
            raise

        tes_task = tesmodels.TesTask()
        tes_task.creation_time = batch_job.creation_time

        tes_log = tesmodels.TaskLog()
        tes_log.start_time = batch_job.creation_time

        if batch_job.state == azbatch.models.JobState.completed:
            tes_log.end_time = batch_job.state_transition_time

        # Default state inheritance, with 'active' as QUEUED unless we get more detailed into from tasks
        state_map = {
            azbatch.models.JobState.active: tesmodels.TaskStatus.QUEUED,
            azbatch.models.JobState.completed: tesmodels.TaskStatus.COMPLETE,
            azbatch.models.JobState.deleting: tesmodels.TaskStatus.CANCELED,
            azbatch.models.JobState.disabled: tesmodels.TaskStatus.PAUSED,
            azbatch.models.JobState.disabling: tesmodels.TaskStatus.PAUSED,
            azbatch.models.JobState.enabling: tesmodels.TaskStatus.PAUSED,
            azbatch.models.JobState.terminating: tesmodels.TaskStatus.RUNNING,
        }
        tes_task.state = state_map.get(batch_job.state, tesmodels.TaskStatus.UNKNOWN)

        # Check prep and release task status, but only if they exist
        if any([batch_job.job_preparation_task, batch_job.job_release_task]):
            for task_info in self.batch_client.job.list_preparation_and_release_task_status(batch_job.id):
                if task_info.job_preparation_task_execution_info:
                    # System error if file marshalling failed
                    if task_info.job_preparation_task_execution_info.result == azbatch.models.TaskExecutionResult.failure:
                        tes_task.state = tesmodels.TaskStatus.SYSTEM_ERROR
                    # Initializing when files are being downloaded
                if task_info.job_preparation_task_execution_info.state == azbatch.models.JobPreparationTaskState.running:
                    tes_task.state = tesmodels.TaskStatus.INITIALIZING

                if task_info.job_release_task_execution_info:
                    # System error if file marshalling failed
                    if task_info.job_release_task_execution_info.result == azbatch.models.TaskExecutionResult.failure:
                        tes_task.state = tesmodels.TaskStatus.SYSTEM_ERROR
                    # Active if files are being uploaded
                    if task_info.job_release_task_execution_info.state == azbatch.models.JobReleaseTaskState.running:
                        tes_task.state = tesmodels.TaskStatus.RUNNING

        # Check status against batch task summary
        if tes_task.state == tesmodels.TaskStatus.UNKNOWN:
            task_status = self.batch_client.job.get_task_counts(batch_job.id)
            if task_status.failed:
                tes_task.state = tesmodels.TaskStatus.EXECUTOR_ERROR
            elif task_status.running == 0 and task_status.active > 0:
                tes_task.state = tesmodels.TaskStatus.QUEUED

        # Get the executor logs (each batch task)
        for batch_task in self.batch_client.task.list(batch_job.id):
            # Above assumes EXECUTOR_ERROR on any task failure - override if it was a platform failure
            if batch_task.execution_info.result == azbatch.models.TaskExecutionResult.failure:
                if batch_task.execution_info.failure_info.category == azbatch.models.ErrorCategory.server_error:
                    batch_job.state = tesmodels.TaskStatus.SYSTEM_ERROR

            # Executor logs
            executor_log = tesmodels.ExecutorLog(start_time=batch_task.creation_time, end_time=batch_task.state_transition_time)
            executor_log.exit_code = batch_task.execution_info.exit_code

            # Add output streams to executor logs (only available if job is completed)
            if batch_job.state == azbatch.models.JobState.completed:
                with _handle_batch_error(should_raise=False):
                    output = self.batch_client.file.get_from_task(batch_job.id, batch_task.id, 'stdout.txt')
                    for data in output:
                        executor_log.stdout += data.decode('utf-8')

                with _handle_batch_error(should_raise=False):
                    output = self.batch_client.file.get_from_task(batch_job.id, batch_task.id, 'stderr.txt')
                    for data in output:
                        executor_log.stderr += data.decode('utf-8')

            tes_log.logs = tes_log.logs + [executor_log]

        # FIXME: tes_task is not loaded from db so outputs is empty here
        for output in tes_task.outputs:
            output_log = tesmodels.OutputFileLog()
            output_log.path = output.path
            output_log.url = output.url
            output_log.size_bytes = 0  # TODO
            tes_log.outputs = tes_log.outputs + [output_log]

        tes_task.logs = [tes_log]
        return tes_task

    def list_tasks(self):
        """Return a list of Azure Batch jobs."""
        # TODO: return simplified job list
        return self.batch_client.job.list()

    def service_info(self):
        """
        Get service details and capacity availability. Implementation gets
        merged with API's defaults, overriding keys if there is overlap.
        """
        return {}

    def cancel_task(self, task_id):
        """Cancel an existing task (job) by id."""
        try:
            self.batch_client.job.delete(task_id)
            current_app.logger.info(f"job {task_id} deleted")
            return True
        except azbatch.models.BatchErrorException:
            return False

    def configure(self):
        pass

    def provision_check(self, provision_request):
        """Checks a ProvisionRequest object for validity with the Batch backend"""

        try:
            credentials = azcredentials.ServicePrincipalCredentials(
                client_id=provision_request.service_principal.client_id,
                secret=provision_request.service_principal.secret,
                tenant=provision_request.service_principal.tenant
            )

            resource_client = azresource_mgmt.ResourceManagementClient(credentials, provision_request.subscription_id)
            storage_client = azstorage_mgmt.StorageManagementClient(credentials, provision_request.subscription_id)
            batch_client = azbatch_mgmt.BatchManagementClient(credentials, provision_request.subscription_id)

            rg_check_result = resource_client.resource_groups.check_existence(provision_request.resource_group)
            if rg_check_result is True:
                with resource_client.resource_groups.get(provision_request.resource_group) as resource_group:
                    if not resource_group.location == provision_request.location:
                        raise AzCloudError('Resource group exists but in different provision_request.location than provided.')

            storage_check_result = storage_client.storage_accounts.check_name_availability(name=provision_request.storage_account_name)
            if not storage_check_result.name_available:
                if not storage_check_result.reason == 'AlreadyExists':
                    raise tesmodels.CloudError(storage_check_result.message)
                else:
                    storage_client.storage_accounts.get_properties(  # <-- will throw exception if in different RG
                        resource_group_name=provision_request.resource_group,
                        account_name=provision_request.storage_account_name)

            batch_check_result = batch_client.location.check_name_availability(
                location_name=provision_request.location,
                name=provision_request.batch_account_name)
            if not batch_check_result.name_available:
                if not batch_check_result.reason.value == 'AlreadyExists':
                    raise AzCloudError(batch_check_result.message)
                else:
                    batch_client.batch_account.get(  # <-- will throw exception if in different RG
                        resource_group_name=provision_request.resource_group,
                        account_name=provision_request.batch_account_name)
        except AzCloudError as err:
            # Return non-azure specific exception instead
            raise tesmodels.CloudError(err)

        return True

    def _create_resource_group(self, credentials, subscription_id, name, location):
        """ Creates requested resource group on Azure """
        resource_client = azresource_mgmt.ResourceManagementClient(credentials, subscription_id)
        return resource_client.resource_groups.create_or_update(
            resource_group_name=name,
            parameters={'location': location}
        )

    def _create_storage_account(self, credentials, subscription_id, resource_group, name, sku, location):
        """ Creates requested storage account on Azure. Returns storage id, a url endpoint and single key """
        from azure.mgmt.storage.models import StorageAccountCreateParameters, Kind, Sku

        storage_client = azstorage_mgmt.StorageManagementClient(credentials, subscription_id)
        storage_async_operation = storage_client.storage_accounts.create(
            resource_group_name=resource_group,
            account_name=name,
            parameters=StorageAccountCreateParameters(
                sku=Sku(name=sku),
                kind=Kind.storage,
                location=location
            )
        )
        storage_account = storage_async_operation.result()
        storage_keys = storage_client.storage_accounts.list_keys(
            resource_group_name=resource_group,
            account_name=name
        )
        return (storage_account.id, storage_account.name, storage_keys.keys[0].value)

    def _create_batch_account(self, credentials, subscription_id, resource_group, name, location, storage_account_id):
        """ Creates requested batch account on Azure. Returns a url endpoint and single key """
        from azure.mgmt.batch.models import BatchAccountCreateParameters, AutoStorageBaseProperties

        batch_client = azbatch_mgmt.BatchManagementClient(credentials, subscription_id)
        batch_async_operation = batch_client.batch_account.create(
            resource_group_name=resource_group,
            account_name=name,
            parameters=BatchAccountCreateParameters(
                location=location,
                auto_storage=AutoStorageBaseProperties(storage_account_id)
            )
        )
        batch_account = batch_async_operation.result()
        keys = batch_client.batch_account.get_keys(
            resource_group_name=resource_group,
            account_name=name
        )
        return (batch_account.name, f'https://{batch_account.account_endpoint}', keys.primary)

    def _try_add_keyvault_config(self, provision_status):
        """ Post secrets to Key Vault if URI in config """
        from tesazure.extensions import key_vault

        if current_app.config.get('KEYVAULT_URL', False):
            keyvault_url = current_app.config['KEYVAULT_URL']
            prefix = current_app.config.get('KEYVAULT_SECRETS_PREFIX', '')

            current_app.logger.info(f'Populating Azure Key Vault ({keyvault_url}) with secrets from provisioning process.')
            key_vault.set(keyvault_url, f'{prefix}BATCH-ACCOUNT-NAME', provision_status.batch_account_name)
            provision_status.batch_account_name = "*******************"
            key_vault.set(keyvault_url, f'{prefix}BATCH-ACCOUNT-URL', provision_status.batch_account_url)
            provision_status.batch_account_url = "*******************"
            key_vault.set(keyvault_url, f'{prefix}BATCH-ACCOUNT-KEY', provision_status.batch_account_key)
            provision_status.batch_account_key = "*******************"
            key_vault.set(keyvault_url, f'{prefix}STORAGE-ACCOUNT-NAME', provision_status.storage_account_name)
            provision_status.storage_account_name = "*******************"
            key_vault.set(keyvault_url, f'{prefix}STORAGE-ACCOUNT-KEY', provision_status.storage_account_key)
            provision_status.storage_account_key = "*******************"
        else:
            current_app.logger.info('Key Vault URL not found in app settings. Skipping adding provisioner results to Key Vault.')
            current_app.logger.info(current_app.config)

    @current_celery_app.task(base=RequestContextTask)
    def _worker_provision_start(id):
        """Provision requested batch cloud resources"""
        def _updateProvisionStatus(provision_request, status):
            """Local helper to serialize the status into the provision_request and save"""
            schema = batchbackendmodels.ProvisionStatusSchema()
            provision_request.status_json = schema.dump(status).data
            provision_request.save()

        current_app.logger.info(f'Worker provisioning batch resources from request id {id}.')

        # Get and validate request from the database
        provision_tracker = tesmodels.ProvisionTracker.get_by_id(id)
        schema = batchbackendmodels.ProvisionRequestSchema()
        provision_request = schema.load(provision_tracker.request_json)
        if len(provision_request.errors) > 0:
            raise ValidationError(provision_request.errors)
        provision_request = provision_request.data

        if not provision_tracker or not provision_request:
            # FIXME: Is there a special not found exception?
            raise Exception('Provision request could not be found')

        # Set initial status
        provision_status = batchbackendmodels.ProvisionStatus()
        provision_status.status = batchbackendmodels.Status.INPROGRESS
        _updateProvisionStatus(provision_tracker, provision_status)

        credentials = azcredentials.ServicePrincipalCredentials(
            client_id=provision_request.service_principal.client_id,
            secret=provision_request.service_principal.secret,
            tenant=provision_request.service_principal.tenant
        )

        # FIXME - move this stuff out of backend or into common
        from tesazure.extensions import compute_backend

        try:
            current_app.logger.debug(f"Creating or updating resource group {provision_request.resource_group} in {provision_request.location}...")
            compute_backend.backend._create_resource_group(credentials, provision_request.subscription_id, provision_request.resource_group, provision_request.location)

            current_app.logger.debug(f"Creating storage account {provision_request.storage_account_name} with SKU {provision_request.storage_sku} in {provision_request.location}...")
            storage_id, provision_status.storage_account_name, provision_status.storage_account_key = \
                compute_backend.backend._create_storage_account(credentials, provision_request.subscription_id, provision_request.resource_group,
                                                                provision_request.storage_account_name, provision_request.storage_sku, provision_request.location)

            current_app.logger.debug(f"Creating batch account {provision_request.batch_account_name} in {provision_request.location}...")
            provision_status.batch_account_name, provision_status.batch_account_url, provision_status.batch_account_key = \
                compute_backend.backend._create_batch_account(credentials, provision_request.subscription_id, provision_request.resource_group,
                                                              provision_request.batch_account_name, provision_request.location, storage_id)

            compute_backend.backend._try_add_keyvault_config(provision_status)
            provision_status.status = batchbackendmodels.Status.CREATED
        except Exception as err:
            current_app.logger.error("Error during batch provisioning process", err)
            provision_status.status = batchbackendmodels.Status.ERROR
            provision_status.error_message = f'Error during batch provisioning process. Error: {err}'
            return
        finally:
            _updateProvisionStatus(provision_tracker, provision_status)

    def provision_start(self, id):
        # Abstract worker from API
        return self._worker_provision_start.delay(str(id))

    def provision_query(self, id):
        """Check status of a given provision tracker"""

        provision_tracker = tesmodels.ProvisionTracker.get_by_id(id)
        if not provision_tracker:
            raise tesmodels.ProvisionTrackerNotFound()

        return provision_tracker.status_json
