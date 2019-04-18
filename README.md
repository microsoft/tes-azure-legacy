# TES API Server for Azure Compute

## Overview
[Global Alliance for Genomics and Health (GA4GH)](https://www.ga4gh.org/) is an organization that sets policies and technical standards related to genomics data sharing and processing. They release the [Task Execution Schema (TES)](https://github.com/ga4gh/task-execution-schemas), an API contract to permit cloud-agnostic execution of tasks in the cloud.

The TES API Server for Azure Compute provides a GA4GH TES (Task Execution Schema) compatible API and leverages Azure compute services on its backend for task execution. Today workloads can be performed by Azure Batch, and Azure Kubernetes Services (AKS) support is planned.

The TES endpoint can be used standalone, or integrated into various existing workflow tools such as [Cromwell](https://cromwell.readthedocs.io/en/stable/backends/TES/) or [cwl-tes](https://github.com/common-workflow-language/cwl-tes).

## Features
*	Plugin-based architecture for compute backends with Azure Batch supported today
*	Support for standalone operation or authentication with multiple users (via AAD+OAuth), with per-tenant or per-user task isolation
*	Automatic file transfer of task inputs and outputs (reads from Azure Blob, HTTP, HTTPS, SFTP, FTP+SSL, AWS S3, GCP and writes to Azure Blob, SFTP, FTP+SSL)
*	Key Vault stores all sensitive secrets
*	App logging & tracing sent to Application Insights
*	Simple, Docker-based deployment provisioned with Terraform; backend resources are also automatically provisioned through a REST API
*	Tasks run using containers sourced from Docker hub or a private container registry


## Components
| Component Name | Purpose |
|----------|-------------|
| api-server | Flask-based API implementing TES with multiple modular Azure compute backends |
| container-filetransfer | Provides input/output file marshalling for containers running in the backend compute |
| local-forwarder | Local telemetry forwarded for Application Insights |


## Documentation
* [User guide](docs/USAGE.md) - getting started deploying and using the TES API Server for Azure Compute
* [Developer documentation](docs/DEVELOPERS.md) - developing & local environment setup
* [Design docs](docs/DESIGN.md) - architecture description and design decisions

## About
### Authors
The project and the code base is maintained by Microsoft Commercial Engineering (CSE) Healthcare Industry team on a best-effort basis.

### Intended Use
Please note that the code provided in this repository is intended as a code sample for kickstarting development, and that you may need to customize and test the code for your intended use case. It does not constitute a product officially supported by Microsoft nor bound to an SLA. If you intend to leverage these code samples, it is your responsibility to deploy them in a manner consistent with the availability and uptime requirements of your project.

### License
Licensed under the [MIT](LICENSE.md) License.

## Issues and feature requests
If you have found any issues, or you want to request a missing feature, please do so by [opening an issue](https://github.com/Microsoft/tes-azure/issues/new).


## Contributing
This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/) and welcomes contributions and suggestions. For more details on contributing, please see the [guidance for contributors](CONTRIBUTING.md).
