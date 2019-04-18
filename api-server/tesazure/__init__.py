# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from flask import Flask, g, render_template, request
import time
import arrow
import logging

from tesazure import config
from tesazure.assets import assets
from tesazure.auth import auth
from tesazure.commands import create_db, drop_db, populate_db, recreate_db
from tesazure.database import db
from tesazure.extensions import lm, migrate, bcrypt, babel, limiter, compute_backend, monitor, celery, jwt_validator, key_vault
from flask_keyvault.exceptions import KeyVaultAuthenticationError
from tesazure.user import user
from tesazure.tesapi import tesapi
from tesazure.provisionerapi import provisionerapi
from tesazure.utils import url_for_other_page


def create_app(config=config.base_config):
    """Returns an initialized Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config)

    register_extensions(app)
    register_blueprints(app)
    register_jinja_env(app)
    register_commands(app)

    load_keyvault_config(app)
    validate_config(app)

    def get_locale():
        """Returns the locale to be used for the incoming request."""
        return request.accept_languages.best_match(config.SUPPORTED_LOCALES)

    if babel.locale_selector_func is None:
        babel.locale_selector_func = get_locale

    @app.before_request
    def before_request():
        """Prepare some things before the application handles a request."""
        g.request_start_time = time.time()
        g.request_time = lambda: '%.5fs' % (time.time() - g.request_start_time)
        g.pjax = 'X-PJAX' in request.headers

    @app.route('/', methods=['GET'])
    def index():
        """Returns the applications index page."""
        return render_template('index.html')

    app.logger.info(f'Successfully started {app.config["SITE_NAME"]}.')
    return app


def register_commands(app):
    """Register custom commands for the Flask CLI."""
    for command in [create_db, drop_db, populate_db, recreate_db]:
        app.cli.command()(command)


def register_extensions(app):
    """Register extensions with the Flask application."""
    key_vault.init_app(app)
    db.init_app(app)
    lm.init_app(app)
    bcrypt.init_app(app)
    assets.init_app(app)
    babel.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    compute_backend.init_app(app)
    monitor.init_app(app)
    app.logger.setLevel(logging.DEBUG)
    jwt_validator.init_app(app)
    celery.init_app(app)
    app.celery = celery.celery


def register_blueprints(app):
    """Register blueprints with the Flask application."""
    app.register_blueprint(tesapi, url_prefix='/v1')
    app.register_blueprint(provisionerapi, url_prefix='/provision')
    app.register_blueprint(user, url_prefix='/user')
    app.register_blueprint(auth)


def register_jinja_env(app):
    """Configure the Jinja env to enable some functions in templates."""
    app.jinja_env.globals.update({
        'timeago': lambda x: arrow.get(x).humanize(),
        'url_for_other_page': url_for_other_page,
    })


def load_keyvault_config(app):
    """Attempts to load configuration from Key Vault if configured """
    if app.config.get('KEYVAULT_URL', False):
        keyvault_url = app.config['KEYVAULT_URL']
        prefix = app.config.get('KEYVAULT_SECRETS_PREFIX', '')

        try:
            for item in key_vault.list(keyvault_url):
                secret_name = item.id.split("/secrets/")[-1]  # Get secret name from url
                if secret_name.startswith(prefix):
                    config_name = secret_name.replace("-", "_")[len(prefix):]
                    app.config[config_name] = key_vault.get(keyvault_url, secret_name)
            app.logger.info('Successfully pulled secrets from KeyVault.')
        except KeyVaultAuthenticationError as err:
            app.logger.exception(f'Error authenticating to Azure Key Vault for setting configuration. {err}')


def validate_config(app):
    """Ensures no invalid configuration is present"""
    # TODO: make a pluggable call to compute backend to validate their config
    if app.config['TASK_ACCESS_RESTRICTIONS'] not in [None, 'per-user', 'per-tenant']:
        raise ValueError("Invalid value for TASK_ACCESS_RESTRICTIONS")
    if app.config['COMPUTE_BACKEND'] not in ['mock', 'aks', 'batch']:
        raise ValueError("Invalid value for COMPUTE_BACKEND")
