import mysql.connector

DB_CONFIG = {
    'user': 'root',
    'password': '39090169',
    'host': 'localhost',
    'database': 'esp32_report'
}

def create_table():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            nombre VARCHAR(255) PRIMARY KEY,
            contrasena VARCHAR(255) NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def add_user(nombre, contraceña):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO employees (nombre, contrasena) VALUES (%s, %s)', (nombre, contraceña))
        conn.commit()
    except mysql.connector.IntegrityError:
        return False  # El usuario ya existe
    finally:
        conn.close()
    return True

def get_user(nombre, contraceña):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM employees WHERE nombre = %s AND contrasena = %s', (nombre, contraceña))
    user = cursor.fetchone()
    conn.close()
    return user