import sqlite3

DB_PATH = 'travel_planner.db'

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS itineraries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            destination TEXT,
            start_date TEXT,
            end_date TEXT,
            notes TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_user(username, password):
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
    conn.commit()
    conn.close()

def get_user_by_username(username):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = c.fetchone()
    conn.close()
    return user

def create_itinerary(username, destination, start_date, end_date, notes):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        INSERT INTO itineraries (username, destination, start_date, end_date, notes)
        VALUES (?, ?, ?, ?, ?)
    ''', (username, destination, start_date, end_date, notes))
    conn.commit()
    conn.close()

def get_itineraries_by_user(username):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM itineraries WHERE username = ?', (username,))
    itineraries = c.fetchall()
    conn.close()
    return itineraries
