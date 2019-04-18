variable "az_cli_user" {
  type           = "string"
  description = "Login name (email) of the user authenticating to the CLI. Needed for populating Key Vault."
}

variable "resource_group_name" {
  type           = "string"
  description = "Name of the azure resource group."
  default       = "tesazure"
}

variable "resource_group_location" {
  type           = "string"
  description = "Location of the azure resource group."
  default       = "westus2"
}

variable "postgresql_sku_name" {
  type           = "string"
  description = "Name of Azure PostgreSQL SKU"
  default       = "B_Gen5_2"
}
variable "postgresql_sku_capacity" {
  type           = "string"
  description = "Capacity of Azure PostgreSQL SKU"
  default       = "2"
}
variable "postgresql_sku_tier" {
  type           = "string"
  description = "Tier of Azure PostgreSQL SKU"
  default       = "Basic"
}
variable "postgresql_sku_family" {
  type           = "string"
  description = "Family of Azure PostgreSQL SKU"
  default       = "Gen5"
}

variable "redis_family" {
  type           = "string"
  description = "Family of Azure Redis instance for backend tasks"
  default       = "C"
}
variable "redis_sku_name" {
  type           = "string"
  description = "SKU name of Azure Redis instance for backend tasks"
  default       = "Basic"
}

variable "app_service_plan_sku_tier" {
  type            = "string"
  description = "SKU tier of the App Service Plan"
  default       = "Standard"
}
variable "app_service_plan_sku_size" {
  type           = "string"
  description = "SKU size of the App Service Plan"
  default        = "S1"
}

variable "acr_login_server" {
  type        = "string"
  description = "Full URL to the Azure Container Repository where the TES API and related images are stored"
  default     = "http://tesazure.azurecr.io"
}
variable "acr_login_username" {
  type            = "string"
  description = "Username to login to the ACR server"
  default        = ""
}
variable "acr_login_password" {
  type           = "string"
  description = "Password to login to the ACR server"
  default        = ""
}