import argparse
import uuid
import sys
import re
import xml.etree.ElementTree as ET

# --- Constants: Dimensions ---
WIDTH_KEY = 40
WIDTH_NAME = 150
WIDTH_TYPE = 110
TABLE_WIDTH = WIDTH_KEY + WIDTH_NAME + WIDTH_TYPE  # Total: 300
ROW_HEIGHT = 30
GRID_PADDING_X = 340
MAX_COLS_PER_ROW = 3

# --- Constants: Styles ---
STYLE_TABLE = (
    "shape=table;startSize=30;container=1;collapsible=1;childLayout=tableLayout;"
    "fixedRows=1;rowLines=0;fontStyle=1;align=center;resizeLast=1;html=1;whiteSpace=wrap;"
)
STYLE_ROW_NORMAL = (
    "shape=tableRow;horizontal=0;startSize=0;swimlaneHead=0;swimlaneBody=0;"
    "fillColor=none;collapsible=0;dropTarget=0;points=[[0,0.5],[1,0.5]];"
    "portConstraint=eastwest;top=0;left=0;right=0;bottom=0;html=1;"
)
STYLE_ROW_SEPARATOR = (
    "shape=tableRow;horizontal=0;startSize=0;swimlaneHead=0;swimlaneBody=0;"
    "fillColor=none;collapsible=0;dropTarget=0;points=[[0,0.5],[1,0.5]];"
    "portConstraint=eastwest;top=0;left=0;right=0;bottom=1;html=1;"
)
STYLE_CELL_KEY = (
    "shape=partialRectangle;connectable=0;fillColor=none;top=0;left=0;"
    "bottom=0;right=0;fontStyle=1;overflow=hidden;html=1;whiteSpace=wrap;align=center;"
)
STYLE_CELL_NAME = (
    "shape=partialRectangle;connectable=0;fillColor=none;top=0;left=0;"
    "bottom=0;right=0;align=left;spacingLeft=6;overflow=hidden;html=1;whiteSpace=wrap;"
)
STYLE_CELL_TYPE = (
    "shape=partialRectangle;connectable=0;fillColor=none;top=0;left=0;"
    "bottom=0;right=0;align=left;spacingLeft=6;overflow=hidden;html=1;whiteSpace=wrap;"
    "fontColor=#000080;fontStyle=2;"
)
STYLE_EDGE_BASE = (
    "endArrow=none;html=1;rounded=0;edgeStyle=entityRelationEdgeStyle;"
)
STYLE_LABEL_BASE = (
    "resizable=0;html=1;whiteSpace=wrap;verticalAlign=bottom;"
)


# --- Custom Parser Logic ---

class PostgresSchema:
    def __init__(self):
        self.tables = {}

    def add_table(self, name):
        name = self._clean_name(name)
        if name not in self.tables:
            self.tables[name] = {"columns": [], "pk": set(), "fk": {}, "uq": set()}
        return name

    def add_column(self, table, col_name, col_type, is_not_null):
        table = self._clean_name(table)
        col_name = self._clean_name(col_name)
        if table in self.tables:
            col_type = re.sub(r'\s+', ' ', col_type).strip()
            self.tables[table]["columns"].append({
                "name": col_name,
                "type": col_type,
                "not_null": is_not_null
            })

    def get_column_info(self, table, col_name):
        table = self._clean_name(table)
        col_name = self._clean_name(col_name)
        if table in self.tables:
            for col in self.tables[table]["columns"]:
                if col["name"] == col_name:
                    return col
        return None

    def add_pk(self, table, cols):
        table = self._clean_name(table)
        if table in self.tables:
            for c in cols:
                self.tables[table]["pk"].add(self._clean_name(c))

    def add_fk(self, table, col, ref_table):
        table = self._clean_name(table)
        col = self._clean_name(col)
        ref_table = self._clean_name(ref_table)
        if table in self.tables:
            self.tables[table]["fk"][col] = ref_table

    def add_uq(self, table, cols):
        table = self._clean_name(table)
        if table in self.tables:
            for c in cols:
                self.tables[table]["uq"].add(self._clean_name(c))

    def _clean_name(self, name):
        name = name.strip()
        name = name.replace('"', '')
        if '.' in name:
            name = name.split('.')[-1]
        return name


def parse_sql(content):
    schema = PostgresSchema()
    content = re.sub(r'--.*', '', content)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    statements = content.split(';')

    re_create_table = re.compile(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\(]+)\s*\(([\s\S]*)\)',
        re.IGNORECASE)
    re_alter_pk = re.compile(
        r'ALTER\s+TABLE\s+(?:ONLY\s+)?([^\s]+)\s+ADD\s+CONSTRAINT\s+.*?\s+PRIMARY\s+KEY\s*\(([^\)]+)\)',
        re.IGNORECASE)
    re_alter_fk = re.compile(
        r'ALTER\s+TABLE\s+(?:ONLY\s+)?([^\s]+)\s+ADD\s+CONSTRAINT\s+.*?\s+FOREIGN\s+KEY\s*\(([^\)]+)\)\s+REFERENCES\s+([^\s\(]+)',
        re.IGNORECASE)
    re_create_idx = re.compile(
        r'CREATE\s+UNIQUE\s+INDEX\s+.*?\s+ON\s+([^\s]+)\s+(?:USING\s+\w+\s+)?\(([^\)]+)\)',
        re.IGNORECASE)

    for stmt in statements:
        stmt = stmt.strip()
        if not stmt: continue

        match_table = re_create_table.search(stmt)
        if match_table:
            table_raw_name = match_table.group(1).strip()
            body = match_table.group(2)
            t_name = schema.add_table(table_raw_name)
            lines = body.split('\n')
            for line in lines:
                line = line.strip()
                if not line or line.upper().startswith(
                        "CONSTRAINT") or line.upper().startswith("PRIMARY KEY"):
                    continue
                is_not_null = "NOT NULL" in line.upper()
                parts = line.split(maxsplit=1)
                if len(parts) < 2: continue
                col_name = parts[0]
                rest = parts[1]
                type_match = re.match(r'([a-zA-Z0-9_\[\]\(\)\s]+)', rest)
                col_type = "unknown"
                if type_match:
                    col_type = type_match.group(1).strip()
                    keywords = ["NOT NULL", "NULL", "DEFAULT", "PRIMARY", "REFERENCES",
                                "CHECK", "UNIQUE"]
                    for k in keywords:
                        pattern = re.compile(r'\s+' + k + r'.*$', re.IGNORECASE)
                        col_type = pattern.sub('', col_type)
                    col_type = col_type.rstrip(',')
                schema.add_column(t_name, col_name, col_type, is_not_null)
                if "PRIMARY KEY" in rest.upper():
                    schema.add_pk(t_name, [col_name])

    for stmt in statements:
        stmt = stmt.strip()
        clean_stmt = " ".join(stmt.split())

        m_pk = re_alter_pk.search(clean_stmt)
        if m_pk:
            schema.add_pk(m_pk.group(1), [c.strip() for c in m_pk.group(2).split(',')])
            continue

        m_fk = re_alter_fk.search(clean_stmt)
        if m_fk:
            col = m_fk.group(2).split(',')[0].strip()
            schema.add_fk(m_fk.group(1), col, m_fk.group(3))
            continue

        m_idx = re_create_idx.search(clean_stmt)
        if m_idx:
            cols = [c.strip().split()[0] for c in m_idx.group(2).split(',')]
            schema.add_uq(m_idx.group(1), cols)
            continue

    return schema


# --- Draw.io Generation ---

def generate_id():
    return f"id_{uuid.uuid4().hex[:10]}"


def get_cardinality(schema, source_table, source_col, target_table):
    """
    Infers explicit cardinality with '0' notation.
    """
    source_pks = schema.tables[source_table]["pk"]
    source_uqs = schema.tables[source_table]["uq"]

    # 1. Source (Child) Side:
    # Can a Parent exist without a Child? Yes (0).
    # Is the FK unique? If yes, max 1 child. If no, max N children.
    is_unique_fk = (source_col in source_pks) or (source_col in source_uqs)

    # UPDATED: Explicitly using 0..N or 0..1
    if is_unique_fk:
        label_source = "0..1"  # One-to-One (but Parent doesn't need Child)
    else:
        label_source = "0..N"  # One-to-Many (Parent doesn't need Child)

    # 2. Target (Parent) Side:
    # Check Nullability of the FK column
    col_info = schema.get_column_info(source_table, source_col)
    is_not_null = col_info["not_null"] if col_info else False

    # If NOT NULL: Child MUST have 1 Parent.
    # If NULL: Child can have 0 or 1 Parent.
    label_target = "1" if is_not_null else "0..1"

    return label_source, label_target


def main():
    parser_arg = argparse.ArgumentParser(description="Convert SQL Schema to Draw.io XML")
    parser_arg.add_argument("--input_path", required=True)
    parser_arg.add_argument("--output_path", required=True)
    args = parser_arg.parse_args()

    try:
        with open(args.input_path, 'r', encoding='utf-8') as f:
            raw_content = f.read()
        schema = parse_sql(raw_content)
        if not schema.tables:
            print("Warning: No tables found.")
            sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    mxfile = ET.Element("mxfile", host="Electron", version="21.0.0")
    diagram = ET.SubElement(mxfile, "diagram", name="Database Schema", id=generate_id())
    model = ET.SubElement(diagram, "mxGraphModel", dx="1000", dy="1000", grid="1",
                          gridSize="10", guides="1", tooltips="1", connect="1",
                          arrows="1", fold="1", page="1", pageScale="1", pageWidth="827",
                          pageHeight="1169", math="0", shadow="0")
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")

    table_col_id_map = {}
    table_id_map = {}
    table_positions = {}

    current_x = 40
    current_y = 40
    col_counter = 0
    max_height_in_row = 0

    print(f"Found {len(schema.tables)} tables. Generating XML...")

    for table_name, table_data in schema.tables.items():
        columns = table_data["columns"]
        pks = table_data["pk"]
        fks = table_data["fk"]
        uqs = table_data["uq"]

        pk_cols = []
        other_cols = []
        for col in columns:
            if col['name'] in pks:
                pk_cols.append(col)
            else:
                other_cols.append(col)
        sorted_columns = pk_cols + other_cols
        last_pk_index = len(pk_cols) - 1 if pk_cols else -1

        table_height = (len(sorted_columns) * ROW_HEIGHT) + ROW_HEIGHT
        if table_height > max_height_in_row:
            max_height_in_row = table_height

        table_id = generate_id()
        table_id_map[table_name] = table_id
        table_col_id_map[table_name] = {}
        table_positions[table_name] = {'x': current_x, 'y': current_y}

        mx_cell_table = ET.SubElement(root, "mxCell")
        mx_cell_table.set("id", table_id)
        mx_cell_table.set("value", table_name)
        mx_cell_table.set("style", STYLE_TABLE)
        mx_cell_table.set("vertex", "1")
        mx_cell_table.set("parent", "1")

        geo_table = ET.SubElement(mx_cell_table, "mxGeometry")
        geo_table.set("x", str(current_x))
        geo_table.set("y", str(current_y))
        geo_table.set("width", str(TABLE_WIDTH))
        geo_table.set("height", str(table_height))
        geo_table.set("as", "geometry")

        y_offset = ROW_HEIGHT

        for idx, col in enumerate(sorted_columns):
            col_name = col['name']
            col_type = col['type']
            display_name = col_name + ("*" if col['not_null'] else "")

            is_pk = (col_name in pks)
            is_fk = (col_name in fks)
            is_uq = (col_name in uqs) and (not is_pk)

            key_label = []
            if is_pk: key_label.append("PK")
            if is_fk: key_label.append("FK")
            if is_uq: key_label.append("UQ")
            key_text = ",".join(key_label)

            style = STYLE_ROW_SEPARATOR if (
                        is_pk and idx == last_pk_index) else STYLE_ROW_NORMAL

            row_id = generate_id()
            table_col_id_map[table_name][col_name] = row_id

            mx_cell_row = ET.SubElement(root, "mxCell")
            mx_cell_row.set("id", row_id)
            mx_cell_row.set("value", "")
            mx_cell_row.set("style", style)
            mx_cell_row.set("vertex", "1")
            mx_cell_row.set("parent", table_id)

            geo_row = ET.SubElement(mx_cell_row, "mxGeometry")
            geo_row.set("x", "0")
            geo_row.set("y", str(y_offset))
            geo_row.set("width", str(TABLE_WIDTH))
            geo_row.set("height", str(ROW_HEIGHT))
            geo_row.set("as", "geometry")

            cell_key = ET.SubElement(root, "mxCell")
            cell_key.set("id", generate_id())
            cell_key.set("value", key_text)
            cell_key.set("style", STYLE_CELL_KEY)
            cell_key.set("vertex", "1")
            cell_key.set("parent", row_id)
            geo_key = ET.SubElement(cell_key, "mxGeometry")
            geo_key.set("width", str(WIDTH_KEY))
            geo_key.set("height", str(ROW_HEIGHT))
            geo_key.set("as", "geometry")

            cell_name = ET.SubElement(root, "mxCell")
            cell_name.set("id", generate_id())
            cell_name.set("value", display_name)
            cell_name.set("style", STYLE_CELL_NAME)
            cell_name.set("vertex", "1")
            cell_name.set("parent", row_id)
            geo_name = ET.SubElement(cell_name, "mxGeometry")
            geo_name.set("x", str(WIDTH_KEY))
            geo_name.set("width", str(WIDTH_NAME))
            geo_name.set("height", str(ROW_HEIGHT))
            geo_name.set("as", "geometry")

            cell_type = ET.SubElement(root, "mxCell")
            cell_type.set("id", generate_id())
            cell_type.set("value", col_type)
            cell_type.set("style", STYLE_CELL_TYPE)
            cell_type.set("vertex", "1")
            cell_type.set("parent", row_id)
            geo_type = ET.SubElement(cell_type, "mxGeometry")
            geo_type.set("x", str(WIDTH_KEY + WIDTH_NAME))
            geo_type.set("width", str(WIDTH_TYPE))
            geo_type.set("height", str(ROW_HEIGHT))
            geo_type.set("as", "geometry")

            y_offset += ROW_HEIGHT

        col_counter += 1
        current_x += GRID_PADDING_X
        if col_counter >= MAX_COLS_PER_ROW:
            col_counter = 0
            current_x = 40
            current_y += (max_height_in_row + 50)
            max_height_in_row = 0

    # --- Draw Relationships ---
    for table_name, table_data in schema.tables.items():
        for col_name, target_table_name in table_data["fk"].items():

            source_row_id = table_col_id_map.get(table_name, {}).get(col_name)

            target_pk_cols = list(schema.tables[target_table_name]["pk"])
            target_row_id = None
            if target_pk_cols:
                target_col_name = target_pk_cols[0]
                target_row_id = table_col_id_map.get(target_table_name, {}).get(
                    target_col_name)
            if not target_row_id:
                target_row_id = table_id_map.get(target_table_name)

            if source_row_id and target_row_id:
                label_source, label_target = get_cardinality(schema, table_name, col_name,
                                                             target_table_name)

                src_pos = table_positions.get(table_name, {'x': 0, 'y': 0})
                tgt_pos = table_positions.get(target_table_name, {'x': 0, 'y': 0})

                # --- Smart Routing Logic ---
                edge_anchor_style = "exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;"
                src_align = "align=left;"
                tgt_align = "align=right;"

                if tgt_pos['x'] < src_pos['x']:
                    edge_anchor_style = "exitX=0;exitY=0.5;exitDx=0;exitDy=0;entryX=1;entryY=0.5;entryDx=0;entryDy=0;"
                    src_align = "align=right;"
                    tgt_align = "align=left;"

                final_edge_style = STYLE_EDGE_BASE + edge_anchor_style

                edge_id = generate_id()
                edge = ET.SubElement(root, "mxCell")
                edge.set("id", edge_id)
                edge.set("style", final_edge_style)
                edge.set("edge", "1")
                edge.set("parent", "1")
                edge.set("source", source_row_id)
                edge.set("target", target_row_id)
                geo_edge = ET.SubElement(edge, "mxGeometry")
                geo_edge.set("relative", "1")
                geo_edge.set("as", "geometry")

                # Source Label (0..N or 0..1)
                lbl_src = ET.SubElement(root, "mxCell")
                lbl_src.set("id", generate_id())
                lbl_src.set("value", label_source)
                lbl_src.set("style", STYLE_LABEL_BASE + src_align)
                lbl_src.set("vertex", "1")
                lbl_src.set("connectable", "0")
                lbl_src.set("parent", edge_id)
                geo_lbl_src = ET.SubElement(lbl_src, "mxGeometry")
                geo_lbl_src.set("x", "-1")
                geo_lbl_src.set("relative", "1")
                geo_lbl_src.set("as", "geometry")

                # Target Label (0..1 or 1)
                lbl_tgt = ET.SubElement(root, "mxCell")
                lbl_tgt.set("id", generate_id())
                lbl_tgt.set("value", label_target)
                lbl_tgt.set("style", STYLE_LABEL_BASE + tgt_align)
                lbl_tgt.set("vertex", "1")
                lbl_tgt.set("connectable", "0")
                lbl_tgt.set("parent", edge_id)
                geo_lbl_tgt = ET.SubElement(lbl_tgt, "mxGeometry")
                geo_lbl_tgt.set("x", "1")
                geo_lbl_tgt.set("relative", "1")
                geo_lbl_tgt.set("as", "geometry")

    tree = ET.ElementTree(mxfile)
    tree.write(args.output_path, encoding='UTF-8', xml_declaration=True)
    print(f"Successfully generated {args.output_path}")


if __name__ == "__main__":
    main()
