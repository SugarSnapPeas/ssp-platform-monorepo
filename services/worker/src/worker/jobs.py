"""Background jobs that drive api orders. Imports BOTH api and shared-core."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

from api.errors import ApiError, Conflict, NotFound
from api.orders import Order, OrderBook
from shared_core.retry import RetryExhausted, retry
from worker.queue import Task, TaskQueue

__all__ = ["JobResult", "PaymentGateway", "settle_payment", "OrderProcessor"]


@dataclass(frozen=True)
class JobResult:
    task: str
    order_id: str
    ok: bool
    detail: str = ""


class PaymentGateway:
    """A deterministic fake gateway: fails the first ``flaky_for`` calls."""

    def __init__(self, flaky_for: int = 0, always_fail: bool = False) -> None:
        self.flaky_for = flaky_for
        self.always_fail = always_fail
        self.calls = 0

    def charge(self, order_id: str) -> str:
        self.calls += 1
        if self.always_fail or self.calls <= self.flaky_for:
            raise ConnectionError("gateway unavailable for {0}".format(order_id))
        return "auth-{0}-{1}".format(order_id, self.calls)


def settle_payment(
    gateway: PaymentGateway,
    order_id: str,
    attempts: int = 3,
    sleeper: Callable[[float], None] = lambda _: None,
) -> str:
    """Charge with retries, using ``shared_core.retry``.

    Raises :class:`shared_core.retry.RetryExhausted` when the gateway never
    recovers.
    """

    @retry(
        attempts=attempts,
        delay=0.01,
        factor=2.0,
        exceptions=(ConnectionError,),
        sleeper=sleeper,
    )
    def _charge() -> str:
        return gateway.charge(order_id)

    return _charge()


class OrderProcessor:
    """Consumes a :class:`~worker.queue.TaskQueue` against an api OrderBook."""

    HANDLED = ("pay", "fulfil", "close", "cancel")

    def __init__(
        self,
        orders: OrderBook,
        gateway: Optional[PaymentGateway] = None,
        attempts: int = 3,
    ) -> None:
        self.orders = orders
        self.gateway = gateway or PaymentGateway()
        self.attempts = attempts
        self.results: List[JobResult] = []
        self.authorisations: List[str] = []

    def enqueue_new_orders(self, queue: TaskQueue) -> TaskQueue:
        """Queue a ``pay`` task for every order still in the ``new`` state."""
        for order in sorted(self.orders.find_by_state("new"), key=lambda o: o.order_id):
            queue.push(Task("pay", order.order_id, priority=1))
        return queue

    def handle(self, task: Task) -> JobResult:
        if task.name not in self.HANDLED:
            return JobResult(task.name, str(task.payload), False, "unknown task")
        order_id = str(task.payload)
        try:
            if task.name == "pay":
                auth = settle_payment(self.gateway, order_id, attempts=self.attempts)
                self.authorisations.append(auth)
                self.orders.advance(order_id, "paid")
                return JobResult(task.name, order_id, True, auth)
            target = {"fulfil": "fulfilled", "close": "closed", "cancel": "cancelled"}[task.name]
            self.orders.advance(order_id, target)
            return JobResult(task.name, order_id, True, target)
        except RetryExhausted as exc:
            return JobResult(task.name, order_id, False, "payment failed after {0}".format(exc.attempts))
        except (NotFound, Conflict) as exc:
            return JobResult(task.name, order_id, False, exc.code)
        except ApiError as exc:  # pragma: no cover - defensive
            return JobResult(task.name, order_id, False, exc.code)

    def run(self, queue: TaskQueue) -> List[JobResult]:
        batch = [self.handle(task) for task in queue.drain()]
        self.results.extend(batch)
        return batch

    def failures(self) -> List[JobResult]:
        return [r for r in self.results if not r.ok]
