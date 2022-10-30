from sys import argv
import socket

if len(argv) != 3:
    print(f"Usage: {argv[0]} <host> <port>")
server_addr = (argv[1], int(argv[2]))

conn_accepting_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conn_accepting_sock.bind(server_addr)
conn_accepting_sock.listen()

client_conn, client_addr = conn_accepting_sock.accept()
print(f"Connected by {client_addr}")
while True:
    data = client_conn.recv(1024)
    if not data:
        break
    client_conn.sendall(data)

client_conn.close()
conn_accepting_sock.close()
