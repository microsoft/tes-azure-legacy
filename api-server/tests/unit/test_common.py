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
