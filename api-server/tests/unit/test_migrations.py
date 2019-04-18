# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from alembic.config import Config
from alembic import command

from tesazure import db as _db


class TestCase:
    def disabled_test_migrations(self, session):
        """Applies all alembic migrations."""
        # FIXME: disabled as we did not provide initial migrations for tes_task table structure
        # FIXME: suspicion that drop_all() may affect future tests
        # FIXME: render_as_batch is configured in env.py but alter columns are still failing on sqlite in-memory
        _db.drop_all()

        alembic_cfg = Config('./migrations/alembic.ini')
        alembic_cfg.attributes['connection'] = session.get_bind()
        alembic_cfg.attributes['render_as_batch'] = True
        alembic_cfg.set_main_option("script_location", "migrations")
        command.upgrade(alembic_cfg, "head")
