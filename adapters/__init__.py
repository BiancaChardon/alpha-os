from adapters.base import AdapterRegistry
from adapters.caiso import CAISOAdapter
from adapters.eia import EIAAdapter
from adapters.eia_today import EIATodayAdapter
from adapters.ercot import ERCOTAdapter
from adapters.ferc import FERCAdapter
from adapters.fred import FREDAdapter
from adapters.noaa import NOAAAdapter
from adapters.opec import OPECAdapter
from adapters.pjm import PJMAdapter


def build_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    for adapter in [
        EIAAdapter(),
        FREDAdapter(),
        PJMAdapter(),
        ERCOTAdapter(),
        CAISOAdapter(),
        NOAAAdapter(),
        EIATodayAdapter(),
        FERCAdapter(),
        OPECAdapter(),
    ]:
        registry.register(adapter)
    return registry
