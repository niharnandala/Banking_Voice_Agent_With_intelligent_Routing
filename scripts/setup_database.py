from connections import db_conn

# ============================================================
# WHAT THIS FILE DOES
# ============================================================
# reuses the db_conn we already created in connections.py
# no need to connect again, just import the existing connection
# creates three tables: customers, accounts, loans
# safe to run again — IF NOT EXISTS prevents errors on re-run

cursor = db_conn.cursor()


# ============================================================
# STEP 1 — CREATE CUSTOMERS TABLE
# ============================================================
print("creating customers table...")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        customer_id     VARCHAR(20) PRIMARY KEY,
        name             VARCHAR(100) NOT NULL,
        phone_number     VARCHAR(15),
        email            VARCHAR(100),
        created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
print("customers table ready!")


# ============================================================
# STEP 2 — CREATE ACCOUNTS TABLE
# ============================================================
print("creating accounts table...")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        account_id                 SERIAL PRIMARY KEY,
        customer_id                VARCHAR(20) REFERENCES customers(customer_id),
        account_type                VARCHAR(20),
        balance                     DECIMAL(10, 2),
        minimum_balance_required    DECIMAL(10, 2),
        status                      VARCHAR(20) DEFAULT 'active'
    )
""")
print("accounts table ready!")


# ============================================================
# STEP 3 — CREATE LOANS TABLE
# ============================================================
print("creating loans table...")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS loans (
        loan_id              SERIAL PRIMARY KEY,
        customer_id          VARCHAR(20) REFERENCES customers(customer_id),
        loan_type             VARCHAR(20),
        principal_amount      DECIMAL(10, 2),
        outstanding_amount    DECIMAL(10, 2),
        emi_amount            DECIMAL(10, 2),
        emi_due_date          DATE,
        status                VARCHAR(20) DEFAULT 'active'
    )
""")
print("loans table ready!")


# ============================================================
# STEP 4 — INSERT TEST DATA
# ============================================================
# 5 customers covering different scenarios
# CU001, CU002, CU003 — normal customers, good standing
# CU004 — low balance (below minimum) AND overdue EMI, good for escalation demo
# CU005 — high balance customer, premium account

print("inserting test customers...")

cursor.execute("""
    INSERT INTO customers (customer_id, name, phone_number, email)
    VALUES
        ('CU001', 'Ravi Kumar', '9876543210', 'ravi@email.com'),
        ('CU002', 'Priya Sharma', '9876543211', 'priya@email.com'),
        ('CU003', 'Arjun Reddy', '9876543212', 'arjun@email.com'),
        ('CU004', 'Sneha Iyer', '9876543213', 'sneha@email.com'),
        ('CU005', 'Vikram Singh', '9876543214', 'vikram@email.com'),
        ('CU007', 'Nihar Nandala', '9876543214', 'niharnandala@email.com')
    ON CONFLICT (customer_id) DO NOTHING
""")
print("customers inserted!")


print("inserting test accounts...")

cursor.execute("""
    INSERT INTO accounts (customer_id, account_type, balance, minimum_balance_required, status)
    VALUES
        ('CU001', 'savings', 25000.00, 1000.00, 'active'),
        ('CU002', 'premium', 80000.00, 5000.00, 'active'),
        ('CU003', 'zero_balance', 3000.00, 0.00, 'active'),
        ('CU004', 'savings', 500.00, 1000.00, 'active'),
        ('CU005', 'premium', 150000.00, 5000.00, 'active'),
        ('CU007', 'premium', 150000.00, 5000.00, 'active')

""")
print("accounts inserted!")


print("inserting test loans...")

cursor.execute("""
    INSERT INTO loans (customer_id, loan_type, principal_amount, outstanding_amount, emi_amount, emi_due_date, status)
    VALUES
        ('CU001', 'home', 2000000.00, 1500000.00, 18500.00, '2026-07-05', 'active'),
        ('CU002', 'car', 800000.00, 350000.00, 14200.00, '2026-07-05', 'active'),
        ('CU003', 'personal', 200000.00, 50000.00, 9800.00, '2026-07-05', 'active'),
        ('CU004', 'personal', 100000.00, 95000.00, 6200.00, '2026-06-05', 'active'),
        ('CU005', 'home', 3000000.00, 2800000.00, 27000.00, '2026-07-10', 'active'),
        ('CU007', 'home', 3000000.00, 2800000.00, 27000.00, '2026-07-10', 'active')

""")
print("loans inserted!")


# ============================================================
# STEP 5 — SAVE CHANGES
# ============================================================
db_conn.commit()
cursor.close()

print("\nall tables created and test data inserted successfully!")