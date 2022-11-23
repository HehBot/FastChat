from sys import argv
import socket
import selectors
import types
import json
import sqlite3
import psycopg2

import rsa
from request import verify_registering_req, verify_onboarding_req, pub_key_to_str, str_to_pub_key

if len(argv) != 5:
    print(f"Usage: {argv[0]} <server ip> <server port> <balancing server ip> <balancing server port>")
    exit(-1)

server_addr = (argv[1], int(argv[2]))
balancing_server_addr = (argv[3], int(argv[4]))

sel = selectors.DefaultSelector()

balancing_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
balancing_server_sock.connect(balancing_server_addr)

sel.register(fileobj=balancing_server_sock, events=selectors.EVENT_WRITE, data=types.SimpleNamespace(sock_type="balancing_server_sock"))
balancing_server_sock.sendall(b"server")

print(f"Connected to balancing server at {balancing_server_addr}")

other_servers = balancing_server_sock.recv(1024).decode("utf-8").split(';')
if other_servers[0] != "FIRST":
    for i in other_servers:
        other_server_addr = i.split(':')
        other_server_addr = (other_server_addr[0], int(other_server_addr[1]))
        
        other_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        other_server_sock.connect(other_server_addr)

        other_server_sock.sendall(json.dumps({"hdr":"server"}))
        data = types.SimpleNamespace(sock_type="server_sock", addr=other_server_addr, inb="")
        sel.register(fileobj=balancing_server_sock, events=selectors.EVENT_READ | selectors.EVENT_WRITE, data=data)

conn_accepting_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conn_accepting_sock.bind(server_addr)
conn_accepting_sock.listen()
print(f"Listening on {server_addr} as connection accepter of server")
conn_accepting_sock.setblocking(False)

sel.register(fileobj=conn_accepting_sock, events=selectors.EVENT_READ, data=None)  # as we only want to read from conn_accepting_sock

# dbfile stores whether the database file exists or not
dbfile = True
try:
    f = open("localfastchat.db", 'r')
    f.close()
except:
    dbfile = False

conn = sqlite3.connect("localfastchat.db", isolation_level=None)
local_cursor = conn.cursor()
conn1 = sqlite3.connect("fastchat.db", isolation_level=None)
cursor = conn1.cursor()
#cursor.execute("PRAGMA journal_mode=wal")


if not dbfile:
    cursor.execute("CREATE TABLE customers (uname TEXT NOT NULL, pub_key TEXT NOT NULL, PRIMARY KEY(uname))")
    cursor.execute("CREATE TABLE groups (group_id INTEGER NOT NULL, uname TEXT, isAdmin INTEGER, PRIMARY KEY (group_id, uname), FOREIGN KEY(uname) REFERENCES customers(uname))")
    local_cursor.execute("CREATE TABLE local_buffer (uname TEXT NOT NULL, output_buffer TEXT)")

def append_output_buffer(uname, newdata):
    print()
    print(f'ADDING TO OUTPUT BUFFER {newdata} of {uname}')
    print()
    is_present = local_cursor.execute("SELECT uname FROM local_buffer WHERE uname = '%s'"%(uname)).fetchone()
    print(is_present)
    if is_present==None:
        local_cursor.execute("INSERT INTO local_buffer(uname,output_buffer) VALUES('%s','%s')" % (uname,newdata))
    else:
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
    print()

    req = json.loads(req_str)

    if req["hdr"] == "server":
        data = types.SimpleNamespace(sock_type="server_sock", addr=client_addr, inb="")
        sel.register(fileobj=client_sock, events=selectors.EVENT_READ | selectors.EVENT_WRITE, data=data)

    elif req["hdr"] == "registering":
        if not verify_registering_req(req_str):
            print(f"Rejected attempt from client {client_addr}: Invalid registration request")
            resp = json.dumps({ "hdr":"error:0", "msg":"Invalid registration request" })
            client_sock.sendall(resp.encode("utf-8"))
            client_sock.close()
            return
        uname, pub_key, _ = req["msg"].split()

        check_if_registered = cursor.execute(f"SELECT * FROM customers WHERE uname='{uname}'").fetchone()
        if check_if_registered != None:
            print(f"Rejected attempt from client {client_addr}: User {uname} already registered")
            resp = json.dumps({ "hdr":"error:1", "msg":f"User {uname} already registered" })
            client_sock.sendall(resp.encode("utf-8"))
            client_sock.close()
            return

        cursor.execute("INSERT INTO customers(uname, pub_key) VALUES('%s', '%s')" % (uname, pub_key))

        print(f"User {uname} registered")
        resp = json.dumps({ "hdr":"registered", "msg":f"User {uname} is now registered" })

        client_sock.sendall(resp.encode("utf-8"))
        data = types.SimpleNamespace(addr=client_addr, sock_type="client_sock", inb="", uname=uname)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        sel.register(fileobj=client_sock, events=events, data=data)

    elif (req["hdr"] == "onboarding"):
        uname, _ = req["msg"].split()

        pub_key = cursor.execute(f"SELECT pub_key FROM customers WHERE uname='{uname}'").fetchone()[0]
        if pub_key == None:
            print(f"Rejected attempt from client {client_addr}: User {uname} not registered")
            resp = json.dumps({ "hdr":"error:2", "msg":f"User {uname} not registered" })
            client_sock.sendall(resp.encode("utf-8"))
            client_sock.close()
            return

        pub_key = str_to_pub_key(pub_key)

        if (not verify_onboarding_req(req_str, pub_key)):
            print(f"Rejected attempt from client {client_addr}: Invalid onboarding request")
            resp = json.dumps({ "hdr":"error:3", "msg":"Invalid onboarding request" })
            client_sock.sendall(resp.encode("utf-8"))
            client_sock.close()
            return

        print(f"User {uname} connected")
        resp = json.dumps({ "hdr":"onboarded", "msg":f"User {uname} onboarded" })

        client_sock.sendall(resp.encode("utf-8"))
        data = types.SimpleNamespace(addr=client_addr, inb="", uname=uname)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        sel.register(fileobj=client_sock, events=events, data=data)

# u is the group id
u = 1
def service_client_connection(key, event):
    client_sock = key.fileobj
    data = key.data
    
    if event & selectors.EVENT_READ:
        recv_data = client_sock.recv(1024).decode("utf-8")

        if recv_data == "":
            print(f"Closing connection to {data.addr}")
            sel.unregister(client_sock)
            client_sock.close()
            return

        data.inb += recv_data
        
        def process_data(json_string):
            pub_key = cursor.execute("SELECT customers.pub_key FROM customers WHERE uname='%s'" % (data.uname)).fetchone()[0]

            print("\nLOADS")
            print(json_string)
            print()
            req = json.loads(json_string)

            # Response to public key request
            if (req["hdr"] == "pub_key"):
                resp = None
                pub_key_output_buffer = cursor.execute("SELECT pub_key FROM customers WHERE uname='%s'" % (req["msg"])).fetchone()
                if pub_key_output_buffer == None:
                    resp = { "hdr":"error:4", "msg":f"User {req['msg']} not registered" }
                else:
                    pub_key = pub_key_output_buffer[0]
                    resp = { "hdr":"pub_key", "msg":pub_key }

                append_output_buffer(data.uname, json.dumps(resp))

            # Response to group creating request
            elif (req["hdr"] == "grp_registering"):
                global u
                group_id = u
                cursor.execute("INSERT INTO groups(group_id, uname, isAdmin) VALUES(%d, '%s', %d)" % (group_id, data.uname, 1))
                resp = json.dumps({"hdr":"group_id", "msg":str(group_id)})
                client_sock.sendall(resp.encode("utf-8"))
                
                print("\nRegistered new group with id " + str(group_id) + '\n')
                
                u = u + 1

            # Personal message
            elif req["hdr"][0] == ">":
                recip_uname = req["hdr"][1:]
                mod_data = json.dumps({ "hdr":'>' + data.uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })

                append_output_buffer(recip_uname, mod_data)

                print("\nSending " + mod_data + " to " + recip_uname + '\n')
           
            # Group operations
            elif req["hdr"][0] == "<":

                # Removing from a group
                if "::" in req["hdr"][1:]:
                    k = req["hdr"].find(":")
                    group_id = int(req["hdr"][1:k])
                    recip_name = req["hdr"][k + 2:]
                    
                    is_admin = cursor.execute("SELECT groups.isAdmin FROM groups WHERE group_id=%d AND groups.uname='%s'" % (group_id, data.uname)).fetchone()[0]

                    # Admin removing someone else
                    if is_admin == 1 and recip_name != data.uname:
                        print("Removing from group")

                        cursor.execute("DELETE FROM groups WHERE groups.group_id = '%s' AND groups.uname = '%s' " %(group_id, recip_name))

                        resp1 = json.dumps({"hdr":"group_removed:" + str(group_id) + ":" + data.uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"],"time":req["time"], "sign":req["sign"]})
                        append_output_buffer(recip_name, resp1)

                        resp2 = json.dumps({"hdr":"person_removed:" + str(group_id) + ":" + recip_name + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"],"time":req["time"], "sign":req["sign"]})
                        group_participants = cursor.execute("SELECT groups.uname FROM groups WHERE groups.group_id = %s" %(group_id)).fetchall()
                        for i in group_participants:
                            append_output_buffer(i[0], resp2)

                        print("\nRemoved " + recip_name + " from group " + str(group_id) + " by " + data.uname + '\n')

                    # Admin leaving
                    elif is_admin == 1 and recip_name == data.uname:
                        print("Admin may not leave group")
                        resp1 = json.dumps({"hdr":"error:5", "msg":"Admin may not leave group"})
                        append_output_buffer(recip_name, resp1)
                    
                    # If not admin
                    else:
                        # Leaving the group
                        if recip_name == data.uname:
                            print("Exiting from group")
                            
                            cursor.execute("DELETE FROM groups WHERE groups.group_id = '%s' AND groups.uname = '%s' " %(group_id, recip_name))

                            resp1 = json.dumps({"hdr":"group_left:" + str(group_id), "msg":""})
                            append_output_buffer(recip_name, resp1)

                            resp2 = json.dumps({"hdr":"person_left:" + str(group_id) + ":" + recip_name + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"],"time":req["time"], "sign":req["sign"]})

                            group_participants = cursor.execute("SELECT groups.uname FROM groups WHERE groups.group_id = %s" %(group_id)).fetchall()
                            for i in group_participants:
                                append_output_buffer(i[0], resp2)

                            print('\n' + recip_name + " left group " + str(group_id) + '\n')
                        
                        # Not admin and trying to remove someone else
                        else:
                            pass

                # Adding this person to group
                elif ":" in req["hdr"][1:]:
                    k=req["hdr"].find(":")
                    group_id = int(req["hdr"][1:k])
                    recip_name = req["hdr"][k + 1:]
                    
                    print("TRYING TO ADD NEW PERSON")
                    print(f"group_id: {group_id}, recip_name = {recip_name}, MyName = {data.uname}")
                    
                    is_admin = cursor.execute("SELECT groups.isAdmin FROM groups WHERE group_id=%d AND groups.uname='%s'" % (group_id, data.uname)).fetchone()[0]

                    if(is_admin == 1):
                        resp2 = json.dumps({"hdr":"person_added:" + str(group_id) + ":" + recip_name + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"],"time":req["time"], "sign":req["sign"]})
                        group_participants = cursor.execute("SELECT groups.uname FROM groups WHERE groups.group_id = %s" %(group_id)).fetchall()
                        for i in group_participants:
                            append_output_buffer(i[0], resp2)

                        cursor.execute("INSERT INTO groups(group_id,  uname, isAdmin) VALUES(%d, '%s', %d)" % (group_id, recip_name, 0))

                        resp1 = json.dumps({"hdr":"group_added:" + str(group_id) + ":" + data.uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"],"time":req["time"], "sign":req["sign"]})
                        append_output_buffer(recip_name, resp1)

                        print("\nAdded " + recip_name + " to group " + str(group_id) + " by " + data.uname + '\n')

                    else: #If not admin
                        # TODO
                        pass

                # Messaging on a group
                else:
                    group_id = int(req["hdr"][1:])
                    mod_data = json.dumps({ "hdr":'<' + str(group_id) + ':' + data.uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })
                    list_of_names = cursor.execute("SELECT groups.uname FROM groups WHERE group_id=%d" % (group_id)).fetchall()
                    if list_of_names:
                        for recip_uname in list_of_names:
                            if recip_uname[0] != data.uname:
                                append_output_buffer(recip_uname[0], mod_data)

                        print("\nSending " + mod_data + " to " + str(group_id) + '\n')
        
        n = 0
        i = 0
        while i != len(data.inb):
            if data.inb[i] == '}' and n % 2 == 0:
                json_string = data.inb[:i + 1]
                data.inb = data.inb[i + 1:]
                n = 0
                i = 0
                process_data(json_string)
                continue
            if data.inb[i] == '"' and data.inb[i - 1] != '\\':
                n += 1
            i += 1
        
    if event & selectors.EVENT_WRITE:
        output_buffer = local_cursor.execute(f"SELECT output_buffer FROM local_buffer WHERE uname='{data.uname}'").fetchone()
        
        if output_buffer != None:
            local_cursor.execute(f"UPDATE local_buffer SET output_buffer='' WHERE uname='{data.uname}'")
            client_sock.sendall(output_buffer[0].encode("utf-8"))

try:
    while True:
        events = sel.select(timeout=None)
        for key, event in events:
            if key.data == None:
                accept_wrapper(key.fileobj)
            elif key.data.sock_type == "server_sock":
                service_server_connection(key, event)
            elif key.data.sock_type == "client_sock":
                service_client_connection(key, event)
            elif key.data.sock_type == "balancing_server_sock":
                service_balancing_server_connection(key, event)
except KeyboardInterrupt:
    print("Caught keyboard interrupt, exiting")
finally:
    sel.close()
    conn_accepting_sock.close()
conn.commit()
conn.close()
