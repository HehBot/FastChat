from sys import argv
import sys
import socket
import selectors
import types
import json
import sqlite3
import psycopg2
from server_to_server import Server_to_Server
from server_to_client import Server_to_Client
from balancing_server_to_server import Balancing_Server_to_Server

import rsa
sys.path.append('../')
from request import verify_registering_req, verify_onboarding_req, pub_key_to_str, str_to_pub_key

if len(argv) != 5:
    print(f"Usage: {argv[0]} <server ip> <server port> <balancing server ip> <balancing server port>")
    exit(-1)

server_addr = (argv[1], int(argv[2]))
balancing_server_addr = (argv[3], int(argv[4]))
this_server_name = argv[1] + ':' + argv[2]

# dbfile stores whether the database file exists or not
dbfile = True
try:
    f = open("localfastchat.db", 'r')
    f.close()
except:
    dbfile = False

local_conn = sqlite3.connect("localfastchat.db", isolation_level=None)
local_cursor = local_conn.cursor()

if not dbfile:
    local_cursor.execute("CREATE TABLE local_buffer (uname TEXT NOT NULL, output_buffer TEXT, PRIMARY KEY(uname))")
    local_cursor.execute("CREATE TABLE server_map (uname TEXT NOT NULL, serv_name TEXT, PRIMARY KEY(uname))")

sel = selectors.DefaultSelector()

balancing_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
balancing_server_sock.connect(balancing_server_addr)

data_class = Balancing_Server_to_Server(":balance_serv:", balancing_server_sock, local_cursor, this_server_name, [])
sel.register(fileobj=balancing_server_sock, events=selectors.EVENT_WRITE, data=data_class)

init_req = json.dumps({ "hdr":"server", "msg":this_server_name })
balancing_server_sock.sendall(init_req.encode("utf-8"))

print(f"Connected to balancing server at {balancing_server_addr}")

other_servers_string, psql_dbname, psql_uname, psql_pwd = balancing_server_sock.recv(1024).decode("utf-8").split('-')
other_servers = other_servers_string.split(';')

if other_servers[0] != "FIRST":
    for i in other_servers:
        other_server_addr = i.split(':')
        other_server_addr = (other_server_addr[0], int(other_server_addr[1]))

        other_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        other_server_sock.connect(other_server_addr)

        connection_req = json.dumps({ "hdr":"server", "msg":this_server_name })
        other_server_sock.sendall(connection_req.encode("utf-8"))
        print(f"Sent connection request to server {i}")

        data = Server_to_Server(other_server_addr, i , other_server_sock, local_cursor, this_server_name, other_servers)
        sel.register(fileobj=other_server_sock, events=selectors.EVENT_READ | selectors.EVENT_WRITE, data=data)

        local_cursor.execute(f"INSERT INTO local_buffer (uname, output_buffer) VALUES ('{i}', '')")

else:
    other_servers = []

conn_accepting_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conn_accepting_sock.bind(server_addr)
conn_accepting_sock.listen()
print(f"Listening on {server_addr} as connection accepter of server")
conn_accepting_sock.setblocking(False)

sel.register(fileobj=conn_accepting_sock, events=selectors.EVENT_READ, data=None)  # as we only want to read from conn_accepting_sock
conn = psycopg2.connect(dbname=psql_dbname, user=psql_uname, password=psql_pwd)
cursor = conn.cursor()

def append_output_buffer(uname, newdata):
    print()
    print(f'ADDING TO OUTPUT BUFFER {newdata} of {uname}')
    print()
    local_cursor.execute("UPDATE local_buffer SET output_buffer=output_buffer||'%s' WHERE uname='%s'" % (newdata, uname))

def accept_wrapper(sock):
    client_sock, client_addr = sock.accept()

    print(f"Accepted connection at {client_addr}")

    req_str = client_sock.recv(1024).decode()

    print("\nLOADING :")
    print(req_str)

    if req_str == "":
        client_sock.close()
        return

    req = json.loads(req_str)

    if req["hdr"] == "server":
        data = Server_to_Server( client_addr, req["msg"], client_sock, local_cursor, this_server_name, other_servers )
        other_servers.append(req["msg"])
        print(f"Accepted connection from server {req['msg']}")
        local_cursor.execute(f"INSERT INTO local_buffer (uname, output_buffer) VALUES ('{req['msg']}', '')")
        sel.register(fileobj=client_sock, events=selectors.EVENT_READ | selectors.EVENT_WRITE, data=data)

    elif req["hdr"] == "registering":
        if not verify_registering_req(req_str):
            print(f"Rejected attempt from client {client_addr}: Invalid registration request")
            resp = json.dumps({ "hdr":"error:0", "msg":"Invalid registration request" })
            client_sock.sendall(resp.encode("utf-8"))
            client_sock.close()
            return
        uname, pub_key, _ = req["msg"].split()

        cursor.execute(f"SELECT * FROM customers WHERE uname='{uname}'")
        check_if_registered = cursor.fetchone()
        if check_if_registered != None:
            print(f"Rejected attempt from client {client_addr}: User {uname} already registered")
            resp = json.dumps({ "hdr":"error:1", "msg":f"User {uname} already registered" })
            client_sock.sendall(resp.encode("utf-8"))
            client_sock.close()
            return

        cursor.execute("INSERT INTO customers (uname, pub_key) VALUES('%s', '%s')" % (uname, pub_key))
        conn.commit()
        local_cursor.execute("INSERT INTO local_buffer (uname, output_buffer) VALUES('%s', '')" % (uname))
        local_cursor.execute("INSERT INTO server_map (uname, serv_name) VALUES('%s', '%s')" % (uname, this_server_name))
        # Informing all servers
        server_data = json.dumps({"hdr":"reg", "msg":uname})
        for i in other_servers:
            append_output_buffer(i, server_data)

        print(f"User {uname} registered")
        resp = json.dumps({ "hdr":"registered", "msg":f"User {uname} is now registered" })

        client_sock.sendall(resp.encode("utf-8"))

        data = Server_to_Client(client_addr, uname, client_sock, local_cursor, this_server_name, cursor, conn, other_servers, pub_key)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        sel.register(fileobj=client_sock, events=events, data=data)

    elif (req["hdr"] == "onboarding"):
        uname, _ = req["msg"].split()

        cursor.execute(f"SELECT pub_key FROM customers WHERE uname='{uname}'")
        pub_key = cursor.fetchone()
        if pub_key == None:
            print(f"Rejected attempt from client {client_addr}: User {uname} not registered")
            resp = json.dumps({ "hdr":"error:2", "msg":f"User {uname} not registered" })
            client_sock.sendall(resp.encode("utf-8"))
            client_sock.close()
            return

        pub_key = str_to_pub_key(pub_key[0])

        if (not verify_onboarding_req(req_str, pub_key)):
            print(f"Rejected attempt from client {client_addr}: Invalid onboarding request")
            resp = json.dumps({ "hdr":"error:3", "msg":"Invalid onboarding request" })
            client_sock.sendall(resp.encode("utf-8"))
            client_sock.close()
            return

        # Informing all servers
        server_data = json.dumps({"hdr":"onb", "msg":uname})
        for i in other_servers:
            append_output_buffer(i, server_data)

        print(f"User {uname} connected")
        resp = json.dumps({ "hdr":"onboarded", "msg":f"User {uname} onboarded" })

        client_sock.sendall(resp.encode("utf-8"))
        data = Server_to_Client(client_addr, uname, client_sock, local_cursor, this_server_name, cursor, conn, other_servers, pub_key)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        sel.register(fileobj=client_sock, events=events, data=data)

try:
    while True:
        events = sel.select(timeout=None)
        for key, event in events:
            if key.data == None:
                accept_wrapper(key.fileobj)
            else:
                if event & selectors.EVENT_WRITE:
                    key.data.write()
                if event & selectors.EVENT_READ:
                    key.data.read()
                if key.data.stop:
                    sel.unregister(key.fileobj)
except KeyboardInterrupt:
    print("Caught keyboard interrupt, exiting")
finally:
    sel.close()
    conn_accepting_sock.close()
local_conn.commit()
conn.commit()
local_cursor.close()
local_conn.close()
local_conn.close()
conn.close()
