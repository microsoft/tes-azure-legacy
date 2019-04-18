# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from types import SimpleNamespace
import pytest
import uuid

import azure.batch as azbatch
from tesazure import models
from tesazure.backends.batch import models as batchbackendmodels
from tesazure.extensions import compute_backend


def setup_common_mocks_for_create(mocker):
    """
    Boilerplate for most of the test_create_* methods
    """
    mocked_batch_client = mocker.patch('azure.batch.batch_service_client.BatchServiceClient')
    mocked_batch_client.return_value.job.list.return_value = []
    mocked_blob_client = mocker.patch('azure.storage.blob.BlockBlobService')  # noqa: F841
    mocked_files_client = mocker.patch('azure.storage.file.FileService')  # noqa: F841
    return (mocked_batch_client, mocked_blob_client, mocked_files_client)


def setup_common_mocks_for_provision(mocker):
    """
    Boilerplate for most of the test_provision_* methods
    """
    mocked_credentials = mocker.patch('azure.common.credentials.ServicePrincipalCredentials')
    mocked_resource_mgmt = mocker.patch('azure.mgmt.resource.ResourceManagementClient')
    mocked_storage_mgmt = mocker.patch('azure.mgmt.storage.StorageManagementClient')
    mocked_batch_mgmt = mocker.patch('azure.mgmt.batch.BatchManagementClient')
    spn = batchbackendmodels.ServicePrincipal("client_id", "secret", "tenant")
    return (mocked_credentials, mocked_resource_mgmt, mocked_storage_mgmt, mocked_batch_mgmt, spn)


@pytest.mark.options(COMPUTE_BACKEND='batch')
class TestCase:
    @pytest.mark.options(BATCH_OVERRIDE_POOL_ID='example-pool-id')
    def test_initialize_pool_hardcode(self, app, mocker):
        """
        Verifies hardcoded pool option does not call Batch service
        """
        mocked_batch_client = mocker.patch('azure.batch.batch_service_client.BatchServiceClient')
        mocked_files_client = mocker.patch('azure.storage.file.FileService')
        assert(mocked_files_client.return_value.create_share.call_count == 0)
        assert(mocked_batch_client.return_value.pool.add.call_count == 0)

    def test_initialize_pool(self, app, mocker):
        """
        Verifies Batch pool is created upon request
        """
        mocked_batch_client = mocker.patch('azure.batch.batch_service_client.BatchServiceClient')
        mocked_files_client = mocker.patch('azure.storage.file.FileService')
        compute_backend.backend._initializePool('Standard_A1_v2')
        assert(mocked_files_client.return_value.create_share.call_count == 1)
        assert(mocked_batch_client.return_value.pool.add.call_count == 1)

    @pytest.mark.options(BATCH_NODE_ADMIN_USERNAME='adminuser')
    @pytest.mark.options(BATCH_NODE_ADMIN_PASSWORD='adminpw!')
    def test_initialize_pool_with_admin(self, app, mocker):
        """
        Verifies admin user is added when config options are set
        """
        mocked_batch_client = mocker.patch('azure.batch.batch_service_client.BatchServiceClient')
        mocked_files_client = mocker.patch('azure.storage.file.FileService')
        compute_backend.backend._initializePool('Standard_A1_v2')

        args, kwargs = mocked_batch_client.return_value.pool.add.call_args
        user_accounts = args[0].user_accounts
        admin_account = user_accounts[0]
        assert(isinstance(admin_account, azbatch.models.UserAccount))
        assert(admin_account.elevation_level == azbatch.models.ElevationLevel.admin)
        assert(admin_account.name == 'adminuser')
        assert(admin_account.password == 'adminpw!')
        assert(mocked_files_client.return_value.create_share.call_count == 1)
        assert(mocked_batch_client.return_value.pool.add.call_count == 1)

    @pytest.mark.options(PRIVATE_DOCKER_REGISTRY_URL='foo.azurecr.io')
    @pytest.mark.options(PRIVATE_DOCKER_REGISTRY_USERNAME='adminuser')
    @pytest.mark.options(PRIVATE_DOCKER_REGISTRY_PASSWORD='adminpw!')
    def test_initialize_pool_with_private_acr(self, app, mocker):
        """
        Verifies private docker registry is added when config options are set
        """
        mocked_batch_client = mocker.patch('azure.batch.batch_service_client.BatchServiceClient')
        mocked_files_client = mocker.patch('azure.storage.file.FileService')

        compute_backend.backend._initializePool('Standard_A1_v2')

        args, kwargs = mocked_batch_client.return_value.pool.add.call_args
        vm_config = args[0].virtual_machine_configuration
        container_config = vm_config.container_configuration
        container_registry = container_config.container_registries[0]
        assert(isinstance(container_registry, azbatch.models.ContainerRegistry))
        assert(container_registry.registry_server == 'foo.azurecr.io')
        assert(container_registry.user_name == 'adminuser')
        assert(container_registry.password == 'adminpw!')
        assert(mocked_files_client.return_value.create_share.call_count == 1)
        assert(mocked_batch_client.return_value.pool.add.call_count == 1)

    def test_create_job_exists(self, app, mocker):
        """
        Verifies failure when job ID already exists in Batch account
        """
        hardcoded_uuid = 'b95e3451-5cd0-4e46-b595-6e8b0bb9bb62'
        returned_uuids = [uuid.UUID(hardcoded_uuid)]

        mocked_batch_client, mocked_blob_client, mocked_file_client = setup_common_mocks_for_create(mocker)
        mocked_batch_client.return_value.job.list.return_value = [azbatch.models.CloudJob(id=hardcoded_uuid)]
        mock_uuid = mocker.patch('tesazure.backends.batch.uuid.uuid4', autospec=True)
        mock_uuid.side_effect = returned_uuids

        task = models.TesTask()
        result = compute_backend.backend.createJob(task)

        assert(result is False)
        assert(mocked_blob_client.return_value.create_container.call_count == 0)
        assert(mocked_batch_client.return_value.job.add.call_count == 0)

    def test_create_input_url(self, app, mocker):
        """
        Verifies prep task is added without using temporary blob when URL input
        is provided
        """
        mocked_batch_client, mocked_blob_client, mocked_file_client = setup_common_mocks_for_create(mocker)

        task = models.TesTask(
            name="task-name",
            description="task-description",
            inputs=[
                models.TesInput(
                    url="https://tesazure.blob.core.windows.net/samples/random.dat",
                    path="random.dat",
                    description="input-description",
                    name="input-name",
                    type=models.TesFileType.FILE,
                )
            ]
        )
        result = compute_backend.backend.createJob(task)

        assert(uuid.UUID(result))
        assert(mocked_blob_client.return_value.create_container.call_count == 1)
        assert(mocked_blob_client.return_value.create_blob_from_text.call_count == 0)
        assert(mocked_batch_client.return_value.job.add.call_count == 1)

        args, kwargs = mocked_batch_client.return_value.job.add.call_args
        job_preparation_task = args[0].job_preparation_task
        assert("pipefail" in job_preparation_task.command_line)

    def test_create_input_content(self, app, mocker):
        """
        Verifies temporary blob is created & corresponding prep task added when
        URL input is provided
        """
        mocked_batch_client, mocked_blob_client, mocked_file_client = setup_common_mocks_for_create(mocker)
        mocked_blob_client.return_value.make_blob_url.side_effect = ["https://account.blob.core.windows.net/container/blob"]

        task = models.TesTask(
            name="task-name",
            description="task-description",
            inputs=[
                models.TesInput(
                    path="/tes-wd/shared/script",
                    description="Should echo OK",
                    content='#!/bin/bash\necho "OK"',
                    name="commandScript",
                    type=models.TesFileType.FILE
                )
            ]
        )
        result = compute_backend.backend.createJob(task)

        assert(uuid.UUID(result))
        assert(mocked_blob_client.return_value.create_container.call_count == 1)
        assert(mocked_blob_client.return_value.create_blob_from_text.call_count == 1)
        assert(mocked_batch_client.return_value.job.add.call_count == 1)

        args, kwargs = mocked_batch_client.return_value.job.add.call_args
        job_preparation_task = args[0].job_preparation_task
        assert("pipefail" in job_preparation_task.command_line)

    def test_create_output_url_no_input(self, app, mocker):
        """
        Verifies stub prep task is used when outputs are present without inputs
        """
        mocked_batch_client, mocked_blob_client, mocked_file_client = setup_common_mocks_for_create(mocker)

        task = models.TesTask(
            name="task-name",
            description="task-description",
            outputs=[
                models.TesOutput(
                    url="https://tesazure.blob.core.windows.net/samples/random.dat",
                    path="random.dat",
                    description="output-description",
                    name="output-name",
                    type=models.TesFileType.FILE
                )
            ]
        )
        result = compute_backend.backend.createJob(task)

        assert(uuid.UUID(result))
        assert(mocked_blob_client.return_value.create_container.call_count == 1)
        assert(mocked_batch_client.return_value.job.add.call_count == 1)

        args, kwargs = mocked_batch_client.return_value.job.add.call_args
        batch_job = args[0]
        assert("true" in batch_job.job_preparation_task.command_line)
        assert("pipefail" in batch_job.job_release_task.command_line)

    def test_create_no_marshalling(self, app, mocker):
        """
        Verifies no prep/release tasks are used if not inputs or outputs are
        provided
        """
        mocked_batch_client, mocked_blob_client, mocked_file_client = setup_common_mocks_for_create(mocker)

        task = models.TesTask(
            name="task-name",
            description="task-description",
            inputs=[],
            outputs=[]
        )
        result = compute_backend.backend.createJob(task)

        assert(uuid.UUID(result))
        assert(mocked_batch_client.return_value.job.add.call_count == 1)

        args, kwargs = mocked_batch_client.return_value.job.add.call_args
        batch_job = args[0]
        assert("true" in batch_job.job_preparation_task.command_line)
        assert(batch_job.job_release_task is None)

    def test_multiple_executors(self, app, mocker):
        """
        Verifies task is added for each executor
        """
        mocked_batch_client, mocked_blob_client, mocked_file_client = setup_common_mocks_for_create(mocker)

        task = models.TesTask(
            name="task-name",
            description="task-description",
            executors=[
                models.TesExecutor(
                    image="alpine",
                    command=["pwd"]
                ),
                models.TesExecutor(
                    image="ubuntu:latest",
                    command=["ls", "-l"],
                    workdir="/tes-wd/shared",
                ),
                models.TesExecutor(
                    image="ubuntu@sha256:868fd30a0e47b8d8ac485df174795b5e2fe8a6c8f056cc707b232d65b8a1ab68",
                    command=["ls -l"],
                    workdir="/tes-wd",
                )
            ]
        )
        result = compute_backend.backend.createJob(task)

        assert(uuid.UUID(result))
        assert(mocked_batch_client.return_value.job.add.call_count == 1)
        assert(mocked_batch_client.return_value.task.add.call_count == len(task.executors))

    def test_create_executor_environment(self, app, mocker):
        """
        Verifies environment variables are mapped to tasks
        """
        environ = {"foo": "bar"}

        mocked_batch_client, mocked_blob_client, mocked_file_client = setup_common_mocks_for_create(mocker)

        task = models.TesTask(
            name="task-name",
            description="task-description",
            executors=[
                models.TesExecutor(
                    image="ubuntu:latest",
                    command=["ls", "-l"],
                    env=environ,
                )
            ]
        )
        result = compute_backend.backend.createJob(task)

        assert(uuid.UUID(result))
        # ensure env mappings are present
        args, kwargs = mocked_batch_client.return_value.task.add.call_args
        batch_task = kwargs['task']
        assert(isinstance(batch_task, azbatch.models.TaskAddParameter))
        assert(batch_task.environment_settings == [azbatch.models.EnvironmentSetting(name=k, value=v) for k, v in environ.items()])

    def test_create_executor_output_streams(self, app, mocker):
        """
        Verifies presence of output stream mapping in executor causes adds an
        additional task to handle stream copy
        """
        mocked_batch_client, mocked_blob_client, mocked_file_client = setup_common_mocks_for_create(mocker)

        task = models.TesTask(
            name="task-name",
            description="task-description",
            executors=[
                models.TesExecutor(
                    image="ubuntu:latest",
                    command=["ls", "-l"],
                    stdout="/tes-wd/shared/executions/stdout.txt",
                    stderr="/tes-wd/shared/executions/stderr.txt"
                ),
                models.TesExecutor(
                    image="ubuntu:latest",
                    command=["ls", "-l"],
                    stdout="/tes-wd/shared/executions/stdout.txt",
                    stderr="/tes-wd/shared/executions/stderr.txt"
                )
            ]
        )
        result = compute_backend.backend.createJob(task)

        assert(uuid.UUID(result))
        assert(mocked_batch_client.return_value.job.add.call_count == 1)
        assert(mocked_batch_client.return_value.task.add.call_count == len(task.executors))

    def test_provision_check_validate_availability(self, app, mocker):
        """
        Tests provision check to ensure it's validating resource group, storage account, batch account
        are available to be used.
        """
        mocked_credentials, mocked_resource_mgmt, mocked_storage_mgmt, mocked_batch_mgmt, spn = setup_common_mocks_for_provision(mocker)

        # Easy path - nothing exists
        mocked_resource_mgmt.return_value.resource_groups.check_existence.return_value = False
        mocked_storage_mgmt.return_value.storage_accounts.check_name_availability.name_available.return_value = True
        mocked_batch_mgmt.return_value.location.check_name_availability.name_available.return_value = True

        request = batchbackendmodels.ProvisionRequest(spn, "sub_id")
        result = compute_backend.backend.provision_check(request)

        assert(result)
        assert(mocked_credentials.call_count == 1)
        assert(mocked_resource_mgmt.return_value.resource_groups.check_existence.call_count == 1)
        assert(mocked_resource_mgmt.return_value.resource_groups.get.call_count == 0)
        assert(mocked_storage_mgmt.return_value.storage_accounts.check_name_availability.call_count == 1)
        assert(mocked_storage_mgmt.return_value.storage_accounts.get_properties.call_count == 0)
        assert(mocked_batch_mgmt.return_value.location.check_name_availability.call_count == 1)
        assert(mocked_batch_mgmt.return_value.batch_account.get.call_count == 0)

    def test_provision_check_validate_existing_resources(self, app, mocker):
        """
        Tests provision check to ensure already existing resources (resource group, storage account, batch account)
        are accessible by the supplied subscription.
        """
        mocked_credentials, mocked_resource_mgmt, mocked_storage_mgmt, mocked_batch_mgmt, spn = setup_common_mocks_for_provision(mocker)

        mocked_resource_mgmt.return_value.resource_groups.check_existence.return_value = True
        mocked_resource_mgmt.return_value.resource_groups.get.return_value.__enter__.return_value = SimpleNamespace(location="westus2")
        mocked_storage_mgmt.return_value.storage_accounts.check_name_availability.return_value = SimpleNamespace(name_available=False, reason='AlreadyExists')
        mocked_batch_mgmt.return_value.location.check_name_availability.return_value = SimpleNamespace(name_available=False, reason=SimpleNamespace(value='AlreadyExists'))

        request = batchbackendmodels.ProvisionRequest(service_principal=spn, subscription_id="sub_id", location="westus2")
        result = compute_backend.backend.provision_check(request)

        assert(result)
        assert(mocked_credentials.call_count == 1)
        assert(mocked_resource_mgmt.return_value.resource_groups.check_existence.call_count == 1)
        assert(mocked_resource_mgmt.return_value.resource_groups.get.call_count == 1)
        assert(mocked_storage_mgmt.return_value.storage_accounts.check_name_availability.call_count == 1)
        assert(mocked_storage_mgmt.return_value.storage_accounts.get_properties.call_count == 1)
        assert(mocked_batch_mgmt.return_value.location.check_name_availability.call_count == 1)
        assert(mocked_batch_mgmt.return_value.batch_account.get.call_count == 1)

    def test_provision_start_provisions_and_updates_status(self, app, mocker, session):
        """
        Tests provision start to ensure proper provision endpoints are called
        """
        # insert fake data into the database (after adding required data)
        spn = batchbackendmodels.ServicePrincipal("client_id", "secret", "tenant")
        request = batchbackendmodels.ProvisionRequest(service_principal=spn, subscription_id="sub_id", location="westus2")
        request_schema = batchbackendmodels.ProvisionRequestSchema()
        provision = models.ProvisionTracker(request_json=request_schema.dump(request).data)
        session.add(provision)
        session.commit()

        mocker.patch('azure.common.credentials.ServicePrincipalCredentials')
        mocked_rg_creator = mocker.patch.object(compute_backend.backend, "_create_resource_group")
        mocked_storage_creator = mocker.patch.object(compute_backend.backend, '_create_storage_account')
        mocked_batch_creator = mocker.patch.object(compute_backend.backend, '_create_batch_account')
        mocked_keyvault_config = mocker.patch.object(compute_backend.backend, '_try_add_keyvault_config')

        mocked_storage_creator.return_value = ("storage_id", "storage", "storagekey")
        mocked_batch_creator.return_value = ("batchname", "http://batch", "batchkey")

        # Calling the Celery task directly, API endpoint is passthrough
        compute_backend.backend._worker_provision_start(str(provision.id))

        # Test provision methods called
        assert(mocked_rg_creator.call_count == 1)
        assert(mocked_storage_creator.call_count == 1)
        assert(mocked_batch_creator.call_count == 1)
        assert(mocked_keyvault_config.call_count == 1)

        # Ensure the status object was updated in the database
        test_provision = models.ProvisionTracker.get_by_id(str(provision.id))
        status_schema = batchbackendmodels.ProvisionStatusSchema()
        test_provision_status = status_schema.load(test_provision.status_json).data
        assert(test_provision_status.status == batchbackendmodels.Status.CREATED)
        assert(test_provision_status.storage_account_name == "storage")
        assert(test_provision_status.storage_account_key == "storagekey")
        assert(test_provision_status.batch_account_name == "batchname")
        assert(test_provision_status.batch_account_url == "http://batch")
        assert(test_provision_status.batch_account_key == "batchkey")

    def test_provision_query_returns_provision_tracker(self, app, session):
        """
        Tests provision query to ensure the proper object is returned
        """
        # insert fake data into the database (after adding required data)
        spn = batchbackendmodels.ServicePrincipal("client_id", "secret", "tenant")
        request = batchbackendmodels.ProvisionRequest(service_principal=spn, subscription_id="sub_id")
        request_schema = batchbackendmodels.ProvisionRequestSchema()
        status = batchbackendmodels.ProvisionStatus(status=batchbackendmodels.Status.CREATED)
        status_schema = batchbackendmodels.ProvisionStatusSchema()
        provision = models.ProvisionTracker(request_json=request_schema.dump(request).data, status_json=status_schema.dump(status).data)
        session.add(provision)
        session.commit()

        # Test returned from DB value
        test_status = compute_backend.backend.provision_query(str(provision.id))
        assert(status_schema.dump(status).data == test_status)

    def test_provision_query_raises_not_found(self, app):
        """
        Tests provision query to ensure the proper exception is raised if not found
        """
        # Test returned from DB value
        with pytest.raises(models.ProvisionTrackerNotFound):
            compute_backend.backend.provision_query(str("not-found-uuid"))
