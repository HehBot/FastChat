from server_temp import Server_temp
from request import pub_key_to_str
import json 

class Server_to_Client(Server_temp):
    def __init__(self, client_addr, uname, client_sock, local_cursor, this_server_name, cursor, conn, other_servers, pub_key):
        Server_temp.__init__(self, uname, client_sock, local_cursor, this_server_name, other_servers)
        self.sock_type = "client_sock" 
        self.addr = client_addr 
        self.inb = ''
        self.cursor = cursor
        self.conn = conn 
        self.pub_key = pub_key
        
    def write(self):
        output_buffer = self.local_cursor.execute(f"SELECT output_buffer FROM local_buffer WHERE uname='{self.uname}'").fetchone()

        if output_buffer != None and output_buffer[0] != '':
            self.local_cursor.execute(f"UPDATE local_buffer SET output_buffer='' WHERE uname='{self.uname}'")
            self.bigsendall(output_buffer[0].encode("utf-8"))

    def read(self):
        recv_data = self.sock.recv(4096).decode("utf-8")

        if recv_data == "":
            print(f"Closing connection to {self.addr}")
            # Informing all servers
            server_data = json.dumps({"hdr":"left", "msg":self.uname})
            for i in self.other_servers:
                self.append_output_buffer(i, server_data)
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
                self.process_data(json_string)
                continue
            if self.inb[i] == '"' and self.inb[i - 1] != '\\':
                n += 1
            i += 1

    def process_data(self, json_string):
        print("\nLOADS")
        print(json_string)
        print()
        self.req = json.loads(json_string)

        # Response to public key request
        if (self.req["hdr"] == "pub_key"):
            self.pub_key_req()

        # Response to group creating request
        elif (self.req["hdr"] == "grp_registering"):
            self.group_register()
        elif self.req["hdr"][0] == ">":
            self.personal_msg()
            
        # Group operations
        elif self.req["hdr"][0] == "<":
            self.group_operation()

    def pub_key_req(self):
        resp = None
        self.cursor.execute("SELECT pub_key FROM customers WHERE uname='%s'" % (self.req["msg"]))
        resp_pub_key = self.cursor.fetchone()
        if resp_pub_key == None:
            resp = { "hdr":"error:4", "msg":f"User {self.req['msg']} not registered" }
        else:
            resp_pub_key = resp_pub_key[0]
            resp = { "hdr":"pub_key", "msg":resp_pub_key }

        self.append_output_buffer(self.uname, json.dumps(resp))

    def group_register(self):
        # TODO may need to implement transaction  
        self.cursor.execute("SELECT isAdmin FROM groups WHERE group_id=0")
        group_id = int(self.cursor.fetchone()[0])
        self.cursor.execute("UPDATE groups SET isAdmin=%d WHERE group_id=0" % (group_id + 1))
        self.cursor.execute("INSERT INTO groups(group_id, uname, isAdmin) VALUES(%d, '%s', %d)" % (group_id, self.uname, 1))
        self.conn.commit()

        resp = json.dumps({"hdr":"group_id", "msg":str(group_id)})
        self.sock.sendall(resp.encode("utf-8"))

        print("\nRegistered new group with id " + str(group_id) + '\n')

    def personal_msg(self):
        recip_uname = self.req["hdr"][1:]
        mod_data = json.dumps({ "send_to":recip_uname, "hdr":'>' + self.uname + ':' + pub_key_to_str(self.pub_key), "msg":self.req["msg"], "aes_key":self.req["aes_key"], "time":self.req["time"], "sign":self.req["sign"] })
#TypeError: can only concatenate str (not "PublicKey") to str
        serv = self.local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'"%(recip_uname)).fetchone()[0]
        if serv == self.this_server_name:
            self.append_output_buffer(recip_uname, mod_data)
        else:
            self.append_output_buffer(serv, mod_data)

        print("\nSending " + mod_data + " to " + recip_uname + '\n')

    def group_operation(self):
        if "::" in self.req["hdr"][1:]:
            self.group_remove()
        elif ":" in self.req["hdr"][1:]:
            self.group_add()
        else:
            self.group_msg()
            
    def group_remove(self):
        k = self.req["hdr"].find(":")
        group_id = int(self.req["hdr"][1:k])
        recip_uname = self.req["hdr"][k + 2:]

        self.cursor.execute("SELECT groups.isAdmin FROM groups WHERE group_id=%d AND groups.uname='%s'" % (group_id, self.uname))
        is_admin = self.cursor.fetchone()
        # Admin removing someone else
        if is_admin!=None and is_admin[0] == 1 and recip_uname != self.uname:
            print("Removing from group")
            # TODO Can remove from group even if not present
            self.cursor.execute("DELETE FROM groups WHERE groups.group_id = '%s' AND groups.uname = '%s' " %(group_id, recip_uname))
            self.conn.commit()

            resp1 = {"hdr":"group_removed:" + str(group_id) + ":" + self.uname + ':' + pub_key_to_str(self.pub_key), "msg":self.req["msg"], "aes_key":self.req["aes_key"], "time":self.req["time"], "sign":self.req["sign"]}
            resp1["send_to"] = recip_uname
            serv = self.local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'"%(recip_uname)).fetchone()[0]
            if serv == self.this_server_name:
                self.append_output_buffer(recip_uname, json.dumps(resp1))
            else:
                self.append_output_buffer(serv, json.dumps(resp1))

            resp2 = {"hdr":"person_removed:" + str(group_id) + ":" + recip_uname + ':' + pub_key_to_str(self.pub_key), "msg":self.req["msg"], "aes_key":self.req["aes_key"], "time":self.req["time"], "sign":self.req["sign"]}
            self.cursor.execute("SELECT groups.uname FROM groups WHERE groups.group_id = %s" %(group_id))
            group_participants = self.cursor.fetchall()
            for i in group_participants:
                resp2["send_to"] = i[0]
                serv = self.local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'" % (i[0])).fetchone()[0]
                if serv == self.this_server_name:
                    self.append_output_buffer(i[0], json.dumps(resp2))
                else:
                    self.append_output_buffer(serv, json.dumps(resp2))

            print("\nRemoved " + recip_uname + " from group " + str(group_id) + " by " + self.uname + '\n')

        # Admin leaving
        elif is_admin!=None and is_admin[0] == 1 and recip_uname == self.uname:
            print("Admin may not leave group")
            resp1 = json.dumps({"hdr":"error:5", "msg":"Admin may not leave group"})
            self.append_output_buffer(recip_uname, resp1)

        # If not admin
        elif is_admin!=None and is_admin[0]!=1:
            # Leaving the group
            if recip_uname == self.uname:
                print("Exiting from group")

                self.cursor.execute("DELETE FROM groups WHERE groups.group_id = '%s' AND groups.uname = '%s' " %(group_id, recip_uname))
                self.conn.commit()
                resp1 = {"hdr":"group_left:" + str(group_id), "msg":""}
                resp1["send_to"] = recip_uname
                serv = self.local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'"%(recip_uname)).fetchone()[0]
                if serv == self.this_server_name:
                    self.append_output_buffer(recip_uname, json.dumps(resp1))
                else:
                    self.append_output_buffer(serv, json.dumps(resp1))

                resp2 = {"hdr":"person_left:" + str(group_id) + ":" + recip_uname + ':' + pub_key_to_str(self.pub_key), "msg":self.req["msg"], "aes_key":self.req["aes_key"], "time":self.req["time"], "sign":self.req["sign"]}
                self.cursor.execute("SELECT groups.uname FROM groups WHERE groups.group_id = %s" %(group_id))
                group_participants = self.cursor.fetchall()
                for i in group_participants:
                    resp2["send_to"] = i[0]
                    serv = self.local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'" % (i[0])).fetchone()[0]
                    if serv == self.this_server_name:
                        self.append_output_buffer(i[0], json.dumps(resp2))
                    else:
                        self.append_output_buffer(serv, json.dumps(resp2))

                print('\n' + recip_uname + " left group " + str(group_id) + '\n')

            # Not admin and trying to remove someone else
            else:
                return

        #Not even present in the group 
        else:
            return  

    def group_add(self):
        k = self.req["hdr"].find(":")
        group_id = int(self.req["hdr"][1:k])
        recip_uname = self.req["hdr"][k + 1:]

        print("TRYING TO ADD NEW PERSON")
        print(f"group_id: {group_id}, recip_uname = {recip_uname}, MyName = {self.uname}")

        self.cursor.execute("SELECT groups.isAdmin FROM groups WHERE group_id=%d AND groups.uname='%s'" % (group_id, self.uname))
        is_admin = self.cursor.fetchone()[0]
        if is_admin!=None and is_admin == 1:
            resp2 = {"hdr":"person_added:" + str(group_id) + ":" + recip_uname + ':' + pub_key_to_str(self.pub_key), "msg":self.req["msg"], "aes_key":self.req["aes_key"], "time":self.req["time"], "sign":self.req["sign"]}
            self.cursor.execute("SELECT groups.uname FROM groups WHERE groups.group_id = %s" %(group_id))
            group_participants = self.cursor.fetchall()
            
            for i in group_participants:
                resp2["send_to"] = i[0]
                serv = self.local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'" % (i[0])).fetchone()[0]
                if serv == self.this_server_name:
                    self.append_output_buffer(i[0], json.dumps(resp2))
                else:
                    self.append_output_buffer(serv, json.dumps(resp2))

            self.cursor.execute("INSERT INTO groups(group_id,  uname, isAdmin) VALUES(%d, '%s', %d)" % (group_id, recip_uname, 0))
            self.conn.commit()

            resp1 = {"hdr":"group_added:" + str(group_id) + ":" + self.uname + ':' + pub_key_to_str(self.pub_key), "msg":self.req["msg"], "aes_key":self.req["aes_key"], "time":self.req["time"], "sign":self.req["sign"]}

            serv = self.local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'"%(recip_uname)).fetchone()[0]

            resp1["send_to"] = recip_uname
            if serv == self.this_server_name:
                self.append_output_buffer(recip_uname, json.dumps(resp1))
            else:
                self.append_output_buffer(serv, json.dumps(resp1))

            print("\nAdded " + recip_uname + " to group " + str(group_id) + " by " + self.uname + '\n')

        else: #If not admin or not present
            return

    def group_msg(self):
        group_id = int(self.req["hdr"][1:])
        mod_data = { "hdr":'<' + str(group_id) + ':' + self.uname + ':' + pub_key_to_str(self.pub_key), "msg":self.req["msg"], "aes_key":self.req["aes_key"], "time":self.req["time"], "sign":self.req["sign"] }
        self.cursor.execute("SELECT groups.uname FROM groups WHERE group_id=%d" % (group_id))
        list_of_names = self.cursor.fetchall()

        for i in list_of_names:
            if i[0] != self.uname:
                mod_data["send_to"] = i[0]
                serv = self.local_cursor.execute("SELECT serv_name FROM server_map WHERE uname = '%s'" % (i[0])).fetchone()[0]
                if serv == self.this_server_name:
                    self.append_output_buffer(i[0], json.dumps(mod_data))
                else:
                    self.append_output_buffer(serv, json.dumps(mod_data))


        print("\nSending " + json.dumps(mod_data) + " to " + str(group_id) + '\n')
