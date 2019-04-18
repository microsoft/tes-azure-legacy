# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from flask_assets import Environment
from flask_babel import Babel
from flask_bcrypt import Bcrypt
from flask_celeryext import FlaskCeleryExt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_keyvault import KeyVault

from werkzeug.contrib.cache import SimpleCache

from .jwt_validator import JwtValidator
from .AzureMonitor import AzureMonitor
from .backends import ComputeBackend


assets = Environment()
babel = Babel()
bcrypt = Bcrypt()
cache = SimpleCache()
celery = FlaskCeleryExt()
limiter = Limiter(key_func=get_remote_address)
lm = LoginManager()
migrate = Migrate()
compute_backend = ComputeBackend()
monitor = AzureMonitor()
jwt_validator = JwtValidator()
key_vault = KeyVault()
