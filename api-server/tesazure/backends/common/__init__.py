# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from abc import ABC, abstractmethod
from . import commands  # noqa: F401


class AbstractComputeBackend(ABC):
    """Abstract class that specifies methods required for compute backend plugins"""

    @abstractmethod
    def create_task(self, task):
        """Create a new task"""
        pass

    @abstractmethod
    def get_task(self, task_id):
        """Get details on existing task"""
        pass

    @abstractmethod
    def list_tasks(self):
        """List all known tasks"""
        pass

    @abstractmethod
    def service_info(self):
        """
        Get service details and capacity availability. Implementation gets
        merged with API's defaults, overriding keys if there is overlap.
        """
        {}

    @abstractmethod
    def cancel_task(self, task_id):
        """Cancel an existing task"""
        pass

    @abstractmethod
    def configure(self):
        """Configure the backend to be ready to accept tasks"""
        pass


def determine_azure_vm_for_task(tes_resources, fallback_cpu_cores=1, fallback_mem_GiB=2, fallback_disk_GiB=10):
    GbToGib = 1000**3 / 1024**3
    cpu_cores = tes_resources.cpu_cores or fallback_cpu_cores
    mem_GiB = tes_resources.ram_gb * GbToGib or fallback_mem_GiB
    disk_GiB = tes_resources.disk_gb * GbToGib or fallback_disk_GiB
    low_prio = tes_resources.preemptible is True  # noqa: F841
    # TODO: support 'zones'

    vms_by_preference = [
        {'sku': 'Standard_A1_v2', 'cpu': 1, 'mem': 2, 'disk': 10, 'ssd': True},
        {'sku': 'Standard_A2m_v2', 'cpu': 2, 'mem': 16, 'disk': 20, 'ssd': True},
        {'sku': 'Standard_A2_v2', 'cpu': 2, 'mem': 4, 'disk': 20, 'ssd': True},
        {'sku': 'Standard_A4m_v2', 'cpu': 4, 'mem': 32, 'disk': 40, 'ssd': True},
        {'sku': 'Standard_A4_v2', 'cpu': 4, 'mem': 8, 'disk': 40, 'ssd': True},
        {'sku': 'Standard_A8m_v2', 'cpu': 8, 'mem': 64, 'disk': 80, 'ssd': True},
        {'sku': 'Standard_A8_v2', 'cpu': 8, 'mem': 16, 'disk': 80, 'ssd': True},
        {'sku': 'Standard_D2_v3', 'cpu': 2, 'mem': 8, 'disk': 50, 'ssd': True},
        {'sku': 'Standard_D4_v3', 'cpu': 4, 'mem': 16, 'disk': 100, 'ssd': True},
        {'sku': 'Standard_D8_v3', 'cpu': 8, 'mem': 32, 'disk': 200, 'ssd': True},
        {'sku': 'Standard_D16_v3', 'cpu': 16, 'mem': 64, 'disk': 400, 'ssd': True},
        {'sku': 'Standard_D32_v3', 'cpu': 32, 'mem': 128, 'disk': 800, 'ssd': True},
        {'sku': 'Standard_D64_v3', 'cpu': 64, 'mem': 256, 'disk': 1600, 'ssd': True},
        {'sku': 'Standard_G1', 'cpu': 2, 'mem': 28, 'disk': 384, 'ssd': True},
        {'sku': 'Standard_G2', 'cpu': 4, 'mem': 56, 'disk': 768, 'ssd': True},
        {'sku': 'Standard_G3', 'cpu': 8, 'mem': 112, 'disk': 1536, 'ssd': True},
        {'sku': 'Standard_G4', 'cpu': 16, 'mem': 224, 'disk': 3072, 'ssd': True},
        {'sku': 'Standard_G5', 'cpu': 32, 'mem': 448, 'disk': 6144, 'ssd': True}
    ]

    remaining_vms = list(filter(lambda vm: vm['cpu'] >= cpu_cores and vm['mem'] >= mem_GiB and vm['disk'] >= disk_GiB, vms_by_preference))
    if remaining_vms:
        return remaining_vms[0]['sku']
    else:
        raise ValueError("No such VM available")
