from client import Client
import base64
from listen import listen
from sys import argv
import threading
from tkinter.filedialog import askopenfilename

if len(argv) != 3:
    print(f"Usage: {argv[0]} <server ip> <server port>")
    exit(-1)

server_addr = (argv[1], int(argv[2]))

# dbfile stores whether the database file exists or not
dbfile = True
try:
    f = open("fastchatclient.db", 'r')
    f.close()
except:
    dbfile = False

the_client = Client(dbfile,server_addr)

t1 = threading.Thread(target=listen, args=(the_client,))
t1.daemon = True
t1.start()




try:
    attached_file_name = ""
    file = ""

    while True:
        if (attached_file_name != ""):
            x = attached_file_name
            if len(x) > 20:
                x = x[:17] + "..."
            print(x + " -> ", end = '')

        x = input()

        if x == "!":
            attached_file_path = askopenfilename()
            file = base64.b64encode(open(attached_file_path, "rb").read()).decode("utf-8")
            attached_file_name = attached_file_path.split('/')[-1]

        elif x == "!!":
            attached_file_name = ""
            file = ""
        elif x[0] == ':':
            the_client.send_group_message(x[1:],file)
        elif x == '':
            continue
        elif x[0]=='$':
            if "::" in x:
                the_client.remove_person(x[1:])
            elif ":" in x:
                the_client.add_to_group(x[1:])
            else :
                the_client.create_group(x[1:])
        else:
            the_client.send_personal_message(x,file)
            
except KeyboardInterrupt:
    print("Closing")

