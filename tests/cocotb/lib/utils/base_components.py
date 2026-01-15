"""
Base UVM-like components for cocotb verification

Provides base classes similar to UVM components:
- BaseTransaction: Base class for all transaction types
- BaseDriver: Base driver class with standardized API
- BaseMonitor: Base monitor class with callback support
- BaseAgent: Base agent class combining driver and monitor
"""

import cocotb
from cocotb.triggers import RisingEdge, Event
from cocotb.log import SimLog
from typing import Optional, Any, Callable, List
import queue


class BaseTransaction:
    """Base class for all transaction types (similar to uvm_sequence_item)"""

    def __init__(self, name: str = "transaction"):
        self.name = name
        self.timestamp = None

    def __str__(self) -> str:
        """String representation of transaction"""
        return f"{self.__class__.__name__}({self.name})"

    def copy(self) -> 'BaseTransaction':
        """Create a deep copy of the transaction"""
        raise NotImplementedError("Subclasses must implement copy()")


class BaseDriver:
    """Base driver class (similar to uvm_driver)"""

    def __init__(self, dut: Any, clk: Any, name: str = "driver"):
        self.dut = dut
        self.clk = clk
        self.name = name
        self.log = SimLog(f"cocotb.{name}")
        self.busy = False

    async def reset(self) -> None:
        """Reset driver signals to default values"""
        raise NotImplementedError("Subclasses must implement reset()")

    async def drive(self, transaction: BaseTransaction) -> None:
        """Drive a transaction on the bus"""
        raise NotImplementedError("Subclasses must implement drive()")


class BaseMonitor:
    """Base monitor class (similar to uvm_monitor)"""

    def __init__(self, dut: Any, clk: Any, name: str = "monitor"):
        self.dut = dut
        self.clk = clk
        self.name = name
        self.log = SimLog(f"cocotb.{name}")
        self.callbacks: List[Callable] = []
        self._mon_task = None

    def add_callback(self, callback: Callable) -> None:
        """Add a callback function to be called when a transaction is detected"""
        self.callbacks.append(callback)

    async def _monitor_loop(self) -> None:
        """Main monitor loop - to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement _monitor_loop()")

    def start(self) -> None:
        """Start the monitor"""
        if self._mon_task is None:
            self._mon_task = cocotb.start_soon(self._monitor_loop())

    def stop(self) -> None:
        """Stop the monitor"""
        if self._mon_task is not None:
            self._mon_task.kill()
            self._mon_task = None

    def _notify_callbacks(self, transaction: BaseTransaction) -> None:
        """Notify all registered callbacks of a new transaction"""
        for callback in self.callbacks:
            try:
                callback(transaction)
            except Exception as e:
                self.log.error(f"Callback error: {e}")


class BaseAgent:
    """Base agent class (similar to uvm_agent)"""

    def __init__(self, dut: Any, clk: Any, name: str = "agent"):
        self.dut = dut
        self.clk = clk
        self.name = name
        self.log = SimLog(f"cocotb.{name}")
        self.driver: Optional[BaseDriver] = None
        self.monitor: Optional[BaseMonitor] = None

    async def reset(self) -> None:
        """Reset agent and its components"""
        if self.driver:
            await self.driver.reset()

    def start_monitor(self) -> None:
        """Start the monitor if present"""
        if self.monitor:
            self.monitor.start()

    def stop_monitor(self) -> None:
        """Stop the monitor if present"""
        if self.monitor:
            self.monitor.stop()


class TransactionQueue:
    """Thread-safe queue for transactions with cocotb Events"""

    def __init__(self, name: str = "queue"):
        self.name = name
        self.queue = queue.Queue()
        self.put_event = Event()
        self.log = SimLog(f"cocotb.{name}")

    def put(self, item: BaseTransaction) -> None:
        """Put an item in the queue"""
        self.queue.put(item)
        self.put_event.set()

    async def get(self) -> BaseTransaction:
        """Get an item from the queue (async)"""
        while self.queue.empty():
            await self.put_event.wait()
            self.put_event.clear()
        return self.queue.get()

    def empty(self) -> bool:
        """Check if queue is empty"""
        return self.queue.empty()

    def qsize(self) -> int:
        """Get queue size"""
        return self.queue.qsize()
