from sys import argv
import socket
import selectors
import types

sel = selectors.DefaultSelector()

server_addr = (argv[1], int(argv[2]))
conn_accepting_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conn_accepting_sock.bind(server_addr)
conn_accepting_sock.listen()
print(f"Listening on {server_addr}")
conn_accepting_sock.setblocking(False)
sel.register(fileobj=conn_accepting_sock, events=selectors.EVENT_READ, data=None)  # as we only want to read from |conn_accepting_sock|

def accept_wrapper(sock):
    client_sock, client_addr = sock.accept()
    print(f"Accepted connection from {client_addr}")
    client_sock.setblocking(False)
    data = types.SimpleNamespace(addr=client_addr, inb=b"", outb=b"")
    events = selectors.EVENT_READ | selectors.EVENT_WRITE
    sel.register(fileobj=client_sock, events=events, data=data)

def service_connection(key, event):
    client_sock = key.fileobj
    data = key.data
    if event & selectors.EVENT_READ:
        recv_data = client_sock.recv(1024)
        if recv_data:
            data.outb += recv_data
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