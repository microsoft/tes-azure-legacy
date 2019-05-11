# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import datetime
from ..common import AbstractComputeBackend
from ... import models as tesmodels


class MockBackend(AbstractComputeBackend):
    """Mock backend for testing"""

    @property
    def provision_request_schema(self):
        """MarshmallowSchema for backend specific provision request"""
        return None

    def create_task(self, task):
        """Create a new task"""
        return "baz"

    def get_task(self, task_id):
        """Get details on existing task"""
        tes_log = tesmodels.TaskLog()
        tes_log.start_time = datetime.datetime.now()

        executor_log = tesmodels.ExecutorLog(start_time=datetime.datetime.now(), end_time=datetime.datetime.now(), stdout="out", stderr="err")

        tes_log.logs += [executor_log]

        tes_task = tesmodels.TesTask(id=task_id, logs=[tes_log])
        tes_task.creation_time = datetime.datetime.now()
        tes_task.state = tesmodels.TaskStatus.COMPLETE
        return tes_task

    def list_tasks(self):
        """Configure the backend to be ready to accept tasks"""
        return [tesmodels.TesTask(id='foo'), tesmodels.TesTask(id='bar')]

    def service_info(self, debug=False):
        """
        Get service details and capacity availability. Implementation gets
        merged with API's defaults, overriding keys if there is overlap.
        """
        return {
            'doc': "Built by Microsoft - Mock Engine",
        }

    def cancel_task(self, task_id):
        """Cancel an existing task"""
        return "{}"

    def configure(self):
        """Configure the backend to be ready to accept tasks"""
        pass

    ProvisionRequestSchema = None

    def provision_check(self, provision_request):
        """Checks a BatchProvisionRequest object for validity"""
        return True

    def provision_start(self, id):
        """Provision requested cloud resources. Mocks delay to worker."""
        return True

    def provision_query(self, id):
        """Check status of Provisioning of requested cloud resources"""
        return {}
