from server_temp import Server_temp
import json
import sqlite3
from time import time, strftime, localtime

class Server_to_Server(Server_temp):
    """Class that abstracts the server to server data

    :param sock_type: The type of socket that we are connecting to
    :type sock_type: Socket
    :param addr: Address of the server we have connected to
    :type addr: Ip:port
    :param inb: Input buffer for this connection
    :type inb: String
    """
    def __init__(self, other_server_addr, uname, server_sock, local_cursor, this_server_name, other_servers ):
        """Class constructor
        """
        Server_temp.__init__(self, uname, server_sock, local_cursor, this_server_name, other_servers)
        self.sock_type = "server_sock" 
        self.addr = other_server_addr 
        self.inb = ''

    def write(self):
        """Function to write to the output buffer of the object
        """
        output_buffer = self.local_cursor.execute(f"SELECT output_buffer FROM local_buffer WHERE uname='{self.uname}'").fetchone()
        if output_buffer != None and output_buffer[0] != '':
            self.local_cursor.execute(f"UPDATE local_buffer SET output_buffer='' WHERE uname='{self.uname}'")
            self.bigsendall(output_buffer[0].encode("utf-8"))

    def read(self):
        """Function to read from the connected socket
        """
        recv_data = self.sock.recv(4096).decode("utf-8")
        if recv_data == "":
            print(f"Closing connection to {self.addr}")
            self.stop = True
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
        """Function to process the incoming json file
        
        :param json_string: The json to be processed
        :type json_string: JSON string
        """
        print("Processing data recieved from Server", end=' ')
        curr_time = time()
        print(strftime(f"%a, %d %b %Y %H:%M:%S.{str(curr_time - int(curr_time))[2:6]}", localtime(curr_time)))

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
        """Registers a client to the database
        """
        new_person = self.req["msg"]
        print("Trying to insert " + new_person)
        self.local_cursor.execute("INSERT INTO local_buffer (uname, output_buffer) VALUES('%s', '')" % (new_person))
        self.local_cursor.execute("INSERT INTO server_map (uname, serv_name) VALUES('%s', '%s')" % (new_person, self.uname))
        print(f'Added new user {new_person} to server {self.uname}')

    def onb(self):
        """Function to allow an existing client to onboard and communicate it to the required server
        """
        new_person = self.req["msg"]
        self.local_cursor.execute("UPDATE server_map SET serv_name = '%s' WHERE uname = '%s'" % (self.uname, new_person))
        output_buffer = self.local_cursor.execute(f"SELECT output_buffer FROM local_buffer WHERE uname='{new_person}'").fetchone()[0]
        self.local_cursor.execute(f"UPDATE local_buffer SET output_buffer='' WHERE uname='{new_person}'")
        # forward this directly to next server
        self.append_output_buffer(self.uname, output_buffer)
        print(f'User {new_person} is online on server {self.uname}')

    def left(self):
        """Function to signify when a user goes offline
        """
        left_person = self.req["msg"]
        self.local_cursor.execute("UPDATE server_map SET serv_name = '%s' WHERE uname = '%s'" % (self.this_server_name, left_person))
        print(f'User {left_person} went offline from server {self.uname}')
