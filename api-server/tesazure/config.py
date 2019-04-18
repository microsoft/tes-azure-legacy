# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from flask_env import MetaFlaskEnv
from celery.schedules import crontab


class base_config(object, metaclass=MetaFlaskEnv):
    """Default configuration options."""
    ENV_PREFIX = 'APP_'

    SITE_NAME = 'TES API Server for Azure Compute'
    SECRET_KEY = 'secrets'

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = 'postgresql+psycopg2://username:password@host:5432/dbname'

    CELERY_RESULT_BACKEND = 'redis://key@host:6379'
    CELERY_BROKER_URL = 'redis://key@host:6379'

    SUPPORTED_LOCALES = ['en']

    # Requests are logged via OpenCensus.
    APPINSIGHTS_DISABLE_REQUEST_LOGGING = True
    APPINSIGHTS_DISABLE_TRACE_LOGGING = False
    APPINSIGHTS_DISABLE_EXCEPTION_LOGGING = False
    APPINSIGHTS_INSTRUMENTATIONKEY = None

    COMPUTE_BACKEND = "mock"  # among ['mock', 'aks', 'batch']

    STORAGE_ACCOUNT_NAME = ''
    STORAGE_ACCOUNT_KEY = ''

    AAD_VERIFY = False
    AAD_AUDIENCE = 'aad-client-id'
    AAD_TENANT_ID = 'aad-tenant-id'
    AAD_JWKS_URI = 'https://login.microsoftonline.com/common/discovery/v2.0/keys'

    # Choices among [None, 'per-user', 'per-tenant']
    # Anything other than None requires AAD_VERIFY to be True
    TASK_ACCESS_RESTRICTIONS = None

    # batch engine config
    BATCH_ACCOUNT_NAME = ''
    BATCH_ACCOUNT_KEY = ''
    BATCH_ACCOUNT_URL = ''
    BATCH_STORAGE_TMP_CONTAINER_NAME = 'batchtmp'
    BATCH_STORAGE_FILESHARE_NAME = 'batchfiles'

    BATCH_POOL_DEDICATED_NODE_COUNT = 0
    BATCH_POOL_LOW_PRIORITY_NODE_COUNT = 1
    BATCH_NODE_ADMIN_USERNAME = None
    BATCH_NODE_ADMIN_PASSWORD = None

    PRIVATE_DOCKER_REGISTRY_URL = None  # "myregistry.azurecr.io"
    PRIVATE_DOCKER_REGISTRY_USERNAME = "username"
    PRIVATE_DOCKER_REGISTRY_PASSWORD = "password"

    # Replace with KeyVault URL and SPN info for access
    KEYVAULT_URL = None
    KEYVAULT_SECRETS_PREFIX = "TESAZURE-"
    AZURE_CLIENT_ID = None
    AZURE_SECRET = None
    AZURE_TENANT = None

    # Used by celery beat scheduler container
    CELERY_BEAT_SCHEDULE = {
        "cleanup_tasks": {
            "task": "tesazure.jobs.cleanup_tasks",
            "schedule": crontab(minute='*/5')
        }
    }
    TASK_BACKEND_CLEANUP_HOURS = 24
    TASK_DATABASE_CLEANUP_HOURS = 48
    TASK_EXECUTION_TIMEOUT_HOURS = 12


class dev_config(base_config, metaclass=MetaFlaskEnv):
    """Development configuration options."""
    ENV_PREFIX = 'APP_'

    ASSETS_DEBUG = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'postgresql+psycopg2://tesadmin:testpassword@postgres:5432/tesapi'
    CELERY_RESULT_BACKEND = 'redis://redis:6379'
    CELERY_BROKER_URL = 'redis://redis:6379'
    ADMIN_USER_NAME = "sshdebug"
    ADMIN_USER_PASSWORD = "testUser!!12345"
    POOL_LOW_PRIORITY_NODE_COUNT = 1

    BATCH_OVERRIDE_POOL_ID = None

    SQLALCHEMY_ECHO = False


class test_config(base_config, metaclass=MetaFlaskEnv):
    """Testing configuration options."""
    ENV_PREFIX = 'APP_'

    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///memory'

    COMPUTE_BACKEND = 'mock'
