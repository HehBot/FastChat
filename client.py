import socket
import select
from sys import argv, stdin

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
if len(argv) != 4:
    print("Correct usage: python3 " + argv[0] + " <name> <IP address> <port number>")
    exit(0)

name = str(argv[1])
IP_address = str(argv[2])
Port = int(argv[3])
server.connect((IP_address, Port))

connected = True
server.send(("::INIT " + name).encode('UTF-8'))
while connected:
    sockets_list = [stdin, server]
    read_sockets,write_socket, error_socket = select.select(sockets_list, [], [])
    for socks in read_sockets:
        if socks == server:
            message = socks.recv(2048)
            print(message.decode('UTF-8'))
        else:
            message = input()
            if (message == '!exit'):
                connected = False
            else:
                server.send(message.encode('UTF-8'))
server.close()
