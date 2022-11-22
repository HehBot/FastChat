from sys import argv
import socket
import selectors
import types
import json
import sqlite3
import threading
import ast

import rsa
from request import verify_registering_req, verify_onboarding_req, pub_key_to_str, str_to_pub_key

if len(argv) < 3:
    print(f"Usage: {argv[0]} <server ip> <server port>")
    exit(-1)

server_addr = (argv[1], int(argv[2]))

conn_accepting_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conn_accepting_sock.bind(server_addr)
conn_accepting_sock.listen()
print(f"Listening on {server_addr} as connection accepter of flag server")
conn_accepting_sock.setblocking(False)

sel = selectors.DefaultSelector()
sel.register(fileobj=conn_accepting_sock, events=selectors.EVENT_READ, data=None)  # as we only want to read from |conn_accepting_sock|

# dbfile stores whether the database file exists or not
dbfile = True
try:
    f = open("fastchat.db")
    f.close()
except:
    dbfile = False

conn = sqlite3.connect("fastchat.db")
cursor = conn.cursor()

if not dbfile:
    cursor.execute("CREATE TABLE customers (uname TEXT NOT NULL, pub_key TEXT NOT NULL, output_buffer TEXT, PRIMARY KEY(uname))")
    cursor.execute("CREATE TABLE groups (group_id INTEGER NOT NULL, uname TEXT, isAdmin INTEGER, PRIMARY KEY (group_id, uname), FOREIGN KEY(uname) REFERENCES customers(uname))")


new_server_addr = (argv[3], int(argv[4]))
Server_connect_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

a=0
while a==0:
    try:
        Server_connect_sock.connect(new_server_addr)
        a=1
    except ConnectionRefusedError:
        pass


#ser_data = types.SimpleNamespace(addr=new_server_addr, uname=argv[4], isClient=False)
print()
print("Connected to server with address:")
print(new_server_addr)
print()
head = "server"+argv[2]
json_msg = {"hdr":head}
Server_connect_sock.sendall(json.dumps(json_msg).encode())
Server_connect_sock.setblocking(False)
# sel.register(fileobj=Server_connect_sock, events=selectors.EVENT_READ, data=ser_data)
def listen_to_server():
    while True:
        print("NEW HERE?")
        data_from_server = Server_connect_sock.recv(1024).decode()
        print("NEW OR HERE?")
        req = json.loads(data_from_server)
        senders_name = req.pop("sender")
        print()
        print("RECEIVED FROM SERVER A MESSAGE FROM "+senders_name)
        print(req)
        print()
        if req["hdr"][0] == ">":
            recip_uname = req["hdr"][1:]
            append_output_buffer(recip_uname,senders_name,json.dumps(req))
        TODO
        
t1 = threading.Thread(target=listen_to_server)
t1.daemon = True
t1.start()

output_buffer_map = {}
output_buffer_map[argv[4]] = []
def append_output_buffer(uname, senders_uname, newdata):
    # output_buffer = cursor.execute(f"SELECT output_buffer FROM customers WHERE uname='{uname}'").fetchone()[0]
    # output_list=ast.literal_eval(output_buffer)
    # output_list.append([newdata, senders_uname])
    # cursor.execute("UPDATE customers SET output_buffer='%s' WHERE uname='%s'" % (output_list, uname))
    output_buffer_map[uname].append([senders_uname,newdata])


def accept_wrapper(sock):
    client_sock, client_addr = sock.accept()
    print(f"Accepted connection from client {client_addr}")
    
    while (True):
        req_str = client_sock.recv(1024).decode()
        
        print("\nLOADING :")
        print(req_str)
        print()
        req = json.loads(req_str)

        if (req["hdr"] == "registering"):
            if (not verify_registering_req(req_str)):
                print(f"Rejected attempt from client {client_addr}: Invalid registration request")
                resp = json.dumps({ "hdr":"error:0", "msg":"Invalid registration request" })
                client_sock.sendall(resp.encode("utf-8"))
                continue
            uname, pub_key, _ = req["msg"].split()

            check_if_registered = cursor.execute(f"SELECT * FROM customers WHERE uname='{uname}'").fetchone()
            if check_if_registered != None:
                print(f"Rejected attempt from client {client_addr}: User {uname} already registered")
                resp = json.dumps({ "hdr":"error:1", "msg":f"User {uname} already registered" })
                client_sock.sendall(resp.encode("utf-8"))

                continue

            cursor.execute("INSERT INTO customers(uname, pub_key, output_buffer) VALUES('%s', '%s', '[]')" % (uname, pub_key))
            output_buffer_map[uname]=[]
            print(f"User {uname} registered")
            resp = json.dumps({ "hdr":"registered", "msg":f"User {uname} is now registered" })

            client_sock.sendall(resp.encode("utf-8"))
            data = types.SimpleNamespace(addr=client_addr, uname=uname, isClient=True)
            events = selectors.EVENT_READ | selectors.EVENT_WRITE
            sel.register(fileobj=client_sock, events=events, data=data)
            break

        elif (req["hdr"] == "onboarding"):
            uname, _ = req["msg"].split()

            pub_key = cursor.execute(f"SELECT pub_key FROM customers WHERE uname='{uname}'").fetchone()[0]
            if pub_key == None:
                print(f"Rejected attempt from client {client_addr}: User {uname} not registered")
                resp = json.dumps({ "hdr":"error:2", "msg":f"User {uname} not registered" })
                client_sock.sendall(resp.encode("utf-8"))
                continue

            pub_key = str_to_pub_key(pub_key)

            if (not verify_onboarding_req(req_str, pub_key)):
                print(f"Rejected attempt from client {client_addr}: Invalid onboarding request")
                resp = json.dumps({ "hdr":"error:3", "msg":"Invalid onboarding request" })
                client_sock.sendall(resp.encode("utf-8"))
                client_sock.close()
                continue

            print(f"User {uname} connected")
            resp = json.dumps({ "hdr":"onboarded", "msg":f"User {uname} onboarded" })

            client_sock.sendall(resp.encode("utf-8"))
            data = types.SimpleNamespace(addr=client_addr, uname=uname, isClient = True)
            events = selectors.EVENT_READ | selectors.EVENT_WRITE
            sel.register(fileobj=client_sock, events=events, data=data)
            break
        elif req["hdr"][:6]=="server":
            serv_name = req["hdr"][6:]
            data = types.SimpleNamespace(addr=client_addr, uname=serv_name, isClient=False)
            print("Writing to the server")
            print(serv_name)
            print(client_addr)
            print()
            sel.register(fileobj=client_sock, events=selectors.EVENT_WRITE, data=data)
            break 

# u is the group id
u = 1
def service_connection(key, event):
    client_sock = key.fileobj
    data = key.data
    if event & selectors.EVENT_READ:
        recv_data = client_sock.recv(1024).decode()
        pub_key = cursor.execute("SELECT customers.pub_key FROM customers WHERE uname='%s'" % (data.uname)).fetchone()[0]
        if recv_data:
            print("\nLOADS")
            print(recv_data)
            print()
            req = json.loads(recv_data)

            # Public key request
            if (req["hdr"] == "pub_key"):
                append_output_buffer(data.uname,data.uname, json.dumps(req))

            # Group creating request
            elif (req["hdr"] == "grp_registering"): #Creating group
                global u
                group_id = u
                cursor.execute("INSERT INTO groups(group_id, uname, isAdmin) VALUES(%d, '%s', %d)" % (group_id, data.uname, 1))
                resp = json.dumps({"hdr":"group_id", "msg":str(group_id)})
                client_sock.sendall(resp.encode("utf-8"))
                
                print("\nRegistered new group with id " + str(group_id) + '\n')
                
                u = u + 1

            # Normal Message
            elif req["hdr"][0] == ">":
                recip_uname = req["hdr"][1:]
                TODO
                append_output_buffer(argv[4],data.uname,json.dumps(req))
            
            # Group Operation Adding and sending non abelian groups
            elif req["hdr"][0] == "<":
                #Adding this person to group
                if ":" in req["hdr"][1:]: 
                    k=req["hdr"].find(":")
                    group_id = int(req["hdr"][1:k])
                    recip_name = req["hdr"][k + 1:]
                    
                    print("TRYING TO ADD NEW PERSON")
                    print(f"group_id: {group_id}, recip_name = {recip_name}, MyName = {data.uname}")
                    
                    is_admin = cursor.execute("SELECT groups.isAdmin FROM groups WHERE group_id=%d AND groups.uname='%s'" % (group_id, data.uname)).fetchone()[0]

                    if(is_admin == 1):
                        cursor.execute("INSERT INTO groups(group_id,  uname, isAdmin) VALUES(%d, '%s', %d)" % (group_id, recip_name, 0))
                        resp=json.dumps({"hdr":"<roup_added:" + str(group_id) + ":" + data.uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"],"time":req["time"], "sign":req["sign"]})
#                        output_buffer[recip_name].append(resp)
                        TODO
                        append_output_buffer(recip_name,data.uname, resp)
                        print("\nAdded " + recip_name + " to group " + str(group_id) + " by " + data.uname + '\n')

                    else: #If not admin
                        TODO

                # Messaging on a group
                else: 
                    group_id = int(req["hdr"][1:])
                    list_of_names = cursor.execute("SELECT groups.uname FROM groups WHERE group_id=%d" % (group_id)).fetchall()
                    for recip_uname in list_of_names:
                        if recip_uname[0] != data.uname:
                            TODO
                            append_output_buffer(recip_uname[0],data.uname, json.dumps(req))
                    
                    print("\nSending ") 
                    print(req) 
                    print(" to " + str(group_id) + '\n')
            
        else:
            print(f"Closing connection to {data.addr}")
            sel.unregister(client_sock)
            client_sock.close()
        
    if event & selectors.EVENT_WRITE:
        # output_buffer = cursor.execute(f"SELECT output_buffer FROM customers WHERE uname='{data.uname}'").fetchone()[0]
        # output_list = ast.literal_eval(output_buffer)
        output_list = output_buffer_map[data.uname]
        for i in output_list:
            print()
            print("OUTPUT BUFFER HAS")
            print(i)
            print()
            print("THIS")
            senders_uname = i[0]
            sent_req = json.loads(i[1])
            pub_key = cursor.execute("SELECT customers.pub_key FROM customers WHERE uname='%s'" % (senders_uname)).fetchone()[0]

            if (sent_req["hdr"] == "pub_key"):
                resp = None
                pub_key_output_buffer = cursor.execute("SELECT pub_key, output_buffer FROM customers WHERE uname='%s'" % (sent_req["msg"])).fetchone()
                if pub_key_output_buffer == None:
                    resp = { "hdr":"error", "msg":f"User {sent_req['msg']} not registered" }
                else:
                    pub_key_req = pub_key_output_buffer[0]
                    resp = { "hdr":"pub_key", "msg":pub_key_req }

                #append_output_buffer(senders_uname, json.dumps(resp))
                client_sock.send(json.dumps(resp).encode("utf-8"))

            elif sent_req["hdr"][0] == ">":
                recip_uname = sent_req["hdr"][1:]
                mod_data = json.dumps({ "hdr":'>' + senders_uname + ':' + pub_key, "msg":sent_req["msg"], "aes_key":sent_req["aes_key"], "time":sent_req["time"], "sign":sent_req["sign"] })

                #append_output_buffer(recip_uname, mod_data)
                client_sock.send(mod_data.encode("utf-8"))
                print("\nSending " + mod_data + " to " + recip_uname + '\n')

            elif sent_req["hdr"][0] == "<":
                
                # Group addition
                if sent_req["hdr"][0:11]=="<roup_added":
                    client_sock.send(json.dumps(sent_req).encode("utf-8"))

                else: #Messaging on a group
                    group_id = int(sent_req["hdr"][1:])
                    mod_data = json.dumps({ "hdr":'<' + str(group_id) + ':' + senders_uname + ':' + pub_key, "msg":sent_req["msg"], "aes_key":sent_req["aes_key"], "time":sent_req["time"], "sign":sent_req["sign"] })
                    client_sock.send(mod_data.encode("utf-8"))
                
                    print("\nSending " + mod_data + " to " + str(group_id) + '\n')
        
        output_buffer_map[data.uname]=[]
        cursor.execute(f"UPDATE customers SET output_buffer='[]' WHERE uname='{data.uname}'")

def server_connection(key,event):
    data = key.data
    server_sock = key.fileobj
    # if event and selectors.EVENT_READ:
    #     pass

    if event & selectors.EVENT_WRITE:

        output_list = output_buffer_map[data.uname]
        for i in output_list:
            resp = json.loads(i[0])
            resp["sender"] = i[0]
            server_sock.sendall(json.dumps(resp).encode("utf-8"))
            

        output_buffer_map[data.uname] = []

try:
    while True:
        events = sel.select(timeout=None)
        for key, event in events:
            if key.data is None:
                accept_wrapper(key.fileobj)
            elif key.data.isClient:
                service_connection(key, event)
            else:
                server_connection(key,event)
except KeyboardInterrupt:
    print("Caught keyboard interrupt, exiting")
finally:
    sel.close()
    conn_accepting_sock.close()
conn.commit()
conn.close()
