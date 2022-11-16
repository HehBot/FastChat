from sys import argv
import socket
import json
import threading
import rsa
import sqlite3
from time import time, strftime, localtime

from request import *

if len(argv) < 3:
    print(f"Usage: {argv[0]} <server ip> <server port>")
server_addr = (argv[1], int(argv[2]))
conn=sqlite3.connect('fastchatclient.db')
cursor=conn.cursor()

conn.execute("DROP TABLE IF EXISTS group_name_id;")
conn.execute("CREATE TABLE group_name_id (group_id TEXT NOT NULL PRIMARY KEY, group_name TEXT NOT NULL, group_pub_key TEXT NOT NULL, group_priv_key TEXT NOT NULL)")#May need to change group id to int
keyfile = None
try:
    keyfile = open("local.key", 'r')
except:
    keyfile = None

client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_sock.connect(server_addr)

uname, pub_key, priv_key = None, None, None

grp_name_to_id={} ## grp_name : [grp_id, grp_pub_key, grp_private_key]

if keyfile == None:
    pub_key, priv_key = rsa.newkeys(512)
    while (True):
        uname = input("Enter username: ")
        req = create_registering_req(uname, pub_key, priv_key)
        client_sock.sendall(req.encode("utf-8"))

        resp = json.loads(client_sock.recv(1024).decode())

        print(resp["msg"])
        if (resp["hdr"][:5] == "error"):
            continue
        elif (resp["hdr"] == "registered"):
            break
    keyfile = open("local.key", 'w')
    keyfile.write(uname + ' ' + pub_key_to_str(pub_key) + ' ' + priv_key_to_str(priv_key))
    keyfile.close()
else:
    uname, pub_key, priv_key = keyfile.read().split()
    pub_key = str_to_pub_key(pub_key)
    priv_key = str_to_priv_key(priv_key)
    req = create_onboarding_req(uname, pub_key, priv_key)
    client_sock.sendall(req.encode("utf-8"))

    resp = json.loads(client_sock.recv(1024).decode())

    print(resp["msg"])

var = [None, False, False] # recip_pub_key, pub_key_set, incorrect_uname
grp_registering_info = [None,False] # Group_id, is Group id set

def listen(ls):
    while(True):
        data = client_sock.recv(1024).decode('utf-8')
        req = json.loads(data)

        if req["hdr"] == "pub_key":
            ls[0] = str_to_pub_key(req["msg"])
            ls[1] = True
            ls[2] = False

        elif req["hdr"] == "group_id":
            grp_registering_info[0] = req["msg"]
            grp_registering_info[1] = True 

        elif req["hdr"][:11] == "group_added":
            grp_id = req["hdr"].split(':')[1]
            admin_id = req["hdr"].split(":")[2]
            admin_pub_key = req["hdr"].split(':')[3]
            sent_data = json.dumps({ "hdr":'<' + group_id + uname, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })
            msg = decrypt_e2e_req(sent_data, priv_key, admin_pub_key)
            p = msg.find(':')
            grp_name = msg[:p]
            grp_pub_key,grp_priv_key = msg[p+1:].split(' ')

            grp_info = [grp_id,grp_pub_key, grp_priv_key]
            cursor.execute("INSERT INTO group_name_id(group_id, group_name, group_pub_key, group_priv_key) VALUES('%s', '%s', '%s', '%s')" %(grp_info[0], grp_name, grp_info[1], grp_info[2]))
            print()
            print("You have been added to " + grp_name + " by "+admin_id)
            print()

        elif req["hdr"] == "error":
            ls[1] = True
            ls[2] = True
        elif req["hdr"][0]=='>':
            sndr_uname, sndr_pub_key = req["hdr"][1:].split(':')
            sndr_pub_key = str_to_pub_key(sndr_pub_key)
            sent_data = json.dumps({ "hdr":'>' + uname, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })
            msg = decrypt_e2e_req(sent_data, priv_key, sndr_pub_key)

            print()
            print(f"Received from {sndr_uname}:")            
            print(strftime("%a, %d %b %Y %H:%M:%S", localtime(float(msg["time"]))))
            print()
            print("\t" + msg["msg"])
            print()

        # grp msg 
        elif req["hdr"][0] == '<':
            x = req["hdr"][1:]
            group_id = x.split(':')[0]
            sender_id = x.split(':')[1]
            sender_pub_key = x.split(':')[2]
            sent_data = json.dumps({ "hdr":'<' + group_id, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })
            a=cursor.execute("SELECT group_name_id.group_priv_key FROM group_name_id WHERE group_name_id.group_id = '%s'" %(group_id)).fetchall()
            msg = decrypt_e2e_req(sent_data,a[0][0],sender_pub_key)

            print()
            print(f"Received on from {sender_id}:")            
            print(strftime("%a, %d %b %Y %H:%M:%S", localtime(float(msg["time"]))))
            print()
            print("\t" + msg["msg"])
            print()
            TODO


t1 = threading.Thread(target=listen, args=(var,))
t1.daemon = True
t1.start()

try:
    while True:
        x = input()

        # Grp_messaging
        if x[0]==':':
            x = x[1:]
            u = x.find(':')
            grp_name=x[0:u]
            a=cursor.execute("SELECT group_name_id.group_id, group_name_id.group_pub_key, group_name_id.group_priv_key FROM group_name_id WHERE group_name_id.group_name ='%s'" %(grp_name)).fetchall()
            grp_id = a[0][0]
            grp_pub_key = a[0][1]
            grp_priv_key = a[0][2]
            msg = x[u+1:]
            req = { "hdr":"<"+grp_id, "msg":msg, "time": str(time())}
            enc_req = encrypt_e2e_req(req, grp_pub_key, priv_key)
            client_sock.sendall(enc_req.encode("utf-8"))

        elif x[0]=='$':
            # Adding people in the group 
            if ':' in x:
                x = x[1:]
                u = x.find(':')
                grp_name=x[0:u]
                a=cursor.execute("SELECT group_name_id.group_id, group_name_id.group_pub_key, group_name_id.group_priv_key FROM group_name_id WHERE group_name_id.group_name = '%s'" %(grp_name)).fetchall()
                grp_id = a[0][0]
                grp_pub_key = a[0][1]
                grp_priv_key = a[0][2]
                recip_uname = x[u+1:]

                pub_key_req = json.dumps({ "hdr":"pub_key", "msg":recip_uname })
                client_sock.sendall(pub_key_req.encode("utf-8"))

                while (not var[1]):
                    continue
                var[1] = False

                if var[2]:
                    print(f"User {recip_uname} not registered")
                    var[2] = False
                    continue

                msg=grp_name+":"+grp_pub_key+" "+grp_priv_key

                req = { "hdr":"<"+grp_id+":"+recip_uname, "msg":msg, "time": str(time())}
                req = json.dumps(req)
                enc_req = encrypt_e2e_req(req, var[0], priv_key)
                client_sock.sendall(enc_req.encode("utf-8"))
                print()
                print("Added "+ recip_uname +" to the group "+ grp_name)
                print()

            else :
                #Creating new group
                grp_name = x[1:]

                grp_pub_key, grp_priv_key = rsa.newkeys(512)
 
                # May need to change encyrption here
                msg = ""
                req = { "hdr":"grp_registering", "msg":msg, "time": str(time())}
                enc_req = encrypt_e2e_req(req, grp_pub_key, grp_priv_key)
                client_sock.sendall(enc_req.encode("utf-8"))

                while (not grp_registering_info[1]):
                    continue
                grp_registering_info[1] = False

                grp_info = [grp_registering_info[0],grp_pub_key, grp_priv_key]
                cursor.execute("INSERT INTO group_name_id(group_id, group_name, group_pub_key, group_priv_key) VALUES('%s', '%s', '%s', '%s')" %(grp_info[0], grp_name, grp_info[1], grp_info[2])) 
                print()
                print("Created new group "+ grp_name+" with id "+grp_info[0])
                print()               
        else: 
            u = x.find(':')
            recip_uname = x[:u]

            pub_key_req = json.dumps({ "hdr":"pub_key", "msg":recip_uname })
            client_sock.sendall(pub_key_req.encode("utf-8"))

            while (not var[1]):
                continue
            var[1] = False

            if var[2]:
                print(f"User {recip_uname} not registered")
                var[2] = False
                continue

            hdr = '>' + recip_uname

            msg = x[u+1:]
            req = { "hdr":hdr, "msg":msg, "time": str(time())}

            enc_req = encrypt_e2e_req(req, var[0], priv_key)
            client_sock.sendall(enc_req.encode("utf-8"))
except KeyboardInterrupt:
    print("Caught keyboard interrupt, closing")
    client_sock.close()
conn.commit()
conn.close()