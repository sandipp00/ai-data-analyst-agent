"""Create the demo e-commerce schema, load synthetic data, and create the read-only role.

Run: python -m scripts.seed
"""
import math
import random
from datetime import date, timedelta

import psycopg

from analyst.config import settings

SCHEMA = """
DROP TABLE IF EXISTS order_items, orders, products, customers CASCADE;

CREATE TABLE customers (
    id          integer PRIMARY KEY,
    name        text NOT NULL,
    email       text NOT NULL UNIQUE,
    country     text NOT NULL,
    segment     text NOT NULL,          -- consumer | small_business | enterprise
    signup_date date NOT NULL
);
CREATE TABLE products (
    id       integer PRIMARY KEY,
    name     text NOT NULL,
    category text NOT NULL,
    price    numeric(10,2) NOT NULL,
    cost     numeric(10,2) NOT NULL
);
CREATE TABLE orders (
    id          integer PRIMARY KEY,
    customer_id integer NOT NULL REFERENCES customers(id),
    order_date  date NOT NULL,
    status      text NOT NULL           -- completed | shipped | cancelled | returned
);
CREATE TABLE order_items (
    id         integer PRIMARY KEY,
    order_id   integer NOT NULL REFERENCES orders(id),
    product_id integer NOT NULL REFERENCES products(id),
    quantity   integer NOT NULL,
    unit_price numeric(10,2) NOT NULL
);
CREATE INDEX ON orders (order_date);
CREATE INDEX ON orders (customer_id);
CREATE INDEX ON order_items (order_id);
"""

GRANTS = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst_ro') THEN
    CREATE ROLE analyst_ro LOGIN PASSWORD 'analyst_ro';
  END IF;
END $$;
GRANT CONNECT ON DATABASE analytics TO analyst_ro;
GRANT USAGE ON SCHEMA public TO analyst_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst_ro;
"""

COUNTRIES = ["United States", "United Kingdom", "Germany", "India", "Brazil", "Canada", "Australia", "France"]
SEGMENTS = ["consumer", "small_business", "enterprise"]
CATALOG = {
    "Electronics": [("Wireless Earbuds", 59), ("Smart Speaker", 89), ("4K Webcam", 120), ("USB-C Hub", 45), ("Mechanical Keyboard", 110), ("Gaming Mouse", 65)],
    "Home": [("Desk Lamp", 35), ("Air Purifier", 180), ("Coffee Maker", 95), ("Standing Desk Mat", 40), ("Throw Blanket", 30), ("Robot Vacuum", 260)],
    "Fitness": [("Yoga Mat", 28), ("Resistance Bands", 18), ("Smart Water Bottle", 38), ("Adjustable Dumbbells", 220), ("Fitness Tracker", 99), ("Foam Roller", 25)],
    "Office": [("Notebook Set", 14), ("Ergonomic Chair", 310), ("Monitor Stand", 55), ("Label Printer", 85), ("Whiteboard", 70), ("Pen Pack", 9)],
}


def main() -> None:
    rng = random.Random(42)
    today = date.today()
    start = today - timedelta(days=730)

    customers = []
    for i in range(1, 301):
        signup = start + timedelta(days=rng.randint(0, 700))
        customers.append((i, f"Customer {i}", f"customer{i}@example.com",
                          rng.choices(COUNTRIES, weights=[30, 12, 10, 14, 8, 8, 6, 12])[0],
                          rng.choices(SEGMENTS, weights=[65, 25, 10])[0], signup))

    products, pid = [], 1
    for category, items in CATALOG.items():
        for name, price in items:
            products.append((pid, name, category, price, round(price * rng.uniform(0.4, 0.7), 2)))
            pid += 1

    orders, items_rows, item_id = [], [], 1
    for oid in range(1, 4001):
        cust = rng.choice(customers)
        # growth trend + Q4 seasonality: later and holiday dates are likelier
        while True:
            d = start + timedelta(days=rng.randint(0, 729))
            weight = (0.5 + (d - start).days / 730) * (1.5 if d.month in (11, 12) else 1.0)
            if d >= cust[5] and rng.random() < weight / 3:
                break
        status = rng.choices(["completed", "shipped", "cancelled", "returned"], weights=[70, 15, 8, 7])[0]
        orders.append((oid, cust[0], d, status))
        for _ in range(rng.choices([1, 2, 3, 4], weights=[50, 30, 15, 5])[0]):
            p = rng.choice(products)
            qty = 1 + int(math.fabs(rng.gauss(0, 1.2)))
            items_rows.append((item_id, oid, p[0], qty, p[3]))
            item_id += 1

    with psycopg.connect(settings.admin_database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
            cur.executemany("INSERT INTO customers VALUES (%s,%s,%s,%s,%s,%s)", customers)
            cur.executemany("INSERT INTO products VALUES (%s,%s,%s,%s,%s)", products)
            cur.executemany("INSERT INTO orders VALUES (%s,%s,%s,%s)", orders)
            cur.executemany("INSERT INTO order_items VALUES (%s,%s,%s,%s,%s)", items_rows)
            cur.execute(GRANTS)
    print(f"Seeded {len(customers)} customers, {len(products)} products, "
          f"{len(orders)} orders, {len(items_rows)} order items.")


if __name__ == "__main__":
    main()
