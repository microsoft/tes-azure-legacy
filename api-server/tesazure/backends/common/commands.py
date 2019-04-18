# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import posixpath
import shlex


def generate_input_download_command(url, path):
    """Outputs command to download 'url' to 'path'"""
    return f"python /home/ft/cloud-transfer.py -v -d {shlex.quote(url)} {shlex.quote(path)}"


def generate_input_download_commands(task):
    """Outputs list of commands to download task inputs"""
    cli_commands = []
    for input in task.inputs:
        if input.content is not None:
            continue  # spec says 'url' must be ignored if 'content' is populated
        cli_command = generate_input_download_command(input.url, input.path)
        cli_commands.append(cli_command)
    return cli_commands


def generate_output_upload_command(path, url):
    """Outputs command to upload 'url' to 'path'"""
    return f"python /home/ft/cloud-transfer.py -v -u {shlex.quote(path)} {shlex.quote(url)}"


def generate_output_upload_commands(task):
    """Outputs list of commands to upload task outputs"""
    cli_commands = []
    for output in task.outputs:
        cli_command = generate_output_upload_command(output.path, output.url)
        cli_commands.append(cli_command)
    return cli_commands


def generate_copy_commands(source, destination):
    """
    Generates commands to copy source to destination, creating destination
    directories as necessary
    """
    commands = []

    # Create parent dir if necessary
    destination_dirname = posixpath.dirname(destination)
    if destination_dirname:
        commands.append(f"mkdir -p {shlex.quote(destination_dirname)}")

    # Copy Batch's log to desired location
    # FIXME: Source should be shell quoted - ctrl+f 'quoted' comment in batch backend
    commands.append(f"cp -f {source} {shlex.quote(destination)}")
    return commands
