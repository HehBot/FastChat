from sys import argv
import socket
import selectors
import types
import sqlite3
import psycopg2
import json
'''Python script to start the load balancing server
This server accepts connections from other servers and adds them to the list of servers
It also accepts connections from clients and directs them towards servers

'''
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
# dbfile stores whether the local database file exists or not
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

# Assuming database fastchat has already been created
dbname = "fastchat"
user = "postgres"
password = "Hello@123"

shared_conn = psycopg2.connect(dbname=dbname, user=user, password=password)
shared_cursor = shared_conn.cursor()

shared_cursor.execute("CREATE TABLE IF NOT EXISTS customers (uname TEXT NOT NULL, pub_key TEXT NOT NULL, PRIMARY KEY(uname))")
shared_cursor.execute("CREATE TABLE IF NOT EXISTS groups (group_id INTEGER NOT NULL, uname TEXT, isAdmin INTEGER, PRIMARY KEY (group_id, uname))")
shared_cursor.execute("INSERT INTO groups (group_id, uname, isAdmin) VALUES (0, ':', 1) ON CONFLICT DO NOTHING")
shared_conn.commit()
shared_cursor.close()
shared_conn.close()

def decide_server():
    '''This decides which server does the incoming client connect to
    We return the server with least number of currently logged in clients

    :return: Address of server to be connected to
    :rtype: String 
    '''
    cursor.execute("SELECT server_addr, MIN(connections) FROM servers")
    return cursor.fetchone()[0]

def accept_wrapper(sock):
    ''' Accepts connections from server or client

    :param sock:The socket on which information has been received
    :type sock: Socket
    '''
    other_sock, other_addr = sock.accept()
    print(f"Accepted connection from {other_addr}")
    
    req = json.loads(other_sock.recv(1024).decode("utf-8"))
    if req["hdr"] == "server":
        data = types.SimpleNamespace(addr=req["msg"])
        sel.register(fileobj=other_sock, events=selectors.EVENT_READ, data=data)

        cursor.execute(f"SELECT server_addr FROM servers")
        other_servers = cursor.fetchall()

        if len(other_servers) == 0:
            other_servers = "FIRST"
        else:
            other_servers = "".join([x[0] + ';' for x in other_servers])[:-1]

        other_servers = other_servers + '-' + dbname + '-' + user + '-' + password
        other_sock.sendall(other_servers.encode("utf-8"))
        
        cursor.execute("INSERT INTO servers (server_addr, connections) VALUES ('" + req['msg'] + "', 0)")
        print(f"\tAdded {other_addr} as a server")

    elif req["hdr"] == "client":
        server_addr = decide_server()
        other_sock.sendall(server_addr.encode("utf-8"))
        cursor.execute(f"UPDATE servers SET connections=connections+1 WHERE server_addr='{server_addr}'")
        other_sock.close()

def service_connection(key):
    '''Communicating with server after it has joined
    
    :param key: The key in which changes have been made
    :type key: Selector key
    '''
    server_sock = key.fileobj
    server_addr = key.data.addr

    recv_data = server_sock.recv(1024).decode("utf-8")
    
    if recv_data == "":
        print(f"Closing connection to {server_addr}")
        sel.unregister(server_sock), event
        server_sock.close()
        return

    req = json.loads(recv_data)
    if req["hdr"] == "client_disconnected":
        cursor.execute(f"UPDATE servers SET connections=connections-1 WHERE server_addr='{server_addr}'")

try:
    while True:
        events = sel.select(timeout=None)
        for key, event in events:
            if key.data is None:
                accept_wrapper(key.fileobj)
            else:
                service_connection(key)

except KeyboardInterrupt:
    print("Caught keyboard interrupt, exiting")
    sel.close()
    conn_accepting_sock.close()
    conn.commit()
    conn.close()
