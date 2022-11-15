from sys import argv
import socket
import json

if len(argv) < 3:
    print(f"Usage: {argv[0]} <host> <port>")

id = int(argv[3])
rid = int(argv[4])


server_addr = (argv[1], int(argv[2]))

client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_sock.connect(server_addr)

di = {"id":id, "mssg":"Anish","recipient":rid}
msg=json.dumps(di)


#client_sock.sendall(b"Hello networking world\n")

client_sock.sendall(bytes(msg, encoding="utf-8"))
data = client_sock.recv(1024)

print("Recieved:")
while data:
    print(json.loads(data.decode("UTF-8"))["mssg"])
    data=client_sock.recv(1024)

client_sock.close()
