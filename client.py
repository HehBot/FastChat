from sys import argv
import socket
import json
import threading
import rsa
from time import time

from request import *

if len(argv) < 3:
    print(f"Usage: {argv[0]} <server ip> <server port>")
server_addr = (argv[1], int(argv[2]))

pub_key, priv_key = rsa.newkeys(512)
self_id = pubkey_to_id(pub_key)
print(f"Your id: {self_id}")

client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_sock.connect(server_addr)
client_sock.sendall(create_onboarding_req(pub_key, priv_key).encode())

def listen():
    while(True):
        data = client_sock.recv(1024).decode('utf-8')
        enc_msg = data#""
    #    while data:
    #        string += data.decode('utf-8')
    #        print(string)
    #        data = client_sock.recv(1024)
        y = json.loads(enc_msg)
        pub_key = id_to_pubkey(y["hdr"].split('>')[0])
        msg = decrypt_e2e_req(enc_msg, priv_key, pub_key)
        print()
        print(f"Recieved from {y['hdr'].split('>')[0]} at {msg['time']}:")
        print()
        print("\t" + msg["msg"])

t1 = threading.Thread(target=listen)
t1.daemon = True
t1.start()

try:
    while True:
        x = input()

        u = x.find(':')
        recip_id = x[0:u]
        recip_pub_key = id_to_pubkey(recip_id)

        hdr = self_id + ">" + recip_id

        msg = x[u+1:]
        req = { "hdr":hdr, "msg":msg, "time": str(time())}

        enc_req = encrypt_e2e_req(req, recip_pub_key, priv_key)
        client_sock.sendall(enc_req.encode("utf-8"))
except KeyboardInterrupt:
    print("Caught keyboard interrupt, closing")
    client_sock.close()
