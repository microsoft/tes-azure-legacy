# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import json
import os
import pytest
import shlex
from marshmallow import ValidationError
from tesazure import models as tesmodels
from tesazure.backends import common


class TestCase:
    def test_output_stream_command_generation(self):
        with open(os.path.join('tests', 'unit', 'data', 'test_common.json')) as fh:
            json_input = fh.read()
            task_json = json.loads(json_input)

        schema = tesmodels.TesTaskSchema()
        task = schema.load(task_json)
        if len(task.errors) > 0:
            raise ValidationError(task.errors)

        src = "/foo/stderr.txt"
        for executor in task.data.executors:
            # we expect a mkdir and cp command for stdout and stderr
            commands = common.commands.generate_copy_commands(src, executor.stderr)
            assert(len(commands) == 2)

            # turn the first pair of commands (stderr) into a list arg form
            mkdir_command, copy_command = [shlex.split(command) for command in commands]

            # validate
            assert(['mkdir', '-p'] == mkdir_command[:2])
            assert(copy_command[0] == 'cp')
            assert(copy_command[1] == '-f')
            assert(src in copy_command[2])
            assert(mkdir_command[2] in copy_command[3])
            assert(copy_command[3] == executor.stderr)

    def test_copy_command_generation_with_dirs(self):
        executor = tesmodels.TesExecutor()
        executor.stderr = '/a/b/c/foo'

        # we expect a mkdir and cp command for stdout and stderr
        commands = common.commands.generate_copy_commands("stderr.txt", executor.stderr)
        assert(len(commands) == 2)

    def test_copy_command_generation_nodirs(self):
        executor = tesmodels.TesExecutor()
        # no directory prefixes on these
        executor.stdout = 'foo'

        # we expect a cp command only, for stdout and stderr
        commands = common.commands.generate_copy_commands("stdout.txt", executor.stdout)
        assert(len(commands) == 1)
        for command in commands:
            assert(command.startswith('cp'))

    def test_vm_sizing(self):
        """Ensures we are returning the appropriate VM size given some TES constraints"""
        assert(common.determine_azure_vm_for_task(tesmodels.TesResources()) == 'Standard_A1_v2')
        assert(common.determine_azure_vm_for_task(tesmodels.TesResources(cpu_cores=64)) == 'Standard_D64_v3')
        assert(common.determine_azure_vm_for_task(tesmodels.TesResources(cpu_cores=32, ram_gb=384)) == 'Standard_G5')
        assert(common.determine_azure_vm_for_task(tesmodels.TesResources(ram_gb=256)) == 'Standard_D64_v3')
        assert(common.determine_azure_vm_for_task(tesmodels.TesResources(disk_gb=6144)) == 'Standard_G5')
        pytest.raises(ValueError, common.determine_azure_vm_for_task, tesmodels.TesResources(disk_gb=10000))

    def test_submitter_detection_none(self):
        with open(os.path.join('tests', 'unit', 'data', 'test_models_task.json')) as fh:
            task_json = json.loads(fh.read())

        schema = tesmodels.TesTaskSchema()
        task = schema.load(task_json)
        if len(task.errors) > 0:
            raise ValidationError(task.errors)
        tags = common.detect_tags_for_submitter(task.data)

        assert(tags == {})

    def test_submitter_detection_cromwell(self):
        with open(os.path.join('tests', 'unit', 'data', 'test_submitter_detection-cromwell.json')) as fh:
            task_json = json.loads(fh.read())

        schema = tesmodels.TesTaskSchema()
        task = schema.load(task_json)
        if len(task.errors) > 0:
            raise ValidationError(task.errors)
        tags = common.detect_tags_for_submitter(task.data)

        assert(tags.get('ms-submitter-name', None) == 'cromwell')
        assert(tags.get('ms-submitter-workflow-id', None) == '0911c1c7-de5d-442f-94e8-31814a035f8c')
        assert(tags.get('ms-submitter-workflow-name', None) == 'wf_hello')
        assert(tags.get('ms-submitter-workflow-stage', None) == 'hello')
        assert(tags.get('ms-submitter-cromwell-executiondir', None) == '/tes-wd/shared/wf_hello/0911c1c7-de5d-442f-94e8-31814a035f8c/call-hello/execution')

    def test_submitter_detection_cromwell_composite(self):
        """Cromwell tasks whose inputs are composed of other tasks' outputs have nested directories after the 'call-Foo' folder"""
        with open(os.path.join('tests', 'unit', 'data', 'test_submitter_detection-cromwell_composite.json')) as fh:
            task_json = json.loads(fh.read())

        schema = tesmodels.TesTaskSchema()
        task = schema.load(task_json)
        if len(task.errors) > 0:
            raise ValidationError(task.errors)
        tags = common.detect_tags_for_submitter(task.data)

        assert(tags.get('ms-submitter-name', None) == 'cromwell')
        assert(tags.get('ms-submitter-workflow-id', None) == '600f4b49-aefd-41fc-9797-94e5b781b0bb')
        assert(tags.get('ms-submitter-workflow-name', None) == 'MultiStep')
        assert(tags.get('ms-submitter-workflow-stage', None) == 'SliceBytes')
        assert(tags.get('ms-submitter-cromwell-executiondir', None) == '/tes-wd/shared/MultiStep/600f4b49-aefd-41fc-9797-94e5b781b0bb/call-SliceBytes/shard-1/execution')

    def test_task_mangling_cromwell(self, mocker):
        mocked_blob_client = mocker.patch('azure.storage.blob.BlockBlobService')

        task = tesmodels.TesTask(
            inputs=[
                tesmodels.TesInput(name='outside_prefix', path='/foo', url='https://other-source', type=tesmodels.TesFileType.FILE),
                tesmodels.TesInput(name='within_prefix-nested', path='/tes-wd/shared/foo/bar', url='/tes-wd/shared/foo/bar', type=tesmodels.TesFileType.FILE),
                tesmodels.TesInput(name='within_prefix-global', path='/tes-wd/shared-global/foo/bar', url='/tes-wd/shared-global/foo/bar', type=tesmodels.TesFileType.FILE),
                tesmodels.TesInput(name='external_source', path='/tes-wd/shared/other/source', url='https://other-source', type=tesmodels.TesFileType.FILE),
                tesmodels.TesInput(name='external_source_global', path='/tes-wd/shared-global/other/source', url='https://other-source', type=tesmodels.TesFileType.FILE),
                tesmodels.TesInput(name='raw_content', path='/tes-wd/shared/raw', content='raw_content', type=tesmodels.TesFileType.FILE),
            ],
            outputs=[
                tesmodels.TesOutput(name='outside_prefix', path='/tes-wd/foo', url='/tes-wd/foo', type=tesmodels.TesFileType.FILE),
                tesmodels.TesOutput(name='within_prefix-nested', path='/tes-wd/shared/foo/bar', url='/tes-wd/shared/foo/bar', type=tesmodels.TesFileType.FILE),
                tesmodels.TesOutput(name='within_prefix-global', path='/tes-wd/shared-global/foo/bar', url='/tes-wd/shared-global/foo/bar', type=tesmodels.TesFileType.FILE),
                tesmodels.TesOutput(name='external_source', path='/tes-wd/shared-global/other/source', url='https://other-source', type=tesmodels.TesFileType.FILE),
            ],
            tags={
                'ms-submitter-name': 'cromwell',
                'ms-submitter-workflow-id': '0911c1c7-de5d-442f-94e8-31814a035f8c',
                'ms-submitter-workflow-name': 'wf_hello',
                'ms-submitter-workflow-stage': 'hello',
                'ms-submitter-cromwell-executiondir': '/tes-wd/shared/wf_hello/0911c1c7-de5d-442f-94e8-31814a035f8c/call-hello/execution'
            }
        )

        mocked_blob_client.return_value.make_blob_url.return_value = "http://account.blob.core.windows.net/foo/bar"
        mocked_blob_client.return_value.list_blob_names.return_value = [
            task.tags.get('ms-submitter-cromwell-executiondir') + '/foo',  # this is will get uploaded (since input 'foo' above is not from cromwell)
            task.tags.get('ms-submitter-cromwell-executiondir') + '/bar',  # this is will get ignored (since input '/tes-wd/shared/bar' above already exists from cromwell)
            task.tags.get('ms-submitter-cromwell-executiondir') + '/write_tsv'  # this is will get uploaded (since it matches no cromwell inputs above)
        ]

        orig_num_inputs = len(task.inputs)
        common.mangle_task_for_submitter(task)

        assert(mocked_blob_client.return_value.create_container.call_count == 1)
        assert(mocked_blob_client.return_value.list_blob_names.call_count == 1)
        assert(mocked_blob_client.return_value.generate_container_shared_access_signature.call_count == 2)
        # Two for mangled inputs, two for mangled output, two for injected
        assert(mocked_blob_client.return_value.make_blob_url.call_count == 2 + 2 + 2)

        # outside prefix should not be mangled, even if it otherwise matches
        assert(task.inputs[0].name == 'outside_prefix' and task.inputs[0].path == '/foo' and task.inputs[0].url == 'https://other-source')
        assert(task.outputs[0].name == 'outside_prefix' and task.outputs[0].path == task.outputs[0].url)

        # within prefix should be mangled
        assert(task.inputs[1].name == 'within_prefix-nested' and task.inputs[1].path != task.inputs[1].url)
        assert(task.inputs[2].name == 'within_prefix-global' and task.inputs[2].path != task.inputs[2].url)
        assert(task.outputs[1].name == 'within_prefix-nested' and task.outputs[1].path != task.outputs[1].url)
        assert(task.outputs[2].name == 'within_prefix-global' and task.outputs[2].path != task.outputs[2].url)

        # external sources should not be modified
        assert(task.inputs[3].name == 'external_source' and task.inputs[3].path == '/tes-wd/shared/other/source' and task.inputs[3].url == 'https://other-source')
        assert(task.inputs[4].name == 'external_source_global' and task.inputs[4].path == '/tes-wd/shared-global/other/source' and task.inputs[4].url == 'https://other-source')
        assert(task.outputs[3].name == 'external_source' and task.outputs[3].url == 'https://other-source')

        # raw content should be ignored
        assert(task.inputs[5].name == 'raw_content' and not task.inputs[5].url)

        # raw content should be ignored
        assert(task.inputs[5].name == 'raw_content' and not task.inputs[5].url)

        # injected
        assert(len(task.inputs) == orig_num_inputs + 2)
        assert(task.inputs[-2].path == task.tags.get('ms-submitter-cromwell-executiondir') + '/foo')
        assert(task.inputs[-1].path == task.tags.get('ms-submitter-cromwell-executiondir') + '/write_tsv')
