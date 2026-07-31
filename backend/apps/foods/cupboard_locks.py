"""Canonical globally ordered cupboard row-lock bundles."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

from django.apps import apps


@dataclass(frozen=True)
class CupboardItemLocks:
    """Cupboard rows locked by ascending primary key on one database alias."""

    using: str
    items_by_pk: dict[int, Any]

    def covers(self, item_ids: Iterable[int], using: str) -> bool:
        """Return whether this live bundle covers all requested stock rows.

        Args:
            item_ids: Stock row primary keys that must already be locked.
            using: Database alias on which the locks must be held.

        Returns:
            Whether this bundle covers every requested row on the alias.
        """
        return self.using == using and set(item_ids).issubset(self.items_by_pk)


_active_cupboard_item_locks: ContextVar[CupboardItemLocks | None] = ContextVar(
    "active_cupboard_item_locks", default=None
)


def get_cupboard_item_locks() -> CupboardItemLocks | None:
    """Return the cupboard lock bundle active in this execution context.

    Returns:
        The active bundle, or ``None`` when no bundle is scoped.
    """
    return _active_cupboard_item_locks.get()


@contextmanager
def activate_cupboard_item_locks(
    locks: CupboardItemLocks,
) -> Iterator[None]:
    """Expose live cupboard locks to nested model and signal writers.

    Args:
        locks: Bundle held by the enclosing transaction.
    """
    token = _active_cupboard_item_locks.set(locks)
    try:
        yield
    finally:
        _active_cupboard_item_locks.reset(token)


def lock_cupboard_items(
    item_ids: Iterable[int], using: str
) -> CupboardItemLocks:
    """Lock the complete cupboard set once in ascending primary-key order.

    Args:
        item_ids: Complete stock-row primary-key set for the mutation.
        using: Database alias on which rows must be locked.

    Returns:
        The locked, alias-scoped cupboard bundle.

    Raises:
        RuntimeError: If a nested caller attempts to expand an active bundle.
    """
    ordered_ids = tuple(sorted(set(item_ids)))
    active = get_cupboard_item_locks()
    if active is not None and active.covers(ordered_ids, using):
        return active
    if active is not None:
        raise RuntimeError("cannot expand an active cupboard lock bundle")
    if not ordered_ids:
        return CupboardItemLocks(using, {})
    item_model = apps.get_model("foods", "CupboardItem")
    items = tuple(
        item_model.objects.select_for_update(of=("self",))
        .using(using)
        .filter(pk__in=ordered_ids)
        .select_related("food")
        .order_by("pk")
    )
    return CupboardItemLocks(using, {item.pk: item for item in items})
