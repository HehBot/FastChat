from sys import argv
import socket
import selectors
import types
import sqlite3
import json

if len(argv) != 3:
    print(f"Usage: {argv[0]} <server ip> <server port>")
    exit(-1)

server_addr = (argv[1], int(argv[2]))

conn_accepting_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conn_accepting_sock.bind(server_addr)
conn_accepting_sock.listen()
print(f"Listening on {server_addr} as connection accepter of load-balancing server")
conn_accepting_sock.setblocking(False)

sel = selectors.DefaultSelector()
sel.register(fileobj=conn_accepting_sock, events=selectors.EVENT_READ, data=None)

# dbfile stores whether the database file exists or not
dbfile = True
try:
    f = open("fastchat_balancing_server.db", 'r')
    f.close()
except:
    dbfile = False

conn = sqlite3.connect("fastchat_balancing_server.db")
cursor = conn.cursor()

if not dbfile:
    cursor.execute("CREATE TABLE servers (server_addr TEXT NOT NULL, connections INT NOT NULL)")

def decide_server():
    return cursor.execute("SELECT server_addr, MIN(connections) FROM servers").fetchone()[0]

def accept_wrapper(sock):
    other_sock, other_addr = sock.accept()
    print(f"Accepted connection from {other_addr}")
    
    req = json.loads(other_sock.recv(1024).decode("utf-8"))
    if req["hdr"] == "server":
        data = types.SimpleNamespace(addr=other_addr)
        sel.register(fileobj=other_sock, events=selectors.EVENT_READ, data=data)

        other_servers = cursor.execute(f"SELECT server_addr FROM servers")
        other_servers = [x[0] + ';' for x in other_servers]
        other_servers = "".join(other_servers)[:-1]

        if other_servers != "":
            other_sock.sendall(other_servers.encode("utf-8"))
        else:
            other_sock.sendall(b"FIRST")

        cursor.execute(f"INSERT INTO servers (server_addr, connections) VALUES ('{req['msg']}', 0)")
        print(f"\tAdded {other_addr} as a server")

    elif req["hdr"] == "client":
        server_addr = decide_server()
        other_sock.sendall(server_addr.encode("utf-8"))
        cursor.execute(f"UPDATE servers SET connections=connections+1 WHERE server_addr='{server_addr[0] + ':' + str(server_addr[1])}'")
        other_sock.close()

def service_connection(key, event):
    server_sock = key.fileobj
    server_addr=key.data.addr

    recv_data = json.loads(server_sock.recv(1024).decode("utf-8"))
    if recv_data["hdr"] == "client_disconnected":
        cursor.execute(f"UPDATE servers SET connections=connections-1 WHERE server_addr='{server_addr[0] + ':' + str(server_addr[1])}'")

try:
    while True:
        events = sel.select(timeout=None)
        for key, event in events:
            if key.data is None:
                accept_wrapper(key.fileobj)
            else:
                service_connection(key, event)

except KeyboardInterrupt:
    print("Caught keyboard interrupt, exiting")
    sel.close()
    conn_accepting_sock.close()
    conn.commit()
    conn.close()
