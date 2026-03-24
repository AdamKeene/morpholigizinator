import os
import sqlite3
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any

# Database configuration
DB_FILE = "grammar_categories.db"

def create_database():
    """Create the SQLite database with required tables."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create categories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            node_type TEXT NOT NULL,
            is_clause BOOLEAN DEFAULT 0
        )
    ''')
    
    # Create dependencies table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT NOT NULL,
            dependency TEXT NOT NULL,
            FOREIGN KEY (category_name) REFERENCES categories (name)
        )
    ''')
    
    # Create index for faster lookups
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_node_type ON categories (node_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_is_clause ON categories (is_clause)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_category_name ON dependencies (category_name)')
    
    conn.commit()
    conn.close()

def fetch_html_data():
    """Fetch HTML data from the web or local file."""
    link = "https://www.grammaticalframework.org/lib/doc/absfuns.html"
    local_filename = "absfuns.html"
    
    if os.path.exists(local_filename):
        with open(local_filename, "r", encoding="utf-8") as f:
            return f.read()
    else:
        response = requests.get(link)
        html_content = response.text
        with open(local_filename, "w", encoding="utf-8") as f:
            f.write(html_content)
        return html_content

def populate_database():
    """Parse HTML and populate the database with category data."""
    html_content = fetch_html_data()
    soup = BeautifulSoup(html_content, 'html.parser')
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Clear existing data
    cursor.execute('DELETE FROM dependencies')
    cursor.execute('DELETE FROM categories')
    
    clause_types = ['Cl', 'RCl', 'QCl', 'ClAdv', 'ClSlash', 'Utt', 'S']
    clause_dependencies = ['Cl', 'RCl', 'QCl', 'ClAdv', 'ClSlash', 'Utt', 'S', 'VP']
    
    for item in soup.find_all('tr'):
        cells = item.find_all('td')
        if len(cells) < 2:
            continue
            
        name = cells[0].text.strip()
        node_type = cells[1].text.split()[-1]
        dependencies = cells[1].text.split()[:-1]
        
        # Clean up dependencies
        dependencies = [dep for dep in dependencies if dep != '->']
        
        # Determine if this is a clause
        is_clause = (node_type in clause_types or 
                    any(dep in clause_dependencies for dep in dependencies))
        
        # Insert category
        cursor.execute('''
            INSERT OR REPLACE INTO categories (name, node_type, is_clause)
            VALUES (?, ?, ?)
        ''', (name, node_type, is_clause))
        
        # Insert dependencies
        for dep in dependencies:
            cursor.execute('''
                INSERT INTO dependencies (category_name, dependency)
                VALUES (?, ?)
            ''', (name, dep))
    
    conn.commit()
    conn.close()

def get_categories_by_type(node_type: str) -> List[str]:
    """Get all categories of a specific node type."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM categories WHERE node_type = ?', (node_type,))
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results

def get_all_clauses() -> List[str]:
    """Get all clause categories."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM categories WHERE is_clause = 1')
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results

def get_dependencies(category_name: str) -> List[str]:
    """Get all dependencies for a specific category."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT dependency FROM dependencies WHERE category_name = ?', (category_name,))
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results

def get_category_info(category_name: str) -> Dict[str, Any]:
    """Get complete information about a category."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT name, node_type, is_clause 
        FROM categories 
        WHERE name = ?
    ''', (category_name,))
    
    result = cursor.fetchone()
    if not result:
        conn.close()
        return None
    
    name, node_type, is_clause = result
    
    # Get dependencies
    cursor.execute('SELECT dependency FROM dependencies WHERE category_name = ?', (category_name,))
    dependencies = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        'name': name,
        'node_type': node_type,
        'is_clause': bool(is_clause),
        'dependencies': dependencies
    }

# Dictionary-like interface — lazily initialized on first access.
class CategoryDB:
    def __init__(self):
        self._ready = False

    def _ensure_initialized(self):
        if self._ready:
            return
        if not os.path.exists(DB_FILE):
            create_database()
            populate_database()
        self._ready = True

    def __getitem__(self, key):
        self._ensure_initialized()
        if key == 'all_clauses':
            return get_all_clauses()
        return get_categories_by_type(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except Exception:
            return default

    def keys(self):
        self._ensure_initialized()
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT node_type FROM categories')
        node_types = [row[0] for row in cursor.fetchall()]
        conn.close()
        return ['all_clauses'] + node_types


cats = CategoryDB()