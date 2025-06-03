import sqlite3
import sqlparse
import os
import re
import sys
import subprocess
from graphviz import Digraph
from typing import Union, Dict, List, Tuple
import hashlib
from InquirerPy import prompt
from InquirerPy.base.control import Choice
from InquirerPy.validator import PathValidator

BRIGHT_COLORS_LIGHT = [
    '#E63946', '#F4A261', '#2A9D8F', '#264653', '#6A4C93',
    '#FFB703', '#3D405B', '#D62828', '#457B9D', '#A8DADC',
    '#1D3557', '#F9844A', '#43AA8B', '#9A031E', '#5F0F40',
    '#0F4C5C', '#F77F00', '#6D6875', '#2C7DA0', '#8ECAE6'
]
BRIGHT_COLORS_DARK = [
    '#FF6B6B', '#FFD93D', '#6BCB77', '#4D96FF', '#F9C80E',
    '#FF9F1C', '#A9DEF9', '#E4C1F9', '#70D6FF', '#FF70A6',
    '#C0FDFB', '#F6F740', '#FFA69E', '#CBF3F0', '#D0F4DE',
    '#FEC8D8', '#FFDAC1', '#F5F5F5', '#FFFFFF', '#D9ED92'
]

def check_graphviz_installation():
    """Check if Graphviz is installed and accessible."""
    # Common Graphviz installation paths
    possible_paths = [
        r"C:\Program Files\Graphviz\bin",
        r"C:\Program Files (x86)\Graphviz\bin",
        r"C:\Other\Programs\Graphviz\bin",  # Your custom path
    ]
    
    # Check if dot is already in PATH
    try:
        subprocess.run(['dot', '-V'], capture_output=True, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        # If not in PATH, try to find it in common locations
        for path in possible_paths:
            if os.path.exists(os.path.join(path, 'dot.exe')):
                # Add to PATH for this process
                os.environ['PATH'] = path + os.pathsep + os.environ['PATH']
                try:
                    subprocess.run(['dot', '-V'], capture_output=True, check=True)
                    return True
                except (subprocess.SubprocessError, FileNotFoundError):
                    continue
    
    # If we get here, Graphviz is not found
    print("Error: Graphviz is not installed or not in PATH.")
    print("\nTo fix this:")
    print("1. Download Graphviz from https://graphviz.org/download/")
    print("2. Install it on your system")
    print("3. Make sure the Graphviz bin directory is in your PATH")
    print("   (usually C:\\Program Files\\Graphviz\\bin)")
    print("\nIf Graphviz is installed in a custom location, add it to your PATH:")
    print("1. Press Windows + R")
    print("2. Type 'sysdm.cpl' and press Enter")
    print("3. Go to the 'Advanced' tab")
    print("4. Click 'Environment Variables'")
    print("5. Under 'System Variables', find and select 'Path'")
    print("6. Click 'Edit'")
    print("7. Click 'New'")
    print("8. Add the path to your Graphviz bin directory")
    print("9. Click 'OK' on all windows")
    print("\nAfter installation, you may need to restart your terminal.")
    sys.exit(1)

class DatabaseMapper:
    def __init__(self, assume_relationships: bool = False):
        self.tables: Dict[str, Dict] = {}
        self.relationships: List[Tuple[str, str, str]] = []  # (table1, table2, relationship_type)
        self.assume_relationships = assume_relationships
        self.explicit_relationships: List[Tuple[str, str, str]] = []  # Store explicit relationships separately
        self.color_tables: bool = False
        self.dark_mode: bool = False
        self.full_mode: bool = False
        self.diagram_font: str = 'Consolas'
        self.arrow_type: str = 'curved'
        self.layout: str = 'LR'  # Default left-to-right layout
        self.compact_mode: bool = False  # Whether to use compact layout
        self.engine: str = 'dot'  # Default Graphviz engine
        self.nodesep: float = 0.6  # Default node separation
        self.ranksep: float = 0.7  # Default rank separation
        self.overlap: str = None   # Default overlap setting
        self.sort_by_incoming: bool = False  # Sort tables by incoming connections only if flag is set
        self.font_size: int = 12  # Default font size
        self.dpi: int = 96        # Default DPI
        self.show_indexes: bool = False  # Show index marker in diagram
        self.indexed_columns: dict = {}  # table_name -> set of indexed column names
        
    def _find_potential_relationships(self) -> List[Tuple[str, str, str]]:
        """Find potential relationships based on column naming patterns, including advanced pluralization."""
        assumed_relationships = []
        # Common patterns for foreign key columns
        patterns = [
            r'^(\w+)_id$',  # table_id
            r'^(\w+)ID$',   # tableID
            r'^(\w+)Id$',   # tableId
            r'^(\w+)_ID$',  # table_ID
            r'^(\w+)Key$',  # tableKey
            r'^(\w+)_key$', # table_key
        ]
        
        # First, find all primary key columns
        pk_columns = {}  # table_name -> column_name
        for table_name, table_info in self.tables.items():
            for col in table_info['columns']:
                if col['pk']:
                    pk_columns[table_name] = col['name']
        
        # Pluralization helpers
        def plural_candidates(base):
            candidates = set()
            candidates.add(base)
            candidates.add(base + 's')
            if base.endswith('s'):
                candidates.add(base[:-1])
            if base.endswith('y'):
                candidates.add(base[:-1] + 'ies')
            if base.endswith('ies'):
                candidates.add(base[:-3] + 'y')
            if base.endswith('ss'):
                candidates.add(base + 'es')
            if base.endswith('es'):
                candidates.add(base[:-2])
            return candidates
        
        # Then look for potential foreign keys
        for table_name, table_info in self.tables.items():
            for col in table_info['columns']:
                col_name = col['name'].lower()
                
                # Skip if this is a primary key column
                if col_name == pk_columns.get(table_name, '').lower():
                    continue
                
                # Check each pattern
                for pattern in patterns:
                    match = re.match(pattern, col_name)
                    if match:
                        referenced_base = match.group(1).lower()
                        candidates = plural_candidates(referenced_base)
                        # Check if the referenced table exists (advanced pluralization aware)
                        for potential_table in self.tables.keys():
                            pt_lower = potential_table.lower()
                            if pt_lower in candidates:
                                if potential_table in pk_columns:
                                    assumed_relationships.append((
                                        table_name,
                                        potential_table,
                                        f"{col['name']} → {pk_columns[potential_table]}"
                                    ))
                                break
        
        return assumed_relationships
        
    def parse_sqlite_db(self, db_path: str) -> None:
        """Parse a SQLite database file and extract table information."""
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
            
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        self.indexed_columns = {}
        
        for table in tables:
            table_name = table[0]
            # Get table schema
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            
            self.tables[table_name] = {
                'columns': [{'name': col[1], 'type': col[2], 'nullable': not col[3], 'pk': col[5]} 
                          for col in columns]
            }
            
            # Get foreign keys
            cursor.execute(f"PRAGMA foreign_key_list({table_name});")
            foreign_keys = cursor.fetchall()
            
            for fk in foreign_keys:
                self.explicit_relationships.append((
                    table_name,
                    fk[2],  # referenced table
                    fk[3]   # referenced column
                ))
            
            # Get indexed columns
            indexed_cols = set()
            cursor.execute(f"PRAGMA index_list({table_name});")
            for idx in cursor.fetchall():
                idx_name = idx[1]
                # Only consider non-unique indexes and unique indexes (ignore internal PK index)
                if idx_name.startswith('sqlite_autoindex'):
                    continue
                cursor.execute(f"PRAGMA index_info({idx_name});")
                for idxinfo in cursor.fetchall():
                    indexed_cols.add(idxinfo[2])
            # Add PK columns as indexed
            for col in self.tables[table_name]['columns']:
                if col['pk']:
                    indexed_cols.add(col['name'])
            self.indexed_columns[table_name] = indexed_cols
        
        conn.close()
        
        # Always add explicit relationships
        self.relationships = list(self.explicit_relationships)
        # If assume_relationships is True, add assumed relationships too
        if self.assume_relationships:
            assumed = self._find_potential_relationships()
            for rel in assumed:
                # rel = (child, parent, label)
                # Only add if not already present as an explicit relationship for the same child, parent, and child column
                child_col = rel[2].split('→')[0].strip()
                already_explicit = any(
                    rel[0] == exp[0] and rel[1] == exp[1] and child_col == exp[2].split('→')[0].strip()
                    for exp in self.explicit_relationships
                )
                if not already_explicit and rel not in self.relationships:
                    self.relationships.append(rel)
    
    def _extract_column_info(self, column_def: str) -> Dict:
        """Extract column information from a column definition string."""
        # Remove any comments
        column_def = re.sub(r'--.*$', '', column_def).strip()
        
        # Split into name and definition
        parts = column_def.split(None, 1)
        if len(parts) < 2:
            return None
            
        name = parts[0].strip('"[]`')
        definition = parts[1].upper()
        
        # Extract type
        type_match = re.search(r'(\w+)(?:\([^)]+\))?', definition)
        col_type = type_match.group(1) if type_match else 'TEXT'
        
        # Check for constraints
        is_pk = 'PRIMARY KEY' in definition
        is_nullable = 'NOT NULL' not in definition
        
        return {
            'name': name,
            'type': col_type,
            'nullable': is_nullable,
            'pk': is_pk
        }
    
    def _extract_foreign_keys(self, table_name: str, create_stmt: str) -> None:
        """Extract foreign key relationships from CREATE TABLE statement."""
        # Look for FOREIGN KEY constraints
        fk_pattern = r'FOREIGN\s+KEY\s*\(([^)]+)\)\s*REFERENCES\s+([^\s(]+)(?:\s*\(([^)]+)\))?'
        fk_matches = re.finditer(fk_pattern, create_stmt, re.IGNORECASE)
        
        for match in fk_matches:
            local_col = match.group(1).strip('"[]`')
            ref_table = match.group(2).strip('"[]`')
            ref_col = match.group(3).strip('"[]`') if match.group(3) else local_col
            
            self.explicit_relationships.append((table_name, ref_table, ref_col))
    
    def parse_sql_file(self, sql_path: str) -> None:
        """Parse a SQL file containing CREATE TABLE statements."""
        if not os.path.exists(sql_path):
            raise FileNotFoundError(f"SQL file not found: {sql_path}")
            
        with open(sql_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # Normalize SQL content
        sql_content = sql_content.replace('\n', ' ').replace('\r', ' ')
        sql_content = re.sub(r'\s+', ' ', sql_content)
        
        # Find all CREATE TABLE statements
        create_pattern = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)\s*\((.*?)\)(?:\s*;|\s*$)'
        create_matches = re.finditer(create_pattern, sql_content, re.IGNORECASE)
        
        for match in create_matches:
            table_name = match.group(1).strip('"[]`')
            table_def = match.group(2)
            
            # Split into column definitions
            # This regex handles nested parentheses for complex types
            column_defs = []
            current_def = []
            paren_count = 0
            
            for part in table_def.split(','):
                paren_count += part.count('(') - part.count(')')
                current_def.append(part)
                
                if paren_count == 0:
                    column_defs.append(','.join(current_def))
                    current_def = []
            
            # Process columns
            columns = []
            for col_def in column_defs:
                col_def = col_def.strip()
                # Remove any trailing ')' or ';' from the last column
                col_def = col_def.rstrip('); \n\t')
                # Skip table-level constraints
                if col_def.upper().startswith(('FOREIGN KEY', 'PRIMARY KEY', 'UNIQUE', 'CHECK')):
                    continue
                col_info = self._extract_column_info(col_def)
                if col_info:
                    columns.append(col_info)
            
            if columns:
                self.tables[table_name] = {'columns': columns}
                
            # Extract foreign keys
            self._extract_foreign_keys(table_name, table_def)
        
        # Always add explicit relationships
        self.relationships = list(self.explicit_relationships)
        # If assume_relationships is True, add assumed relationships too
        if self.assume_relationships:
            assumed = self._find_potential_relationships()
            for rel in assumed:
                # rel = (child, parent, label)
                # Only add if not already present as an explicit relationship for the same child, parent, and child column
                child_col = rel[2].split('→')[0].strip()
                already_explicit = any(
                    rel[0] == exp[0] and rel[1] == exp[1] and child_col == exp[2].split('→')[0].strip()
                    for exp in self.explicit_relationships
                )
                if not already_explicit and rel not in self.relationships:
                    self.relationships.append(rel)
    
    def generate_diagram(self, output_path: str = 'database_diagram') -> None:
        """Generate a compact, clustered, and relational-only diagram of the database structure."""
        dot = Digraph(comment='Database Schema', engine=self.engine)
        dot.attr(charset='UTF-8')
        
        # Use user-specified or default spacing, divide by 10, min 0.1
        nodesep_val = max(int(self.nodesep), 1) / 10
        ranksep_val = max(int(self.ranksep), 1) / 10
        nodesep = str(nodesep_val)
        ranksep = str(ranksep_val)
        
        # Adjust spacing based on compact mode
        if self.compact_mode:
            dot.attr(rankdir=self.layout, nodesep=nodesep, ranksep=ranksep, splines='true')
            dot.attr(compound='true')
            dot.attr('node', margin='0.2')
            dot.attr('edge', minlen='1')
        else:
            dot.attr(rankdir=self.layout, nodesep=nodesep, ranksep=ranksep)
        
        # Set overlap if specified (especially useful for neato/fdp)
        if self.overlap:
            dot.attr(overlap=self.overlap)
        
        # Set font size and DPI
        fontsize = str(self.font_size)
        dot.attr('node', fontsize=fontsize)
        dot.attr('edge', fontsize=fontsize)
        dot.attr('graph', fontsize=fontsize)
        dot.attr(dpi=str(self.dpi))
        
        fontname = getattr(self, 'diagram_font', 'Consolas')

        if getattr(self, 'dark_mode', False):
            dot.attr(bgcolor='#111111')
            fontcolor = '#eeeeee'
        else:
            dot.attr(bgcolor='white')
            fontcolor = '#222222'

        dot.attr('node', fontname=fontname)
        dot.attr('edge', fontname=fontname)
        dot.attr('graph', fontname=fontname)

        table_colors = {}
        if getattr(self, 'color_tables', False):
            for table_name in self.tables:
                table_colors[table_name] = get_table_color(table_name, getattr(self, 'dark_mode', False))
        else:
            for table_name in self.tables:
                table_colors[table_name] = fontcolor

        # Group tables by prefix for clustering
        clusters = {}
        for table_name in self.tables:
            prefix = table_name.split('_')[0] if '_' in table_name else table_name
            clusters.setdefault(prefix, []).append(table_name)

        # Helper to get relational columns
        def is_relational(col):
            return col['pk'] or re.search(r'_id$|_ID$|_Id$|ID$|Id$|Key$|_key$', col['name'])

        # Calculate incoming connection counts for each table
        incoming_counts = {table: 0 for table in self.tables}
        for _, to_table, _ in self.relationships:
            if to_table in incoming_counts:
                incoming_counts[to_table] += 1

        # Sort clusters and tables by incoming connection count if enabled
        def sort_key(table):
            return -incoming_counts.get(table, 0), table  # Descending by incoming, then name
        
        # Sort clusters by the highest incoming count of any table in the cluster
        cluster_items = list(clusters.items())
        if self.sort_by_incoming:
            cluster_items.sort(key=lambda item: max([incoming_counts.get(t, 0) for t in item[1]]), reverse=True)
        
        # Add clusters (subgraphs) only if more than one table in group
        clustered_tables = set()
        for prefix, table_names in cluster_items:
            if len(table_names) > 1:
                # Sort tables in cluster if enabled
                if self.sort_by_incoming:
                    table_names = sorted(table_names, key=sort_key)
                with dot.subgraph(name=f'cluster_{prefix}') as c:
                    if getattr(self, 'dark_mode', False):
                        c.attr(label=prefix.upper(), style='dashed', color='#cccccc', fontcolor='#cccccc', fontname=fontname)
                    else:
                        c.attr(label=prefix.upper(), style='dashed', fontname=fontname)
                    if self.compact_mode:
                        c.attr(margin='0.2')
                    for table_name in table_names:
                        table_info = self.tables[table_name]
                        if getattr(self, 'full_mode', False):
                            show_cols = table_info['columns']
                            table_label = table_name
                        else:
                            show_cols = [col for col in table_info['columns'] if is_relational(col)]
                            table_label = table_name
                        label = f'''<
<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4">
  <TR><TD WIDTH="120"><U><B>{table_label}</B></U></TD></TR>'''
                        for col in show_cols:
                            col_display = col["name"]
                            # Show index marker if enabled and column is indexed
                            if self.show_indexes and table_name in self.indexed_columns and col["name"] in self.indexed_columns[table_name]:
                                col_display += ' [i]'
                            label += f'  <TR><TD ALIGN="LEFT">{col_display} ({col["type"]})'
                            if col['pk']:
                                label += ' <B>[PK]</B>'
                            label += '</TD></TR>'
                        label += '</TABLE>>'
                        node_kwargs = dict(shape='plaintext', width='1.5', fontcolor=table_colors[table_name], fontname=fontname)
                        if getattr(self, 'dark_mode', False):
                            node_kwargs['color'] = '#eeeeee'
                        c.node(table_name, label=label, **node_kwargs)
                        clustered_tables.add(table_name)
        # Add non-clustered tables
        non_clustered = [t for t in self.tables if t not in clustered_tables]
        if self.sort_by_incoming:
            non_clustered = sorted(non_clustered, key=sort_key)
        for table_name in non_clustered:
            table_info = self.tables[table_name]
            if getattr(self, 'full_mode', False):
                show_cols = table_info['columns']
                table_label = table_name
            else:
                show_cols = [col for col in table_info['columns'] if is_relational(col)]
                table_label = table_name
            label = f'''<
<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4">
  <TR><TD WIDTH="120"><U><B>{table_label}</B></U></TD></TR>'''
            for col in show_cols:
                col_display = col["name"]
                if self.show_indexes and table_name in self.indexed_columns and col["name"] in self.indexed_columns[table_name]:
                    col_display += ' [i]'
                label += f'  <TR><TD ALIGN="LEFT">{col_display} ({col["type"]})'
                if col['pk']:
                    label += ' <B>[PK]</B>'
                label += '</TD></TR>'
            label += '</TABLE>>'
            node_kwargs = dict(shape='plaintext', width='1.5', fontcolor=table_colors[table_name], fontname=fontname)
            if getattr(self, 'dark_mode', False):
                node_kwargs['color'] = '#eeeeee'
            dot.node(table_name, label=label, **node_kwargs)

        # Add relationships
        for table1, table2, rel_type in self.relationships:
            edge_color = table_colors.get(table1, fontcolor)
            # Use HTML-like labels for bold/italic
            if self.assume_relationships:
                if (table1, table2, rel_type) in self.explicit_relationships:
                    label_html = f'<<B>{rel_type}</B>>'
                else:
                    label_html = f'<<I>{rel_type}</I>>'
                if (table1, table2, rel_type) not in self.explicit_relationships:
                    dot.edge(table1, table2, label=label_html, style='dashed', color=edge_color, fontcolor=edge_color)
                else:
                    dot.edge(table1, table2, label=label_html, color=edge_color, fontcolor=edge_color)
            else:
                dot.edge(table1, table2, label=rel_type, color=edge_color, fontcolor=edge_color)
            # If referenced table does not exist, add a node for it
            if table2 not in self.tables:
                if getattr(self, 'dark_mode', False):
                    dot.node(table2, table2, shape='circle', style='filled', fillcolor='#eeeeee', fontcolor='#222222', fontname=fontname)
                else:
                    dot.node(table2, table2, shape='circle', style='filled', fillcolor='black', fontcolor='white', fontname=fontname)

        # Set edge style based on arrow_type
        arrow_type = getattr(self, 'arrow_type', 'curved')
        if arrow_type == 'curved':
            dot.attr(splines='true')
        elif arrow_type == 'polyline':
            dot.attr(splines='polyline')
        elif arrow_type == 'ortho':
            dot.attr(splines='ortho')
        else:
            dot.attr(splines='true')  # fallback

        # Save diagram
        dot.render(output_path, format='png', cleanup=True)

    def _suggest_indexes(self) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
        """Suggest indexes for tables based on column characteristics.
        Returns a tuple of (definite_indexes, possible_indexes) where each is a dict of table_name -> list of index statements."""
        definite_indexes = {}
        possible_indexes = {}
        
        for table_name, table_info in self.tables.items():
            # Skip sqlite_sequence table
            if table_name == 'sqlite_sequence':
                continue
                
            definite = []
            possible = []
            
            # Get all columns
            columns = table_info['columns']
            
            # Find primary key column
            pk_col = next((col['name'] for col in columns if col['pk']), None)
            
            # Find foreign key columns
            fk_cols = []
            for rel in self.relationships:
                if rel[0] == table_name:  # This table is the child
                    # Extract just the column name from the relationship label
                    fk_col = rel[2].split('→')[0].strip()
                    fk_cols.append(fk_col)
            
            # Definite indexes:
            # 1. Foreign key columns (if not already indexed)
            for fk_col in fk_cols:
                if fk_col != pk_col:  # Don't index if it's already the PK
                    definite.append(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{fk_col} ON {table_name}({fk_col});")
            
            # 2. Columns that are frequently used in WHERE clauses (based on naming)
            where_patterns = [
                r'status$', r'type$', r'category$', r'is_', r'has_', r'active$',
                r'date$', r'created$', r'updated$', r'deleted$', r'name$'
            ]
            for col in columns:
                col_name = col['name'].lower()
                if any(re.search(pattern, col_name) for pattern in where_patterns):
                    if col_name != pk_col and col_name not in fk_cols:
                        definite.append(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{col['name']} ON {table_name}({col['name']});")
            
            # Possible indexes:
            # 1. Columns that might be used in WHERE clauses (based on type)
            for col in columns:
                col_name = col['name'].lower()
                col_type = col['type'].upper()
                
                # Skip if already in definite indexes or is PK
                if col_name == pk_col or col_name in fk_cols:
                    continue
                
                # Suggest indexes for columns that might be used in filtering
                if col_type in ('INTEGER', 'BOOLEAN', 'DATE', 'DATETIME', 'TIMESTAMP'):
                    possible.append(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{col['name']} ON {table_name}({col['name']});")
                
                # Suggest indexes for columns that might be used in sorting
                if col_type in ('TEXT', 'VARCHAR', 'CHAR', 'INTEGER', 'DATE', 'DATETIME', 'TIMESTAMP'):
                    if 'name' in col_name or 'title' in col_name or 'code' in col_name:
                        possible.append(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{col['name']} ON {table_name}({col['name']});")
            
            if definite:
                definite_indexes[table_name] = definite
            if possible:
                possible_indexes[table_name] = possible
        
        return definite_indexes, possible_indexes

def get_table_color(table_name, dark_mode=False):
    palette = BRIGHT_COLORS_DARK if dark_mode else BRIGHT_COLORS_LIGHT
    idx = int(hashlib.md5(table_name.encode()).hexdigest(), 16) % len(palette)
    return palette[idx]

def show_help():
    """Display detailed help information about all options."""
    help_text = """
Database Mapper Help
===================

Main Actions:
-------------
1. Generate database diagram
   Creates a visual representation of your database schema
   - Shows tables, columns, and relationships
   - Supports various layout engines and styles
   - Can show assumed relationships based on naming patterns

2. Generate SQL for missing foreign keys
   Creates ALTER TABLE statements for assumed relationships
   - Wraps statements in a transaction
   - Names constraints automatically
   - Only includes relationships not already defined

3. Generate SQLite FOREIGN KEY clauses
   Creates FOREIGN KEY clauses for CREATE TABLE statements
   - Groups by table
   - Includes proper comma separation
   - Ready to paste into CREATE TABLE statements

4. Generate suggested indexes
   Suggests indexes based on column characteristics
   - Definite indexes: foreign keys and common filter columns
   - Possible indexes: columns likely to be used in WHERE/ORDER BY
   - Includes index names and table references

5. Generate suggested triggers
   Suggests useful triggers for your tables
   - Audit triggers for change tracking
   - Validation triggers for data integrity
   - Auto-update triggers for timestamps
   - Soft delete triggers
   - Referential integrity triggers

Diagram Options:
--------------
1. Basic Options:
   - Assume relationships: Detect relationships based on column naming patterns
   - Use colors: Assign unique colors to tables and their relationships
   - Dark mode: Use dark background with light text
   - Show all columns: Display non-relational columns too
   - Show indexed columns: Mark columns that are indexed
   - Sort by incoming: Place referenced tables more centrally
   - Compact layout: Reduce spacing between elements

2. Layout Direction:
   - Left to Right (LR): Traditional horizontal layout
   - Right to Left (RL): Reverse horizontal layout
   - Top to Bottom (TB): Traditional vertical layout
   - Bottom to Top (BT): Reverse vertical layout

3. Layout Engines:
   - Dot (hierarchical): Best for most diagrams, supports all arrow styles
   - Neato (force-directed): Good for small to medium graphs
   - FDP (force-directed): Good for large graphs
   - SFDP (force-directed): Best for very large graphs
   - Twopi (radial): Good for hierarchical data
   - Circo (circular): Good for cyclic structures

4. Arrow Styles:
   - Curved: Works with all engines
   - Straight lines: Only works with dot engine
   - Right-angled: Only works with dot engine

5. Advanced Options:
   - Node separation: Space between nodes (especially for force-directed engines)
   - Rank separation: Space between rows/columns (especially for force-directed engines)
   - Font size: Size of all text in the diagram
   - DPI: Image resolution (higher = better quality)
   - Overlap handling: Controls how nodes avoid overlapping
     * false: No overlap allowed
     * scale: Reduce overlap by scaling
     * prism: Force-directed overlap removal
     * compress: Reduce size to avoid overlap
     * vpsc: Variable overlap removal
     * ortho/orthoxy/ortho_yx: Orthogonal layouts
     * pcompress: Parallel compression
     * ipsep: Incremental separation
     * sep/sep+: Separation methods
     * true: Allow overlap

Tips:
-----
1. For large databases:
   - Use SFDP engine
   - Enable compact layout
   - Use overlap handling
   - Consider showing only relational columns

2. For better readability:
   - Use dark mode for light backgrounds
   - Increase font size
   - Use higher DPI for better quality
   - Enable colors for better distinction

3. For force-directed layouts:
   - Adjust node and rank separation
   - Use appropriate overlap handling
   - Consider using curved arrows

4. For hierarchical data:
   - Use dot engine with TB layout
   - Consider using ortho arrows
   - Enable sort by incoming connections
"""
    print(help_text)
    input("\nPress Enter to continue...")

def interactive_menu(args):
    """Handle interactive menu mode."""
    try:
        # First, get the input file if not provided
        if not args.input_file:
            input_question = [
                {
                    "type": "filepath",
                    "message": "Select database or SQL file:",
                    "name": "input_file",
                    "validate": PathValidator(is_file=True, message="Input is not a file"),
                    "only_files": True,
                    "filter": lambda x: x.strip('"')
                }
            ]
            input_answer = prompt(input_question)
            if not input_answer:
                print("\nOperation cancelled.")
                sys.exit(0)
            args.input_file = input_answer["input_file"]

        # Main action menu
        main_questions = [
            {
                "type": "list",
                "message": "Select action:",
                "name": "action",
                "choices": [
                    Choice("diagram", "Generate database diagram"),
                    Choice("create_keys", "Generate SQL for missing foreign keys"),
                    Choice("create_sqlite_keys", "Generate SQLite FOREIGN KEY clauses"),
                    Choice("create_indexes", "Generate suggested indexes"),
                    Choice("create_triggers", "Generate suggested triggers"),
                    Choice("help", "Show detailed help"),
                    Choice("cancel", "Cancel and exit")
                ]
            }
        ]
        main_answer = prompt(main_questions)
        if not main_answer or main_answer["action"] == "cancel":
            print("\nOperation cancelled.")
            sys.exit(0)

        # Handle different actions
        if main_answer["action"] == "help":
            show_help()
            # After showing help, show the menu again
            interactive_menu(args)
        elif main_answer["action"] == "diagram":
            diagram_menu(args)
        elif main_answer["action"] == "create_keys":
            args.create_keys = True
        elif main_answer["action"] == "create_sqlite_keys":
            args.create_sqlite_keys = True
        elif main_answer["action"] == "create_indexes":
            args.create_indexes = True
        elif main_answer["action"] == "create_triggers":
            trigger_menu(args)
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"\nAn error occurred: {str(e)}")
        sys.exit(1)

def diagram_menu(args):
    """Interactive menu for diagram generation options."""
    try:
        # Basic options
        basic_questions = [
            {
                "type": "checkbox",
                "message": "Select diagram options:",
                "name": "options",
                "choices": [
                    Choice("assume", "Assume relationships based on column naming"),
                    Choice("color", "Use colors for tables and relationships"),
                    Choice("dark", "Use dark mode"),
                    Choice("full", "Show all columns"),
                    Choice("show_indexes", "Show indexed columns"),
                    Choice("sort_by_incoming", "Sort tables by incoming connections"),
                    Choice("compact", "Use compact layout")
                ]
            },
            {
                "type": "list",
                "message": "Select layout direction:",
                "name": "layout",
                "choices": [
                    Choice("LR", "Left to Right"),
                    Choice("RL", "Right to Left"),
                    Choice("TB", "Top to Bottom"),
                    Choice("BT", "Bottom to Top"),
                    Choice("cancel", "Cancel and exit")
                ]
            }
        ]
        basic_answers = prompt(basic_questions)
        if not basic_answers or basic_answers["layout"] == "cancel":
            print("\nOperation cancelled.")
            sys.exit(0)

        # Apply basic options
        for option in basic_answers["options"]:
            setattr(args, option, True)
        args.layout = basic_answers["layout"]

        # Engine selection
        engine_question = [
            {
                "type": "list",
                "message": "Select layout engine:",
                "name": "engine",
                "choices": [
                    Choice("dot", "Dot (hierarchical, best for most diagrams)"),
                    Choice("neato", "Neato (force-directed, good for small to medium graphs)"),
                    Choice("fdp", "FDP (force-directed, good for large graphs)"),
                    Choice("sfdp", "SFDP (force-directed, best for very large graphs)"),
                    Choice("twopi", "Twopi (radial, good for hierarchical data)"),
                    Choice("circo", "Circo (circular, good for cyclic structures)"),
                    Choice("cancel", "Cancel and exit")
                ]
            }
        ]
        engine_answer = prompt(engine_question)
        if not engine_answer or engine_answer["engine"] == "cancel":
            print("\nOperation cancelled.")
            sys.exit(0)
        args.engine = engine_answer["engine"]

        # Arrow style
        arrow_question = [
            {
                "type": "list",
                "message": "Select arrow style:",
                "name": "arrow_type",
                "choices": [
                    Choice("curved", "Curved (works with all engines)"),
                    Choice("polyline", "Straight lines (dot engine only)"),
                    Choice("ortho", "Right-angled (dot engine only)"),
                    Choice("cancel", "Cancel and exit")
                ]
            }
        ]
        arrow_answer = prompt(arrow_question)
        if not arrow_answer or arrow_answer["arrow_type"] == "cancel":
            print("\nOperation cancelled.")
            sys.exit(0)
        args.arrow_type = arrow_answer["arrow_type"]

        # Font selection
        font_question = [
            {
                "type": "list",
                "message": "Select font:",
                "name": "font",
                "choices": [
                    "Arial", "Helvetica", "Consolas", "Courier", "Times",
                    "Verdana", "Tahoma", "Trebuchet MS", "Georgia",
                    "Palatino", "Impact", "Comic Sans MS",
                    "cancel"
                ]
            }
        ]
        font_answer = prompt(font_question)
        if not font_answer or font_answer["font"] == "cancel":
            print("\nOperation cancelled.")
            sys.exit(0)
        args.font = font_answer["font"]

        # Advanced options
        advanced_questions = [
            {
                "type": "input",
                "message": "Node separation (default: 0.6, especially useful for force-directed engines):",
                "name": "nodesep",
                "default": "6",
                "validate": lambda x: x.isdigit() and int(x) > 0
            },
            {
                "type": "input",
                "message": "Rank separation (default: 0.7, especially useful for force-directed engines):",
                "name": "ranksep",
                "default": "7",
                "validate": lambda x: x.isdigit() and int(x) > 0
            },
            {
                "type": "input",
                "message": "Font size (default: 12):",
                "name": "font_size",
                "default": "12",
                "validate": lambda x: x.isdigit() and int(x) > 0
            },
            {
                "type": "input",
                "message": "DPI (default: 96):",
                "name": "dpi",
                "default": "96",
                "validate": lambda x: x.isdigit() and int(x) > 0
            },
            {
                "type": "list",
                "message": "Node overlap handling (especially useful for neato/fdp/sfdp):",
                "name": "overlap",
                "choices": [
                    Choice(None, "None (default)"),
                    Choice("false", "False (no overlap)"),
                    Choice("scale", "Scale (reduce overlap)"),
                    Choice("prism", "Prism (force-directed overlap removal)"),
                    Choice("compress", "Compress (reduce size)"),
                    Choice("vpsc", "VPSC (variable overlap removal)"),
                    Choice("ortho", "Ortho (orthogonal layout)"),
                    Choice("orthoxy", "OrthoXY (orthogonal layout with XY constraints)"),
                    Choice("ortho_yx", "OrthoYX (orthogonal layout with YX constraints)"),
                    Choice("pcompress", "PCompress (parallel compression)"),
                    Choice("ipsep", "IPSep (incremental separation)"),
                    Choice("sep", "Sep (separation)"),
                    Choice("sep+", "Sep+ (enhanced separation)"),
                    Choice("true", "True (allow overlap)"),
                    Choice("cancel", "Cancel and exit")
                ]
            }
        ]
        advanced_answers = prompt(advanced_questions)
        if not advanced_answers or advanced_answers["overlap"] == "cancel":
            print("\nOperation cancelled.")
            sys.exit(0)

        # Apply advanced options
        args.nodesep = int(advanced_answers["nodesep"])
        args.ranksep = int(advanced_answers["ranksep"])
        args.font_size = int(advanced_answers["font_size"])
        args.dpi = int(advanced_answers["dpi"])
        args.overlap = advanced_answers["overlap"]

        # Output file
        output_question = [
            {
                "type": "input",
                "message": "Output filename (without extension):",
                "name": "output",
                "default": "database_diagram"
            }
        ]
        output_answer = prompt(output_question)
        if not output_answer:
            print("\nOperation cancelled.")
            sys.exit(0)
        args.output = output_answer["output"]
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"\nAn error occurred: {str(e)}")
        sys.exit(1)

def trigger_menu(args):
    """Interactive menu for trigger generation options."""
    try:
        # First, parse the database/sql file to get table information
        mapper = DatabaseMapper(assume_relationships=True)
        if args.input_file.endswith(('.db', '.sqlite', '.sqlite3')):
            mapper.parse_sqlite_db(args.input_file)
        else:
            mapper.parse_sql_file(args.input_file)

        # Get available tables
        tables = list(mapper.tables.keys())
        
        # Trigger type selection
        trigger_questions = [
            {
                "type": "checkbox",
                "message": "Select trigger types to generate:",
                "name": "trigger_types",
                "choices": [
                    Choice("audit", "Audit triggers (track changes)"),
                    Choice("validation", "Validation triggers (email, phone)"),
                    Choice("auto_update", "Auto-update triggers (timestamps)"),
                    Choice("soft_delete", "Soft delete triggers"),
                    Choice("referential", "Referential integrity triggers"),
                    Choice("cancel", "Cancel and exit")
                ]
            },
            {
                "type": "checkbox",
                "message": "Select tables to generate triggers for:",
                "name": "selected_tables",
                "choices": [Choice("all", "All tables")] + [Choice(t, t) for t in tables] + [Choice("cancel", "Cancel and exit")]
            }
        ]
        trigger_answers = prompt(trigger_questions)
        if not trigger_answers or "cancel" in trigger_answers["trigger_types"] or "cancel" in trigger_answers["selected_tables"]:
            print("\nOperation cancelled.")
            sys.exit(0)

        # Process selections
        selected_types = [t for t in trigger_answers["trigger_types"] if t != "cancel"]
        selected_tables = [t for t in trigger_answers["selected_tables"] if t not in ["cancel", "all"]]
        
        if "all" in trigger_answers["selected_tables"]:
            selected_tables = tables

        # Generate and print triggers
        suggested_triggers = mapper._suggest_triggers()
        
        print("\nSuggested Triggers:")
        for table_name, triggers in suggested_triggers.items():
            if table_name not in selected_tables:
                continue
                
            print(f"\n  {table_name}:")
            # Group triggers by type
            by_type = {}
            for trigger_type, trigger_sql in triggers:
                if trigger_type in selected_types:
                    by_type.setdefault(trigger_type, []).append(trigger_sql)
            
            for trigger_type, trigger_list in by_type.items():
                print(f"\n    {trigger_type.upper()} Triggers:")
                for trigger in trigger_list:
                    print(f"      {trigger}")
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"\nAn error occurred: {str(e)}")
        sys.exit(1)

def main():
    import argparse
    
    # Check Graphviz installation first
    check_graphviz_installation()
    
    parser = argparse.ArgumentParser(description='Generate database schema diagrams from SQLite DB or SQL files')
    parser.add_argument('input_file', nargs='?', help='Path to SQLite database or SQL file')
    parser.add_argument('--interactive', '-i', action='store_true', help='Launch an interactive menu to select actions and options')
    parser.add_argument('--output', '-o', default='database_diagram', help='Output file name (without extension)')
    parser.add_argument('--assume', '-a', action='store_true', help='Assume relationships based on column naming patterns')
    parser.add_argument('--color', '-c', action='store_true', help='Assign a unique color to each table and its outgoing arrows')
    parser.add_argument('--dark', '-d', action='store_true', help='Use a dark background and light foreground')
    parser.add_argument('--full', '-f', action='store_true', help='Show all columns and increase spacing between tables')
    parser.add_argument('--font', type=str, default='Consolas', help='Font to use for diagram')
    parser.add_argument('--font-size', type=int, default=12, help='Font size for all diagram text')
    parser.add_argument('--dpi', type=int, default=96, help='Image resolution in DPI')
    parser.add_argument('--arrow-type', '-t', type=str, default='curved', 
        choices=['curved', 'polyline', 'ortho'],
        help='Arrow style: curved (all engines), polyline/ortho (dot engine only)')
    parser.add_argument('--layout', '-l', type=str, default='LR', choices=['LR', 'RL', 'TB', 'BT'], help='Diagram layout direction')
    parser.add_argument('--compact', action='store_true', help='Use compact layout')
    parser.add_argument('--engine', type=str, default='dot', 
        choices=['dot', 'neato', 'fdp', 'sfdp', 'twopi', 'circo'], 
        help='Graphviz layout engine: dot (hierarchical), neato/fdp/sfdp (force-directed), twopi (radial), circo (circular)')
    parser.add_argument('--nodesep', type=int, default=6, 
        help='Minimum space between nodes (especially useful for force-directed engines)')
    parser.add_argument('--ranksep', type=int, default=7, 
        help='Minimum space between rows/columns (especially useful for force-directed engines)')
    parser.add_argument('--overlap', type=str, default=None, 
        choices=['false', 'scale', 'prism', 'compress', 'vpsc', 'ortho', 'orthoxy', 'ortho_yx', 
                'pcompress', 'ipsep', 'sep', 'sep+', 'true'],
        help='Node overlap handling (especially useful for neato/fdp/sfdp):\n'
             'false: no overlap\n'
             'scale: reduce overlap\n'
             'prism: force-directed overlap removal\n'
             'compress: reduce size\n'
             'vpsc: variable overlap removal\n'
             'ortho/orthoxy/ortho_yx: orthogonal layouts\n'
             'pcompress: parallel compression\n'
             'ipsep: incremental separation\n'
             'sep/sep+: separation methods\n'
             'true: allow overlap')
    parser.add_argument('--sort-by-incoming', action='store_true', help='Sort tables by number of incoming connections')
    parser.add_argument('--create-keys', action='store_true', help='Print SQL statements to create assumed foreign keys and exit')
    parser.add_argument('--create-sqlite-keys', action='store_true', help='Print assumed FOREIGN KEY clauses for each table and exit')
    parser.add_argument('--create-indexes', action='store_true', help='Print suggested CREATE INDEX statements and exit')
    parser.add_argument('--create-triggers', action='store_true', help='Print suggested CREATE TRIGGER statements and exit')
    parser.add_argument('--show-indexes', action='store_true', help='Show an ⓘ symbol after columns that are indexed')

    args = parser.parse_args()

    # Handle interactive mode
    if args.interactive:
        interactive_menu(args)

    # Handle non-interactive mode
    if args.create_indexes:
        # Only do index creation logic, ignore all other flags
        mapper = DatabaseMapper(assume_relationships=True)
        if args.input_file.endswith(('.db', '.sqlite', '.sqlite3')):
            mapper.parse_sqlite_db(args.input_file)
        else:
            mapper.parse_sql_file(args.input_file)
        
        definite_indexes, possible_indexes = mapper._suggest_indexes()
        
        print("Definite indexes:")
        for table_name, indexes in definite_indexes.items():
            print(f"\n  {table_name}:")
            for idx in indexes:
                print(f"    {idx}")
        
        print("\nPossible indexes:")
        for table_name, indexes in possible_indexes.items():
            print(f"\n  {table_name}:")
            for idx in indexes:
                print(f"    {idx}")
        
        exit(0)
    
    if args.create_keys:
        # Only do key creation logic, ignore all other flags
        mapper = DatabaseMapper(assume_relationships=True)
        if args.input_file.endswith(('.db', '.sqlite', '.sqlite3')):
            mapper.parse_sqlite_db(args.input_file)
        else:
            mapper.parse_sql_file(args.input_file)
        # Find assumed relationships only
        assumed = mapper._find_potential_relationships()
        print('BEGIN;')
        for child, parent, label in assumed:
            # label is like 'child_col → parent_col'
            child_col, parent_col = label.split('→')
            child_col = child_col.strip()
            parent_col = parent_col.strip()
            print(f"ALTER TABLE {child}\nADD CONSTRAINT fk_{child}_{parent}\nFOREIGN KEY ({child_col}) REFERENCES {parent}({parent_col});\n")
        print('COMMIT;')
        exit(0)
    
    if args.create_sqlite_keys:
        # Only do key creation logic, ignore all other flags
        mapper = DatabaseMapper(assume_relationships=True)
        if args.input_file.endswith(('.db', '.sqlite', '.sqlite3', '.db3')):
            mapper.parse_sqlite_db(args.input_file)
        else:
            mapper.parse_sql_file(args.input_file)
        # Find assumed relationships only
        assumed = mapper._find_potential_relationships()
        # Group by child table
        from collections import defaultdict
        fk_map = defaultdict(list)
        for child, parent, label in assumed:
            child_col, parent_col = label.split('→')
            child_col = child_col.strip()
            parent_col = parent_col.strip()
            fk_map[child].append((child_col, parent, parent_col))
        for table, fks in fk_map.items():
            print(f"{table}:")
            for i, (child_col, parent, parent_col) in enumerate(fks):
                comma = ',' if i < len(fks) - 1 else ''
                print(f"    FOREIGN KEY ({child_col}) REFERENCES {parent}({parent_col}){comma}")
            print()
        exit(0)
    
    if args.create_triggers:
        # Only do trigger creation logic, ignore all other flags
        mapper = DatabaseMapper(assume_relationships=True)
        if args.input_file.endswith(('.db', '.sqlite', '.sqlite3')):
            mapper.parse_sqlite_db(args.input_file)
        else:
            mapper.parse_sql_file(args.input_file)
        
        suggested_triggers = mapper._suggest_triggers()
        
        print("Suggested Triggers:")
        for table_name, triggers in suggested_triggers.items():
            print(f"\n  {table_name}:")
            # Group triggers by type
            by_type = {}
            for trigger_type, trigger_sql in triggers:
                by_type.setdefault(trigger_type, []).append(trigger_sql)
            
            for trigger_type, trigger_list in by_type.items():
                print(f"\n    {trigger_type.upper()} Triggers:")
                for trigger in trigger_list:
                    print(f"      {trigger}")
        
        exit(0)
    
    # Default: generate diagram
    mapper = DatabaseMapper(assume_relationships=args.assume)
    mapper.color_tables = args.color
    mapper.dark_mode = args.dark
    mapper.full_mode = args.full
    mapper.diagram_font = args.font
    mapper.font_size = args.font_size
    mapper.dpi = args.dpi
    mapper.arrow_type = args.arrow_type
    mapper.layout = args.layout
    mapper.compact_mode = args.compact
    mapper.engine = args.engine
    mapper.nodesep = args.nodesep
    mapper.ranksep = args.ranksep
    mapper.overlap = args.overlap
    mapper.sort_by_incoming = args.sort_by_incoming
    mapper.show_indexes = args.show_indexes
    
    if args.input_file.endswith(('.db', '.sqlite', '.sqlite3')):
        mapper.parse_sqlite_db(args.input_file)
    else:
        mapper.parse_sql_file(args.input_file)
    
    mapper.generate_diagram(args.output)

if __name__ == '__main__':
    main() 