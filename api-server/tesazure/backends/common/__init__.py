# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import datetime
import pathlib
import re
import uuid
from abc import ABC, abstractmethod

import azure.storage.blob as azblob
import azure.storage.common as azstorage
from flask import current_app
from tesazure import models as tesmodels
from . import commands  # noqa: F401


class AbstractComputeBackend(ABC):
    """Abstract class that specifies methods required for compute backend plugins"""

    @abstractmethod
    def create_task(self, task):
        """Create a new task"""
        pass

    @abstractmethod
    def get_task(self, task_id):
        """Get details on existing task"""
        pass

    @abstractmethod
    def list_tasks(self):
        """List all known tasks"""
        pass

    @abstractmethod
    def service_info(self, debug=False):
        """
        Get service details and capacity availability. Implementation gets
        merged with API's defaults, overriding keys if there is overlap.
        """
        {}

    @abstractmethod
    def cancel_task(self, task_id):
        """Cancel an existing task"""
        pass

    @abstractmethod
    def configure(self):
        """Configure the backend to be ready to accept tasks"""
        pass


def determine_azure_vm_for_task(tes_resources, fallback_cpu_cores=1, fallback_mem_GiB=2, fallback_disk_GiB=10):
    GbToGib = 1000**3 / 1024**3
    cpu_cores = tes_resources.cpu_cores or fallback_cpu_cores
    mem_GiB = tes_resources.ram_gb * GbToGib or fallback_mem_GiB
    disk_GiB = tes_resources.disk_gb * GbToGib or fallback_disk_GiB
    low_prio = tes_resources.preemptible is True  # noqa: F841
    # TODO: support 'zones'

    vms_by_preference = [
        {'sku': 'Standard_A1_v2', 'cpu': 1, 'mem': 2, 'disk': 10, 'ssd': True},
        {'sku': 'Standard_A2m_v2', 'cpu': 2, 'mem': 16, 'disk': 20, 'ssd': True},
        {'sku': 'Standard_A2_v2', 'cpu': 2, 'mem': 4, 'disk': 20, 'ssd': True},
        {'sku': 'Standard_A4m_v2', 'cpu': 4, 'mem': 32, 'disk': 40, 'ssd': True},
        {'sku': 'Standard_A4_v2', 'cpu': 4, 'mem': 8, 'disk': 40, 'ssd': True},
        {'sku': 'Standard_A8m_v2', 'cpu': 8, 'mem': 64, 'disk': 80, 'ssd': True},
        {'sku': 'Standard_A8_v2', 'cpu': 8, 'mem': 16, 'disk': 80, 'ssd': True},
        {'sku': 'Standard_D2_v3', 'cpu': 2, 'mem': 8, 'disk': 50, 'ssd': True},
        {'sku': 'Standard_D4_v3', 'cpu': 4, 'mem': 16, 'disk': 100, 'ssd': True},
        {'sku': 'Standard_D8_v3', 'cpu': 8, 'mem': 32, 'disk': 200, 'ssd': True},
        {'sku': 'Standard_D16_v3', 'cpu': 16, 'mem': 64, 'disk': 400, 'ssd': True},
        {'sku': 'Standard_D32_v3', 'cpu': 32, 'mem': 128, 'disk': 800, 'ssd': True},
        {'sku': 'Standard_D64_v3', 'cpu': 64, 'mem': 256, 'disk': 1600, 'ssd': True},
        {'sku': 'Standard_G1', 'cpu': 2, 'mem': 28, 'disk': 384, 'ssd': True},
        {'sku': 'Standard_G2', 'cpu': 4, 'mem': 56, 'disk': 768, 'ssd': True},
        {'sku': 'Standard_G3', 'cpu': 8, 'mem': 112, 'disk': 1536, 'ssd': True},
        {'sku': 'Standard_G4', 'cpu': 16, 'mem': 224, 'disk': 3072, 'ssd': True},
        {'sku': 'Standard_G5', 'cpu': 32, 'mem': 448, 'disk': 6144, 'ssd': True}
    ]

    remaining_vms = list(filter(lambda vm: vm['cpu'] >= cpu_cores and vm['mem'] >= mem_GiB and vm['disk'] >= disk_GiB, vms_by_preference))
    if remaining_vms:
        return remaining_vms[0]['sku']
    else:
        raise ValueError("No such VM available")


def detect_tags_for_submitter(task):
    """
    Uses properties of the submitted TES task to attempt to identify the
    submitting software, if any.

    Outputs a dict with information about the submitter.
    """
    tags = {}

    # Attempt to detect if Cromwell is submitting this task
    try:
        # Cromwell places workflow UUID in the description
        description_uuid = task.description.split(':')[0]
        uuid.UUID(description_uuid)
    except ValueError:
        description_uuid = False

    # any cromwell task is going to have a 'stderr', 'stdout' and 'rc' output
    output_path_is_url = all([output.path == output.url for output in task.outputs])
    has_rc_output = False
    has_stdout_output = False
    has_stderr_output = False
    match = False
    for output in task.outputs:
        if output.path.endswith('execution/rc'):
            # rc output has crmowell uuid in path
            uuid_regex = "[0-9A-Fa-f]{8}[-][0-9A-Fa-f]{4}[-][0-9A-Fa-f]{4}[-][0-9A-Fa-f]{4}[-][0-9A-Fa-f]{12}"
            match = re.match(rf"/tes-wd(?:/.*)?/([^/]+)/({uuid_regex})/call-([^/]+)(?:/.*)?/execution/rc", output.path)
        has_rc_output = True
        has_stdout_output = has_stdout_output or output.path.endswith('execution/stdout')
        has_stderr_output = has_stderr_output or output.path.endswith('execution/stderr')

    if output_path_is_url and has_rc_output and has_stdout_output and has_stderr_output and match:
        workflow_name, workflow_id, call_name = match.groups()
        # to confirm this isn't a strange coincidence, confirm the UUID in output path for rc matches the description's UUID
        if workflow_id == description_uuid:
            # confirmed cromwell
            current_app.logger.info(f"Detected 'cromwell' as task submitter, task is part of workflow with ID '{workflow_id}'")
            tags['ms-submitter-name'] = 'cromwell'
            tags['ms-submitter-workflow-id'] = workflow_id
            tags['ms-submitter-workflow-name'] = workflow_name
            tags['ms-submitter-workflow-stage'] = call_name
            tags['ms-submitter-cromwell-executiondir'] = str(pathlib.PurePosixPath(output.path).parent)
    return tags


def mangle_task_for_submitter(task):
    """
    Applies transformations for the detected submitter
    """
    if task.tags.get('ms-submitter-name', None) == 'cromwell':
        exec_environ_prefix = '/tes-wd/shared'
        container_name = current_app.config.get('CROMWELL_STORAGE_CONTAINER_NAME', None)
        if not container_name:
            # Setting config key to None creates a storage container per workflow
            # TODO: Document this if/when blobfuse support mounting all containers in an account
            container_name = task.tags.get('ms-submitter-workflow-id', None)

        blob_service = azblob.BlockBlobService(account_name=current_app.config['STORAGE_ACCOUNT_NAME'], account_key=current_app.config['STORAGE_ACCOUNT_KEY'])
        blob_service.create_container(container_name)
        read_sas_token = blob_service.generate_container_shared_access_signature(
            container_name,
            permission=azstorage.models.AccountPermissions.READ,
            expiry=datetime.datetime.utcnow() + datetime.timedelta(hours=48),
        )
        write_sas_token = blob_service.generate_container_shared_access_signature(
            container_name,
            permission=azstorage.models.AccountPermissions.WRITE,
            expiry=datetime.datetime.utcnow() + datetime.timedelta(hours=48),
        )

        replacement_inputs = []
        cromwell_input_filenames = []
        for input in task.inputs:
            if not input.content and input.url == input.path and input.url.startswith(exec_environ_prefix):
                # input is managed by Cromwell, map it to blob container
                # remove execution environment path prefix
                path_parts = pathlib.PurePosixPath(input.path).parts[2:]
                blob_filename = str(pathlib.PurePosixPath(*path_parts))
                input.url = blob_service.make_blob_url(container_name, blob_filename, sas_token=read_sas_token)

                # used to determine which preprocessed files in execution dir do not need injecting
                cromwell_input_filenames.append(str(pathlib.PurePosixPath(input.path).name))
            replacement_inputs.append(input)

        # Some Cromwell commands e.g. write_tsv() write outputs to execution dir on the Cromwell server during preprocessing.
        # These are not passed on to TES inputs, so unless we are using a shared filesystem (i.e. Azure Files) we need to
        execution_dir = task.tags.get('ms-submitter-cromwell-executiondir', None)
        if not execution_dir:
            current_app.logger.warn("ms-submitter-name=cromwell but tag 'ms-submitter-cromwell-executiondir' is missing; skipping automatic upload of Cromwell-preprocessed workflow inputs")
        else:
            # remove execution environment path prefix
            path_parts = pathlib.PurePosixPath(execution_dir).parts[2:]
            blob_execution_dir = str(pathlib.PurePosixPath(*path_parts))
            # do not inject inputs for files present in execution_dir that are already TES tasks inputs
            blobs_to_inject = [blob_path for blob_path in blob_service.list_blob_names(container_name, blob_execution_dir) if str(pathlib.PurePosixPath(blob_path).name) not in cromwell_input_filenames and blob_path != blob_execution_dir]
            for blob_path in blobs_to_inject:
                blob_name = str(pathlib.PurePosixPath(blob_path).name)
                input = tesmodels.TesInput(name=f'injected-{blob_name}', path=str(pathlib.PurePosixPath(execution_dir) / blob_name), url=blob_service.make_blob_url(container_name, blob_path, sas_token=read_sas_token))
                replacement_inputs.append(input)
        task.inputs = replacement_inputs

        replacement_outputs = []
        for output in task.outputs:
            if output.url == output.path and output.path.startswith(exec_environ_prefix):
                # remove execution environment path prefix
                path_parts = pathlib.PurePosixPath(output.path).parts[2:]
                blob_filename = str(pathlib.PurePosixPath(*path_parts))
                output.url = blob_service.make_blob_url(container_name, blob_filename, sas_token=write_sas_token)
            replacement_outputs.append(output)
        task.outputs = replacement_outputs
