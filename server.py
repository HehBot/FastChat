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

sel.register(fileobj=balancing_server_sock, events=selectors.EVENT_WRITE, data=types.SimpleNamespace(sock_type="balancing_server_sock", uname=":balance_serv:"))
init_req = json.dumps({ "hdr":"server", "msg":this_server_name })
balancing_server_sock.sendall(init_req.encode("utf-8"))

print(f"Connected to balancing server at {balancing_server_addr}")

other_servers, psql_dbname, psql_uname, psql_pwd = balancing_server_sock.recv(1024).decode("utf-8").split('-')
other_servers = other_servers.split(';')

if other_servers[0] != "FIRST":
    for i in other_servers:
        other_server_addr = i.split(':')
        other_server_addr = (other_server_addr[0], int(other_server_addr[1]))

        other_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        other_server_sock.connect(other_server_addr)

        connection_req = json.dumps({ "hdr":"server", "msg":this_server_name })
        other_server_sock.sendall(connection_req.encode("utf-8"))
        print(f"Sent connection request to server {i}")

        data = types.SimpleNamespace(sock_type="server_sock", addr=other_server_addr, inb="", uname=i)

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
        data = types.SimpleNamespace(sock_type="server_sock", addr=client_addr, inb="", uname=req["msg"])
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
        server_data = json.dumps({"hdr":"reg","msg":uname})
        for i in other_servers:
            append_output_buffer(i, server_data)

        print(f"User {uname} registered")
        resp = json.dumps({ "hdr":"registered", "msg":f"User {uname} is now registered" })

        client_sock.sendall(resp.encode("utf-8"))
        data = types.SimpleNamespace(addr=client_addr, sock_type="client_sock", inb="", uname=uname)
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
        server_data = json.dumps({"hdr":"onb","msg":uname})
        for i in other_servers:
            append_output_buffer(i, server_data)

        print(f"User {uname} connected")
        resp = json.dumps({ "hdr":"onboarded", "msg":f"User {uname} onboarded" })

        client_sock.sendall(resp.encode("utf-8"))
        data = types.SimpleNamespace(addr=client_addr, sock_type="client_sock", inb="", uname=uname)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        sel.register(fileobj=client_sock, events=events, data=data)

def service_client_connection(key, event):
    client_sock = key.fileobj
    data = key.data

    if event & selectors.EVENT_READ:
        recv_data = client_sock.recv(1024).decode("utf-8")

        if recv_data == "":
            print(f"Closing connection to {data.addr}")
            # Informing all servers
            server_data = json.dumps({"hdr":"left","msg":data.uname})
            for i in other_servers:
                append_output_buffer(i, server_data)
            sel.unregister(client_sock)
            client_sock.close()
            return

        data.inb += recv_data

        def process_data(json_string):
            cursor.execute("SELECT customers.pub_key FROM customers WHERE uname='%s'" % (data.uname))
            pub_key = cursor.fetchone()[0]
            print("\nLOADS")
            print(json_string)
            print()
            req = json.loads(json_string)

            # Response to public key request
            if (req["hdr"] == "pub_key"):
                resp = None
                cursor.execute("SELECT pub_key FROM customers WHERE uname='%s'" % (req["msg"]))
                resp_pub_key = cursor.fetchone()
                if resp_pub_key == None:
                    resp = { "hdr":"error:4", "msg":f"User {req['msg']} not registered" }
                else:
                    resp_pub_key = resp_pub_key[0]
                    resp = { "hdr":"pub_key", "msg":resp_pub_key }

                append_output_buffer(data.uname, json.dumps(resp))

            # Response to group creating request
            elif (req["hdr"] == "grp_registering"):
                cursor.execute("SELECT isAdmin FROM groups WHERE group_id=0")
                group_id = int(cursor.fetchone()[0])
                cursor.execute("INSERT INTO groups(group_id, uname, isAdmin) VALUES(%d, '%s', %d)" % (group_id, data.uname, 1))
                conn.commit()

                resp = json.dumps({"hdr":"group_id", "msg":str(group_id)})
                client_sock.sendall(resp.encode("utf-8"))

                print("\nRegistered new group with id " + str(group_id) + '\n')

                cursor.execute("UPDATE groups SET isAdmin=%d WHERE group_id=0" % (group_id + 1))
                conn.commit()

            # Personal message
            elif req["hdr"][0] == ">":
                recip_uname = req["hdr"][1:]
                mod_data = json.dumps({ "send_to":recip_uname, "hdr":'>' + data.uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })

                serv = local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'"%(recip_uname)).fetchone()[0]
                if serv == this_server_name:
                    append_output_buffer(recip_uname, mod_data)
                else:
                    append_output_buffer(serv, mod_data)

                print("\nSending " + mod_data + " to " + recip_uname + '\n')

            # Group operations
            elif req["hdr"][0] == "<":

                # Removing from a group
                if "::" in req["hdr"][1:]:
                    k = req["hdr"].find(":")
                    group_id = int(req["hdr"][1:k])
                    recip_uname = req["hdr"][k + 2:]

                    cursor.execute("SELECT groups.isAdmin FROM groups WHERE group_id=%d AND groups.uname='%s'" % (group_id, data.uname))
                    is_admin = cursor.fetchone()[0]
                    # Admin removing someone else
                    if is_admin == 1 and recip_uname != data.uname:
                        print("Removing from group")

                        cursor.execute("DELETE FROM groups WHERE groups.group_id = '%s' AND groups.uname = '%s' " %(group_id, recip_uname))
                        conn.commit()

                        resp1 = {"hdr":"group_removed:" + str(group_id) + ":" + data.uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"],"time":req["time"], "sign":req["sign"]}
                        resp1["send_to"] = recip_uname
                        serv = local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'"%(recip_uname)).fetchone()[0]
                        if serv == this_server_name:
                            append_output_buffer(recip_uname, json.dumps(resp1))
                        else:
                            append_output_buffer(serv, json.dumps(resp1))

                        resp2 = {"hdr":"person_removed:" + str(group_id) + ":" + recip_uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"],"time":req["time"], "sign":req["sign"]}
                        cursor.execute("SELECT groups.uname FROM groups WHERE groups.group_id = %s" %(group_id))
                        group_participants = cursor.fetchall()
                        for i in group_participants:
                            resp2["send_to"] = i[0]
                            serv = local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'" % (i[0])).fetchone()[0]
                            if serv == this_server_name:
                                append_output_buffer(i[0], json.dumps(resp2))
                            else:
                                append_output_buffer(serv,json.dumps(resp2))

                        print("\nRemoved " + recip_uname + " from group " + str(group_id) + " by " + data.uname + '\n')

                    # Admin leaving
                    elif is_admin == 1 and recip_uname == data.uname:
                        print("Admin may not leave group")
                        resp1 = json.dumps({"hdr":"error:5", "msg":"Admin may not leave group"})
                        append_output_buffer(recip_uname, resp1)

                    # If not admin
                    else:
                        # Leaving the group
                        if recip_uname == data.uname:
                            print("Exiting from group")

                            cursor.execute("DELETE FROM groups WHERE groups.group_id = '%s' AND groups.uname = '%s' " %(group_id, recip_uname))
                            conn.commit()
                            resp1 = {"hdr":"group_left:" + str(group_id), "msg":""}
                            resp1["send_to"] = recip_uname
                            serv = local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'"%(recip_uname)).fetchone()[0]
                            if serv == this_server_name:
                                append_output_buffer(recip_uname, json.dumps(resp1))
                            else:
                                append_output_buffer(serv, json.dumps(resp1))

                            resp2 = {"hdr":"person_left:" + str(group_id) + ":" + recip_uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"],"time":req["time"], "sign":req["sign"]}
                            cursor.execute("SELECT groups.uname FROM groups WHERE groups.group_id = %s" %(group_id))
                            group_participants = cursor.fetchall()
                            for i in group_participants:
                                resp2["send_to"] = i[0]
                                serv = local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'" % (i[0])).fetchone()[0]
                                if serv == this_server_name:
                                    append_output_buffer(i[0], json.dumps(resp2))
                                else:
                                    append_output_buffer(serv,json.dumps(resp2))

                            print('\n' + recip_uname + " left group " + str(group_id) + '\n')

                        # Not admin and trying to remove someone else
                        else:
                            pass

                # Adding this person to group
                elif ":" in req["hdr"][1:]:
                    k = req["hdr"].find(":")
                    group_id = int(req["hdr"][1:k])
                    recip_uname = req["hdr"][k + 1:]

                    print("TRYING TO ADD NEW PERSON")
                    print(f"group_id: {group_id}, recip_uname = {recip_uname}, MyName = {data.uname}")

                    cursor.execute("SELECT groups.isAdmin FROM groups WHERE group_id=%d AND groups.uname='%s'" % (group_id, data.uname))
                    is_admin = cursor.fetchone()[0]
                    if(is_admin == 1):
                        resp2 = {"hdr":"person_added:" + str(group_id) + ":" + recip_uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"],"time":req["time"], "sign":req["sign"]}
                        cursor.execute("SELECT groups.uname FROM groups WHERE groups.group_id = %s" %(group_id))
                        group_participants = cursor.fetchall()
                        
                        for i in group_participants:
                            resp2["send_to"] = i[0]
                            serv = local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'" % (i[0])).fetchone()[0]
                            if serv == this_server_name:
                                append_output_buffer(i[0], json.dumps(resp2))
                            else:
                                append_output_buffer(serv,json.dumps(resp2))

                        cursor.execute("INSERT INTO groups(group_id,  uname, isAdmin) VALUES(%d, '%s', %d)" % (group_id, recip_uname, 0))
                        conn.commit()

                        resp1 = {"hdr":"group_added:" + str(group_id) + ":" + data.uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"],"time":req["time"], "sign":req["sign"]}

                        serv = local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'"%(recip_uname)).fetchone()[0]

                        resp1["send_to"] = recip_uname
                        if serv == this_server_name:
                            append_output_buffer(recip_uname, json.dumps(resp1))
                        else:
                            append_output_buffer(serv, json.dumps(resp1))

                        print("\nAdded " + recip_uname + " to group " + str(group_id) + " by " + data.uname + '\n')

                    else: #If not admin
                        # TODO
                        pass

                # Messaging on a group
                else:
                    group_id = int(req["hdr"][1:])
                    mod_data = { "hdr":'<' + str(group_id) + ':' + data.uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] }
                    cursor.execute("SELECT groups.uname FROM groups WHERE group_id=%d" % (group_id))
                    list_of_names = cursor.fetchall()

                    for i in list_of_names:
                        if i[0] != data.uname:
                            mod_data["send_to"] = i[0]
                            serv = local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'" % (i[0])).fetchone()[0]
                            if serv == this_server_name:
                                append_output_buffer(i[0], json.dumps(mod_data))
                            else:
                                append_output_buffer(serv,json.dumps(mod_data))


                    print("\nSending " + json.dumps(mod_data) + " to " + str(group_id) + '\n')

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

        if output_buffer != None and output_buffer[0] != '':
            local_cursor.execute(f"UPDATE local_buffer SET output_buffer='' WHERE uname='{data.uname}'")
            client_sock.sendall(output_buffer[0].encode("utf-8"))

def service_server_connection(key, event):
    server_sock = key.fileobj
    data = key.data
    if event & selectors.EVENT_READ:
        recv_data = server_sock.recv(1024).decode("utf-8")
        if recv_data == "":
            print(f"Closing connection to {data.addr}")
            sel.unregister(server_sock)
            server_sock.close()
            return

        data.inb += recv_data

        def process_server_data(json_string):
            print("\nLOADS for server ")
            print(json_string)
            print()
            req = json.loads(json_string)

            # Registration
            if req["hdr"] == "reg":
                new_person = req["msg"]
                print("Trying to insert " + new_person)
                local_cursor.execute("INSERT INTO local_buffer (uname, output_buffer) VALUES('%s', '')" % (new_person))
                local_cursor.execute("INSERT INTO server_map (uname, serv_name) VALUES('%s', '%s')" % (new_person, data.uname))
                print()
                print(f'Added new user {new_person} to server {data.uname}')
                print()

            # Onboarding
            elif req["hdr"] == "onb":
                new_person = req["msg"]
                local_cursor.execute("UPDATE server_map SET serv_name = '%s' WHERE uname = '%s'" % (data.uname, new_person))
                output_buffer = local_cursor.execute(f"SELECT output_buffer FROM local_buffer WHERE uname='{new_person}'").fetchone()[0]
                local_cursor.execute(f"UPDATE local_buffer SET output_buffer='' WHERE uname='{new_person}'")
                # forward this directly to next server
                append_output_buffer(data.uname, output_buffer)
                print()
                print(f'User {new_person} is online on server {data.uname}')
                print()

            elif req["hdr"] == "left":
                left_person = req["msg"]
                local_cursor.execute("UPDATE server_map SET serv_name = '%s' WHERE uname = '%s'" % (this_server_name, left_person))
                print()
                print(f'User {left_person} went offline from server {data.uname}')
                print()

            # Personal message              req["hdr"][0] == '>':
            # Third party added to group    req["hdr"][:12] == "person_added":
            # Recipent added to group       req["hdr"][:11] == "group_added":
            # Third party removed           req["hdr"][:14] == "person_removed":
            # You are removed               req["hdr"][:13] == "group_removed":
            # Grp_message                   req["hdr"][0]=='<':
            else:
                recip_uname = req["send_to"]
                append_output_buffer(recip_uname, json.dumps(req))

        n = 0
        i = 0
        while i != len(data.inb):
            if data.inb[i] == '}' and n % 2 == 0:
                json_string = data.inb[:i + 1]
                data.inb = data.inb[i + 1:]
                n = 0
                i = 0
                process_server_data(json_string)
                continue
            if data.inb[i] == '"' and data.inb[i - 1] != '\\':
                n += 1
            i += 1

    if event & selectors.EVENT_WRITE:
        output_buffer = local_cursor.execute(f"SELECT output_buffer FROM local_buffer WHERE uname='{data.uname}'").fetchone()
        if output_buffer != None and output_buffer[0] != '':
            local_cursor.execute(f"UPDATE local_buffer SET output_buffer='' WHERE uname='{data.uname}'")
            server_sock.sendall(output_buffer[0].encode("utf-8"))

def service_balancing_server_connection(key,event):
    balancing_server_sock = key.fileobj
    data = key.data
    if event & selectors.EVENT_WRITE:
        output_buffer = local_cursor.execute(f"SELECT output_buffer FROM local_buffer WHERE uname='{data.uname}'").fetchone()
        if output_buffer != None and output_buffer[0] != '':
            local_cursor.execute(f"UPDATE local_buffer SET output_buffer='' WHERE uname='{data.uname}'")
            balancing_server_sock.sendall(output_buffer[0].encode("utf-8"))

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
local_conn.commit()
conn.commit()
local_cursor.close()
local_conn.close()
local_conn.close()
conn.close()
