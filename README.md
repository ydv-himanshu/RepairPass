# RepairPass: digital passport for second-hand devices (Flask + MySQL)

Website built on your `schema.sql` (RepairPassDB, 12 tables + `vw_DevicePassport` view).
`schema.sql` is used exactly as you wrote it.

## Setup

1. Install Python 3.9+ and MySQL (with MySQL Workbench or the server running).
2. Open `config.py` and set your MySQL password (or set the `DB_PASSWORD` environment variable).
3. Install the libraries:
   ```
   pip install -r requirements.txt
   ```
4. Create the database from `schema.sql` (tables, sample data and the view):
   ```
   python setup_db.py
   ```
   Use `python setup_db.py --reset` to drop the database and rebuild it from scratch.
   (Or skip this step and run `schema.sql` yourself in MySQL Workbench.)
5. Start the website:
   ```
   python app.py
   ```
6. Open http://127.0.0.1:5000 and search for `F2LX3091DN`.

## Pages

| URL | What it does |
|---|---|
| `/` | Search by serial/IMEI; list of all devices |
| `/passport/<serial>` | Timeline, ownership chain, repairs (parts + derived total), warranties (derived Active/Expired), and the flat `vw_DevicePassport` report |
| `/device/new` | Register a device and its first owner |
| Passport page forms | Transfer ownership, add repair with up to 3 parts, add warranty |
| `/tables` | Browse all 12 tables; add rows to the lookup tables |

## How the design rules are enforced

- Warranty status is calculated with `CURDATE() BETWEEN start_date AND end_date`, never stored.
- Repair total = labour_cost + SUM(part_cost x quantity), never stored. `part_cost` is treated as the cost of one unit.
- Ownership transfer is one transaction: the current owner's row is locked (`SELECT ... FOR UPDATE`), its `end_date` is set to the sale date, and the new row starts on the same date, so there are no gaps.
- MySQL has no partial unique index, so "only one current owner" is enforced in the transfer code.
- Foreign keys, CHECK constraints and UNIQUE(serial_number) come from `schema.sql`; database errors are shown to the user as messages.
- All queries use `%s` placeholders (no SQL injection).

## Files

```
app.py            routes and SQL queries
config.py         MySQL host / user / password / database name
setup_db.py       builds the database from schema.sql
schema.sql        your SQL
requirements.txt  Flask, PyMySQL
templates/        base, index, passport, new_device, tables
```
