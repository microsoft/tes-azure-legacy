# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from flask import Blueprint

provisionerapi = Blueprint('provisionerapi', __name__, template_folder='templates')

from . import api  # noqa: F401
