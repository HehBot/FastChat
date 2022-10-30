from sys import argv
import socket

if len(argv) != 3:
    print(f"Usage: {argv[0]} <host> <port>")

server_addr = (argv[1], int(argv[2]))

client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_sock.connect(server_addr)

client_sock.sendall(b"Hello networking world\n")
data = client_sock.recv(1024)

print("\nRecieved:")
print(data.decode("UTF-8"))

client_sock.close()
