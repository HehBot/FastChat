import json
import socket 
import sqlite3
from rsa import newkeys
import sys
sys.path.append('../')
from request import *
from time import time, strftime, localtime

class Client:
    def __init__(self, dbfile:bool, server_addr:tuple):
        self.pub_key_info = [None, False, False] # recip_pub_key, pub_key_set, incorrect_uname
        self.grp_registering_info = [None, False] # Group_id, is Group id set

        self.client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # The socket

        self.conn = sqlite3.connect('fastchatclient.db', check_same_thread=False)
        self.cursor = self.conn.cursor() # Connecting to sqlite3

        if not dbfile:
            self.uname, self.pub_key, self.priv_key = self.register(server_addr)
        else :
            self.uname, self.pub_key, self.priv_key = self.onboard(server_addr)
    def bigsendall(self, bytedata):
        while len(bytedata) > 0:
            transmitted = self.client_sock.send(bytedata)
            bytedata = bytedata[transmitted:]
    def destroy(self):
        self.client_sock.close()
        self.conn.commit()
        self.cursor.close()
    def register(self, server_addr):
        pub_key, priv_key = newkeys(512)

        while (True):
            uname = input("Enter username: ")
            if (len(uname) == 0):
                continue
            if ':' in uname:
                print("Username may not contain ':'")
                continue
            req = create_registering_req(uname, time(), pub_key, priv_key)

            initial_client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            initial_client_sock.connect(server_addr)
            initial_client_sock.sendall(json.dumps( {"hdr":"client"} ).encode("utf-8"))

            new_addr = initial_client_sock.recv(4096).decode("utf-8").split(':')
            initial_client_sock.close()

            new_addr = (new_addr[0], int(new_addr[1]))
            self.client_sock.connect(new_addr)
            self.client_sock.sendall(req.encode("utf-8"))

            resp = json.loads(self.client_sock.recv(4096).decode("utf-8"))

            print(resp["msg"])
            if (resp["hdr"][:5] == "error"):
                continue
            elif (resp["hdr"] == "registered"):
                break

        self.cursor.execute("CREATE TABLE group_name_keys (group_id INTEGER NOT NULL PRIMARY KEY, group_name TEXT NOT NULL, group_pub_key TEXT NOT NULL, group_priv_key TEXT NOT NULL)")
        self.cursor.execute("INSERT INTO group_name_keys (group_id, group_name, group_pub_key, group_priv_key) VALUES (%d, '%s', '%s', '%s')" % (0, uname, pub_key_to_str(pub_key), priv_key_to_str(priv_key)))
        self.conn.commit()
        print("""-----------------------------------------
<Ctrl+C>
    Exit
!
    Attach file
!!
    Detach file
A:xyz
    "xyz" to user A (with file if attached)
:G:xyz
    "xyz" to group G (with file if attached)
$G
    Create group G with you as admin
$G:A
    Add user A to group G (if you are its admin)
$G::A
    Remove user A from group G (if you are its admin)
$G1::
    Leave group G1 (if you are not its admin)
-----------------------------------------""")
        return uname, pub_key, priv_key
    def onboard(self, server_addr):
        uname, pub_key, priv_key = self.cursor.execute("SELECT group_name, group_pub_key, group_priv_key FROM group_name_keys WHERE group_id=0").fetchone()

        pub_key = str_to_pub_key(pub_key)
        priv_key = str_to_priv_key(priv_key)

        req = create_onboarding_req(uname, time(), pub_key, priv_key)
        
        initial_client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        initial_client_sock.connect(server_addr)
        initial_client_sock.sendall(json.dumps( {"hdr":"client"} ).encode("utf-8"))

        new_addr = initial_client_sock.recv(4096).decode("utf-8").split(':')
        initial_client_sock.close()

        new_addr = (new_addr[0], int(new_addr[1]))
        self.client_sock.connect(new_addr)
        self.client_sock.sendall(req.encode("utf-8"))
        
        resp = json.loads(self.client_sock.recv(4096).decode("utf-8"))

        print(resp["msg"], end=' ')
        curr_time = time()
        print(strftime(f"%a, %d %b %Y %H:%M:%S.{str(curr_time - int(curr_time))[2:6]}", localtime(curr_time)))
        return uname, pub_key, priv_key 

    def process_data(self, data):
        req = json.loads(data)

        if req["hdr"][:5] == "error":
            code = int(req["hdr"][6:])
            if code == 4:
                self.pub_key_info[1] = True
                self.pub_key_info[2] = True
            elif code == 5:
                print("You (admin) may not leave the group")
        
        elif req["hdr"] == "pub_key":
            self.pub_key_info[0] = str_to_pub_key(req["msg"])
            self.pub_key_info[1] = True
            self.pub_key_info[2] = False

        elif req["hdr"] == "group_id":
            self.grp_registering_info[0] = int(req["msg"])
            self.grp_registering_info[1] = True

        elif req["hdr"][:13] == "group_removed":
            group_id = int(req["hdr"].split(':')[1])
            group_name = self.cursor.execute("SELECT group_name FROM group_name_keys WHERE group_name_keys.group_id=%d"%(group_id)).fetchone()
            if group_name != None:
                self.cursor.execute("DELETE FROM group_name_keys WHERE group_id=%d" % (group_id))
                print(f"You were removed from {group_name[0]}(id {group_id})")

        elif req["hdr"][:14] == "person_removed":
            _, group_id, person, sndr_pub_key = req["hdr"].split(':')
            sent_data = json.dumps({ "hdr":'<' + str(group_id) + "::" + person, "msg":req["msg"], "aes_key":req["aes_key"], "sign":req["sign"], "time":req["time"] })
            group_name, group_priv_key = self.cursor.execute("SELECT group_name, group_priv_key FROM group_name_keys WHERE group_id=%d" % (int(group_id))).fetchone()
            recv = decrypt_e2e_req(sent_data, str_to_priv_key(group_priv_key), str_to_pub_key(sndr_pub_key))

            if recv != None:
                print(f"{person} was removed from the group {group_name} (id {group_id})")

        elif req["hdr"][:10] == "group_left":
            group_id = int(req["hdr"].split(':')[1])
            group_name = self.cursor.execute("SELECT group_name FROM group_name_keys WHERE group_id=%d"%(group_id)).fetchone()[0]
            self.cursor.execute("DELETE FROM group_name_keys WHERE group_id=%d" % (group_id))
            print(f"You left {group_name} (id {group_id})")

        elif req["hdr"][:11] == "person_left":
            _, group_id, person, sndr_pub_key = req["hdr"].split(':')
            sent_data = json.dumps({ "hdr":'<' + str(group_id) + "::" + person, "msg":req["msg"], "aes_key":req["aes_key"], "sign":req["sign"], "time":req["time"] })
            group_name, group_priv_key = self.cursor.execute("SELECT group_name, group_priv_key FROM group_name_keys WHERE group_id=%d" % (int(group_id))).fetchone()
            recv = decrypt_e2e_req(sent_data, str_to_priv_key(group_priv_key), str_to_pub_key(sndr_pub_key))

            if recv != None:
                print(f"{person} left {group_name} (id {group_id})")

        elif req["hdr"][:11] == "group_added":
            group_id = int(req["hdr"].split(':')[1])
            admin_name = req["hdr"].split(":")[2]
            admin_pub_key = str_to_pub_key(req["hdr"].split(':')[3])

            sent_data = json.dumps({ "hdr":'<' + str(group_id) +':'+ self.uname, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })

            recv = decrypt_e2e_req(sent_data, self.priv_key, admin_pub_key)

            msg = recv["msg"]

            p = msg.find(':')
            group_name = msg[:p]
            group_pub_key, group_priv_key = msg[p + 1:].split(' ')

            self.cursor.execute("INSERT INTO group_name_keys(group_id, group_name, group_pub_key, group_priv_key) VALUES(%d, '%s', '%s', '%s')" % (group_id, group_name, group_pub_key, group_priv_key))

            sndr_time = float(recv["time"])
            curr_time = time()
            print(strftime(f"\n%a, %d %b %Y %H:%M:%S.{str(curr_time - int(curr_time))[2:6]}", localtime(curr_time)))
            print(strftime(f"Sent at %a, %d %b %Y %H:%M:%S.{str(sndr_time - int(sndr_time))[2:6]}", localtime(sndr_time)))
            print(f"{admin_name} added you to {group_name} (id {group_id})\n")

        elif req["hdr"][:12] == "person_added":
            _, group_id, person, sndr_pub_key = req["hdr"].split(':')

            sent_data_hdr = '<' + str(group_id) + ":" + person
            
            group_name = self.cursor.execute("SELECT group_name, group_priv_key FROM group_name_keys WHERE group_id=%d" % (int(group_id))).fetchone()[0]
           
            valid = True

            try:
                rsa.verify((sent_data_hdr + req["msg"] + req["aes_key"] + req["time"]).encode("utf-8"), base64.b64decode(req["sign"]), str_to_pub_key(sndr_pub_key))
            except rsa.pkcs1.VerificationError:
                valid = False
                return

            if valid:
                print(f"{person} was added to {group_name} (id {group_id})")

        # Personal message
        elif req["hdr"][0] == '>':
            sndr_uname, sndr_pub_key = req["hdr"][1:].split(':')
            sndr_pub_key = str_to_pub_key(sndr_pub_key)

            sent_data = json.dumps({ "hdr":'>' + self.uname, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })

            msg = decrypt_e2e_req(sent_data, self.priv_key, sndr_pub_key)

            sndr_time = float(msg["time"])
            curr_time = time()
            print(strftime(f"\n%a, %d %b %Y %H:%M:%S.{str(curr_time - int(curr_time))[2:6]}", localtime(curr_time)))
            print(strftime(f"Sent at %a, %d %b %Y %H:%M:%S.{str(sndr_time - int(sndr_time))[2:6]}", localtime(sndr_time)))
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

            group_priv_key, group_name = self.cursor.execute("SELECT group_priv_key, group_name FROM group_name_keys WHERE group_id = %d" % (group_id)).fetchone()

            msg = decrypt_e2e_req(sent_data, str_to_priv_key(group_priv_key), str_to_pub_key(sndr_pub_key))
            
            sndr_time = float(msg["time"])
            curr_time = time()
            print(strftime(f"\n%a, %d %b %Y %H:%M:%S.{str(curr_time - int(curr_time))[2:6]}", localtime(curr_time)))
            print(strftime(f"Sent at %a, %d %b %Y %H:%M:%S.{str(sndr_time - int(sndr_time))[2:6]}", localtime(sndr_time)))
            print(f"Received on {group_name} (id {group_id}) from {sndr_uname}:")
            print("\n\t" + msg["msg"])
            
            if "file" in msg.keys():
                file_name, file = msg["file"].split()
                file_name = msg["time"] + '_' + base64.b64decode(file_name.encode("utf-8")).decode("utf-8")
                print(f"\tFile '{file_name}' (saved)")
                file = base64.b64decode(file.encode("utf-8"))
                f = open(file_name, "wb")
                f.write(file)
                f.close()

    def send_group_message(self, x, attached_file_name, file):
        u = x.find(':')
        group_name = x[:u]
        group_info = self.cursor.execute("SELECT group_id, group_pub_key, group_priv_key FROM group_name_keys WHERE group_name ='%s'" % (group_name)).fetchall()

        if len(group_info) != 0:
            if len(group_info) == 1:
                group_info = group_info[0]
            else:
                while len(group_info) > 1:
                    ids = [x[0] for x in group_info]
                    print("Select group_id from " + str(ids))
                    i = int(input())
                    if i in ids:
                        group_info = group_info[ids.index(i)]
                        break
                    else:
                        continue
            
            group_id, group_pub_key, group_priv_key = group_info
            
            group_pub_key = str_to_pub_key(group_pub_key)
            group_priv_key = str_to_priv_key(group_priv_key)

            msg = x[u + 1:]
            req = { "hdr":"<" + str(group_id), "msg":msg, "time": str(time())}

            if file != "":
                req["file"] = base64.b64encode(attached_file_name.encode("utf-8")).decode("utf-8") + ' ' + file

            enc_req = encrypt_e2e_req(req, group_pub_key, self.priv_key)
            self.bigsendall(enc_req.encode("utf-8"))
        else:
            print(f"You are not a member of group {group_name}")

    def remove_person(self, x):
        u = x.find(':')
        group_name = x[:u]
        
        group_info = self.cursor.execute("SELECT group_id, group_pub_key, group_priv_key FROM group_name_keys WHERE group_name = '%s'" % (group_name)).fetchall()

        if group_info != None:
            if len(group_info) == 1:
                group_info = group_info[0]
            else:
                while len(group_info) > 1:
                    ids = [x[0] for x in group_info]
                    print("Select group_id from " + str(ids))
                    i = int(input())
                    if i in ids:
                        group_info = group_info[ids.index(i)]
                        break
                    else:
                        continue

            group_id, group_pub_key, group_priv_key = group_info

            if len(x) > u + 2:
                recip_uname = x[u + 2:]
            else:
                recip_uname = self.uname
            req = { "hdr":"<" + str(group_id) + "::" + recip_uname, "msg":'', "time": str(time()) }
            enc_req = encrypt_e2e_req(req, str_to_pub_key(group_pub_key), self.priv_key)
            self.client_sock.sendall(enc_req.encode("utf-8"))
        else:
            print(f"You are not a member of group {group_name}")
    def add_to_group(self, x):
        u = x.find(':')
        group_name = x[:u]

        group_info = self.cursor.execute("SELECT group_id, group_pub_key, group_priv_key FROM group_name_keys WHERE group_name = '%s'" % (group_name)).fetchall()

        if group_info != None:
            if len(group_info) == 1:
                group_info = group_info[0]
            else:
                while len(group_info) > 1:
                    ids = [x[0] for x in group_info]
                    print("Select group_id from " + str(ids))
                    i = int(input())
                    if i in ids:
                        group_info = group_info[ids.index(i)]
                        break
                    else:
                        continue
            
            group_id, group_pub_key, group_priv_key = group_info
            recip_uname = x[u + 1:]

            pub_key_req = json.dumps({ "hdr":"pub_key", "msg":recip_uname, "time": str(time()) })
            self.client_sock.sendall(pub_key_req.encode("utf-8"))

            while not self.pub_key_info[1]:
                continue
            self.pub_key_info[1] = False

            if self.pub_key_info[2]:
                print(f"User {recip_uname} not registered")
                self.pub_key_info[2] = False
                return

            msg = group_name + ":" + group_pub_key + " " + group_priv_key
            req = { "hdr":"<" + str(group_id) + ":" + recip_uname, "msg":msg, "time": str(time())}

            enc_req = encrypt_e2e_req(req, self.pub_key_info[0], self.priv_key)
            self.client_sock.sendall(enc_req.encode("utf-8"))
        else:
            print(f"You are not a member of group {group_name}")
    def create_group(self, group_name):
        if ':' in group_name:
            print("Group name may not contain ':'")
        else:
            group_pub_key, group_priv_key = newkeys(512)

            msg = ""
            req = { "hdr":"grp_registering", "msg":msg, "time": str(time())}
            enc_req = encrypt_e2e_req(req, group_pub_key, group_priv_key)
            self.client_sock.sendall(enc_req.encode("utf-8"))

            while (not self.grp_registering_info[1]):
                continue
            self.grp_registering_info[1] = False
            group_id = self.grp_registering_info[0]

            self.cursor.execute("INSERT INTO group_name_keys(group_id, group_name, group_pub_key, group_priv_key) VALUES(%d, '%s', '%s', '%s')" % (group_id, group_name, pub_key_to_str(group_pub_key), priv_key_to_str(group_priv_key)) )

            print(f"\nCreated new group {group_name} with id {group_id}\n")
    def send_personal_message(self, x, attached_file_name, file):
        u = x.find(':')
        recip_uname = x[:u]

        pub_key_req = json.dumps({ "hdr":"pub_key", "msg":recip_uname })
        self.client_sock.sendall(pub_key_req.encode("utf-8"))

        while (not self.pub_key_info[1]):
            continue
        self.pub_key_info[1] = False

        if self.pub_key_info[2]:
            print(f"User {recip_uname} not registered")
            self.pub_key_info[2] = False
            return

        hdr = '>' + recip_uname

        msg = x[u + 1:]
        req = { "hdr":hdr, "msg":msg, "time": str(time())}

        if file != "":
            req["file"] = base64.b64encode(attached_file_name.encode("utf-8")).decode("utf-8") + ' ' + file

        enc_req = encrypt_e2e_req(req, self.pub_key_info[0], self.priv_key)
        self.bigsendall(enc_req.encode("utf-8"))
