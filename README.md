# DB Mapper

A Python tool that creates hierarchical diagrams from SQLite databases or SQL schema files.

## Features

- Parse SQLite database files (`.db`, `.sqlite`, `.sqlite3`)
- Parse SQL files containing CREATE TABLE statements
- Generate hierarchical diagrams showing table relationships
- Display column information including data types and constraints
- **Assume relationships** based on column naming patterns (e.g., `user_id` → `users`)
- **Colorful and dark mode** output for better visualization
- **Cluster tables** by prefix for better organization
- **Customizable font** for all diagram text
- **Customizable arrow style**: choose between curved, straight, or right-angled connectors
- **Generate SQL for missing foreign keys** with `--create-keys` and `--create-sqlite-keys`

## Installation

1. Clone this repository
   ```bash
   git clone https://github.com/WolfyD/db_mapper.git
   cd db_mapper
   ```
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install Graphviz on your system (see https://graphviz.org/download/)
  
   Make sure that the executable path is added to the Path environmental variable

## Usage

### Command Line

```bash
python db_mapper.py <input_file> [options]
```

#### Options

- `--output, -o <name>`: Output file name (without extension)
- `--assume, -a`: Assume relationships based on column naming patterns
- `--color, -c`: Assign a unique color to each table and its outgoing arrows
- `--dark, -d`: Use a dark background and light foreground
- `--full, -f`: Show all columns and increase spacing between tables
- `--font <fontname>`: Font to use for diagram. Options: 
  - `Arial`, 
  - `Helvetica`
  - `Consolas`
  - `Courier`
  - `Times`
  - `Verdana`
  - `Tahoma`
  - `Trebuchet MS`
  - `Georgia`
  - `Palatino`
  - `Impact`
  - `Comic Sans MS`
- `--arrow-type, -t <type>`: Arrow style for connections. Options:
  - `curved` (default): Curved arrows
  - `polyline`: Straight arrows
  - `ortho`: Right-angled (orthogonal) arrows
- `--create-keys`: Print SQL statements to create all assumed foreign keys and exit. **All other flags are ignored.**
- `--create-sqlite-keys`: Print assumed FOREIGN KEY clauses for each table (for SQLite CREATE TABLE) and exit. **All other flags are ignored.**

#### Example

```bash
python db_mapper.py schema.sql --assume --color --dark --full --font Arial --arrow-type ortho -o my_diagram
```

#### Example: Generate SQL for missing foreign keys

```bash
python db_mapper.py schema.sql --create-keys
```
This will print a transaction-wrapped list of `ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY ... REFERENCES ...` statements for all assumed relationships:

```
BEGIN;
ALTER TABLE child_table
ADD CONSTRAINT fk_child_table_parent_table
FOREIGN KEY (child_column) REFERENCES parent_table(parent_column);
...
COMMIT;
```

### Python API

```python
from db_mapper import DatabaseMapper

mapper = DatabaseMapper()
mapper.parse_sqlite_db('path/to/your/database.db')
# or
mapper.parse_sql_file('path/to/your/schema.sql')
mapper.generate_diagram('output_filename')  # Will create output_filename.png
```

## Requirements

- Python 3.6+
- sqlparse
- graphviz (Python package and system install)

## Output

The tool generates a PNG file containing a hierarchical diagram of your database schema, showing:
- Tables and their columns (all columns or just relational, depending on flags)
- Column data types and constraints
- Relationships between tables (explicit using Fk and/or assumed based on naming conventions)
- Optional: color, dark mode, custom font, and custom arrow style

---

 ### Disclaimer:
 AI tools were used in the making of db_mapper
 
 ---