output "resource_group" {
  value = "${azurerm_resource_group.rg.name}"
}
# App Service
output "app_service_name" {
  value = "${azurerm_app_service.default.name}"
}
output "app_service_hostname" {
  value = "https://${azurerm_app_service.default.default_site_hostname}"
}
