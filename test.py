import sqlite3

conn=sqlite3.connect('test.db')
curs=conn.cursor()

curs.execute("DROP TABLE IF EXISTS test")
curs.execute("CREATE TABLE test (a INT PRIMARY KEY, b TEXT)")
curs.execute("INSERT INTO test(a, b) VALUES(3, %s)" %("\"anish\""))
a=curs.execute("SELECT test.a, test.b FROM test").fetchall()
for rows in a:
    print(rows)
conn.commit()
conn.close()