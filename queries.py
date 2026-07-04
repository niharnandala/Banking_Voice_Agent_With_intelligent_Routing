from decimal import Decimal
from connections import db_conn
# db_conn is my live database connection imported from connections.py
# Decimal is imported because MySQL gives me back money values
# as Decimal type and i need to convert them to plain floats before returning


def get_customer_full_data(customer_id):
    # i wrapped everything in try/except because the database could be down
    # or the connection could have timed out or the query itself could fail
    # without this one DB error crashes the entire customer call
    try:
        cursor = db_conn.cursor()
        # cursor is my pen to read and write to the database
        # i create a fresh one every time instead of reusing
        # because cursors are not safe to share across operations

        cursor.execute("""
            SELECT *
            FROM customers c
            LEFT JOIN accounts a ON c.customer_id = a.customer_id
            LEFT JOIN loans l ON c.customer_id = l.customer_id
            WHERE c.customer_id = %s
        """, (customer_id,))
        # SELECT * gives me every column from all three tables
        # LEFT JOIN keeps the customer even if they have no loan
        # a regular JOIN would hide customers with no loan entirely
        # %s is a placeholder, the actual value is passed separately
        # this prevents SQL injection — the DB driver handles escaping
        # the comma in (customer_id,) makes it a tuple not just brackets

        row          = cursor.fetchone()
        # fetchone() gives me the first matching row
        # returns None if no customer was found

        column_names = [desc[0] for desc in cursor.description]
        # cursor.description describes each column
        # desc[0] is the column name
        # so i build ["customer_id", "name", "balance", ...]

        cursor.close()
        # i always close the cursor after use to free the DB connection

        if row is None:
            return None
        # customer doesnt exist, caller checks for None and handles it

        customer_data = dict(zip(column_names, row))
        # zip pairs column names with their values
        # gives me {"customer_id": "CU001", "name": "Ravi Kumar", ...}

        for key, value in customer_data.items():
            if isinstance(value, Decimal):
                customer_data[key] = float(value)
            elif hasattr(value, 'isoformat'):
                customer_data[key] = value.isoformat()
        # i convert Decimal to float because Decimal is not JSON serializable
        # i convert date/datetime to string using isoformat()
        # which gives me something clean like "2024-01-15"

        return customer_data

    except Exception as e:
        print(f"[error] get_customer_full_data failed: {e}")
        return None
        # if anything failed i print what went wrong for debugging
        # and return None so the caller handles it gracefully
        # instead of the whole program crashing


def validate_customer_id(customer_id):
    # i wrapped this in try/except for the same reason as above
    # if my DB is down i want to return False safely not crash
    try:
        cursor = db_conn.cursor()

        cursor.execute("""
            SELECT customer_id FROM customers
            WHERE customer_id = %s
        """, (customer_id,))
        # i only select customer_id not SELECT *
        # because i just need to know if this id exists
        # fetching everything would be wasteful here

        row = cursor.fetchone()
        cursor.close()

        return row is not None
        # if row has something the customer exists i return True
        # if row is None the customer doesnt exist i return False

    except Exception as e:
        print(f"[error] validate_customer_id failed: {e}")
        return False
        # i return False if DB is down — safer than assuming valid
        # better to say id not found than let an unverified customer through


if __name__ == "__main__":
    data = get_customer_full_data("CU001")
    print(data)