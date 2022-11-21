import json

def process(req,senders_uname,client_sock,cursor):
    
    if (req["hdr"] == "pub_key"):
        resp = None
        pub_key_output_buffer = cursor.execute("SELECT pub_key, output_buffer FROM customers WHERE uname='%s'" % (req["msg"])).fetchone()
        if pub_key_output_buffer == None:
            resp = { "hdr":"error", "msg":f"User {req['msg']} not registered" }
        else:
            pub_key = pub_key_output_buffer[0]
            resp = { "hdr":"pub_key", "msg":pub_key }

        #append_output_buffer(senders_uname, json.dumps(resp))
        client_sock.send(json.dumps(resp).encode("utf-8"))

    elif req["hdr"][0] == ">":
        recip_uname = req["hdr"][1:]
        mod_data = json.dumps({ "hdr":'>' + senders_uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })

        #append_output_buffer(recip_uname, mod_data)
        client_sock.send(json.dumps(mod_data).encode("utf-8"))
        print("\nSending " + mod_data + " to " + recip_uname + '\n')

    elif req["hdr"][0] == "<":
        if ":" in req["hdr"][1:]: #Adding this person to group
            k=req["hdr"].find(":")
            group_id = int(req["hdr"][1:k])
            recip_name = req["hdr"][k + 1:]
            
            print("TRYING TO ADD NEW PERSON")
            print(f"group_id: {group_id}, recip_name = {recip_name}, MyName = {senders_uname}")
            
            is_admin = cursor.execute("SELECT groups.isAdmin FROM groups WHERE group_id=%d AND groups.uname='%s'" % (group_id, senders_uname)).fetchone()[0]

            if(is_admin == 1):
                cursor.execute("INSERT INTO groups(group_id,  uname, isAdmin) VALUES(%d, '%s', %d)" % (group_id, recip_name, 0))
                resp=json.dumps({"hdr":"group_added:" + str(group_id) + ":" + senders_uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"],"time":req["time"], "sign":req["sign"]})
    #                        output_buffer[recip_name].append(resp)
                #append_output_buffer(recip_name, resp)
                client_sock.send(json.dumps(resp).encode("utf-8"))
                print("\nAdded " + recip_name + " to group " + str(group_id) + " by " + senders_uname + '\n')

            else: #If not admin
                TODO

        else: #Messaging on a group
            group_id = int(req["hdr"][1:])
            mod_data = json.dumps({ "hdr":'<' + str(group_id) + ':' + senders_uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })
            client_sock.send(json.dumps(mod_data).encode("utf-8"))
        
            print("\nSending " + mod_data + " to " + str(group_id) + '\n')