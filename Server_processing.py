import json

def process(req,senders_uname,client_sock,cursor):
    
    pub_key = cursor.execute("SELECT customers.pub_key FROM customers WHERE uname='%s'" % (senders_uname)).fetchone()[0]

    if (req["hdr"] == "pub_key"):
        resp = None
        pub_key_output_buffer = cursor.execute("SELECT pub_key, output_buffer FROM customers WHERE uname='%s'" % (req["msg"])).fetchone()
        if pub_key_output_buffer == None:
            resp = { "hdr":"error", "msg":f"User {req['msg']} not registered" }
        else:
            pub_key_req = pub_key_output_buffer[0]
            resp = { "hdr":"pub_key", "msg":pub_key_req }

        #append_output_buffer(senders_uname, json.dumps(resp))
        client_sock.send(json.dumps(resp).encode("utf-8"))

    elif req["hdr"][0] == ">":
        recip_uname = req["hdr"][1:]
        mod_data = json.dumps({ "hdr":'>' + senders_uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })

        #append_output_buffer(recip_uname, mod_data)
        client_sock.send(json.dumps(mod_data).encode("utf-8"))
        print("\nSending " + mod_data + " to " + recip_uname + '\n')

    elif req["hdr"][0] == "<":
        if ':' in req["hdr"][0]:
            client_sock.send(json.dumps(req).encode("utf-8"))

        else: #Messaging on a group
            group_id = int(req["hdr"][1:])
            mod_data = json.dumps({ "hdr":'<' + str(group_id) + ':' + senders_uname + ':' + pub_key, "msg":req["msg"], "aes_key":req["aes_key"], "time":req["time"], "sign":req["sign"] })
            client_sock.send(json.dumps(mod_data).encode("utf-8"))
        
            print("\nSending " + mod_data + " to " + str(group_id) + '\n')