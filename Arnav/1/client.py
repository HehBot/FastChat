from sys import argv
import socket
import selectors
import types

sel = selectors.DefaultSelector()
messages = [b"Message 1 from client.", b"Message 2 from client."]

server_addr = (argv[1], int(argv[2]))

def start_connections(server_addr, num_conns):
    for conn_id in range(1, num_conns + 1):
        print(f"Starting connection {conn_id} to {server_addr}")
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.setblocking(False)
        client_sock.connect_ex(server_addr)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        data = types.SimpleNamespace(
            conn_id=conn_id,
            msg_total=sum(len(m) for m in messages),
            recv_total=0,
            messages=messages.copy(),
            outb=b""
        )
        sel.register(fileobj=client_sock, events=events, data=data)

def service_connection(key, event):
    client_sock = key.fileobj
    data = key.data
    if event & selectors.EVENT_READ:
        recv_data = client_sock.recv(1024)
        if recv_data:
            print(f"Recieved {recv_data!r} from connection {data.conn_id}")
            data.recv_total += len(recv_data)
        if not recv_data or data.recv_total == data.msg_total:
            print(f"Closing connection {data.conn_id}")
            sel.unregister(client_sock)
            client_sock.close()
    if event & selectors.EVENT_WRITE:
        if not data.outb and data.messages:
            data.outb = data.messages.pop(0)
        if data.outb:
            print(f"Sending {data.outb!r} to connection {data.conn_id}")
            sent = client_sock.send(data.outb)
            data.outb = data.outb[sent:]

start_connections(server_addr, int(argv[3]))

try:
    while True:
        events = sel.select(timeout=None)
        for key, event in events:
            service_connection(key, event)
except KeyboardInterrupt:
        print("Caught keyboard interrupt, exiting")
finally:
    sel.close()
