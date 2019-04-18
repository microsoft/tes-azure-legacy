# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import json
import os
from tesazure import models


class TestCase:
    def test_tes_task_procedural_build(self, session):
        schema = models.TesTaskSchema()

        # Read a sample task from file
        with open(os.path.join('tests', 'unit', 'data', 'test_models_task.json')) as fh:
            task_json = json.loads(fh.read())
        task_from_file = schema.load(task_json).data

        # Define same task programattically
        tags = {"tag-key": "tag-value"}

        executors = [
            models.TesExecutor(
                image="alpine",
                command=["pwd"]
            ),
            models.TesExecutor(
                image="ubuntu:latest",
                command=["ls", "-l"],
                env={"foo": "bar"},
                workdir="/tes-wd/shared",
                stdout="/tes-wd/shared/executions/stdout.txt",
                stderr="/tes-wd/shared/executions/stderr.txt"
            ),
            models.TesExecutor(
                image="ubuntu@sha256:868fd30a0e47b8d8ac485df174795b5e2fe8a6c8f056cc707b232d65b8a1ab68",
                command=["cat"],
                workdir="/tes-wd/shared",
                stdin="/tes-wd/shared/executions/stdin.txt"
            )
        ]

        resources = models.TesResources(
            cpu_cores=4,
            disk_gb=4,
            preemptible=True,
            ram_gb=7
        )

        inputs = [
            models.TesInput(
                url="https://tesazure.blob.core.windows.net/samples/random.dat",
                path="random.dat",
                description="input-description",
                name="input-name",
                type=models.TesFileType.FILE,
            ),
            models.TesInput(
                path="/tes-wd/shared/script",
                description="Should echo OK",
                content='#!/bin/bash\necho "OK"',
                name="commandScript",
                type=models.TesFileType.FILE
            )
        ]

        outputs = [
            models.TesOutput(
                url="https://tesazure.blob.core.windows.net/samples/random.dat",
                path="random.dat",
                description="output-description",
                name="output-name",
                type=models.TesFileType.FILE
            )
        ]

        task_from_code = models.TesTask(
            name="task-name",
            description="task-description",
            tags=tags,
            executors=executors,
            resources=resources,
            inputs=inputs,
            outputs=outputs
        )

        # Ensure they are equivalent
        assert(schema.dump(task_from_code).data == schema.dump(task_from_file).data)

    def test_tes_task_hybrid_cols(self, session):
        """
        Ensures that hybrid properties stored as top-level JSON properties (e.g. state) are properly serialized upon mutation
        """
        schema = models.TesTaskSchema()

        # Read a sample task from file
        with open(os.path.join('tests', 'unit', 'data', 'test_models_task.json')) as fh:
            task_json = json.loads(fh.read())
        mem_task = schema.load(task_json).data
        mem_task.state = models.TaskStatus.CANCELED

        task = schema.load(task_json).data
        task.backend_id = 'foo'
        session.add(task)
        session.commit()

        task.state = models.TaskStatus.CANCELED
        session.add(task)
        session.commit()

        refreshed_task = models.TesTask.get_by_id(str(task.id))

        # Ensure change persisted in memory copy
        assert(mem_task.state == models.TaskStatus.CANCELED)

        # Ensure change persisted in local copy after save
        assert(task.state == models.TaskStatus.CANCELED)

        # Ensure change persisted in refreshed copy
        assert(refreshed_task.state == models.TaskStatus.CANCELED)

    def test_tes_task_hybrid_cols_nested(self, session):
        """
        Ensures that nested values in JSON structure are properly serialized upon mutation
        """
        schema = models.TesTaskSchema()

        # Read a sample task from file
        with open(os.path.join('tests', 'unit', 'data', 'test_models_task.json')) as fh:
            task_json = json.loads(fh.read())
        mem_task = schema.load(task_json).data
        mem_task.tags['foo'] = 'bar'

        task = schema.load(task_json).data
        task.tags['foo'] = 'bar'
        task.backend_id = 'foo'
        session.add(task)
        session.commit()

        task.state = models.TaskStatus.CANCELED
        session.add(task)
        session.commit()

        refreshed_task = models.TesTask.get_by_id(str(task.id))

        expected_tags = {'tag-key': 'tag-value', 'foo': 'bar'}

        # Ensure change persisted in memory copy
        assert(mem_task.tags == expected_tags)

        # Ensure change persisted in local copy after save
        assert(task.tags == expected_tags)

        # Ensure change persisted in refreshed copy
        assert(refreshed_task.tags == expected_tags)
