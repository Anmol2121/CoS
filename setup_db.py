# setup_db.py
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
from dotenv import load_dotenv

load_dotenv()

# Database connection parameters (without database name)
db_params = {
    'host': 'localhost',
    'port': 5432,
    'user': 'postgres',
    'password': 'Ac@5121999'
}

def create_database():
    try:
        # Connect to PostgreSQL server (default database 'postgres')
        conn = psycopg2.connect(**db_params)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'coaching_db'")
        exists = cursor.fetchone()
        
        if not exists:
            # Create database
            cursor.execute('CREATE DATABASE coaching_db')
            print("✅ Database 'coaching_db' created successfully!")
        else:
            print("✅ Database 'coaching_db' already exists.")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error creating database: {e}")
        
def test_connection():
    try:
        # Test connection to the new database
        conn = psycopg2.connect(
            host='localhost',
            port=5432,
            user='postgres',
            password='Ac@5121999',
            database='coaching_db'
        )
        print("✅ Successfully connected to 'coaching_db'!")
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

if __name__ == '__main__':
    print("Setting up database...")
    create_database()
    test_connection()
    print("\nNow run: python app.py")