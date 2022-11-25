import sqlite3

class Server_temp:
    def __init__(self,uname,sock,local_cursor,this_server_name,other_servers):
        self.uname = uname
        self.sock = sock
        self.local_cursor = local_cursor
        self.stop = False
        self.this_server_name = this_server_name 
        self.other_servers = other_servers

    def append_output_buffer(self, name, newdata):
        print()
        print(f'ADDING TO OUTPUT BUFFER {newdata} of {name}')
        print()
        self.local_cursor.execute("UPDATE local_buffer SET output_buffer=output_buffer||'%s' WHERE uname='%s'" % (newdata, name))

    def bigsendall(self, bytedata):
        while len(bytedata) > 0:
            transmitted = self.client_sock.send(bytedata)
            bytedata = bytedata[transmitted:]

class Server(Server_temp):
    pass
