# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import json
import jwt
import re
import requests
from functools import wraps

from flask import abort, request
from werkzeug.local import LocalProxy

try:
    from flask import _app_ctx_stack as ctx_stack
except ImportError:
    from flask import _request_ctx_stack as ctx_stack

claims = LocalProxy(lambda: getattr(ctx_stack.top, 'claims', {}))


class JwtValidator:
    jwks_uri = None
    audience = None
    verify = True

    def __init__(self, jwks_uri=None, audience=None, issuer=None, verify=True):
        self.configured = False
        if jwks_uri and audience:
            self.configure(jwks_uri, audience, verify)

    def init_app(self, app):
        self.configure(app.config['AAD_JWKS_URI'], app.config['AAD_AUDIENCE'], f'https://sts.windows.net/{app.config["AAD_TENANT_ID"]}/', app.config['AAD_VERIFY'])

    def configure(self, jwks_uri=None, audience=None, issuer=None, verify=True):
        self.jwks_uri = jwks_uri
        self.audience = audience
        self.issuer = issuer
        self.verify = verify
        self.configured = True

    def validate(self, scopes=[]):
        if not self.verify:
            return True

        if not self.configured:
            abort(500)

        auth_header = request.headers.get("authorization")
        if not auth_header:
            abort(401)
        try:
            (auth_type, auth_credentials) = re.split(r"\s+", auth_header, 1)
        except ValueError:
            abort(403)

        if auth_type.lower() != 'bearer':
            abort(403)

        try:
            ctx_stack.top.claims = JwtValidator.decode_jwt(self.jwks_uri, auth_credentials, audience=self.audience, issuer=self.issuer)
        except Exception:
            raise
            return False
        return True if claims else False

    def protect(self, scopes=[]):
        """
        Decorator for flask routes: @jwt_validator_instance.protect() or
        @jwt_validator_instance.protect(["foo", "bar"]) for specific scopes
        """
        def decorator(f):
            @wraps(f)
            def inner_decorator(*args, **kwargs):
                if not self.validate(scopes=scopes):
                    abort(401)
                return f(*args, **kwargs)
            return inner_decorator
        return decorator

    @staticmethod
    def decode_jwt(jwks_uri, token, **kwargs):
        token_header = jwt.get_unverified_header(token)
        signing_keys = JwtValidator._get_public_keys_by_kid_from_jwks_uri(jwks_uri)
        token_key = signing_keys[token_header['kid']]
        return jwt.decode(token, key=token_key, algorithms=token_header['alg'], **kwargs)

    @staticmethod
    def _get_public_keys_by_kid_from_jwks_uri(public_keys_url):
        """Gets the set of JWKs from the specified URL (see https://tools.ietf.org/html/rfc7517#section-5)

        Returns a map of of the RSA public keys by key ID ('kid')
        """
        response = requests.get(public_keys_url)
        jwks = response.json()
        return {key_dict['kid']: jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_dict)) for key_dict in jwks['keys']}
