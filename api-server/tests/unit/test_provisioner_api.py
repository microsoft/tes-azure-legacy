# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import json
import uuid
from marshmallow import Schema, fields, post_load
from tesazure.models import ProvisionTracker, CloudError


class ProvisionRequestSchema(Schema):
    field1 = fields.String(required=True)

    @post_load
    def make_resource(self, data):
        return ProvisionRequest(**data)


class ProvisionRequest:
    def __init__(self, field1: str = ""):
        self.field1 = field1


class TestCase:
    def test_initalize_assigns_id_and_creates_provision_request(self, client, session, mocker):
        mock_provision_request = mocker.patch('tesazure.backends.mock.MockBackend.provision_request_schema', new_callable=mocker.PropertyMock)
        mock_provision_request.return_value = ProvisionRequestSchema()

        provisioner_request_json = '{"field1": "testfield1"}'
        resp = client.post('/provision', data=provisioner_request_json, content_type='application/json')
        data = json.loads(resp.data)

        assert resp.status_code == 202
        assert 'id' in data
        assert len(data['id']) > 0

        db_result = ProvisionTracker.get_by_id(data['id'])

        assert db_result.request_json['field1'] == 'testfield1'

    def test_initalize_validates_request_json(self, client, mocker):
        mock_provision_request = mocker.patch('tesazure.backends.mock.MockBackend.provision_request_schema', new_callable=mocker.PropertyMock)
        mock_provision_request.return_value = ProvisionRequestSchema()

        provisioner_request_json = '{"notfield1": "should_error"}'
        resp = client.post('/provision', data=provisioner_request_json, content_type='application/json')
        data = json.loads(resp.data)

        assert resp.status_code == 422
        assert 'errors' in data
        assert len(data['errors']) > 0

    def test_initalize_handles_cloud_error(self, client, mocker):
        mock_provision_request = mocker.patch('tesazure.backends.mock.MockBackend.provision_request_schema')
        mock_provision_request.return_value = ProvisionRequestSchema()
        mock_provision_check = mocker.patch('tesazure.backends.mock.MockBackend.provision_check')
        mock_provision_check.side_effect = CloudError("test")

        provisioner_request_json = '{"field1": "testfield1"}'
        resp = client.post('/provision', data=provisioner_request_json, content_type='application/json')
        data = json.loads(resp.data)

        assert resp.status_code == 422
        assert len(data['error']) > 0
        assert "test" in data['error']

    def test_query_returns_provision_status(self, client, session):
        # insert fake data into the database
        tracker = ProvisionTracker()
        tracker.id = uuid.uuid4()
        tracker.status_json = '{"status": "PASS"}'
        tracker.request_json = '{}'
        session.add(tracker)
        session.commit()

        # Query
        resp = client.get(f'/provision/{tracker.id}')
        # loads called twice because API returns byte literal - probably a bug?
        data = json.loads(json.loads(resp.data))

        assert resp.status_code == 200
        assert 'status' in data
        assert data['status'] == 'PASS'

    def test_query_id_missing(self, client, session):
        resp = client.get(f'/provision/{str(uuid.uuid4())}')
        assert 404 == resp.status_code
