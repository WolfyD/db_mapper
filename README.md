# DB Mapper

A Python tool that creates hierarchical diagrams from SQLite databases or SQL schema files.

## Features

- Parse SQLite database files
- Parse SQL files containing CREATE TABLE statements
- Generate hierarchical diagrams showing table relationships
- Display column information including data types and constraints

## Installation

1. Clone this repository
2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

```python
from db_mapper import DatabaseMapper

# Create a mapper instance
mapper = DatabaseMapper()

# Option 1: Parse a SQLite database
mapper.parse_sqlite_db('path/to/your/database.db')

# Option 2: Parse a SQL file
mapper.parse_sql_file('path/to/your/schema.sql')

# Generate the diagram
mapper.generate_diagram('output_filename')  # Will create output_filename.png
```

## Requirements

- Python 3.6+
- sqlparse
- graphviz (requires Graphviz to be installed on your system)

## Output

The tool generates a PNG file containing a hierarchical diagram of your database schema, showing:
- Tables and their columns
- Column data types and constraints
- Relationships between tables 