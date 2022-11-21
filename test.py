import sqlite3
import ast

conn = sqlite3.connect("fastchat.db")
cursor = conn.cursor()

cursor.execute("DROP TABLE IF EXISTS customers")
cursor.execute("DROP TABLE IF EXISTS groups")

cursor.execute("CREATE TABLE customers (uname TEXT NOT NULL, output_buffer TEXT, PRIMARY KEY(uname))")
cursor.execute("CREATE TABLE groups (group_id INTEGER NOT NULL, uname TEXT, isAdmin INTEGER, PRIMARY KEY (group_id, uname), FOREIGN KEY(uname) REFERENCES customers(uname))")

a=[1,2,3]
cursor.execute("INSERT INTO customers(uname, output_buffer) VALUES('%s', '%s')" %("23", a))
d = cursor.execute("SELECT * FROM customers").fetchall()
for rows in d:
    print(rows)

b = ast.literal_eval(d[0][1])
b.append(4)
print(b)