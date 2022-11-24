from server_temp import Server_temp
import json
import sqlite3

class Server_to_Server(Server_temp):
    def __init__(self, other_server_addr,uname,server_sock,local_cursor,this_server_name,other_servers ):
        Server_temp.__init__(self,uname,server_sock,local_cursor,this_server_name,other_servers)
        self.sock_type="server_sock" 
        self.addr=other_server_addr 
        self.inb=''

    def write(self):
        output_buffer = self.local_cursor.execute(f"SELECT output_buffer FROM local_buffer WHERE uname='{self.uname}'").fetchone()
        if output_buffer != None and output_buffer[0] != '':
            self.local_cursor.execute(f"UPDATE local_buffer SET output_buffer='' WHERE uname='{self.uname}'")
            self.sock.sendall(output_buffer[0].encode("utf-8"))

    def read(self): 
        recv_data = self.sock.recv(1024).decode("utf-8")
        if recv_data == "":
            print(f"Closing connection to {self.addr}")
            self.stop =True
            self.sock.close()
            return

        self.inb += recv_data
        n = 0
        i = 0
        while i != len(self.inb):
            if self.inb[i] == '}' and n % 2 == 0:
                json_string = self.inb[:i + 1]
                self.inb = self.inb[i + 1:]
                n = 0
                i = 0
                self.process_server_data(json_string)
                continue
            if self.inb[i] == '"' and self.inb[i - 1] != '\\':
                n += 1
            i += 1

    def process_server_data(self, json_string):
            print("\nProcessing data recieved from Server : ")
            print(json_string)
            print()
            self.req = json.loads(json_string)
            if self.req["hdr"] == "reg":
                self.reg()
            elif self.req["hdr"] == "onb":
                self.onb()
            elif self.req["hdr"] == "left":\
                self.left()
            else:
                recip_uname = self.req["send_to"]
                self.append_output_buffer(recip_uname, json.dumps(self.req))

    def reg(self):
        new_person = self.req["msg"]
        print("Trying to insert " + new_person)
        self.local_cursor.execute("INSERT INTO local_buffer (uname, output_buffer) VALUES('%s', '')" % (new_person))
        self.local_cursor.execute("INSERT INTO server_map (uname, serv_name) VALUES('%s', '%s')" % (new_person, self.uname))
        print()
        print(f'Added new user {new_person} to server {self.uname}')
        print()

    def onb(self):
        new_person = self.req["msg"]
        self.local_cursor.execute("UPDATE server_map SET serv_name = '%s' WHERE uname = '%s'" % (self.uname, new_person))
        output_buffer = self.local_cursor.execute(f"SELECT output_buffer FROM local_buffer WHERE uname='{new_person}'").fetchone()[0]
        self.local_cursor.execute(f"UPDATE local_buffer SET output_buffer='' WHERE uname='{new_person}'")
        # forward this directly to next server
        self.append_output_buffer(self.uname, output_buffer)
        print()
        print(f'User {new_person} is online on server {self.uname}')
        print()

    def left(self):
        left_person = self.req["msg"]
        self.local_cursor.execute("UPDATE server_map SET serv_name = '%s' WHERE uname = '%s'" % (self.this_server_name, left_person))
        print()
        print(f'User {left_person} went offline from server {self.uname}')
        print()
