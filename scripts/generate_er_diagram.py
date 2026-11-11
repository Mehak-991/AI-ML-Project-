"""Print a Mermaid ER diagram of the database, generated from the SQLAlchemy models.

Usage:  python scripts/generate_er_diagram.py > docs/college-submission/diagrams/er-diagram.mmd
        python scripts/generate_er_diagram.py summary     # table name, column count, primary key
"""
import os
import sys

os.environ.setdefault("APP_ENV", "testing")
sys.path.insert(0, os.getcwd())  # run from the project root

from app.database.models import Base

out = ["erDiagram"]
summary = []
for table in sorted(Base.metadata.sorted_tables, key=lambda t: t.name):
    out.append(f"    {table.name} {{")
    for col in table.columns:
        kind = type(col.type).__name__.replace("TypeEngine", "")
        flags = []
        if col.primary_key:
            flags.append("PK")
        if col.foreign_keys:
            flags.append("FK")
        if col.unique:
            flags.append("UK")
        out.append(f"        {kind} {col.name} {','.join(flags)}".rstrip())
    out.append("    }")
    summary.append((table.name, len(table.columns), [c.name for c in table.columns if c.primary_key]))
edges = sorted(
    (fk.column.table.name, table.name, fk.parent.name)
    for table in Base.metadata.sorted_tables
    for fk in table.foreign_keys
)
for parent, child, column in edges:
    out.append(f'    {parent} ||--o{{ {child} : "{column}"')

mode = sys.argv[1] if len(sys.argv) > 1 else "mermaid"
if mode == "mermaid":
    print("\n".join(out))
else:
    for name, n, pk in summary:
        print(f"{name}\t{n}\t{','.join(pk)}")
