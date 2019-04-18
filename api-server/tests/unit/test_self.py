# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

try:
    from flask import _app_ctx_stack as ctx_stack
except ImportError:
    from flask import _request_ctx_stack as ctx_stack

from tesazure.models import TesTask

"""
This file was created to ensure that the test fixtures are working correctly and
no side-effects exist between unit tests.
"""


class TestCase:
    def test_sideeffects_appstack(self):
        """Sets a value in app context..."""
        ctx_stack.top.foo = 'bar'

    def test_sideeffects_appstack_after(self):
        """... and ensures a new context is present for future tests"""
        assert(getattr(ctx_stack.top, 'foo', None) is None)

    def test_sideeffects_db(self, session):
        """Adds an entry to the database..."""
        task = TesTask()
        task.backend_id = "test-backend-1"
        task.tenant_id = "expected-audience"
        task.user_id = "user1"
        session.add(task)
        session.commit()
        assert(len(TesTask.query.all()) == 1)

    # FIXME: if 'session' is not explicitly asked for, a connection is never
    # opened so TesTask.query.all() fails
    def test_sideeffects_db_after(self, session):
        """... and ensures that it was rolled back for other tests"""
        assert(len(TesTask.query.all()) == 0)

    def test_sideeffects_session(self, session):
        """Adds an object to the SQLAlchemy session..."""
        task = TesTask()
        task.backend_id = "test-backend-1"
        task.tenant_id = "expected-audience"
        task.user_id = "user1"
        session.add(task)

    def test_sideeffects_session_after(self, session):
        """... and ensures that the session was expired between tests"""
        session.commit()
        assert(len(TesTask.query.all()) == 0)
