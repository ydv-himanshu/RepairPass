
import os
import sys

import pymysql

import config

HERE = os.path.dirname(os.path.abspath(__file__))


def statements(sql):
    """Split a SQL script into statements (drops '--' comment lines)."""
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def main():
    reset = "--reset" in sys.argv
    conn = pymysql.connect(host=config.DB_HOST, port=config.DB_PORT,
                           user=config.DB_USER, password=config.DB_PASSWORD,
                           autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
                (config.DB_NAME,))
    existing = cur.fetchone()[0]
    if existing and not reset:
        print(f"Database {config.DB_NAME} already has {existing} tables. "
              "Use --reset to drop it and start over.")
        return
    if reset:
        cur.execute(f"DROP DATABASE IF EXISTS `{config.DB_NAME}`")
    with open(os.path.join(HERE, "schema.sql"), encoding="utf-8") as f:
        for stmt in statements(f.read()):
            cur.execute(stmt)
    print(f"Database {config.DB_NAME} created with sample data.")
    conn.close()


if __name__ == "__main__":
    main()
