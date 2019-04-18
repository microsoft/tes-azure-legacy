# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from flask import current_app
from .aks import AksBackend
from .batch import AzureBatchEngine
from .mock import MockBackend

try:
    from flask import _app_ctx_stack as ctx_stack
except ImportError:
    from flask import _request_ctx_stack as ctx_stack

BACKENDS = {
    'aks': AksBackend,
    'batch': AzureBatchEngine,
    'mock': MockBackend
}


class ComputeBackend:
    compute_backend = None

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        app.config.setdefault('COMPUTE_BACKEND', 'batch')
        app.teardown_appcontext(self.teardown)

    def teardown(self, exception):
        if hasattr(ctx_stack.top, 'compute_backend'):
            pass

    @property
    def backend(self):
        compute_backend = current_app.config.get('COMPUTE_BACKEND')
        ctx = ctx_stack.top
        if ctx is not None:
            if not hasattr(ctx, 'compute_backend'):
                if compute_backend not in BACKENDS:
                    raise ValueError(f"Not a valid backend: {compute_backend}")
                ctx.compute_backend = BACKENDS[compute_backend]()
            return ctx.compute_backend
