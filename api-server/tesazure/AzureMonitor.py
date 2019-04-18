# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from applicationinsights.flask.ext import AppInsights
from opencensus.trace import config_integration
from opencensus.trace.exporters.ocagent import trace_exporter
from opencensus.trace import tracer as tracer_module
from opencensus.trace.propagation.trace_context_http_header_format import TraceContextPropagator
from opencensus.trace.exporters.transports.background_thread import BackgroundThreadTransport
from opencensus.trace.ext.flask.flask_middleware import FlaskMiddleware
import os


class AzureMonitor(object):
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        INTEGRATIONS = ['httplib', 'sqlalchemy', 'requests']

        export_LocalForwarder = trace_exporter.TraceExporter(
            # FIXME - Move to config
            service_name=os.getenv('SERVICE_NAME', 'python-service'),
            endpoint=os.getenv('OCAGENT_TRACE_EXPORTER_ENDPOINT'),
            transport=BackgroundThreadTransport
        )

        tracer = tracer_module.Tracer(exporter=export_LocalForwarder, propagator=TraceContextPropagator())
        config_integration.trace_integrations(INTEGRATIONS, tracer=tracer)

        # Hookup OpenCensus to Flask
        FlaskMiddleware(app=app, exporter=export_LocalForwarder)

        # Also hookup AppInsights for logging
        AppInsights(app)

    def teardown(self, exception):
        pass
