# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import pytest
from datetime import datetime, timedelta

from tesazure import jobs
from tesazure.models import TaskStatus, TesTask


@pytest.mark.options(COMPUTE_BACKEND='mock')
@pytest.mark.options(TASK_BACKEND_CLEANUP_HOURS=24)
@pytest.mark.options(TASK_DATABASE_CLEANUP_HOURS=48)
@pytest.mark.options(TASK_EXECUTION_TIMEOUT_HOURS=12)
class TestCase:
    @pytest.mark.options(TASK_BACKEND_CLEANUP_HOURS=24)
    @pytest.mark.options(TASK_DATABASE_CLEANUP_HOURS=23)
    def test_scheduler_enforces_cleanup_order(self, app):
        """
        The reaper currently requires the database cleanup to be further in the future than the backend cleanup
        (it's hard to clean the backend when the record doesn't exist in the db). This test confirms this constraint.
        """
        with pytest.raises(Exception):
            jobs.cleanup_tasks()

    @pytest.mark.options(TASK_BACKEND_CLEANUP_HOURS=24)
    def test_reap_from_backend(self, session, mocker):
        """Tests removal of TesTask from backend after specified expiration in TASK_BACKEND_CLEANUP_HOURS"""
        # Setup task in db created so it will get reaped in backend
        task = TesTask()
        task.backend_id = "test-backend-reap-id"
        task.updated_ts = datetime.utcnow() - timedelta(hours=25)
        session.add(task)
        session.commit()

        mock_backend_get_task = mocker.patch('tesazure.backends.mock.MockBackend.get_task')
        mock_backend_cancel_task = mocker.patch('tesazure.backends.mock.MockBackend.cancel_task')

        jobs.cleanup_tasks()

        # Task was confirmed to exist in backend and cancelled
        assert(mock_backend_get_task.call_count == 1)
        assert(mock_backend_cancel_task.call_count == 1)

    @pytest.mark.options(TASK_DATABASE_CLEANUP_HOURS=48)
    def test_reap_from_database(self, session):
        """Tests removal of TesTask from database after specified expiration in TASK_DATABASE_CLEANUP_HOURS"""

        # Setup task in db created so it will get reaped in db
        task = TesTask()
        task.backend_id = "test-database-reap-id"
        task.updated_ts = datetime.utcnow() - timedelta(hours=49)
        session.add(task)
        session.commit()
        id = task.id

        jobs.cleanup_tasks()

        # Task was pruned from db
        assert(TesTask().get_by_id(str(id)) is None)

    @pytest.mark.options(TASK_EXECUTION_TIMEOUT_HOURS=12)
    def test_cancel_long_running_task(self, session, mocker):
        """Tests cancellation of task running longer than specified timeout in TASK_EXECUTION_TIMEOUT_HOURS"""
        # Setup task in db created so it will get canceled
        task = TesTask()
        task.backend_id = "test-timeout-id"
        task.state = TaskStatus.RUNNING
        task.updated_ts = datetime.utcnow() - timedelta(hours=13)
        session.add(task)
        session.commit()
        id = task.id

        mock_backend_get_task = mocker.patch('tesazure.backends.mock.MockBackend.get_task')
        mock_backend_get_task.return_value = True
        mock_backend_cancel_task = mocker.patch('tesazure.backends.mock.MockBackend.cancel_task')

        jobs.cleanup_tasks()

        # Task was confirmed to exist in backend then cancelled
        assert(mock_backend_get_task.call_count == 1)
        assert(mock_backend_cancel_task.call_count == 1)
        assert(TesTask.get_by_id(str(id)).state == TaskStatus.CANCELED)

    def test_update_orphaned_task(self, session, mocker):
        """Updates status of task database to CANCELED when it's an orphan (doesn't exist in backend) """
        # Setup task in db created so it will get canceled
        task = TesTask()
        task.backend_id = "test-orphan-id"
        task.state = TaskStatus.RUNNING
        session.add(task)
        session.commit()
        id = task.id

        mock_backend_get_task = mocker.patch('tesazure.backends.mock.MockBackend.get_task')
        mock_backend_get_task.return_value = False

        jobs.cleanup_tasks()

        # Task was attempted to be retrieved (which failed), and then flagged as UNKNOWN
        assert(mock_backend_get_task.call_count == 1)
        assert(TesTask.get_by_id(str(id)).state == TaskStatus.UNKNOWN)
