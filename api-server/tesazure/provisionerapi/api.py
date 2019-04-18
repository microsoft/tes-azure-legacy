# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from flask import current_app, request
from flask_restful import Resource, Api
from ..provisionerapi import provisionerapi
from marshmallow import ValidationError
from tesazure.extensions import compute_backend
from tesazure.models import ProvisionTracker, CloudError
import json


class Provision(Resource):
    def post(self):
        # FIXME - remove secrets and log?
        # current_app.logger.debug(f'Received batch provision JSON: {request.data}')

        json_input = request.get_json()
        schema = compute_backend.backend.provision_request_schema

        try:
            provision_request = schema.load(json_input)
            if len(provision_request.errors) > 0:
                raise ValidationError(provision_request.errors)
        except ValidationError as err:
            current_app.logger.error("Validation error while parsing provision request. " + json.dumps(err.messages))
            return {'errors': err.messages}, 422
        provision_request = provision_request.data

        try:
            compute_backend.backend.provision_check(provision_request=provision_request)

            try:
                req = ProvisionTracker(request_json=schema.dump(provision_request).data)
                req.save()
            except Exception as err:
                current_app.logger.error(f'Error saving provision request to database. {err}')
                return {'error': err}, 500

            compute_backend.backend.provision_start(id=req.id)
            return {'id': str(req.id)}, 202
        except CloudError as err:
            return {'error': str(err)}, 422


class Query(Resource):
    def get(self, provision_tracker_id):
        # Get + validate input format
        current_app.logger.info(f"Received query for Provisioner Tracker: {provision_tracker_id}")

        provision_request = ProvisionTracker.get_by_id(provision_tracker_id)
        if not provision_request:
            return {'errors': 'Provision request could not be found'}, 404

        return provision_request.status_json


# Create the Flask-Restful API manager
api = Api(provisionerapi)

# Add resources
api.add_resource(Provision, '')
api.add_resource(Query, '/<string:provision_tracker_id>')
