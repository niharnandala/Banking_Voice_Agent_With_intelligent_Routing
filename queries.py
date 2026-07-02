from decimal import Decimal

from connections import db_conn


def get_customer_full_data(customer_id):
    """
    fetches everything about one customer in a single query
    joins customers + accounts + loans tables together
    uses SELECT * so we never miss a column, even if tables change later

    why LEFT JOIN and not regular JOIN?
    regular JOIN only returns rows where BOTH tables have a match
    if a customer has no loan, regular JOIN would hide that customer entirely
    LEFT JOIN keeps the customer even if loan data is missing,
    loan fields just come back as None
    """

    cursor = db_conn.cursor()

    cursor.execute("""
        SELECT *
        FROM customers c
        LEFT JOIN accounts a ON c.customer_id = a.customer_id
        LEFT JOIN loans l ON c.customer_id = l.customer_id
        WHERE c.customer_id = %s
    """, (customer_id,))

    row = cursor.fetchone()

    # cursor.description gives us the column names in order
    # this lets us build a dictionary automatically
    # instead of manually typing row[0], row[1], row[2]...
    column_names = [desc[0] for desc in cursor.description]

    cursor.close()

    if row is None:
        return None

    # zip pairs each column name with its value
    # eg column_names[0] = "customer_id", row[0] = "CU001"
    # this creates {"customer_id": "CU001", "name": "Ravi Kumar", ...}
    customer_data = dict(zip(column_names, row))
    for key, value in customer_data.items():
        if isinstance(value, Decimal):
            customer_data[key] = float(value)
        elif hasattr(value, 'isoformat'):
            customer_data[key] = value.isoformat()



    return customer_data

def validate_customer_id(customer_id):
     """
    checks if customer_id actually exists in the database
    before we try to fetch their data or answer any questions
    returns True if found, False if not found
    """
     cursor = db_conn.cursor()

     cursor.execute("""
                    SELECT customer_id from customers
                    where customer_id=%s
                    """,(customer_id))
     row=cursor.fetchone()
     cursor.close()
     return row is not None



if __name__ == "__main__":
    data = get_customer_full_data("CU001")
    print(data)
