import sqlite3
import sqlparse
import os
import re
import sys
import subprocess
from graphviz import Digraph
from typing import Union, Dict, List, Tuple
import hashlib

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
        
        conn.close()
        
        # Always add explicit relationships
        self.relationships = list(self.explicit_relationships)
        # If assume_relationships is True, add assumed relationships too
        if self.assume_relationships:
            assumed = self._find_potential_relationships()
            for rel in assumed:
                if rel not in self.relationships:
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
                if rel not in self.relationships:
                    self.relationships.append(rel)
    
    def generate_diagram(self, output_path: str = 'database_diagram') -> None:
        """Generate a compact, clustered, and relational-only diagram of the database structure."""
        dot = Digraph(comment='Database Schema')
        dot.attr(rankdir='LR', nodesep='0.6', ranksep='0.7')  # More readable spacing

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

        # Add clusters (subgraphs) only if more than one table in group
        clustered_tables = set()
        for prefix, table_names in clusters.items():
            if len(table_names) > 1:
                with dot.subgraph(name=f'cluster_{prefix}') as c:
                    if getattr(self, 'dark_mode', False):
                        c.attr(label=prefix.upper(), style='dashed', color='#cccccc', fontcolor='#cccccc', fontname=fontname)
                    else:
                        c.attr(label=prefix.upper(), style='dashed', fontname=fontname)
                    for table_name in table_names:
                        table_info = self.tables[table_name]
                        if getattr(self, 'full_mode', False):
                            show_cols = table_info['columns']
                            table_label = table_name
                        else:
                            show_cols = [col for col in table_info['columns'] if is_relational(col)]
                            table_label = table_name
                        label = f'''<
<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="6">
  <TR><TD WIDTH="120"><U><B>{table_label}</B></U></TD></TR>'''
                        for col in show_cols:
                            label += f'  <TR><TD ALIGN="LEFT">{col["name"]} ({col["type"]})'
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
        for table_name in self.tables:
            if table_name not in clustered_tables:
                table_info = self.tables[table_name]
                if getattr(self, 'full_mode', False):
                    show_cols = table_info['columns']
                    table_label = table_name
                else:
                    show_cols = [col for col in table_info['columns'] if is_relational(col)]
                    table_label = table_name
                label = f'''<
<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="6">
  <TR><TD WIDTH="120"><U><B>{table_label}</B></U></TD></TR>'''
                for col in show_cols:
                    label += f'  <TR><TD ALIGN="LEFT">{col["name"]} ({col["type"]})'
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
            if self.assume_relationships and (table1, table2, rel_type) not in self.explicit_relationships:
                dot.edge(table1, table2, label=rel_type, style='dashed', color=edge_color, fontcolor=edge_color)
            else:
                dot.edge(table1, table2, label=rel_type, color=edge_color, fontcolor=edge_color)

        # Save diagram
        dot.render(output_path, format='png', cleanup=True)

def get_table_color(table_name, dark_mode=False):
    palette = BRIGHT_COLORS_DARK if dark_mode else BRIGHT_COLORS_LIGHT
    idx = int(hashlib.md5(table_name.encode()).hexdigest(), 16) % len(palette)
    return palette[idx]

def main():
    import argparse
    
    # Check Graphviz installation first
    check_graphviz_installation()
    
    parser = argparse.ArgumentParser(description='Generate database schema diagrams from SQLite DB or SQL files')
    parser.add_argument('input_file', help='Path to SQLite database or SQL file')
    parser.add_argument('--output', '-o', default='database_diagram', help='Output file name (without extension)')
    parser.add_argument('--assume', '-a', action='store_true', help='Assume relationships based on column naming patterns')
    parser.add_argument('--color', '-c', action='store_true', help='Assign a unique color to each table and its outgoing arrows')
    parser.add_argument('--dark', '-d', action='store_true', help='Use a dark background and light foreground')
    parser.add_argument('--full', '-f', action='store_true', help='Show all columns and increase spacing between tables')
    parser.add_argument('--font', type=str, default='Consolas', help='Font to use for diagram (e.g., Arial, Helvetica, Consolas, Courier, Times, Verdana, Tahoma, Trebuchet MS, Georgia, Palatino, Impact, Comic Sans MS)')

    args = parser.parse_args()
    
    mapper = DatabaseMapper(assume_relationships=args.assume)
    mapper.color_tables = args.color
    mapper.dark_mode = args.dark
    mapper.full_mode = args.full
    mapper.diagram_font = args.font
    
    if args.input_file.endswith('.db') or args.input_file.endswith('.sqlite') or args.input_file.endswith('.sqlite3'):
        mapper.parse_sqlite_db(args.input_file)
    else:
        mapper.parse_sql_file(args.input_file)
    
    mapper.generate_diagram(args.output)

if __name__ == '__main__':
    main() 