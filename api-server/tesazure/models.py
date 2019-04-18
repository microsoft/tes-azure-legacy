# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from enum import Enum, auto
from typing import List
from marshmallow import Schema, fields, post_load, validates_schema, ValidationError
from marshmallow_enum import EnumField
from tesazure.database import db, CRUDMixin
from sqlalchemy_utils import UUIDType
from sqlalchemy_json import NestedMutableJson, JSONType
from sqlalchemy.ext.hybrid import hybrid_property
import uuid
import datetime

"""
Provides Python object constructors and serialization schemas for the data models
supplied in the TES Swagger docs here: https://bit.ly/2QIqzcl

Marshmallow is handling schemas (serialization and input validation); It expects
Python objects with kwargs on its constructors to deserialize JSON. The objects
are currently used in-memory only.
"""


class StringValuedEnum(Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name


class TaskStatus(StringValuedEnum):
    UNKNOWN = auto()
    QUEUED = auto()
    INITIALIZING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETE = auto()
    EXECUTOR_ERROR = auto()
    SYSTEM_ERROR = auto()
    CANCELED = auto()


class TesFileType(StringValuedEnum):
    FILE = auto()
    DIRECTORY = auto()


class TesResourcesSchema(Schema):
    cpu_cores = fields.Int()
    preemptible = fields.Bool()
    ram_gb = fields.Int()
    disk_gb = fields.Int()
    zones = fields.Str()

    @post_load
    def make_resource(self, data):
        return TesResources(**data)


class TesResources:
    def __init__(self, cpu_cores: int = 0, preemptible: bool = True, ram_gb: int = 0, disk_gb: int = 0, zones: str = ""):
        self.cpu_cores = cpu_cores
        self.preemptible = preemptible
        self.ram_gb = ram_gb
        self.disk_gb = disk_gb
        self.zones = zones


class TesInputSchema(Schema):
    url = fields.Str()
    path = fields.Str()
    type = EnumField(TesFileType)
    name = fields.Str()
    description = fields.Str()
    content = fields.Str(allow_none=True)

    @validates_schema
    def validate_input(self, data):
        if 'url' not in data and 'content' not in data:
            raise ValidationError("One of the 'url' or 'content' parameters must be present")

    @post_load
    def make_input(self, data):
        return TesInput(**data)


class TesInput:
    def __init__(self, path: str = "", url: str = "", type: TesFileType = TesFileType.FILE, name: str = "", description: str = "", content: bytes = None):
        self.url = url
        self.path = path
        self.type = type
        self.name = name
        self.description = description
        self.content = content


class TesOutputSchema(Schema):
    url = fields.Str(required=True)
    path = fields.Str(required=True)
    name = fields.Str()
    description = fields.Str()
    type = EnumField(TesFileType)

    @post_load
    def make_output(self, data):
        return TesOutput(**data)


class TesOutput:
    def __init__(self, url: str = "", path: str = "", name: str = "", description: str = "", type: TesFileType = TesFileType.FILE):
        self.url = url
        self.path = path
        self.name = name
        self.description = description
        self.type = type


class TesExecutorSchema(Schema):
    image = fields.Str(required=True)
    command = fields.List(fields.Str, required=True)
    workdir = fields.Str()
    # Note: these are paths where the std* should be /written/ to
    stdin = fields.Str()
    stdout = fields.Str()
    stderr = fields.Str()
    env = fields.Dict()

    @post_load
    def make_executor(self, data):
        return TesExecutor(**data)


class TesExecutor:
    def __init__(self, image: str = "", command: List[str] = [], workdir: str = "",
                 stdin: str = "", stdout: str = "", stderr: str = "", env:
                 dict = {}):
        self.image = image
        self.command = command
        self.workdir = workdir
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.env = env


class OutputFileLogSchema(Schema):
    url = fields.Str(required=True)
    path = fields.Str(required=True)
    size_bytes = fields.Str(required=True)

    @post_load
    def make_output_file_log(self, data):
        return OutputFileLog(**data)


class OutputFileLog:
    def __init__(self, url: str = "", path: str = "", size_bytes: str = ""):
        self.url = url
        self.path = path
        self.size_bytes = size_bytes


class ExecutorLogSchema(Schema):
    start_time = fields.Str()
    end_time = fields.Str()
    stdout = fields.Str()
    stderr = fields.Str()
    exit_code = fields.Int(required=True)

    @post_load
    def make_executor_log(self, data):
        return ExecutorLog(**data)


class ExecutorLog:
    def __init__(self, exit_code: int = -1, start_time: str = "", end_time: str = "",
                 stdout: str = "", stderr: str = ""):
        self.exit_code = exit_code
        self.start_time = start_time
        self.end_time = end_time
        self.stdout = stdout
        self.stderr = stderr


class TaskLogSchema(Schema):
    logs = fields.Nested(ExecutorLogSchema, many=True, required=True)
    metadata = fields.Dict()
    start_time = fields.DateTime()
    end_time = fields.DateTime()
    outputs = fields.Nested(OutputFileLogSchema, many=True, required=True)
    system_logs = fields.Str()

    @post_load
    def make_task_log(self, data):
        return TaskLog(**data)


class TaskLog:
    def __init__(self, logs: List[str] = [], metadata: dict = {},
                 start_time: str = "", end_time: str = "",
                 outputs: List[OutputFileLog] = [], system_logs: List[str] = []):
        self.logs = logs
        self.metadata = metadata
        self.start_time = start_time
        self.end_time = end_time
        self.outputs = outputs
        self.system_logs = system_logs


class TesTaskSchema(Schema):
    resources = fields.Nested(TesResourcesSchema, required=True)
    executors = fields.Nested(TesExecutorSchema, many=True, required=True)
    id = fields.Str(dump_only=True)
    tenant_id = fields.Str(load_only=True)
    user_id = fields.Str(load_only=True)
    backend_id = fields.Str(load_only=True)
    state = EnumField(TaskStatus, dump_only=True)
    name = fields.Str()
    description = fields.Str()
    inputs = fields.Nested(TesInputSchema, many=True)
    outputs = fields.Nested(TesInputSchema, many=True)
    tags = fields.Dict()
    logs = fields.Nested(TaskLogSchema, many=True, dump_only=True)
    creation_time = fields.DateTime(dump_only=True)

    @post_load
    def make_task(self, data):
        return TesTask(**data)


class TesTask(CRUDMixin, db.Model):
    id = db.Column(UUIDType(binary=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(64), nullable=True)
    tenant_id = db.Column(db.String(64), nullable=True)
    backend_id = db.Column(db.String(64), nullable=False)
    task_json = db.Column(NestedMutableJson)
    state = db.Column(db.Enum(TaskStatus), nullable=False)
    created_ts = db.Column(
        db.DateTime(timezone=True),
        default=datetime.datetime.utcnow
    )
    updated_ts = db.Column(
        db.DateTime(timezone=True),
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow
    )

    @hybrid_property
    def creation_time(self):
        return self.created_ts

    @creation_time.setter
    def creation_time(self, value):
        self.created_ts = value

    @hybrid_property
    def resources(self):
        return TesResourcesSchema().load(self.task_json["resources"]).data

    @resources.setter
    def resources(self, value):
        self.task_json["resources"] = TesResourcesSchema().dump(value).data

    @hybrid_property
    def executors(self):
        return TesExecutorSchema().load(self.task_json["executors"], many=True).data

    # FIXME: .append() fails to trigger setter on list hybrid properties
    # https://groups.google.com/forum/#!topic/sqlalchemy/HZKTuD36Drs
    @executors.setter
    def executors(self, value):
        self.task_json["executors"] = TesExecutorSchema().dump(value, many=True).data

    @hybrid_property
    def name(self):
        return (self.task_json["name"])

    @name.setter
    def name(self, value):
        self.task_json["name"] = value

    @hybrid_property
    def description(self):
        return (self.task_json["description"])

    @description.setter
    def description(self, value):
        self.task_json["description"] = value

    @hybrid_property
    def inputs(self):
        return TesInputSchema().load(self.task_json["inputs"], many=True).data

    @inputs.setter
    def inputs(self, value):
        self.task_json["inputs"] = TesInputSchema().dump(value, many=True).data

    @hybrid_property
    def outputs(self):
        return TesOutputSchema().load(self.task_json["outputs"], many=True).data

    @outputs.setter
    def outputs(self, value):
        self.task_json["outputs"] = TesOutputSchema().dump(value, many=True).data

    @hybrid_property
    def logs(self):
        return TaskLogSchema().load(self.task_json["logs"], many=True).data

    @logs.setter
    def logs(self, value):
        self.task_json["logs"] = TaskLogSchema().dump(value, many=True).data

    @hybrid_property
    def tags(self):
        return self.task_json["tags"]

    @tags.setter
    def tags(self, value):
        self.task_json["tags"] = value

    def __init__(self,
                 resources: TesResources = TesResources(), executors: List[TesExecutor] = [],
                 id: str = None, state: TaskStatus = TaskStatus.UNKNOWN,
                 name: str = "", description: str = "", inputs: List[TesInput] = [],
                 outputs: List[TesOutput] = [], tags: dict = {},
                 volumes: List[str] = [], logs: List[TaskLogSchema] = [],
                 creation_time: datetime = datetime.datetime.utcnow):
        self.task_json = TesTaskSchema().dump({
            "resources": resources,
            "executors": executors,
            "name": name,
            "description": description,
            "inputs": inputs,
            "outputs": outputs,
            "logs": logs,
            "tags": tags
        }).data
        self.state = state


class ProvisionTrackerSchema(Schema):
    id = fields.Str(dump_only=True)
    request_json = fields.Str()
    status_json = fields.Str()

    @post_load
    def make_task(self, data):
        return ProvisionTracker(**data)


class ProvisionTracker(CRUDMixin, db.Model):
    id = db.Column(UUIDType(binary=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    request_json = db.Column(JSONType)
    status_json = db.Column(JSONType)

    def __init__(self, id: str = None, request_json: str = "", status_json: str = ""):
        self.request_json = request_json
        self.status_json = status_json


class ProvisionTrackerNotFound(Exception):
    """Lookup Provision Tracker id failed"""
    pass


class CloudError(Exception):
    """Generic error when trying to use a cloud resource"""
    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message
