from sys import argv
import socket
import json
import threading
import rsa
from time import time, strftime, localtime

from request import *

if len(argv) < 3:
    print(f"Usage: {argv[0]} <server ip> <server port>")
server_addr = (argv[1], int(argv[2]))

keyfile = None
try:
    keyfile = open("local.key", 'r')
except:
    keyfile = None

client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_sock.connect(server_addr)

uname, pub_key, priv_key = None, None, None

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

def listen(ls):
    while(True):
        data = client_sock.recv(1024).decode('utf-8')
        req = json.loads(data)

        if req["hdr"] == "pub_key":
            ls[0] = str_to_pub_key(req["msg"])
            ls[1] = True
            ls[2] = False
        elif req["hdr"] == "error":
            ls[1] = True
            ls[2] = True
        else:
            sndr_uname, sndr_pub_key = req["hdr"].split(':')
            sndr_pub_key = str_to_pub_key(sndr_pub_key)
            sent_data = json.dumps({ "hdr":'>' + uname, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })
            msg = decrypt_e2e_req(sent_data, priv_key, sndr_pub_key)
            print()
            print(f"Recieved from {sndr_uname}:")            
            print(strftime("%a, %d %b %Y %H:%M:%S", localtime(float(msg["time"]))))
            print()
            print("\t" + msg["msg"])
            print()

t1 = threading.Thread(target=listen, args=(var,))
t1.daemon = True
t1.start()

try:
    while True:
        x = input()

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
