# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import json
import os
import pytest
import uuid

try:
    from flask import _app_ctx_stack as ctx_stack
except ImportError:
    from flask import _request_ctx_stack as ctx_stack

from tesazure.models import TaskStatus, TesTask, TesResources, TesExecutor, TaskLog, ExecutorLog


class TestCase:
    def setup_acl_tests(self, session):
        """
        Sets up a garden variety of tasks in the DB for ACL verifications
        """
        ctx_stack.top.claims = {'sub': 'user1', 'tid': 'expected-audience'}

        tenant1_tasks = []
        tenant2_tasks = []
        global_tasks = []

        task = TesTask()
        task.backend_id = "test-backend-1"
        task.tenant_id = "expected-audience"
        task.user_id = "user1"
        session.add(task)
        tenant1_tasks.append(task)

        task = TesTask()
        task.backend_id = "test-backend-2"
        task.tenant_id = "expected-audience"
        task.user_id = "user2"
        session.add(task)
        tenant1_tasks.append(task)

        task = TesTask()
        task.backend_id = "test-backend-3"
        task.tenant_id = "other-audience"
        task.user_id = "user1"
        session.add(task)
        tenant2_tasks.append(task)

        task = TesTask()
        task.backend_id = "test-backend-4"
        task.tenant_id = None
        task.user_id = None
        session.add(task)
        global_tasks.append(task)
        session.commit()

        return (tenant1_tasks, tenant2_tasks, global_tasks)

    def test_list_tasks(self, client, session):
        # insert fake data into the database (after adding required data)
        task1 = TesTask()
        task1.backend_id = 'test1-backend-id'
        task1.resources = TesResources()
        task1.executors = [TesExecutor()]
        task2 = TesTask()
        task2.backend_id = 'test2-backend-id'
        task2.resources = TesResources()
        task2.executors = [TesExecutor()]
        session.add(task1)
        session.add(task2)
        session.commit()

        resp = client.get('/v1/tasks')
        data = json.loads(resp.data)
        assert any(x['id'] == str(task1.id) for x in data['tasks'])
        assert any(x['id'] == str(task2.id) for x in data['tasks'])

    def test_service_info(self, app, client):
        resp = client.get('/v1/tasks/service-info')
        data = json.loads(resp.data)
        assert app.config['SITE_NAME'] == data['name']
        assert 'Built by Microsoft - Mock Engine' == data['doc']

    def test_create_task_assigns_id(self, client, session):
        with open(os.path.join('tests', 'unit', 'data', 'test_api_create.json')) as fh:
            task_json = fh.read()
        resp = client.post('/v1/tasks', data=task_json, content_type='application/json')
        data = json.loads(resp.data)
        assert 'id' in data
        assert len(data['id']) > 0

    def test_get_task(self, client, session):
        # insert fake data into the database (after adding required data)
        task = TesTask()
        task.backend_id = "test-backend-id"
        task.resources = TesResources()
        task.executors = [TesExecutor()]
        task.state = TaskStatus.QUEUED
        session.add(task)
        session.commit()
        id = str(task.id)

        resp = client.get('/v1/tasks/' + id)
        data = json.loads(resp.data)

        # Task should be present from DB
        assert id == data['id']
        # Backend should override saved status
        assert TaskStatus.COMPLETE.name == data['state']

    def test_get_task_returns_stdout(self, client, session):
        task = TesTask()
        task.backend_id = "test-backend-id"
        task.resources = TesResources()

        task_log = TaskLog()
        task_log.logs += [ExecutorLog(stdout="out")]
        task.logs += [task_log]

        task.executors = [TesExecutor()]
        session.add(task)
        session.commit()
        id = task.id

        resp = client.get(f'/v1/tasks/{id}')
        data = json.loads(resp.data)
        assert str(id) == data['id']
        assert 'out' == data['logs'][0]['logs'][0]['stdout']

    def test_get_task_missing(self, client):
        resp = client.get('/v1/tasks/baz')
        assert 404 == resp.status_code

    def test_cancel_task_exists(self, client, session):
        # insert fake data into the database (after adding required data)
        task = TesTask()
        task.backend_id = "test-backend-id"
        task.resources = TesResources()
        task.executors = [TesExecutor()]
        session.add(task)
        session.commit()
        id = task.id

        resp = client.post('/v1/tasks/' + str(id) + ':cancel')
        assert b'{}' in resp.data

    def test_cancel_task_missing(self, client, session):
        resp = client.post('/v1/tasks/' + str(uuid.uuid4()) + ':cancel')
        assert 404 == resp.status_code

    @pytest.mark.options(AAD_VERIFY=False)
    @pytest.mark.options(AAD_AUDIENCE='expected-audience')
    @pytest.mark.options(AAD_TENANT_ID='tenant-id')
    @pytest.mark.options(TASK_ACCESS_RESTRICTIONS='per-tenant')
    def test_list_tasks_acl_without_verify(self, app, client, session):
        (tenant1_tasks, tenant2_tasks, global_tasks) = self.setup_acl_tests(session)

        resp = client.get('/v1/tasks')
        data = json.loads(resp.data)
        assert 200 == resp.status_code
        assert len(data['tasks']) == 1

    @pytest.mark.options(AAD_VERIFY=True)
    @pytest.mark.options(AAD_AUDIENCE='expected-audience')
    @pytest.mark.options(AAD_TENANT_ID='tenant-id')
    @pytest.mark.options(TASK_ACCESS_RESTRICTIONS=None)
    def test_list_tasks_acl_none(self, client, session):
        (tenant1_tasks, tenant2_tasks, global_tasks) = self.setup_acl_tests(session)

        resp = client.get('/v1/tasks')
        data = json.loads(resp.data)
        assert 200 == resp.status_code
        assert len(data['tasks']) == 4

    @pytest.mark.options(AAD_VERIFY=True)
    @pytest.mark.options(AAD_AUDIENCE='aad-audience')
    @pytest.mark.options(AAD_TENANT_ID='tenant-id')
    @pytest.mark.options(TASK_ACCESS_RESTRICTIONS='per-tenant')
    def test_list_tasks_acl_per_tenant(self, client, session):
        (tenant1_tasks, tenant2_tasks, global_tasks) = self.setup_acl_tests(session)

        resp = client.get('/v1/tasks')
        data = json.loads(resp.data)
        assert 200 == resp.status_code
        assert len(data['tasks']) == 3

    @pytest.mark.options(AAD_VERIFY=True)
    @pytest.mark.options(AAD_AUDIENCE='aad-audience')
    @pytest.mark.options(AAD_TENANT_ID='tenant-id')
    @pytest.mark.options(TASK_ACCESS_RESTRICTIONS='per-user')
    def test_list_tasks_acl_per_user(self, app, client, session, request_ctx):
        (tenant1_tasks, tenant2_tasks, global_tasks) = self.setup_acl_tests(session)

        resp = client.get('/v1/tasks')
        data = json.loads(resp.data)
        assert 200 == resp.status_code
        assert len(data['tasks']) == 2

    @pytest.mark.options(AAD_VERIFY=False)
    @pytest.mark.options(AAD_AUDIENCE='expected-audience')
    @pytest.mark.options(AAD_TENANT_ID='tenant-id')
    @pytest.mark.options(TASK_ACCESS_RESTRICTIONS='per-tenant')
    def test_get_task_acl_without_verify(self, app, client, session):
        (tenant1_tasks, tenant2_tasks, global_tasks) = self.setup_acl_tests(session)

        resp = client.get('/v1/tasks/' + str(tenant1_tasks[0].id))
        assert 403 == resp.status_code

        resp = client.get('/v1/tasks/' + str(tenant2_tasks[0].id))
        assert 403 == resp.status_code

        resp = client.get('/v1/tasks/' + str(global_tasks[0].id))
        assert 200 == resp.status_code

    @pytest.mark.options(AAD_VERIFY=True)
    @pytest.mark.options(AAD_AUDIENCE='expected-audience')
    @pytest.mark.options(AAD_TENANT_ID='tenant-id')
    @pytest.mark.options(TASK_ACCESS_RESTRICTIONS=None)
    def test_get_task_acl_none(self, client, session):
        (tenant1_tasks, tenant2_tasks, global_tasks) = self.setup_acl_tests(session)

        resp = client.get('/v1/tasks/' + str(tenant1_tasks[0].id))
        assert 200 == resp.status_code

        assert tenant1_tasks[0].user_id != tenant1_tasks[1].user_id
        resp = client.get('/v1/tasks/' + str(tenant1_tasks[1].id))
        assert 200 == resp.status_code

        resp = client.get('/v1/tasks/' + str(tenant2_tasks[0].id))
        assert 200 == resp.status_code

        resp = client.get('/v1/tasks/' + str(global_tasks[0].id))
        assert 200 == resp.status_code

    @pytest.mark.options(AAD_VERIFY=True)
    @pytest.mark.options(AAD_AUDIENCE='aad-audience')
    @pytest.mark.options(AAD_TENANT_ID='tenant-id')
    @pytest.mark.options(TASK_ACCESS_RESTRICTIONS='per-tenant')
    def test_get_task_acl_per_tenant(self, client, session):
        (tenant1_tasks, tenant2_tasks, global_tasks) = self.setup_acl_tests(session)

        resp = client.get('/v1/tasks/' + str(tenant1_tasks[0].id))
        assert 200 == resp.status_code

        assert tenant1_tasks[0].user_id != tenant1_tasks[1].user_id
        resp = client.get('/v1/tasks/' + str(tenant1_tasks[1].id))
        assert 200 == resp.status_code

        resp = client.get('/v1/tasks/' + str(tenant2_tasks[0].id))
        assert 403 == resp.status_code

        resp = client.get('/v1/tasks/' + str(global_tasks[0].id))
        assert 200 == resp.status_code

    @pytest.mark.options(AAD_VERIFY=True)
    @pytest.mark.options(AAD_AUDIENCE='aad-audience')
    @pytest.mark.options(AAD_TENANT_ID='tenant-id')
    @pytest.mark.options(TASK_ACCESS_RESTRICTIONS='per-user')
    def test_get_task_acl_per_user(self, app, client, session, request_ctx):
        (tenant1_tasks, tenant2_tasks, global_tasks) = self.setup_acl_tests(session)

        resp = client.get('/v1/tasks/' + str(tenant1_tasks[0].id))
        assert 200 == resp.status_code

        assert tenant1_tasks[0].user_id != tenant1_tasks[1].user_id
        resp = client.get('/v1/tasks/' + str(tenant1_tasks[1].id))
        assert 403 == resp.status_code

        resp = client.get('/v1/tasks/' + str(tenant2_tasks[0].id))
        assert 403 == resp.status_code

        resp = client.get('/v1/tasks/' + str(global_tasks[0].id))
        assert 200 == resp.status_code

    @pytest.mark.options(AAD_VERIFY=False)
    @pytest.mark.options(AAD_AUDIENCE='expected-audience')
    @pytest.mark.options(AAD_TENANT_ID='tenant-id')
    @pytest.mark.options(TASK_ACCESS_RESTRICTIONS='per-tenant')
    def test_cancel_task_acl_without_verify(self, app, client, session):
        (tenant1_tasks, tenant2_tasks, global_tasks) = self.setup_acl_tests(session)

        resp = client.post('/v1/tasks/' + str(tenant1_tasks[0].id) + ':cancel')
        assert 403 == resp.status_code

        resp = client.post('/v1/tasks/' + str(tenant2_tasks[0].id) + ':cancel')
        assert 403 == resp.status_code

        resp = client.post('/v1/tasks/' + str(global_tasks[0].id) + ':cancel')
        assert 200 == resp.status_code

    @pytest.mark.options(AAD_VERIFY=True)
    @pytest.mark.options(AAD_AUDIENCE='expected-audience')
    @pytest.mark.options(AAD_TENANT_ID='tenant-id')
    @pytest.mark.options(TASK_ACCESS_RESTRICTIONS=None)
    def test_cancel_task_acl_none(self, client, session):
        (tenant1_tasks, tenant2_tasks, global_tasks) = self.setup_acl_tests(session)

        resp = client.post('/v1/tasks/' + str(tenant1_tasks[0].id) + ':cancel')
        assert 200 == resp.status_code

        assert tenant1_tasks[0].user_id != tenant1_tasks[1].user_id
        resp = client.post('/v1/tasks/' + str(tenant1_tasks[1].id) + ':cancel')
        assert 200 == resp.status_code

        resp = client.post('/v1/tasks/' + str(tenant2_tasks[0].id) + ':cancel')
        assert 200 == resp.status_code

        resp = client.post('/v1/tasks/' + str(global_tasks[0].id) + ':cancel')
        assert 200 == resp.status_code

    @pytest.mark.options(AAD_VERIFY=True)
    @pytest.mark.options(AAD_AUDIENCE='aad-audience')
    @pytest.mark.options(AAD_TENANT_ID='tenant-id')
    @pytest.mark.options(TASK_ACCESS_RESTRICTIONS='per-tenant')
    def test_cancel_task_acl_per_tenant(self, client, session):
        (tenant1_tasks, tenant2_tasks, global_tasks) = self.setup_acl_tests(session)

        resp = client.post('/v1/tasks/' + str(tenant1_tasks[0].id) + ':cancel')
        assert 200 == resp.status_code

        assert tenant1_tasks[0].user_id != tenant1_tasks[1].user_id
        resp = client.post('/v1/tasks/' + str(tenant1_tasks[1].id) + ':cancel')
        assert 200 == resp.status_code

        resp = client.post('/v1/tasks/' + str(tenant2_tasks[0].id) + ':cancel')
        assert 403 == resp.status_code

        resp = client.post('/v1/tasks/' + str(global_tasks[0].id) + ':cancel')
        assert 200 == resp.status_code

    @pytest.mark.options(AAD_VERIFY=True)
    @pytest.mark.options(AAD_AUDIENCE='aad-audience')
    @pytest.mark.options(AAD_TENANT_ID='tenant-id')
    @pytest.mark.options(TASK_ACCESS_RESTRICTIONS='per-user')
    def test_cancel_task_acl_per_user(self, app, client, session, request_ctx):
        (tenant1_tasks, tenant2_tasks, global_tasks) = self.setup_acl_tests(session)

        resp = client.post('/v1/tasks/' + str(tenant1_tasks[0].id) + ':cancel')
        assert 200 == resp.status_code

        assert tenant1_tasks[0].user_id != tenant1_tasks[1].user_id
        resp = client.post('/v1/tasks/' + str(tenant1_tasks[1].id) + ':cancel')
        assert 403 == resp.status_code

        resp = client.post('/v1/tasks/' + str(tenant2_tasks[0].id) + ':cancel')
        assert 403 == resp.status_code

        resp = client.post('/v1/tasks/' + str(global_tasks[0].id) + ':cancel')
        assert 200 == resp.status_code
