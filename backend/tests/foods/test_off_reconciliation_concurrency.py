"""PostgreSQL contention coverage for OFF barcode reconciliation."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, connections

from apps.foods.models import FoodProduct
from apps.foods.off_reconciliation import reconcile_off_product
from apps.foods.open_food_facts import _map_product
from tests.foods.test_off_reconciliation import _product
from tests.foods.test_product_barcode_schema import BARCODE, _off_payload


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("second_barcode", [BARCODE, "036000291452"])
def test_concurrent_reconciliation_preserves_one_product(second_barcode):
    """Concurrent scans serialize before claiming the same missing barcode."""
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    product = _product()
    draft = _map_product(_off_payload()["product"], BARCODE)
    assert draft is not None
    ready = Barrier(2)

    def worker(barcode):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")

            def synchronize(execute, sql, params, many, context):
                if "FOR UPDATE" in sql and "foods_foodproduct" in sql:
                    ready.wait(timeout=10)
                return execute(sql, params, many, context)

            with connection.execute_wrapper(synchronize):
                result = reconcile_off_product(
                    replace(draft, barcode=barcode), may_update=True
                )
            return result.pk if result else None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(worker, BARCODE)
        second = executor.submit(worker, second_barcode)
        results = [first.result(timeout=20), second.result(timeout=20)]

    product.refresh_from_db()
    assert FoodProduct.objects.count() == 1
    if second_barcode == BARCODE:
        assert results == [product.pk, product.pk]
        assert product.barcode == BARCODE
    else:
        assert results.count(product.pk) == 1
        assert results.count(None) == 1
        assert product.barcode in (BARCODE, second_barcode)
