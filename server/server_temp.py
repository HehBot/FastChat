import sqlite3
from time import time, strftime, localtime

class Server_temp:
    """Class to abstract the data for a server template

    :param uname: The unique name of the object this server is connected to (server or client) 
    :type uname: String
    :param sock: The socket address corresponding to the object
    :type sock: Socket
    :param local_cursor: The cursor for the local database
    :type local_cursor: SQL cursor
    :param this_server_name: The address (ip:port) of the server corresponding to this server
    :type this_server_name: Ip:Port
    :param other_servers: A list of other servers connected to this server
    :type other_servers: List of strings
    """
    def __init__(self,uname,sock,local_cursor,this_server_name,other_servers):
        """The constructor of the class
        """
        self.uname = uname
        self.sock = sock
        self.local_cursor = local_cursor
        self.stop = False
        self.this_server_name = this_server_name 
        self.other_servers = other_servers

    def append_output_buffer(self, name, newdata):
        """Function to append to the output buffer 
        
        :param name: Name of the client 
        :type name: String
        :param newdata: The data to be appended to the output buffer
        :type newdata: String
        """
        print(f'ADDING TO OUTPUT BUFFER of {name}')
        curr_time = time()
        print(strftime(f"%a, %d %b %Y %H:%M:%S.{str(curr_time - int(curr_time))[2:6]}", localtime(curr_time)))
        self.local_cursor.execute("UPDATE local_buffer SET output_buffer=output_buffer||'%s' WHERE uname='%s'" % (newdata, name))

    def bigsendall(self, bytedata):
        """Sends a big chunk of data
        :param bytedata: The Bytedata to be sent
        :type bytedata: byte array
        """
        while len(bytedata) > 0:
            transmitted = self.sock.send(bytedata)
            bytedata = bytedata[transmitted:]

class Server(Server_temp):
    pass
