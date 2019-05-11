# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import json

from flask import current_app, request
from flask_restful import Resource, Api
from marshmallow import ValidationError
from sqlalchemy import or_

from ..backends import common
from ..jwt_validator import claims as jwt_claims
from ..models import TesTask, TesTaskSchema
from ..tesapi import tesapi
from tesazure.extensions import compute_backend, jwt_validator

"""
Provides API endpoints using Flask-Restful for the endpoints supplied in the TES
Swagger docs here: https://bit.ly/2QIqzcl

Serialization to/from JSON is performed using Marshmallow schemas.
"""


class TaskList(Resource):
    @jwt_validator.protect()
    def get(self):
        schema = TesTaskSchema()
        tasks_query = TesTask.query

        if current_app.config['AAD_VERIFY'] is True:
            # We have a user identity so filter on it
            if current_app.config['TASK_ACCESS_RESTRICTIONS'] is not None:
                tasks_query = tasks_query.filter(or_(TesTask.tenant_id.is_(None), TesTask.tenant_id == jwt_claims['tid']))
            if current_app.config['TASK_ACCESS_RESTRICTIONS'] == 'per-user':
                tasks_query = tasks_query.filter(or_(TesTask.user_id.is_(None), TesTask.user_id == jwt_claims['sub']))
        else:
            # We don't know the current user, so hide everything that wasn't
            # intended to be globally visible
            if current_app.config['TASK_ACCESS_RESTRICTIONS'] is not None:
                tasks_query = tasks_query.filter(TesTask.tenant_id.is_(None))

        return {
            'tasks': schema.dump(tasks_query.all(), many=True).data,
            'next_page_token': 'N/A'  # TODO pagination
        }

    @jwt_validator.protect()
    def post(self):
        current_app.logger.debug(f'Task creation received JSON: {request.data}')

        json_input = request.get_json()
        schema = TesTaskSchema()

        try:
            task = schema.load(json_input)
            if len(task.errors) > 0:
                raise ValidationError(task.errors)
        except ValidationError as err:
            current_app.logger.error("Task creation failed: validation error while parsing task. " + json.dumps(err.messages))
            return {'errors': err.messages}, 422
        task = task.data

        # This unusual assignment dance is required because .update() doesn't trigger hybrid property setters
        tags = task.tags
        tags.update(common.detect_tags_for_submitter(task))
        task.tags = tags

        common.mangle_task_for_submitter(task)

        task.backend_id = compute_backend.backend.create_task(task)
        if current_app.config['AAD_VERIFY'] is True:
            task.tenant_id = jwt_claims['tid']
            task.user_id = jwt_claims['sub']
        task.save()

        return {'id': str(task.id)}


class TaskServiceInfo(Resource):
    @jwt_validator.protect()
    def get(self):
        defaults = {
            'name': current_app.config['SITE_NAME'],
            'doc': "Built by Commercial Software Engineering (CSE) @ Microsoft",
            'storage': [
                'file:///local/storage',
                'https:///remote/webserver'
            ]
        }
        is_debug = 'x-debug-secret' in request.headers and request.headers.get('x-debug-secret') == current_app.config.get('SECRET_KEY')
        backend_overrides = compute_backend.backend.service_info(debug=is_debug)
        defaults.update(backend_overrides)

        if is_debug:
            tasks = []
            for task in TesTask.query.order_by(TesTask.created_ts.desc()).limit(5):
                tasks.append({'id': str(task.id), 'backend_id': str(task.backend_id), 'created_ts': task.created_ts.isoformat(), 'updated_ts': task.updated_ts.isoformat(), 'state': task.state.name})
            defaults.update({'recent_tasks': tasks, 'config': {key: str(val) for key, val in current_app.config.items()}})
        return defaults


class Task(Resource):
    @jwt_validator.protect()
    def get(self, task_id):
        task = TesTask.get_by_id(task_id)
        if not task:
            msg = f"TES task '{task_id}' was not found"
            current_app.logger.error(msg)
            return {'errors': msg}, 404

        if current_app.config['AAD_VERIFY'] is True:
            if current_app.config['TASK_ACCESS_RESTRICTIONS'] is not None and task.tenant_id not in [None, jwt_claims['tid']]:
                current_app.logger.error("Authorization required to view task")
                return {'errors': 'Authorization required to view task'}, 403
            if current_app.config['TASK_ACCESS_RESTRICTIONS'] == 'per-user' and task.user_id not in [None, jwt_claims['sub']]:
                current_app.logger.error("Authorization required to view task")
                return {'errors': 'Authorization required to view task'}, 403
        else:
            if current_app.config['TASK_ACCESS_RESTRICTIONS'] is not None and any(None is not x for x in [task.tenant_id, task.user_id]):
                current_app.logger.error("Authorization required to view task")
                return {'errors': 'Authorization required to view task'}, 403

        schema = TesTaskSchema()

        # merge backend status to db
        backend_task = compute_backend.backend.get_task(task.backend_id)
        if not backend_task:
            current_app.logger.error(f"Task status failed: TES task '{task_id}' exists in local cache, but compute backend could not locate backend_id={task.backend_id}")
            return {'errors': f"TES task '{task_id}' exists in local cache, but compute backend could not locate it"}, 500

        for field_name in schema._declared_fields:
            field_value = getattr(backend_task, field_name)
            if field_value:
                setattr(task, field_name, field_value)
        task.save()

        return schema.dump(task)


class TaskCancel(Resource):
    @jwt_validator.protect()
    def post(self, task_id):
        task = TesTask.get_by_id(task_id)
        if not task:
            current_app.logger.error("Task cancellation failed: TES task '{task_id}' was not found")
            return {'errors': "TES task '{task_id}' was not found"}, 404

        if current_app.config['AAD_VERIFY'] is True:
            if current_app.config['TASK_ACCESS_RESTRICTIONS'] is not None and task.tenant_id not in [None, jwt_claims['tid']]:
                current_app.logger.error("Authorization required to cancel task")
                return {'errors': 'Authorization required to cancel task'}, 403
            if current_app.config['TASK_ACCESS_RESTRICTIONS'] == 'per-user' and task.user_id not in [None, jwt_claims['sub']]:
                current_app.logger.error("Authorization required to cancel task")
                return {'errors': 'Authorization required to cancel task'}, 403
        else:
            if current_app.config['TASK_ACCESS_RESTRICTIONS'] is not None and any(None is not x for x in [task.tenant_id, task.user_id]):
                current_app.logger.error("Authorization required to cancel task")
                return {'errors': 'Authorization required to cancel task'}, 403

        if compute_backend.backend.cancel_task(task.backend_id):
            current_app.logger.info(f"TES task '{task_id}' was successfully cancelled")
            return "{}"
        else:
            current_app.logger.error(f"Task cancellation failed: TES task '{task_id}' exists in local cache, but compute backend could not locate backend_id={task.backend_id}")
            return {'errors': f"TES task '{task_id}' exists in local cache, but compute backend could not locate it"}, 500


# Create the Flask-Restful API manager
api = Api(tesapi)

# Add resources
api.add_resource(TaskList, '/tasks')
api.add_resource(TaskServiceInfo, '/tasks/service-info')
api.add_resource(Task, '/tasks/<string:task_id>')
api.add_resource(TaskCancel, '/tasks/<string:task_id>:cancel')
