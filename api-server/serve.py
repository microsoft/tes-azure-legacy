# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from tesazure import create_app, config

app = create_app(config.dev_config)
