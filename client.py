from sys import argv
import socket
import json
import threading
import rsa
import sqlite3
from time import time, strftime, localtime

from request import *

if len(argv) != 3:
    print(f"Usage: {argv[0]} <server ip> <server port>")
    exit(-1)

server_addr = (argv[1], int(argv[2]))

dbfile = True
try:
    f = open("fastchatclient.db", 'r')
    f.close()
except:
    dbfile = False

client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_sock.connect(server_addr)

uname, pub_key, priv_key = None, None, None

conn = sqlite3.connect('fastchatclient.db', check_same_thread=False)
cursor = conn.cursor()

if not dbfile:
    pub_key, priv_key = rsa.newkeys(512)

    while (True):
        uname = input("Enter username: ")
        if (len(uname) == 0):
            continue
        req = create_registering_req(uname, time(), pub_key, priv_key)
        client_sock.sendall(req.encode("utf-8"))

        resp = json.loads(client_sock.recv(1024).decode())

        print(resp["msg"])
        if (resp["hdr"][:5] == "error"):
            continue
        elif (resp["hdr"] == "registered"):
            break

    cursor.execute("CREATE TABLE group_name_keys (group_id INTEGER NOT NULL PRIMARY KEY, group_name TEXT NOT NULL, group_pub_key TEXT NOT NULL, group_priv_key TEXT NOT NULL)")

    cursor.execute("INSERT INTO group_name_keys (group_id, group_name, group_pub_key, group_priv_key) VALUES ('%s', '%s', '%s', '%s')" % (0, uname, pub_key_to_str(pub_key), priv_key_to_str(priv_key)))

else:
    uname, pub_key, priv_key = cursor.execute("SELECT group_name, group_pub_key, group_priv_key FROM group_name_keys WHERE group_id=0").fetchone()

    pub_key = str_to_pub_key(pub_key)
    priv_key = str_to_priv_key(priv_key)

    req = create_onboarding_req(uname, time(), pub_key, priv_key)
    client_sock.sendall(req.encode("utf-8"))

    resp = json.loads(client_sock.recv(1024).decode())

    print(resp["msg"])

pub_key_info = [None, False, False] # recip_pub_key, pub_key_set, incorrect_uname
grp_registering_info = [None, False] # Group_id, is Group id set

def listen():
    input_buffer = ""
    while(True):
        n = 0
        i = 0
        
        def process_data(data):
            req = json.loads(data)

            if req["hdr"] == "pub_key":
                pub_key_info[0] = str_to_pub_key(req["msg"])
                pub_key_info[1] = True
                pub_key_info[2] = False

            elif req["hdr"] == "group_id":
                grp_registering_info[0] = req["msg"]
                grp_registering_info[1] = True 

            elif req["hdr"][:11] == "<roup_added":
                grp_id = int(req["hdr"].split(':')[1])
                admin_name = req["hdr"].split(":")[2]
                admin_pub_key = str_to_pub_key(req["hdr"].split(':')[3])

                sent_data = json.dumps({ "hdr":'<' + str(grp_id) +':'+ uname, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })

                msg = decrypt_e2e_req(sent_data, priv_key, admin_pub_key)
                
                print(strftime("%a, %d %b %Y %H:%M:%S", localtime(float(msg["time"]))))
                
                msg = msg["msg"]

                p = msg.find(':')
                grp_name = msg[:p]
                grp_pub_key,grp_priv_key = msg[p + 1:].split(' ')

                cursor.execute("INSERT INTO group_name_keys(group_id, group_name, group_pub_key, group_priv_key) VALUES('%d', '%s', '%s', '%s')" % (grp_id, grp_name, grp_pub_key, grp_priv_key))
                print("You have been added to " + grp_name + " by " + admin_name)
                print()

            elif req["hdr"] == "error":
                pub_key_info[1] = True
                pub_key_info[2] = True

            elif req["hdr"][0]=='>':
                sndr_uname, sndr_pub_key = req["hdr"][1:].split(':')
                sndr_pub_key = str_to_pub_key(sndr_pub_key)
                sent_data = json.dumps({ "hdr":'>' + uname, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })
                msg = decrypt_e2e_req(sent_data, priv_key, sndr_pub_key)

                print()
                print(strftime("%a, %d %b %Y %H:%M:%S", localtime(float(msg["time"]))))
                print(f"Received from {sndr_uname}:")            
                print()
                print("\t" + msg["msg"])
                print()

            # grp msg 
            elif req["hdr"][0] == '<':
                x = req["hdr"][1:]
                group_id = int(x.split(':')[0])
                sender_id = x.split(':')[1]
                sender_pub_key = x.split(':')[2]
                sent_data = json.dumps({ "hdr":'<' + str(group_id), "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })
                a = cursor.execute("SELECT group_priv_key, group_name FROM group_name_keys WHERE group_id = '%d'" % (group_id)).fetchone()
                msg = decrypt_e2e_req(sent_data,str_to_priv_key(a[0]),str_to_pub_key(sender_pub_key))
                grp_name = a[1]
                
                print(strftime("\n%a, %d %b %Y %H:%M:%S", localtime(float(msg["time"]))))
                print(f"Received on {grp_name} from {sender_id}:")
                print("\n\t" + msg["msg"] + '\n')

        while i != len(input_buffer):
            if input_buffer[i] == '}' and n%2 == 0:
                data = input_buffer[:i + 1]
                input_buffer = input_buffer[i + 1:]
                i = 0
                process_data(data)
                continue
            if input_buffer[i] == '"' and input_buffer[i - 1] != '\\':
                n += 1
            i += 1
        input_buffer += client_sock.recv(24).decode("utf-8")


t1 = threading.Thread(target=listen)
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
            a=cursor.execute("SELECT group_id, group_pub_key, group_priv_key FROM group_name_keys WHERE group_name ='%s'" % (grp_name)).fetchall()
            grp_id = a[0][0]
            grp_pub_key = str_to_pub_key(a[0][1])
            grp_priv_key = str_to_priv_key(a[0][2])
            msg = x[u + 1:]
            req = { "hdr":"<" + str(grp_id), "msg":msg, "time": str(time())}
            enc_req = encrypt_e2e_req(req, grp_pub_key, priv_key)
            client_sock.sendall(enc_req.encode("utf-8"))

        elif x[0]=='$':
            # Adding people in the group 
            if ':' in x:
                x = x[1:]
                u = x.find(':')
                grp_name=x[0:u]
                a=cursor.execute("SELECT group_id, group_pub_key, group_priv_key FROM group_name_keys WHERE group_name = '%s'" % (grp_name)).fetchall()
                grp_id = a[0][0]
                grp_pub_key = a[0][1]
                grp_priv_key = a[0][2]
                recip_uname = x[u + 1:]

                pub_key_req = json.dumps({ "hdr":"pub_key", "msg":recip_uname, "time": str(time()) })
                client_sock.sendall(pub_key_req.encode("utf-8"))

                while (not pub_key_info[1]):
                    continue
                pub_key_info[1] = False

                if pub_key_info[2]:
                    print(f"User {recip_uname} not registered")
                    pub_key_info[2] = False
                    continue

                msg=grp_name + ":" + grp_pub_key + " " + grp_priv_key

                req = { "hdr":"<" + str(grp_id) + ":" + recip_uname, "msg":msg, "time": str(time())}
                enc_req = encrypt_e2e_req(req, pub_key_info[0], priv_key)
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

                grp_id = grp_registering_info[0]

                cursor.execute("INSERT INTO group_name_keys(group_id, group_name, group_pub_key, group_priv_key) VALUES('%s', '%s', '%s', '%s')" % (grp_id, grp_name, pub_key_to_str(grp_pub_key), priv_key_to_str(grp_priv_key)) )
                print()
                print("Created new group "+ grp_name + " with id " + grp_id)
                print()               
        else: 
            u = x.find(':')
            recip_uname = x[:u]

            pub_key_req = json.dumps({ "hdr":"pub_key", "msg":recip_uname })
            client_sock.sendall(pub_key_req.encode("utf-8"))

            while (not pub_key_info[1]):
                continue
            pub_key_info[1] = False

            if pub_key_info[2]:
                print(f"User {recip_uname} not registered")
                pub_key_info[2] = False
                continue

            hdr = '>' + recip_uname

            msg = x[u + 1:]
            req = { "hdr":hdr, "msg":msg, "time": str(time())}

            enc_req = encrypt_e2e_req(req, pub_key_info[0], priv_key)
            client_sock.sendall(enc_req.encode("utf-8"))
except KeyboardInterrupt:
    print("Caught keyboard interrupt, closing")
    client_sock.close()
conn.commit()
conn.close()
