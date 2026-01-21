# Schema to diagram
Convert PostgreSQL `pg_dump` resulted schema to app.diagrams.net XML file

![](https://shields.io/badge/dependencies-Python_3.13-blue)

A specialized Python script that parses PostgreSQL database schemas (.sql dumps) and converts them into a Draw.io (diagrams.net) compatible XML format.

Unlike generic parsers, this script uses a custom regex-based engine designed to handle the quirks of pg_dump (separated ALTER TABLE constraints, schema prefixes) and generates a clean, 3-column entity-relationship diagram.

## Usage

### 1. Prepare your SQL file
Export your database schema using `pg_dump` or use an existing `.sql` schema file.
```bash
pg_dump "$connection_string" --schema-only --no-owner --no-privileges --no-tablespaces > schema.sql
```

### 2. Run the Converter
Save the python script as `main.py` and run it via terminal:

```bash
python main.py --input_path schema.sql --output_path diagram.drawio
```

Arguments:
*   `--input_path`: Path to your source SQL file.
*   `--output_path`: Desired path for the generated Draw.io XML file.

### 3. Import into Draw.io
1.  Open https://app.diagrams.net/ or the desktop Draw.io application.
2.  Go to File > Open From > Device...
3.  Select the generated `diagram.drawio`.

## Visual Style Guide

The generated diagram uses the following conventions:

| Column  | Content                   | Style                                   |
| :---------- | :---------------------------- | :------------------------------------------ |
| 1. Keys | `PK`, `FK`, `UQ`          | Bold, Centered                          |
| 2. Name | `column_name`             | Standard text. Appends `*` if Not Null. |
| 3. Type | `integer`, `varchar(255)` | *Italic*, Navy Blue Color (`#000080`)   |

## Limitations

*   PostgreSQL Focused: The regex patterns are optimized for PostgreSQL syntax (specifically `pg_dump` output). It may not parse MySQL or MSSQL dumps correctly without modification.
*   DDL Only: Ensure your SQL file contains DDL (Data Definition Language) statements (`CREATE`, `ALTER`). Data insertion (`INSERT INTO`) is ignored.

## Troubleshooting

"Warning: No tables found"
*   Ensure your SQL file is plain text and uses standard `CREATE TABLE` syntax.
*   Ensure you are exporting schema only.

Messy Connector Lines
*   After importing into Draw.io, you can reset the edge routing by selecting all (Ctrl+A) and applying Layout > Orthogonal.