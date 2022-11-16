from sys import argv
import socket
import selectors
import types
import json
import sqlite3

import rsa
from request import verify_registering_req, verify_onboarding_req, pub_key_to_str, str_to_pub_key

sel = selectors.DefaultSelector()

server_addr = (argv[1], int(argv[2]))
conn_accepting_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conn_accepting_sock.bind(server_addr)
conn_accepting_sock.listen()
print(f"Listening on {server_addr} as connection accepter of flag server")
conn_accepting_sock.setblocking(False)
sel.register(fileobj=conn_accepting_sock, events=selectors.EVENT_READ, data=None)  # as we only want to read from |conn_accepting_sock|

conn=sqlite3.connect('fastchat.db')
mycursor = conn.cursor()

conn.execute("DROP TABLE IF EXISTS customers;")
conn.execute("CREATE TABLE customers (person_name TEXT NOT NULL, public_key TEXT NOT NULL, PRIMARY KEY(person_name))")
conn.execute("DROP TABLE IF EXISTS groups ;")
conn.execute("CREATE TABLE groups (group_id INTEGER NOT NULL, person_name TEXT, isAdmin INTEGER, PRIMARY KEY (group_id, person_name), FOREIGN KEY(person_name) REFERENCES customers(person_name))")


# Server List
# no_servers = int(input("Enter number of other servers"))
# for j in range(no_servers):
#     ip = input()
#     port = int(input())
#     other_server_addr = (ip, port)

#     other_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#     other_server_sock.bind(other_server_addr)
#     other_server_sock.listen()
#     print(f"Listening on {other_server_addr} as socket for server at {other_server_addr}")
#     other_server_sock.setblocking(False)
#     data = types.SimpleNamespace(addr=other_server_addr, inb=b"", outb=b"")
#     sel.register(fileobj=other_server_sock, events=selectors.EVENT_READ | selectors.EVENT_WRITE, data=data)
# End

# Client to server
#client_pub_keys_servers = {12345:4, 23456:1}


total_data = {}
pub_keys = {}

def accept_wrapper(sock):
    client_sock, client_addr = sock.accept()
    print(f"Accepted connection from client {client_addr}")
    
    while (True):
        req_str = client_sock.recv(1024).decode()
        print()
        print('LOADING :')
        print(req_str)
        print()
        req = json.loads(req_str)

        if (req["hdr"] == "registering"):
            if (not verify_registering_req(req_str)):
                print(f"Rejected attempt from client {client_addr}: Invalid registration request")
                resp = json.dumps({ "hdr":"error:0", "msg":"Invalid registration request" })
                client_sock.sendall(resp.encode("utf-8"))
                continue
            uname, pub_key = req["msg"].split()
            if (uname in total_data.keys()):
                print(f"Rejected attempt from client {client_addr}: User {uname} already registered")
                resp = json.dumps({ "hdr":"error:1", "msg":f"User {uname} already registered" })
                client_sock.sendall(resp.encode("utf-8"))
                continue
            total_data[uname] = []
            pub_keys[uname] = pub_key

            print(f"User {uname} registered")
            resp = json.dumps({ "hdr":"registered", "msg":f"User {uname} is now registered" })

            client_sock.sendall(resp.encode("utf-8"))
            data = types.SimpleNamespace(addr=client_addr, inb=b"", outb=b"", uname=uname)
            events = selectors.EVENT_READ | selectors.EVENT_WRITE
            sel.register(fileobj=client_sock, events=events, data=data)
            break

        elif (req["hdr"] == "onboarding"):
            uname = req["msg"]
            if not uname in total_data.keys():
                print(f"Rejected attempt from client {client_addr}: User {uname} not registered")
                resp = json.dumps({ "hdr":"error:2", "msg":f"User {uname} not registered" })
                client_sock.sendall(resp.encode("utf-8"))
                continue
            pub_key = str_to_pub_key(pub_keys[uname])
            if (not verify_onboarding_req(req_str, pub_key)):
                print(f"Rejected attempt from client {client_addr}: Invalid onboarding request")
                resp = json.dumps({ "hdr":"error:3", "msg":"Invalid onboarding request" })
                client_sock.sendall(resp.encode("utf-8"))
                client_sock.close()
                continue

            print(f"User {uname} connected")
            resp = json.dumps({ "hdr":"onboarded", "msg":f"User {uname} onboarded" })

            client_sock.sendall(resp.encode("utf-8"))
            data = types.SimpleNamespace(addr=client_addr, inb=b"", outb=b"", uname=uname)
            events = selectors.EVENT_READ | selectors.EVENT_WRITE
            sel.register(fileobj=client_sock, events=events, data=data)
            break

u = 0

def service_connection(key, event):
    client_sock = key.fileobj
    data = key.data
    if event & selectors.EVENT_READ:
        recv_data = client_sock.recv(10024).decode()
        if recv_data:
            print()
            print("LOADS")
            print(recv_data)
            print()
            req = json.loads(recv_data)
            if (req["hdr"] == "pub_key"):
                resp = None
                if not req["msg"] in pub_keys.keys():
                    resp = { "hdr":"error", "msg":f"User {req['msg']} not registered" }
                else:
                    resp = { "hdr":"pub_key", "msg":pub_keys[req["msg"]] }
                total_data[data.uname].append(json.dumps(resp))
            elif (req["hdr"] == "grp_registering"): #Creating group
                global u
                group_id=u
                mycursor.execute("INSERT INTO groups(group_id, person_name, isAdmin) VALUES(%d, '%s', %d)" %(int(group_id), data.uname, 1))
                resp = json.dumps({"hdr":"group_id", "msg":str(u)})
                client_sock.sendall(resp.encode("utf-8"))
                print()
                print("Registered new group with id "+str(u))
                print()
                u=u+1
            elif req["hdr"][0] == ">":
                recip_uname = req["hdr"][1:]
                mod_data = json.dumps({ "hdr":'>' + data.uname + ':' + pub_keys[data.uname], "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })

                total_data[recip_uname].append(mod_data)
                print()
                print("Sending " + mod_data + " to " + recip_uname)
                print()
                #data.inb += recv_data
            elif req["hdr"][0] == "<":
                if ":" in req["hdr"][1:]: #Adding this person to group
                    k=req["hdr"].find(":")
                    group_id = req["hdr"][1:k]
                    recip_name = req["hdr"][k+1:]
                    print()
                    print("TRYING TO ADD NEW PERSON")
                    print(f'group_id: {group_id}, recip_name = {recip_name}, MyName = {data.uname}')
                    print()
                    a=(mycursor.execute("SELECT groups.isAdmin FROM groups WHERE group_id=%d AND groups.person_name='%s'" %(int(group_id), data.uname))).fetchone()
                    print(a[0])
                    if(a[0] == 1):
                        print()
                        print("Added "+recip_name+" to the group "+group_id+" by "+data.uname)
                        print()
                        mycursor.execute("INSERT INTO groups(group_id,  person_name, isAdmin) VALUES(%d, '%s', %d)" %(int(group_id), recip_name, 0))
                        resp=json.dumps({"hdr":"group_added:" + group_id + ":" + data.uname + ':' + pub_keys[data.uname], "msg":req["msg"]})#convert pub_keys to sql
                        total_data[recip_name].append(resp)
                        #resp1=json.dumps({"hdr":"gro", "msg":"ok"})
                        #client_sock.sendall(resp1)

                    else: #If not admin
                        TODO
                else: #Messaging on a group
                    group_id = req["hdr"][1:]
                    mod_data = json.dumps({ "hdr":'<' + group_id + ':' + data.uname + ':' + pub_keys[data.uname], "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })
                    list_of_names=mycursor.execute("SELECT groups.person_name FROM groups WHERE group_id=%d" %(group_id)).fetchall()
                    for recip_uname in list_of_names:
                        if recip_uname[0] != data.uname:
                            total_data[recip_uname[0]].append(mod_data)
                    print()
                    print("Sending " + mod_data + " to " + group_id)
                    print()


            
        else:
            print(f"Closing connection to {data.addr}")
            sel.unregister(client_sock)
            client_sock.close()
        
    if event & selectors.EVENT_WRITE:
        if len(total_data[data.uname])>0:
            for i in total_data[data.uname]:
                client_sock.send(i.encode())
            total_data[data.uname] = []
        

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
finally:
    sel.close()
    conn_accepting_sock.close()
conn.commit()
conn.close()
