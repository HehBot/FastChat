from server_temp import Server_temp

class Balance_Server_to_Server(Server_temp):
    def __init__(self,uname,balancing_server_sock,local_cursor,this_server_name,other_servers ):
        Server_temp.__init__(self,uname,balancing_server_sock,local_cursor,this_server_name ,other_servers)
        self.sock_type="balancing_server_sock"

    def write(self):
        output_buffer = self.local_cursor.execute(f"SELECT output_buffer FROM local_buffer WHERE uname='{self.uname}'").fetchone()
        if output_buffer != None and output_buffer[0] != '':
            self.local_cursor.execute(f"UPDATE local_buffer SET output_buffer='' WHERE uname='{self.uname}'")
            self.sock.sendall(output_buffer[0].encode("utf-8"))