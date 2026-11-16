# database.py
import pymysql
import os
from pymysql import Error
from config import Config

# Ruta del socket de MariaDB en Termux
SOCKET_PATH = '/data/data/com.termux/files/usr/var/run/mysqld.sock'

def get_connection():
    """Devuelve una conexión a la base de datos MySQL usando PyMySQL."""
    try:
        args = {
            'user': Config.DB_USER,
            'password': Config.DB_PASSWORD,
            'database': Config.DB_NAME,
            'charset': 'utf8mb4',
            'connect_timeout': 10,
            'cursorclass': pymysql.cursors.DictCursor
        }

        # En local (Termux) usar socket Unix; en producción (Aiven) usar TCP + SSL
        if Config.DB_HOST in ('localhost', '127.0.0.1') and not Config.DB_SSL and os.path.exists(SOCKET_PATH):
            args['unix_socket'] = SOCKET_PATH
        else:
            args['host'] = Config.DB_HOST
            args['port'] = Config.DB_PORT
            if Config.DB_SSL:
                args['ssl'] = {'ssl': {}}
                args['ssl_verify_cert'] = False
                args['ssl_verify_identity'] = False

        connection = pymysql.connect(**args)
        return connection
    except Error as e:
        print(f"Error conectando a MySQL: {e}")
        return None

def query(sql, params=None, fetchone=False, fetchall=False, commit=False):
    """Ejecuta una consulta SQL de forma segura."""
    conn = get_connection()
    if conn is None:
        return None

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params or ())

        if commit:
            conn.commit()
            last_id = cursor.lastrowid
            cursor.close()
            conn.close()
            return last_id

        if fetchone:
            result = cursor.fetchone()
        elif fetchall:
            result = cursor.fetchall()
        else:
            result = None

        cursor.close()
        conn.close()
        return result
    except Error as e:
        print(f"Error en la consulta: {e}")
        cursor.close()
        conn.close()
        return None
