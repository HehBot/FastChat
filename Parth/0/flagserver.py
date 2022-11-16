from sys import argv
import socket
import json
from datetime import datetime
import selectors
import types
import json
now="\n"+str(datetime.now())

sel = selectors.DefaultSelector()

server_addr = (argv[1], int(argv[2]))
conn_accepting_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conn_accepting_sock.bind(server_addr)
conn_accepting_sock.listen()
print(f"Listening on {server_addr} as connection accepter of flag server")
conn_accepting_sock.setblocking(False)
sel.register(fileobj=conn_accepting_sock, events=selectors.EVENT_READ, data=None)  # as we only want to read from |conn_accepting_sock|

# Server List
no_servers = int(input("Enter number of other servers"))
for j in range(no_servers):
    ip = input()
    port = int(input())
    other_server_addr = (ip, port)

    other_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    other_server_sock.bind(other_server_addr)
    other_server_sock.listen()
    print(f"Listening on {other_server_addr} as socket for server at {other_server_addr}")
    other_server_sock.setblocking(False)
    data = types.SimpleNamespace(addr=other_server_addr, inb=b"", outb=b"")
    sel.register(fileobj=other_server_sock, events=selectors.EVENT_READ | selectors.EVENT_WRITE, data=data)
# End

# Client to server
client_pub_keys_servers = {12345:4}
#client_addr to public key
client_add_pub_key={}

def accept_wrapper(sock):
    client_sock, client_addr = sock.accept()
    client_add_pub_key[client_addr]=
    print(f"Accepted connection from client {client_addr}")
    client_sock.setblocking(False)
    data = types.SimpleNamespace(addr=client_addr, inb=b"", outb=b"", pub_key=client_add_pub_key[client_addr])
    events = selectors.EVENT_READ | selectors.EVENT_WRITE
    sel.register(fileobj=client_sock, events=events, data=data)


def service_connection(key, event):
    client_sock = key.fileobj
    data = key.data
    if event & selectors.EVENT_READ:
        recv_data = client_sock.recv(1024)
        if recv_data:
            data.inb += recv_data
        else:
            print(f"Closing connection to {data.addr}")
            sel.unregister(client_sock)
            client_sock.close()
    if event & selectors.EVENT_WRITE:
        if data.outb:
            print(f"Echoing {data.outb!r} to {data.addr}")
            sent = client_sock.send(data.outb)
            data.outb = data.outb[sent:]

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

