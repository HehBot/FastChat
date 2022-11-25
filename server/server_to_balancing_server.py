from server_temp import Server_temp

class Server_to_Balancing_Server(Server_temp):
    """This class abstracts the data for the socket that sends information between the Balancing server and a server
    
    :param sock_type: Socket type
    :type sock_type: String
    """
    def __init__(self, uname, balancing_server_sock, local_cursor, this_server_name, other_servers ):
        """Class constructor
        :param uname: The username of the client with whom the server is communicating
        :type uname: String
        :param balancing server sock: Socket address of the server
        :type balancing server sock: Socket
        :param local_cursor: The cursor to the local database
        :type local_cursor: SQL cursor 
        :param this_server_name: The address of the server
        :type this_server_name: Server address(ip, port)
        :param other_servers: A list of other running servers
        :type other_servers: List of strings
        """
        Server_temp.__init__(self, uname, balancing_server_sock, local_cursor, this_server_name, other_servers)
        self.sock_type = "balancing_server_sock"

    def write(self):
        """Function to empty the output buffer of the server and send it to the balancing server
        """
        output_buffer = self.local_cursor.execute(f"SELECT output_buffer FROM local_buffer WHERE uname='{self.uname}'").fetchone()
        if output_buffer != None and output_buffer[0] != '':
            self.local_cursor.execute(f"UPDATE local_buffer SET output_buffer='' WHERE uname='{self.uname}'")
            self.sock.sendall(output_buffer[0].encode("utf-8"))
