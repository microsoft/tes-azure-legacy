# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import argparse
import ftplib
import functools
import logging
import os
import paramiko
import posixpath
import pycosio
import requests
import re
import rfc6266
import shutil
import sys
from urllib.parse import urlparse, urljoin, unquote, parse_qs

# FIXME this disables SSL verification
from functools import partialmethod
session = requests.Session
old_request = session.request
session.request = partialmethod(old_request, verify=False)

logger_name = 'cloud_transfer'


def filename_from_url(url):
    """
    Attempt to parse a URL and extract its filename from the path component,
    taking URL encoding into account.
    """
    urlpath = urlparse(url).path
    basename = posixpath.basename(unquote(urlpath))
    if os.path.basename(basename) != basename or unquote(posixpath.basename(urlpath)) != basename:
        # reject '%2f' or 'dir%5Cbasename.ext' on Windows
        raise ValueError("Refusing filename '{basename}' due to possible directory traveral attack")
    return basename


def connect_ftp(url):
    """
    Connects to an FTP server, defaulting to anonymous auth if no credentials
    are provided.
    """
    components = urlparse(url)

    # Initialize connection
    session = ftplib.FTP_TLS() if components.scheme == 'ftps' else ftplib.FTP()
    session.connect(components.hostname, components.port or 21)

    # Login, anonymously if required
    if components.username:
        session.login(components.username, components.password)
    else:
        session.login()

    # Setup secure data connection if necessary
    if isinstance(session, ftplib.FTP_TLS):
        session.prot_p()

    return session


def connect_sftp(url):
    """
    Connects to an SFTP server. Credentials are parsed from the URL, so only
    password authentication is supported at this time.
    """
    components = urlparse(url)
    if not components.username:
        # TODO: This outright hangs if no auth creds are provided, implement timeout
        raise ValueError("Username cannot be empty")

    transport = paramiko.Transport((components.hostname, components.port or 22))
    transport.connect(username=components.username, password=components.password)

    sftp = paramiko.SFTPClient.from_transport(transport)
    return (transport, sftp)

def local_copy(src, dst):
    if not os.path.exists(src):
        logger.warning(f"[local] Skipping copy of '{src}' to '{dst}' because the source does not exist on the local filesystem")
        return False

    try:
        shutil.copy2(src, dst)
        return True
    except Exception:
        logger.exception("File copy failed")
        return False


def download_sftp(url, path):
    if urlparse(url).scheme != 'sftp':
        logger.warning(f"[sftp] Skipping download of '{url}' because of incorrect scheme")
        return False

    transport, sftp = connect_sftp(url)

    components = urlparse(url)
    if os.path.isdir(path):
        local_file = os.path.join(path, filename_from_url(url))
    else:
        local_file = filename_from_url(url)
    sftp.get(components.path, os.path.abspath(local_file))

    sftp.close()
    transport.close()


def download_ftp(url, path):
    # TODO: Implement timeout
    if urlparse(url).scheme not in ['ftp', 'sftp']:
        logger.warning(f"[ftp] Skipping download of '{url}' because of incorrect scheme")
        return False

    session = connect_ftp(url)

    components = urlparse(url)
    if os.path.isdir(path):
        local_file = os.path.join(path, filename_from_url(url))
    else:
        local_file = filename_from_url(url)
    with open(local_file, 'wb') as fh:
        session.retrbinary(f"RETR {components.path}", fh.write)

    session.quit()


def download_http(url, path):
    def filename_from_content_disposition(requests_response):
        """
        Parses the RFC6266 content-disposition header to determine the server-
        suggested filename for content.
        """
        components = urlparse(requests_response.url)
        head, tail = posixpath.split(components.path)
        expected_extension = posixpath.splitext(tail)[1]
        cd = rfc6266.parse_requests_response(requests_response)
        return cd.filename_sanitized(expected_extension.lstrip('.') or 'dat')

    def determine_filename_for_requests(requests_response):
        """
        Determines filename from a response from the 'requests' module. Prefers
        content-disposition when available, falling back to parsing the URL.
        """
        filename = filename_from_content_disposition(requests_response)
        if not filename:
            filename = filename_from_url(requests_response.url)
        return filename

    if urlparse(url).scheme not in ['http', 'https']:
        logger.warning(f"[http] Skipping download of '{url}' because of incorrect scheme")
        return False

    with requests.get(url, allow_redirects=True, stream=True) as response:
        response.raw.read = functools.partial(response.raw.read, decode_content=True)
        if os.path.isdir(path):
            local_file = os.path.join(path, determine_filename_for_requests(response))
        else:
            local_file = path
        with open(local_file, 'wb') as fh:
            shutil.copyfileobj(response.raw, fh)


def download_http_auto(url, path):
    if urlparse(url).scheme not in ['http', 'https']:
        logger.warning(f"[http-auto] Skipping download of '{url}' because of incorrect scheme")
        return False

    # Disabled until we can fix pycosio >8MB
    # provider = cloud_provider_from_url(url)
    # if provider:
    #     return download(url, path, force_handler=provider)
    # else:
    #     return download_http(url, path)

    return download_http(url, path)


def download_amazon_s3(url, path):
    # TODO: Test signed HTTP URLs (does regular http take care of it?)
    if urlparse(url).scheme != 's3':
        logger.warning(f"[amazon-s3] Skipping download of '{url}' because of incorrect scheme")
        return False

    pycosio.copyfile(url, path)


def download_google_storage(url, path):
    """
    Downloads a 'gs://' URI from Google Storage. Assumes that the data is
    publicly accessible without authentication.

    TODO: Support signed URIs
    """
    components = urlparse(url)
    query_string = parse_qs(components.query)
    if components.scheme in ['http', 'https']:
        if 'sig' not in query_string:
            logger.warning(f"[google-storage] Skipping download of '{url}' because of incorrect scheme or missing SAS token")
            return False

    if urlparse(url).scheme != 'gs':
        logger.warning(f"[google-storage] Skipping download of '{url}' because of incorrect scheme")
        return False

    if not components.hostname or not components.path:
        logger.warning(f"[google-storage] Skipping upload to '{url}' because expected a hostname in format of 'gs://bucket/object'")
        return False
    bucket = components.hostname
    object = components.path[1:]  # strip the leading /

    url = urljoin('http://storage.googleapis.com/', posixpath.join(bucket, object))
    return download(url, path)


def download_azure_blob(url, path):
    components = urlparse(url)
    query_string = parse_qs(components.query)
    if components.scheme in ['http', 'https']:
        if 'sig' not in query_string:
            logger.warning(f"[azure-blob] Skipping download of '{url}' because of incorrect scheme or missing SAS token")
            return False

        match = re.match(r'(\w+)\.blob\.(.+)', components.hostname)
        if not match:
            logger.warning(f"[azure-blob] Skipping upload to '{url}' because expected a hostname in format of 'accountname.blob.endpoint_suffix' (e.g. accountname.blob.core.windows.net).")
            return False
        account_name, endpoint_suffix = match.groups()

        # mount the storage so pycosio can detect the URL as backed by Azure
        parameters = {
            'account_name': account_name,
            'endpoint_suffix': endpoint_suffix,
            'sas_token': components.query
        }
        pycosio.mount(storage='azure_blob', storage_parameters=parameters)

        # remove query string from blob_url, pycosio will think it's part of the filename
        blob_url = urljoin(url, urlparse(url).path)

        path_components = urlparse(url).path.strip('/').split('/', 1)
        if len(path_components) == 2 and path_components[1]:
            pycosio.copyfile(blob_url, os.path.abspath(path))
        else:
            logger.warning(f"[azure-blob] Skipping download of '{url}' a specific blob must be specified; operating on whole blob containers is not yet supported.")
            return False
    else:
        logger.warning(f"[azure-blob] Skipping download of '{url}' because of incorrect scheme")
        return False


def upload_sftp(path, url):
    if urlparse(url).scheme != 'sftp':
        logger.warning(f"[sftp] Skipping upload to '{url}' because of incorrect scheme")
        return False

    transport, sftp = connect_sftp(url)

    components = urlparse(url)
    sftp.put(path, components.path)

    sftp.close()
    transport.close()


def upload_ftp(path, url):
    if urlparse(url).scheme not in ['ftp', 'sftp']:
        logger.warning(f"[ftp] Skipping upload to '{url}' because of incorrect scheme")
        return False

    session = connect_ftp(url)

    components = urlparse(url)
    with open(path, 'rb') as fh:
        session.storbinary(f"STOR {components.path}", fh)

    session.quit()


def upload_amazon_s3(path, url):
    # TODO: Implement support for signed HTTP URLs
    if urlparse(url).scheme != 's3':
        logger.warning(f"[amazon-s3] Skipping upload to '{url}' because of incorrect scheme")
        return False
    pycosio.copyfile(path, url)


def upload_google_storage(path, url):
    # TODO: Implement support for signed HTTP URLs
    if urlparse(url).scheme != 'gs':
        logger.warning(f"[google-storage] Skipping upload to '{url}' because of incorrect scheme")
        return False
    pycosio.copyfile(path, url)


def upload_azure_blob(path, url):
    components = urlparse(url)
    query_string = parse_qs(components.query)
    if components.scheme in ['http', 'https']:
        if 'sig' not in query_string:
            logger.warning(f"[azure-blob] Skipping upload to '{url}' because of incorrect scheme or missing SAS token")
            return False

        match = re.match(r'(\w+)\.blob\.(.+)', components.hostname)
        if not match:
            logger.warning(f"[azure-blob] Skipping upload to '{url}' because expected a hostname in format of 'accountname.blob.endpoint_suffix' (e.g. accountname.blob.core.windows.net).")
            return False
        account_name, endpoint_suffix = match.groups()

        # mount the storage so pycosio can detect the URL as backed by Azure
        parameters = {
            'account_name': account_name,
            'endpoint_suffix': endpoint_suffix,
            'sas_token': components.query
        }
        pycosio.mount(storage='azure_blob', storage_parameters=parameters)

        # remove query string from blob_url, pycosio will think it's part of the filename
        path_components = urlparse(url).path.strip('/').split('/', 1)
        if not path_components or not path_components[0]:
            # just the account was given
            logger.warning(f"[azure-blob] Skipping upload to '{url}' because no container was provided")
            return False
        elif len(path_components) == 2 and path_components[1]:
            # full container+blob filename was given
            if os.path.isdir(path):
                for root, dirs, files in os.walk(path, topdown=False):
                    if root.startswith(path):
                        root = root[len(path)+1:]
                    for name in files:
                        blob_url = urljoin(url, posixpath.join(urlparse(url).path, root, name))
                        pycosio.copyfile(os.path.join(path, root, name), blob_url)
            else:
                blob_url = urljoin(url, urlparse(url).path)
                pycosio.copyfile(path, blob_url)
        else:
            # container without blob filename was given
            container = urlparse(url).path[1:]
            filename = posixpath.basename(path)

            if os.path.isdir(path):
                for root, dirs, files in os.walk(path, topdown=False):
                    if root.startswith(path):
                        root = root[len(path)+1:]
                    for name in files:
                        print(root, name)
                        blob_url = urljoin(url, posixpath.join(urlparse(url).path, root, name))
                        pycosio.copyfile(os.path.join(path, root, name), blob_url)
            else:
                blob_url = urljoin(url, posixpath.join(container, filename))
                pycosio.copyfile(path, blob_url)
    else:
        logger.warning(f"[azure-blob] Skipping upload to '{url}' because of incorrect scheme")
        return False


def upload_http_auto(path, url):
    if urlparse(url).scheme not in ['http', 'https']:
        logger.warning(f"[http-auto] Skipping upload to '{url}' because of incorrect scheme")
        return False

    provider = cloud_provider_from_url(url)
    if provider:
        return upload(path, url, force_handler=provider)
    else:
        logger.warning(f"[http-auto] Skipping upload to '{url}' because no cloud provider's URL could be detected")
        return False


def cloud_provider_from_url(url):
    # Detect cloud provider given the URL
    query_string = parse_qs(urlparse(url).query)
    if 'sv' in query_string and 'sig' in query_string:
        logger.debug(f"[auto] Detected Azure SAS URI for '{url}'")
        return 'blob'
    elif 'X-Amz-Credential' in query_string:
        logger.debug(f"[auto] Detected Amazon S3 presigned URI for '{url}'")
        return 's3'
    elif 'GoogleAccessId' in query_string:
        logger.debug(f"[auto] Detected Google Storage signed URL for '{url}'")
        return 'gs'
    else:
        logger.debug(f"[auto] Could not detect cloud provider for '{url}'")
        return False


def download(url, path, force_handler=None):
    """
    Downloads a remote file to local storage. Assumes that path is a local
    directory, and files are downloaded preserving their remote filenames.
    """
    logger = logging.getLogger(logger_name)

    if os.path.exists(path):
        if not os.path.isdir(path):
            logger.warning(f"Skipping download of '{url}': destination '{path}' exists and is not a directory")
            return False
    else:
        dirname = os.path.dirname(path)
        if dirname and not os.path.isdir(dirname):
            try:
                os.makedirs(dirname)
                logger.debug(f"Created directory '{dirname}'")
            except Exception:
                logger.exception(f"Skipping download of '{url}': failed to create destination directory '{dirname}'")
                return False

    handlers = {
        'sftp': download_sftp,
        'ftp': download_ftp,
        'ftps': download_ftp,
        'http': download_http_auto,
        'https': download_http_auto,
        'blob': download_azure_blob,
        's3': download_amazon_s3,
        'gs': download_google_storage,
        '': local_copy
    }

    if force_handler:
        handler = force_handler
    else:
        handler = urlparse(url).scheme

    if handler not in handlers:
        logger.error(f"Skipping download of '{url}': no implemented handlers for '{handler}'")
        return False

    logger.debug(f"Starting downloading of '{url}' to '{path}'")
    try:
        handlers[handler](url, path)
    except FileNotFoundError:
        logger.warning(f"Skipping download of '{url}' because it was not found on the remote server")
    except PermissionError:
        logger.warning(f"Skipping download of '{url}' because of insufficient permissions.")
    except Exception:
        logger.exception(f"Download of '{url}' to '{path}' failed")


def upload(path, url, force_handler=None):
    """
    Uploads a local file or directory to remote storage. Assumes that path is a
    local file or directory, and determines the most upload appropriate handler
    given the url type.
    """
    logger = logging.getLogger(logger_name)

    if not os.path.exists(path):
        logging.error(f"Skipping upload to '{url}': '{path}' does not exist")

    handlers = {
        'sftp': upload_sftp,
        'ftp': upload_ftp,
        'ftps': upload_ftp,
        'https': upload_http_auto,
        'blob': upload_azure_blob,
        's3': upload_amazon_s3,
        'gs': upload_google_storage,
        '': local_copy
    }

    if force_handler:
        handler = force_handler
    else:
        handler = urlparse(url).scheme

    if handler not in handlers:
        logger.error(f"Skipping upload of '{url}': no implemented handlers for '{handler}'")
        return False

    logger.debug(f"Starting upload of '{path}' to '{url}'")
    try:
        handlers[handler](path, url)
    except PermissionError:
        logger.exception(f"Skipping upload of '{path}' to '{url}' because of insufficient permissions")
    except Exception:
        logger.exception(f"Upload of '{path}' to '{url}' failed")


# This code runs only if file is executed directly as a script
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(logger_name)

    parser = argparse.ArgumentParser(description="Cloud file transfer utility")
    parser.add_argument('-d', '--download', action='append', nargs=2, default=[], metavar=('url', 'name'), help='Downloads a URL to path specified')
    parser.add_argument('-u', '--upload', action='append', nargs=2, default=[], metavar=('name', 'url'), help='Uploads specified path to the indicated URL')
    parser.add_argument('-e', '--on-error', choices=["continue", "exit"], help='Action to take upon operation failure', default="exit")  # FIXME support this
    parser.add_argument('-f', '--force', action="store_true", help='Overwrite existing files', default="exit")  # FIXME support this
    parser.add_argument('-v', '--verbose', action="store_true", help='Enables debug messages')

    options = parser.parse_args()

    if options.verbose:
        logger.setLevel(logging.DEBUG)

    options = parser.parse_args()

    if not options.download and not options.upload:
        parser.print_help()
        sys.exit(1)

    for (url, path) in options.download:
        download(url, path)

    for (path, url) in options.upload:
        upload(path, url)

    logging.shutdown()
