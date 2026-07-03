from decimal import Decimal
from connections import db_conn
# db_conn is my live database connection that i imported from connections.py
# i also imported Decimal because MySQL gives me back money values 
# as Decimal type and i need to convert them to plain floats before i return them


def get_customer_full_data(customer_id):

    # i wrapped everything inside try/except because the database could be down
    # or the connection could have timed out or the query itself could fail
    # if i dont catch this, one DB error will crash the entire customer call
    try:
        cursor = db_conn.cursor()
        # i create a cursor which is basically my pen to read and write to the DB
        # i create a fresh one every time instead of reusing one
        # because cursors are not safe to share across different operations

        cursor.execute("""
            SELECT *
            FROM customers c
            LEFT JOIN accounts a ON c.customer_id = a.customer_id
            LEFT JOIN loans l ON c.customer_id = l.customer_id
            WHERE c.customer_id = %s
        """, (customer_id,))
        # i am doing SELECT * which means give me every column from all three tables
        # i used LEFT JOIN instead of regular JOIN because regular JOIN would
        # completely hide a customer who has no loan record
        # LEFT JOIN keeps the customer row and just gives me None for loan columns
        # i use %s as a placeholder and pass the actual value separately
        # this is important because the DB driver handles escaping for me
        # which means no SQL injection is possible this way
        # the comma in (customer_id,) is important — without it its just
        # brackets around a string, not a tuple, and the DB driver will crash

        row = cursor.fetchone()
        # fetchone() gives me the first matching row from the result
        # if no customer was found it just returns None

        column_names = [desc[0] for desc in cursor.description]
        # cursor.description is a list where each item describes one column
        # desc[0] is the column name from each of those items
        # so i am building myself a clean list like
        # ["customer_id", "name", "balance", "loan_amount", ...]

        cursor.close()
        # i always close the cursor after i am done
        # this frees up the database connection for other operations

        if row is None:
            return None
        # if the customer doesnt exist i return None
        # whoever called this function will check for None and handle it

        customer_data = dict(zip(column_names, row))
        # zip pairs each column name with its value from the row
        # so i get {"customer_id": "CU001", "name": "Ravi Kumar", ...}
        # this is much cleaner than doing row[0], row[1], row[2] manually

        for key, value in customer_data.items():
            if isinstance(value, Decimal):
                customer_data[key] = float(value)
            elif hasattr(value, 'isoformat'):
                customer_data[key] = value.isoformat()
        # i loop through every value in my dictionary
        # if i find a Decimal i convert it to float because
        # Decimal is not JSON serializable and causes problems later
        # if i find a date or datetime object i convert it to a string
        # using isoformat() which gives me something like "2024-01-15"

        return customer_data

    except Exception as e:
        print(f"[error] get_customer_full_data failed: {e}")
        return None
        # if anything went wrong in the try block i catch it here
        # i print what went wrong so i can debug it in the terminal
        # and i return None so the caller can handle it gracefully
        # instead of the whole program crashing


def validate_customer_id(customer_id):

    # i wrapped this in try/except for the same reason as above
    # if my DB is down i want to return False safely, not crash
    try:
        cursor = db_conn.cursor()

        cursor.execute("""
            SELECT customer_id FROM customers
            WHERE customer_id = %s
        """, (customer_id,))
        # i am only selecting customer_id here, not SELECT *
        # because i dont need any other data, i just want to know
        # if this id exists or not — fetching everything would be wasteful

        row = cursor.fetchone()
        cursor.close()

        return row is not None
        # if row has something in it, the customer exists, i return True
        # if row is None, the customer doesnt exist, i return False
        # "row is not None" evaluates to exactly True or False for me

    except Exception as e:
        print(f"[error] validate_customer_id failed: {e}")
        return False
        # if DB is down i return False which means "not valid"
        # this is the safer choice — better to say id not found
        # than to accidentally let an unverified customer through