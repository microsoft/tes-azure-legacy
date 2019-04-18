# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from datetime import datetime, timedelta
from flask import current_app
from flask_celeryext.app import current_celery_app
from flask_celeryext import RequestContextTask

from tesazure.models import TaskStatus, TesTask
from tesazure.extensions import compute_backend
from tesazure.database import db


def send_registration_email(uid, token):
    """Sends a registratiion email to the given uid."""
    raise NotImplementedError


@current_celery_app.task(base=RequestContextTask)
def cleanup_tasks():
    """
    Cleans up TES tasks that fulfill one of the four cases:
      - Are in backend but haven't been updated in TASK_BACKEND_CLEANUP_HOURS hours
      - Are in database but haven't been updated in TASK_DATABASE_CLEANUP_HOURS hours
      - Have been running longer than TASK_EXECUTION_TIMEOUT_HOURS
      - Are running but don't exist in backend
    """
    # Backend cleanup must occur before database cleanup
    if current_app.config['TASK_BACKEND_CLEANUP_HOURS'] > current_app.config['TASK_DATABASE_CLEANUP_HOURS']:
        # FIXME - use a more specific exception
        raise Exception("TASK_BACKEND_CLEANUP_HOURS must be less than or equal to TASK_DATABASE_CLEANUP_HOURS.")

    # Cleanup backend tasks
    tasks = TesTask.query.filter(TesTask.updated_ts <= (datetime.utcnow() - timedelta(hours=current_app.config['TASK_BACKEND_CLEANUP_HOURS'])))
    for task in tasks:
        if (compute_backend.backend.get_task(task.backend_id)):
            compute_backend.backend.cancel_task(task.backend_id)

    # Cleanup database
    tasks = TesTask.query.filter(TesTask.updated_ts <= (datetime.utcnow() - timedelta(hours=current_app.config['TASK_DATABASE_CLEANUP_HOURS'])))
    for task in tasks:
        task.delete()

    # Clean orphans & stop long running tasks
    tasks = TesTask.query.filter(TesTask.state == TaskStatus.RUNNING).all()

    for task in tasks:
        if (compute_backend.backend.get_task(task.backend_id) is False):
            task.state = TaskStatus.UNKNOWN  # Orphans map to status Unknown
        elif (task.updated_ts < datetime.utcnow() - timedelta(hours=current_app.config['TASK_EXECUTION_TIMEOUT_HOURS'])):
            compute_backend.backend.cancel_task(task.backend_id)
            task.state = TaskStatus.CANCELED

    db.session.commit()
