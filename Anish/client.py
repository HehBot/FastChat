from sys import argv
import socket
import json
import threading

if len(argv) < 3:
    print(f"Usage: {argv[0]} <host> <port>")

id = int(argv[3])

server_addr = (argv[1], int(argv[2]))

client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_sock.connect(server_addr)

client_sock.sendall(str(id).encode())

def listen():
    data = client_sock.recv(1024)
    print("Recieved:")
    while data:
        print(json.loads(data.decode("UTF-8"))["mssg"])
        data=client_sock.recv(1024)

    client_sock.close()


t1 = threading.Thread(target=listen)

t1.start()


while True:
    x = input()
    u = x.find(':')
    rid = int(x[0:u])
    mssg = x[u+1:]
    di = {"id":id, "mssg":mssg,"recipient":rid}
    msg=json.dumps(di)
    client_sock.sendall(bytes(msg, encoding="utf-8"))



