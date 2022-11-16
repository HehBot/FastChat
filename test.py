import sqlite3

conn=sqlite3.connect('test.db')
curs=conn.cursor()

curs.execute("CREATE TABLE test (a INT, b INT)")
curs.execute("INSERT INTO test(a, b) VALUES(1, 2)")
a=curs.execute("SELECT test.a FROM test").fetchall()
for rows in a:
    print(rows)