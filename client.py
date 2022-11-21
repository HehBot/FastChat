from sys import argv
import socket
import json
import threading
from rsa import newkeys
import sqlite3
from time import time, strftime, localtime

from request import *
from tkinter.filedialog import askopenfilename

if len(argv) != 3:
    print(f"Usage: {argv[0]} <server ip> <server port>")
    exit(-1)

server_addr = (argv[1], int(argv[2]))

# dbfile stores whether the database file exists or not
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
    pub_key, priv_key = newkeys(512)

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

    def process_data(data):
        req = json.loads(data)

        if req["hdr"] == "pub_key":
            pub_key_info[0] = str_to_pub_key(req["msg"])
            pub_key_info[1] = True
            pub_key_info[2] = False

        elif req["hdr"] == "group_id":
            grp_registering_info[0] = int(req["msg"])
            grp_registering_info[1] = True

        elif req["hdr"][:13] == "group_removed":
            group_id = int(req["hdr"].split(':')[1])
            group_name = cursor.execute("SELECT group_name_keys.group_name FROM group_name_keys WHERE group_name_keys.group_id=%d"%(group_id)).fetchone()[0]
            cursor.execute("DELETE FROM group_name_keys WHERE group_name_keys.group_id=%d"%(group_id))
            print("You have been removed from group "+group_name)

        elif req["hdr"][:14] == "person_removed":
            group_id = req["hdr"].split(':')[1]
            group_name = cursor.execute("SELECT group_name_keys.group_name FROM group_name_keys WHERE group_name_keys.group_id=%d"%(int(group_id))).fetchone()[0]
            recip = req["hdr"].split(':')[2]
            print(recip+" was removed from the group "+group_name)   
        elif req["hdr"][:11] == "group_added":
            group_id = int(req["hdr"].split(':')[1])
            admin_name = req["hdr"].split(":")[2]
            admin_pub_key = str_to_pub_key(req["hdr"].split(':')[3])

            sent_data = json.dumps({ "hdr":'<' + str(group_id) +':'+ uname, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })

            recv = decrypt_e2e_req(sent_data, priv_key, admin_pub_key)

            msg = recv["msg"]
            time = recv["time"]

            p = msg.find(':')
            group_name = msg[:p]
            group_pub_key, group_priv_key = msg[p + 1:].split(' ')

            cursor.execute("INSERT INTO group_name_keys(group_id, group_name, group_pub_key, group_priv_key) VALUES(%d, '%s', '%s', '%s')" % (group_id, group_name, group_pub_key, group_priv_key))

            print(strftime("\n%a, %d %b %Y %H:%M:%S", localtime(float(time))))
            print("You have been added to " + group_name + " by " + admin_name + '\n')

#elif req["hdr"][]

        elif req["hdr"] == "error":
            pub_key_info[1] = True
            pub_key_info[2] = True

        # Personal message
        elif req["hdr"][0] == '>':
            sndr_uname, sndr_pub_key = req["hdr"][1:].split(':')
            sndr_pub_key = str_to_pub_key(sndr_pub_key)

            sent_data = json.dumps({ "hdr":'>' + uname, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })

            msg = decrypt_e2e_req(sent_data, priv_key, sndr_pub_key)

            print(strftime("\n%a, %d %b %Y %H:%M:%S", localtime(float(msg["time"]))))
            print(f"Received from {sndr_uname}:")
            print("\n\t" + msg["msg"])

            if "file" in msg.keys():
                file_name, file = msg["file"].split()
                file_name = msg["time"] + '_' + base64.b64decode(file_name.encode("utf-8")).decode("utf-8")
                print(f"\tFile '{file_name}' (saved)")
                file = base64.b64decode(file.encode("utf-8"))
                f = open(file_name, "wb")
                f.write(file)
                f.close()

        # Group message
        elif req["hdr"][0] == '<':
            x = req["hdr"][1:]

            group_id, sndr_uname, sndr_pub_key = x.split(':')
            group_id = int(group_id)

            sent_data = json.dumps({ "hdr":'<' + str(group_id), "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })

            group_priv_key, group_name = cursor.execute("SELECT group_priv_key, group_name FROM group_name_keys WHERE group_id = %d" % (group_id)).fetchone()

            msg = decrypt_e2e_req(sent_data, str_to_priv_key(group_priv_key), str_to_pub_key(sndr_pub_key))

            print(strftime("\n%a, %d %b %Y %H:%M:%S", localtime(float(msg["time"]))))
            print(f"Received on {group_name} from {sndr_uname}:")
            print("\n\t" + msg["msg"])
            
            if "file" in msg.keys():
                file_name, file = msg["file"].split()
                file_name = msg["time"] + '_' + base64.b64decode(file_name.encode("utf-8")).decode("utf-8")
                print(f"\tFile '{file_name}' (saved)")
                file = base64.b64decode(file.encode("utf-8"))
                f = open(file_name, "wb")
                f.write(file)
                f.close()

    while(True):
        n = 0
        i = 0
        while i != len(input_buffer):
            if input_buffer[i] == '}' and n % 2 == 0:
                data = input_buffer[:i + 1]
                input_buffer = input_buffer[i + 1:]
                n = 0
                i = 0
                process_data(data)
                continue
            if input_buffer[i] == '"' and input_buffer[i - 1] != '\\':
                n += 1
            i += 1
        input_buffer += client_sock.recv(1024).decode("utf-8")


t1 = threading.Thread(target=listen)
t1.daemon = True
t1.start()

"""
!
    Attach file
!!
    Detach file
A:xyz
    "xyz" to user A
:G:xyz
    "xyz" to group G
A::xyz
    "xyz" to user A with attached file
:G::xyz
    "xyz" to group G with attached file
"""

try:
    attached_file_name = ""
    file = ""
    while True:
        if (attached_file_name != ""):
            x = attached_file_name
            if len(x) > 20:
                x = x[:17] + "..."
            print(x + " -> ", end = '')

        x = input()

        # Attach file
        if x == "!":
            attached_file_path = askopenfilename()
            file = base64.b64encode(open(attached_file_path, "rb").read()).decode("utf-8")
            attached_file_name = attached_file_path.split('/')[-1]

        # Detach file
        elif x == "!!":
            attached_file_name = ""
            file = ""
            print("Detached\n")

        # Sending message in the group
        elif x[0] == ':':
            x = x[1:]
            u = x.find(':')
            group_name = x[0:u]
            grp_info = cursor.execute("SELECT group_id, group_pub_key, group_priv_key FROM group_name_keys WHERE group_name ='%s'" % (group_name)).fetchone()
            if grp_info:
                group_id, group_pub_key, group_priv_key = grp_info
                group_pub_key = str_to_pub_key(group_pub_key)
                group_priv_key = str_to_priv_key(group_priv_key)

                msg = x[u + 1:]
                req = { "hdr":"<" + str(group_id), "msg":msg, "time": str(time())}

                if (file != ""):
                    req["file"] = base64.b64encode(attached_file_name.encode("utf-8")).decode("utf-8") + ' ' + file

                enc_req = encrypt_e2e_req(req, group_pub_key, priv_key)
                client_sock.sendall(enc_req.encode("utf-8"))

        # Group operations
        elif x == '':
            continue
        elif x[0]=='$':

            # Removing people from group
            if "::" in x:
                x = x[1:]
                u = x.find(':')
                group_name = x[:u]
                group_id, group_pub_key, group_priv_key = cursor.execute("SELECT group_id, group_pub_key, group_priv_key FROM group_name_keys WHERE group_name = '%s'" % (group_name)).fetchone()
                recip_uname = x[u + 2:]
                msg = ''
                req = { "hdr":"<" + str(group_id) + "::" + recip_uname, "msg":msg, "time": str(time())}
                enc_req = encrypt_e2e_req(req, str_to_pub_key(group_pub_key), priv_key)
                client_sock.sendall(enc_req.encode("utf-8"))

                print("\nRemoved"+ recip_uname +" from the group "+ group_name + '\n')


            # Adding people in the group
            elif ":" in x:
                x = x[1:]
                u = x.find(':')
                group_name = x[:u]
                group_id, group_pub_key, group_priv_key = cursor.execute("SELECT group_id, group_pub_key, group_priv_key FROM group_name_keys WHERE group_name = '%s'" % (group_name)).fetchone()
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

                msg = group_name + ":" + group_pub_key + " " + group_priv_key

                req = { "hdr":"<" + str(group_id) + ":" + recip_uname, "msg":msg, "time": str(time())}

                enc_req = encrypt_e2e_req(req, pub_key_info[0], priv_key)
                client_sock.sendall(enc_req.encode("utf-8"))

                print("\nAdded "+ recip_uname +" to the group "+ group_name + '\n')

            # Creating new group
            else :
                group_name = x[1:]

                group_pub_key, group_priv_key = newkeys(512)

                # May need to change encyrption here
                msg = ""
                req = { "hdr":"grp_registering", "msg":msg, "time": str(time())}
                enc_req = encrypt_e2e_req(req, group_pub_key, group_priv_key)
                client_sock.sendall(enc_req.encode("utf-8"))

                while (not grp_registering_info[1]):
                    continue
                grp_registering_info[1] = False
                group_id = grp_registering_info[0]

                cursor.execute("INSERT INTO group_name_keys(group_id, group_name, group_pub_key, group_priv_key) VALUES(%d, '%s', '%s', '%s')" % (group_id, group_name, pub_key_to_str(group_pub_key), priv_key_to_str(group_priv_key)) )

                print("\nCreated new group "+ group_name + " with id " + str(group_id) + '\n')

        # Personal message
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

            if file != "":
                req["file"] = base64.b64encode(attached_file_name.encode("utf-8")).decode("utf-8") + ' ' + file

            enc_req = encrypt_e2e_req(req, pub_key_info[0], priv_key)
            client_sock.sendall(enc_req.encode("utf-8"))

except KeyboardInterrupt:
    print("Caught keyboard interrupt, closing")
    client_sock.close()
conn.commit()
conn.close()
