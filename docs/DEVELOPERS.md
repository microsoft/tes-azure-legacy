# Developing on the tes-azure API server <!-- omit in toc -->
## Table of Contents <!-- omit in toc -->
<!--
Generated with the Markdown All in One extension by Yu Zhang.
https://marketplace.visualstudio.com/items?itemName=yzhang.markdown-all-in-one
-->
- [Design documentation](#design-documentation)
  - [Configuration of Flask application](#configuration-of-flask-application)
  - [Backends](#backends)
    - [Batch backend](#batch-backend)
    - [AKS Backend](#aks-backend)
- [Setup - Docker (recommended)](#setup---docker-recommended)
  - [Populate database tables](#populate-database-tables)
  - [Generate assets](#generate-assets)
  - [Customizing configuration](#customizing-configuration)
  - [Debugging the containerized app with VS Code](#debugging-the-containerized-app-with-vs-code)
- [Setup - local environment (advanced)](#setup---local-environment-advanced)
  - [Local environment setup](#local-environment-setup)
  - [Running Flask locally](#running-flask-locally)
  - [Debugging locally with VS Code](#debugging-locally-with-vs-code)
  - [Testing locally](#testing-locally)
    - [Running tox locally](#running-tox-locally)
    - [Running unit tests locally](#running-unit-tests-locally)
- [Testing the API (i.e. submitting tasks)](#testing-the-api-ie-submitting-tasks)
- [Creating database migrations](#creating-database-migrations)
- [Coding Conventions](#coding-conventions)
  - [Imports](#imports)
  - [Unit testing conventions](#unit-testing-conventions)
    - [Use 'app' and 'mocker' fixtures](#use-app-and-mocker-fixtures)
    - [Avoid `assert_*` convenience methods on mock objects](#avoid-assert_-convenience-methods-on-mock-objects)
    - [Mocks with Flask app configuration](#mocks-with-flask-app-configuration)
    - [Use .return_value for chained mocks](#use-return_value-for-chained-mocks)

## Design documentation
The [design documentation](DESIGN.md) file has some detail as to how the API server hands off tasks to compute backends and performs file marshalling.


### Configuration of Flask application
Although some config defaults are provided in `config.py`, we do not recommend editing this file. Instead, to override the `FOO` configuration parameters simply set `APP_FOO` as an environment variable and Flask will automatically pick it up.


### Backends
#### Batch backend
The Batch backend will create a pool per TES Task submitted against the API and then run one task on the pool for each executor supplied in the TES Task.

When debugging, fix your requests to a single batch pool by setting the `DEBUG_HARDCODED_BATCH_POOL_ID` parameter to your Batch pool ID. If this variable is not set, a new pool will be created for each TES task (preferred in production for data isolation)
Pools when Flask uses the dev environment will have a SSH user added automatically.

#### AKS Backend
AKS backend implementation to come at a later date.


## Setup - Docker (recommended)
A Docker Compose file is available to quickly get setup with the API server. If you do not have [Docker](https://www.docker.com/), install it now.

Docker will map your local directory into the container so that local changes are automatically reflected (and reload) in the Flask application running inside the container.

To run the Flask app and all dependencies:
```bash
docker-compose up -d
```

The API is now accessible locally at [http://localhost:5000](http://localhost:5000), but additional configuration (below) is required before you submit a task.


### Populate database tables
The database is run locally as a PostgreSQL container. It uses a persistent volume, so the database only needs to be created on the initial run (or after destroying and re-creating the `postgres` container). To seed the database, run:
```bash
docker-compose run --rm app flask create-db
docker-compose run --rm app flask db stamp head
```


### Generate assets
The web portal will be missing styling until local assets are generated. You can do so at any time by running:
```bash
yarn install --modules-folder ./tesazure/static/node_modules
docker-compose run --rm app flask assets build
```


### Customizing configuration
If you want to change configuration (such as mapped ports, or Flask app configuration) you can do so by creating a docker compose override file, `docker-compose.override.yml`, with the following contents:
```
version: "3.7"
services:
  app:
    environment:
      - FLASK_APP=serve.py
      - FLASK_ENV=development
      - APP_COMPUTE_BACKEND=batch
      ...
      - PYTHONUNBUFFERED=1 # https://github.com/pallets/flask/issues/1420
```

Docker Compose will automatically read in the overrides. This avoids accidental check-in of secrets into Git.


### Debugging the containerized app with VS Code
We recommend [Visual Studio Code](https://code.visualstudio.com/)'s remote debugging feature [(more details here)](https://code.visualstudio.com/docs/python/debugging#_remote-debugging).

You will need to setup a configuration inside ```.vscode/launch.json``` to tell Code how to connect to the debugger running inside the container. Below is a working configuration for debugging.

```json
{
    "name": "Docker + Flask (Remote Debug)",
    "type": "python",
    "request": "attach",
    "port": 5050,
    "host": "localhost",
    "pathMappings": [
        {"localRoot": "${workspaceFolder}", "remoteRoot": "/var/www/tes-azure"}
    ],
    "debugOptions":  [
        "RedirectOutput"
    ]
}
```

Visual Studio Code will not start the containers for you, so make sure to run through the above setup steps first.

If you make a large change to the application (such as adding packages to `requirements.txt` for example), you will need to **rebuild and restart the containers** like this:

```bash
docker-compose build
docker-compose up -d
```


## Setup - local environment (advanced)
### Local environment setup
We highly recommend using virtual environments with [pipenv](https://pipenv.readthedocs.io/en/latest/). Once installed, setup your local environment with a simple:
```bash
pipenv install -d
```

You will need to bring your own postgresql server and configure the `SQLALCHEMY_DATABASE_URI` configuration variable accordingly. Edit Copy `api-server.env.sample` to `api-server.env` and edit it:
```bash
FLASK_APP=serve.py
...
APP_SQLALCHEMY_DATABASE_URI=...
```

Source those environment variables into your current shell:
```
set -o allexport
. api-server.env
set +o allexport
```

Seed the database and build assets directly:
```bash
pipenv run flask create-db
pipenv run flask db stamp head
yarn install --modules-folder ./tesazure/static/node_modules
pipenv run flask assets build
```


### Running Flask locally
Source your environment variables (see above) then kick it off with:
```bash
pipenv run flask run
```
The API is now available at [http://localhost:5000](http://localhost:5000).


### Debugging locally with VS Code
Add the following to your JSON file:
```json
{
  "name": "Flask (Remote Debug)",
  "type": "python",
  "request": "attach",
  "port": 5050,
  "host": "localhost",
  "debugOptions":  [
      "RedirectOutput"
  ]
}
```
You will then need to start Flask with the `ptvsd` debugger instead:
```bash
pipenv run python -m ptvsd --host 0.0.0.0 --port 5050 -m flask run --host 0.0.0.0 --port 5000 --no-debugger --no-reload`
```

### Testing locally
To test locally, install dependencies into your virtual environment:
```bash
pipenv install -d
```

#### Running tox locally
Running tox will build a virtual environment to run tests and check code style.

Tox is currently configured to test against the versions of Python available on Azure DevOps CI/CD build agents. If you have a different version installed locally, simply edit tox.ini:
```
envlist = py37,pep8
...
basepython = python3.7
...
```

If you add a dependency, remember to refresh the Tox environment with `pipenv run tox -r`


#### Running unit tests locally
Run `pipenv run pytest` to start unit tests. A specific test file's path can be specified to only run that test.

If you are debugging and want to prevent output capture (i.e. to permit `print()` calls in unit tests, use the `-s` argument).


## Testing the API (i.e. submitting tasks)
Use [Postman](https://www.getpostman.com/) to submit requests against the API, such as for POST  [http://localhost/v1/tasks](http://localhost/v1/tasks) to create a task. You will find the JSON body for sample/reference TES tasks in the [resources](../resources) folder.

See also the [task-execution-schemas swagger documentation](https://petstore.swagger.io/?url=https://raw.githubusercontent.com/ga4gh/task-execution-schemas/master/task_execution.swagger.json) for more details on API endpoints and expected parameters.

## Creating database migrations
Database migrations can be auto-generated using [Flask-Migrate](https://flask-migrate.readthedocs.io/en/latest/).

Check the current migration:
```bash
pipenv run flask db current
```

After updating the database models, re-create the tables and auto-generate a new migration:
```bash
pipenv run flask db migrate -m "add foo table"
```
Note that the message gets serialized into the migration filename (e.g. `somehash_add_foo_table.py`) so keep it descriptive of the changes but brief.

Upgrade an old DB to the current migration revision:
```bash
pipenv run flask db upgrade
```

Tell Flask that the current DB is fully upgraded:
```bash
pipenv run flask db stamp
```

## Coding Conventions
### Imports
1. Imports should always be done at the top of a file. Group imports into the following three groups, alphabetically sorted:
    - Standard library imports
    - Third-party imports
    - Application-specific imports

    Within each group, all `import foo` lines should come first followed by all `from foo import bar`.

    For example:

    ```python
    import json
    import uuid
    from datetime import datetime, timedelta

    import azure.batch.batch_service_client as batch
    import azure.batch.batch_auth as batchauth
    import azure.batch.models as batchmodels
    from azure.storage.blob import BlockBlobService, BlobPermissions
    from flask import current_app

    from .. import common as backend_common
    from ... import models as tesmodels
    ```

2. Prefer absolute references when reasonable (for example, `datetime.timedelta` instead of `timedelta`).

3. Import top-level Azure SDK modules and reference relatively from there.

    Many pieces of the code uses the Azure SDKs, which can have naming conflicts (e.g. tes-azure has its own `models` module, as do many of the Azure sub-modules like `azure.batch.models`). To avoid naming conflicts, we recommend importing only top-level Azure SDK packages:
    ```python
    import azure.batch as azbatch
    import azure.batch.batch_auth as azbatch_auth
    import azure.storage as azstorage
    ```

    This way `models`, unless otherwise noted, always refers to the TES application models. Azure SDK models can be referenced easily via e.g. `azbatch.models`.

With the above guidance, the first example can be cleaned up significantly:

```python
import datetime
import uuid

import azure.batch as azbatch
import azure.batch.batch_auth as azbatch_auth
import azure.storage.blob as azblob
from flask import current_app

from .. import common as backend_common
from ... import models as tesmodels
```

and it becomes very clear which models are in use:
```python
# Default state inheritance, with 'active' as QUEUED unless we get more detailed into from tasks
state_map = {
    azbatch.models.JobState.active: tesmodels.TaskStatus.QUEUED,
    azbatch.models.JobState.completed: tesmodels.TaskStatus.COMPLETE,
    azbatch.models.JobState.deleting: tesmodels.TaskStatus.CANCELED,
    azbatch.models.JobState.disabled: tesmodels.TaskStatus.PAUSED,
    azbatch.models.JobState.disabling: tesmodels.TaskStatus.PAUSED,
    azbatch.models.JobState.enabling: tesmodels.TaskStatus.PAUSED,
    azbatch.models.JobState.terminating: tesmodels.TaskStatus.CANCELED,
}
tes_task.state = state_map.get(batch_job.state, tesmodels.TaskStatus.UNKNOWN)
```

### Unit testing conventions
#### Use 'app' and 'mocker' fixtures
Application that needs Flask app context should request the `app` fixture and monkey-patching mocks should be done via the `mocker` fixture:

```python
from tesazure.extensions import compute_backend


class TestCase:
    def test_mything_scenariodescriptor(self, app, mocker):
        mocked_batch_client = mocker.patch('azure.batch.batch_service_client.BatchServiceClient')
        # this call to the flask extension needs app context
        compute_backend.backend.foo()
```

#### Avoid `assert_*` convenience methods on mock objects
Never use the mock built-in methods to create assertions, Yelp did a great write-up on why in their post [assert_called_once: Threat or Menace](https://engineeringblog.yelp.com/2015/02/assert_called_once-threat-or-menace.html). Essentially, mock methods will happily carry on if you make a typo or if the API changes in the future.

To ensure correctness, use `assert()` checks on mock properties like `mock.call_args`, `mock.call_args_list`, `mock.mock_calls`, and `mock.call_count`.

Note that `mock.mock_calls` and `mock.call_args` return a `mock._Call` object which is a wrapped tuple object. The correct way to interact with it is `call[0]` which returns a tuple of the value args passed (i.e. suitable for use with `*args`) and `call[1]` returns the keyword args passed (i.e. suitable for use with `**kwargs`)

For example:
```python
mocked_object = mocker.patch('RestThing.client.ThingClient')
args, kwargs = mocked_object.do_something.call_args
assert(isinstance(args[0], MyClass))
```

#### Mocks with Flask app configuration
If you need to mock configuration, do not attempt to edit app.config directly. This will fail for extensions like the backend, which initialize only at app creation time. Instead, mutate the configuration via pytest decorator:
```python
@pytest.mark.options(CONFIG_VAR='value')
```

#### Use .return_value for chained mocks
When a mocked class is instantiated (common in the Azure SDKs), be sure to use mock chaining (`mocked_client.return_value`) to ensure you retrieve the `Mock` instance created as a result of the instantiation. For example the `BatchServiceClient` might be mocked, but running `client = BatchServiceClient()` results in **a new mock** (that `mocked_client.return_value` returns).

If you do not do mock chaining per above, [call tracking behavior will fail](https://stackoverflow.com/a/54719015) since e.g. `BatchServiceClient().job.add` is actually being called on the new mock from instantiation, not `mocked_client`.

Here's a concrete example of what **won't** work:
```python
def test_initialize_pool(self, app, mocker):
    mocked_batch_client = mocker.patch('azure.batch.batch_service_client.BatchServiceClient')
    compute_backend.backend._initializePool()
    # fails, since we are operating on the mocked client class, not the Mock instance consumed by the target code
    assert(mocked_batch_client.pool.add.call_count == 1)
```

This example **does** work:
```python
def test_initialize_pool(self, app, mocker):
    mocked_batch_client = mocker.patch('azure.batch.batch_service_client.BatchServiceClient')
    compute_backend.backend._initializePool()
    # this retrieves the new Mock instance returned by BatchServiceClient() in the target code, so it succeeds
    assert(mocked_batch_client.return_value.pool.add.call_count == 1)
```
