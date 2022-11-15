from sys import argv
import socket
import selectors
import types
import json

import rsa
from request import verify_onboarding_req, pubkey_to_id, id_to_pubkey

sel = selectors.DefaultSelector()

server_addr = (argv[1], int(argv[2]))
conn_accepting_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conn_accepting_sock.bind(server_addr)
conn_accepting_sock.listen()
print(f"Listening on {server_addr} as connection accepter of flag server")
conn_accepting_sock.setblocking(False)
sel.register(fileobj=conn_accepting_sock, events=selectors.EVENT_READ, data=None)  # as we only want to read from |conn_accepting_sock|


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

def accept_wrapper(sock):
    client_sock, client_addr = sock.accept()
    print(f"Accepted connection from client {client_addr}")
    
    onboarding = client_sock.recv(1024).decode()
    if (not verify_onboarding_req(onboarding)):
        sel.unregister(client_sock)
        client_sock.close()

    onboarding = json.loads(onboarding)
    cl_id = onboarding["msg"]
    
    data = types.SimpleNamespace(addr=client_addr, inb=b"", outb=b"", cl_id=cl_id)
    events = selectors.EVENT_READ | selectors.EVENT_WRITE

    if cl_id not in total_data.keys():    
        total_data[cl_id] = []
    
    sel.register(fileobj=client_sock, events=events, data=data)


def service_connection(key, event):
    client_sock = key.fileobj
    data = key.data
    if event & selectors.EVENT_READ:
        recv_data = client_sock.recv(1024).decode()
        if recv_data:
            recip_id = json.loads(recv_data)['hdr'].split('>')[1]
            if recip_id in total_data.keys():
                total_data[recip_id].append(recv_data)
            print()
            print("Sending " + recv_data + " to " + recip_id)
            #data.inb += recv_data
        else:
            print(f"Closing connection to {data.addr}")
            sel.unregister(client_sock)
            client_sock.close()
        
    if event & selectors.EVENT_WRITE:
        if len(total_data[data.cl_id])>0:
            for i in total_data[data.cl_id]:
                print(f"Sent to {data.cl_id}")
                client_sock.send(i.encode())
            total_data[data.cl_id] = []
        

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
