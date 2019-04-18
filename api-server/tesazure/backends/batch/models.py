# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from marshmallow import Schema, fields, post_load
from marshmallow_enum import EnumField
from enum import Enum, auto
from random import randint

"""
Provides Python object constructors and serialization schemas for the data models
needed for Azure Batch provisioning.

Marshmallow is handling schemas (serialization and input validation); It expects
Python objects with kwargs on its constructors to deserialize JSON. The objects
are currently used in-memory only.
"""


class StringValuedEnum(Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name


class Status(StringValuedEnum):
    UNKNOWN = auto()
    NOTFOUND = auto()
    ERROR = auto()
    INPROGRESS = auto()
    CREATED = auto()


class ServicePrincipalSchema(Schema):
    client_id = fields.Str(required=True)
    secret = fields.Str(required=True)
    tenant = fields.Str(required=True)

    @post_load
    def make_resource(self, data):
        return ServicePrincipal(**data)


class ServicePrincipal:
    def __init__(self, client_id: str = "", secret: str = "", tenant: str = ""):
        self.client_id = client_id
        self.secret = secret
        self.tenant = tenant


class ProvisionRequestSchema(Schema):
    service_principal = fields.Nested(ServicePrincipalSchema, required=True)
    subscription_id = fields.String(required=True)
    resource_group = fields.String()
    location = fields.String()
    storage_account_name = fields.String()
    storage_sku = fields.String()
    batch_account_name = fields.String()

    @post_load
    def make_resource(self, data):
        return ProvisionRequest(**data)


class ProvisionRequest:
    def __init__(self,
                 service_principal: ServicePrincipal = None, subscription_id: str = "",
                 resource_group: str = "", location: str = "",
                 storage_account_name: str = "", storage_sku: str = "",
                 batch_account_name: str = ""):

        random_num = str(randint(0, 9999))
        self.service_principal = service_principal
        self.subscription_id = subscription_id
        self.resource_group = "tesazure-batch-" + random_num if resource_group == "" else resource_group
        self.location = "westus2" if location == "" else location
        self.storage_account_name = "tesazurebatchstorage" + random_num if storage_account_name == "" else storage_account_name
        self.storage_sku = "standard_lrs" if storage_sku == "" else storage_sku
        self.batch_account_name = "tesazurebatch" + random_num if batch_account_name == "" else batch_account_name


class ProvisionStatusSchema(Schema):
    status = EnumField(Status)
    error_message = fields.String()
    storage_account_name = fields.String()
    storage_account_key = fields.String()
    batch_account_name = fields.String()
    batch_account_url = fields.String()
    batch_account_key = fields.String()

    @post_load
    def make_resource(self, data):
        return ProvisionStatus(**data)


class ProvisionStatus:
    def __init__(self,
                 status: Status = Status.UNKNOWN, error_message: str = "",
                 storage_account_name: str = "", storage_account_key: str = "",
                 batch_account_name: str = "", batch_account_url: str = "",
                 batch_account_key: str = ""):
        self.status = status
        self.error_message = error_message
        self.storage_account_name = storage_account_name
        self.storage_account_key = storage_account_key
        self.batch_account_name = batch_account_name
        self.batch_account_url = batch_account_url
        self.batch_account_key = batch_account_key
