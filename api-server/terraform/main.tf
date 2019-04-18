#########################
# Setup 
#########################

# Authenticates using Azure CLI
provider "azurerm" {  }
data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "rg" {
  name     = "${var.resource_group_name}"
  location = "${var.resource_group_location}"
}

# Random number is used for resource names to avoid global collisions with other tes-azure deployments
resource "random_integer" "ri" {
  min = 10000
  max = 99999
}

resource "azurerm_application_insights" "default" {
  name                            = "tesazure-appinsights-${random_integer.ri.result}"
  resource_group_name = "${azurerm_resource_group.rg.name}"
  location                         = "${azurerm_resource_group.rg.location}"
  application_type           = "Web"

  depends_on = [
    "azurerm_resource_group.rg"
  ]
}

#########################
# Database
#########################
resource "random_string" "postgres_password" {
  length = 16
  special = true
}

resource "azurerm_postgresql_server" "sql" {
  name                             = "tesazure-postgresql-${random_integer.ri.result}"
  location                         = "${azurerm_resource_group.rg.location}"
  resource_group_name = "${azurerm_resource_group.rg.name}"

  sku {
    name     = "${var.postgresql_sku_name}"
    capacity = "${var.postgresql_sku_capacity}"
    tier         = "${var.postgresql_sku_tier}"
    family    = "${var.postgresql_sku_family}"
  }

  storage_profile {
    storage_mb                    = 5120
    backup_retention_days  = 7
    geo_redundant_backup = "Disabled"
  }

  administrator_login                   = "psqladminun"
  administrator_login_password = "${random_string.postgres_password.result}"
  version                                     = "10.0"
  ssl_enforcement                      = "Enabled"

  depends_on = [
    "azurerm_resource_group.rg"
  ]
}

resource "azurerm_postgresql_database" "db" {
  name                = "tesapi"
  resource_group_name = "${azurerm_resource_group.rg.name}"
  server_name         = "${azurerm_postgresql_server.sql.name}"
  charset             = "UTF8"
  collation           = "English_United States.1252"

  depends_on = [
    "azurerm_postgresql_server.sql"
  ]
}

// Currently will fail because of - https://github.com/MicrosoftDocs/azure-docs/issues/20758
resource "azurerm_postgresql_firewall_rule" "db" {
  name                = "AllowAllWindowsAzureIps"
  resource_group_name = "${azurerm_resource_group.rg.name}"
  server_name         = "${azurerm_postgresql_server.sql.name}"
  start_ip_address    = "0.0.0.0"
  end_ip_address      = "0.0.0.0"

  depends_on = [
    "azurerm_postgresql_server.sql"
  ]
}

locals {
  postgres_connection_string = "postgresql+psycopg2://${azurerm_postgresql_server.sql.administrator_login}${urlencode("@")}${azurerm_postgresql_server.sql.name}:${urlencode(azurerm_postgresql_server.sql.administrator_login_password)}@${azurerm_postgresql_server.sql.name}.postgres.database.azure.com:5432/${azurerm_postgresql_database.db.name}"
}

#########################
# Backend for API task queue
#########################
resource "azurerm_redis_cache" "redis" {
  name                             = "tesazure-broker-${random_integer.ri.result}"
  location                         = "${azurerm_resource_group.rg.location}"
  resource_group_name = "${azurerm_resource_group.rg.name}"
  capacity                        = 0
  family                            = "${var.redis_family}"
  sku_name                    = "${var.redis_sku_name}"
  # FIXME: Figure out how to connect celery to redis over SSL
  enable_non_ssl_port   = true

  redis_configuration {}

  depends_on = [
    "azurerm_resource_group.rg"
  ]
}

locals {
  redis_connection_string = "redis://:${azurerm_redis_cache.redis.primary_access_key}@${azurerm_redis_cache.redis.hostname}:${azurerm_redis_cache.redis.port}"
}

#########################
# Service Principals
#########################
# SPN for multi-container since MSI isn't supported yet
# https://docs.microsoft.com/en-us/azure/app-service/containers/tutorial-multi-container-app#preview-feature-limitations
resource "azuread_application" "tesazure" {
  name = "tesazure"
}
resource "azuread_service_principal" "tesazure" {
  application_id = "${azuread_application.tesazure.application_id}"
}
resource "random_string" "spn_password" {
  length = 16
  special = true
}
resource "azuread_service_principal_password" "tesazure" {
  service_principal_id = "${azuread_service_principal.tesazure.id}"
  value                        = "${random_string.spn_password.result}"
  end_date_relative    = "26280h"
}

/*
# MSI KeyVault Access Policy - uncomment once MSI is available for App Service compose
resource "azurerm_key_vault_access_policy" "msi" {
  key_vault_id = "${azurerm_key_vault.vault.id}"

  tenant_id = "${azurerm_app_service.default.identity.0.tenant_id}"
  object_id = "${azurerm_app_service.default.identity.0.principal_id}"

  key_permissions = [
  ]

  secret_permissions = [
    "get",
    "list",
    "set",
    "delete"
  ]

  depends_on = [
    "azurerm_key_vault.vault",
    "azurerm_app_service.default"
  ]
}
*/

#########################
# Key Vault and Secrets
#########################
resource "azurerm_key_vault" "vault" {
  name                                       = "tesazure-${random_integer.ri.result}"
  location                                   = "${azurerm_resource_group.rg.location}"
  resource_group_name           = "${azurerm_resource_group.rg.name}"
  enabled_for_disk_encryption = true
  tenant_id                                = "${data.azurerm_client_config.current.tenant_id}"

  sku {
    name = "standard"
  }

  depends_on = [
    "azurerm_resource_group.rg"
  ]
}

# Allow SPN that App Service will use access to KeyVault. Provisioner writes secrets, hence the write permissions.
resource "azurerm_key_vault_access_policy" "spn_id" {
  key_vault_id = "${azurerm_key_vault.vault.id}"
  tenant_id      = "${data.azurerm_client_config.current.tenant_id}"
  object_id      = "${azuread_service_principal.tesazure.id}"

  secret_permissions = ["get", "list", "set", "delete"]

  depends_on = [
    "azurerm_key_vault.vault"
  ]
}

provider "azuread" {
  alias = "ad"
}
data "azuread_user" "cli_user" {
  provider = "azuread.ad"
  user_principal_name = "${var.az_cli_user}"
}

# Give access to current Azure CLI user to populate secrets from provisioning.
resource "azurerm_key_vault_access_policy" "client_id" {
  key_vault_id = "${azurerm_key_vault.vault.id}"
  tenant_id      = "${data.azurerm_client_config.current.tenant_id}"
  object_id      = "${data.azuread_user.cli_user.id}"

  secret_permissions = ["set", "get", "list", "delete"]

  depends_on = [
    "azurerm_key_vault.vault"
  ]
}
resource "azurerm_key_vault_secret" "postgres_connection_string" {
  name           = "TESAZURE-SQLALCHEMY-DATABASE-URI"
  value            = "${local.postgres_connection_string}"
  key_vault_id = "${azurerm_key_vault.vault.id}"

  depends_on = [
    "azurerm_key_vault_access_policy.client_id"
  ]
}
resource "azurerm_key_vault_secret" "celery_result_backend" {
  name           = "TESAZURE-CELERY-RESULT-BACKEND"
  value            = "${local.redis_connection_string}"
  key_vault_id = "${azurerm_key_vault.vault.id}"

  depends_on = [
    "azurerm_key_vault_access_policy.client_id"
  ]
}
resource "azurerm_key_vault_secret" "celery_broker_url" {
  name           = "TESAZURE-CELERY-BROKER-URL"
  value            = "${local.redis_connection_string}"
  key_vault_id = "${azurerm_key_vault.vault.id}"

  depends_on = [
    "azurerm_key_vault_access_policy.client_id"
  ]
}

#########################
# App Service for Containers
#########################
resource "azurerm_app_service_plan" "default" {
  name                             = "tesazure-appservice-${random_integer.ri.result}-plan"
  location                         = "${azurerm_resource_group.rg.location}"
  resource_group_name = "${azurerm_resource_group.rg.name}"

  # Required for Linux
  kind         = "Linux"
  reserved = true

  sku {
    tier = "${var.app_service_plan_sku_tier}"
    size = "${var.app_service_plan_sku_size}"
  }

  depends_on = [
    "azurerm_resource_group.rg"
  ]
}
resource "random_string" "flask_secret_key" {
  length = 16
  special = true
}
locals {
  docker_base_registry = "${replace(replace(var.acr_login_server, "http://", ""), "https://", "")}"
}
resource "azurerm_app_service" "default" {
  name                             = "tesazure-${random_integer.ri.result}"
  location                         = "${azurerm_resource_group.rg.location}"
  resource_group_name = "${azurerm_resource_group.rg.name}"
  app_service_plan_id    = "${azurerm_app_service_plan.default.id}"

  app_settings {
    WEBSITES_ENABLE_APP_SERVICE_STORAGE = false
    APPINSIGHTS_INSTRUMENTATIONKEY               = "${azurerm_application_insights.default.instrumentation_key}"
    DOCKER_REGISTRY_SERVER_URL                    = "${var.acr_login_server}"
    DOCKER_IMAGE_BASE_URL                                = "${local.docker_base_registry}"
    DOCKER_REGISTRY_SERVER_USERNAME       = "${var.acr_login_username}"
    DOCKER_REGISTRY_SERVER_PASSWORD       = "${var.acr_login_password}"
    APP_SECRET_KEY                                                 = "${random_string.flask_secret_key.result}"
    APP_KEYVAULT_URL                                             = "${azurerm_key_vault.vault.vault_uri}"
    APP_AZURE_CLIENT_ID                                        = "${azuread_application.tesazure.application_id}"
    APP_AZURE_SECRET                                            = "${random_string.spn_password.result}"
    APP_AZURE_TENANT                                            = "${data.azurerm_client_config.current.tenant_id}"
    APP_POOL_DEDICATED_NODE_COUNT             = 0
    APP_POOL_LOW_PRIORITY_NODE_COUNT       = 2
    APP_POOL_VM_SIZE                                              = "STANDARD_A1"
    APP_STANDARD_OUT_FILENAME                        = "stdout.txt"
    APP_COMPUTE_BACKEND                                    = "batch"
    PYTHONUNBUFFERED                                          = 1
    OCAGENT_TRACE_EXPORTER_ENDPOINT        = "local-forwarder:55678"
    WEBSITE_HTTPLOGGING_RETENTION_DAYS    = 3
  }

  site_config {
    # Reading environment variables in a Compose file on App Service does not appear to be working - just replacing on load
    linux_fx_version = "COMPOSE|${base64encode(replace(file("../docker-compose-azure.yml"), "$${DOCKER_IMAGE_BASE_URL}", "${local.docker_base_registry}"))}"
    always_on = true
    # httpLoggingEnabled = true  -- not supported yet
  }

  # Managed identity isn't supported by multi-container App Service workloads yet
  # Keeping this here for easy uncommenting once MSI is available
  # identity {
  #  type = "SystemAssigned"
  #}

  depends_on = [
    "azurerm_app_service_plan.default",
    "azurerm_application_insights.default",
    "azurerm_key_vault.vault",
    "azuread_application.tesazure"
  ]
}
