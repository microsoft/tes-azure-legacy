# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from flask import Blueprint

user = Blueprint('user', __name__, template_folder='templates')

from . import views  # noqa: F401
