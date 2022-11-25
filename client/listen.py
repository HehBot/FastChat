import json 

def listen(the_client):
    input_buffer = ""
    while True:
        n = 0
        i = 0
        while i != len(input_buffer):
            if input_buffer[i] == '}' and n % 2 == 0:
                data = input_buffer[:i + 1]
                input_buffer = input_buffer[i + 1:]
                n = 0
                i = 0
                the_client.process_data(data)
                continue
            if input_buffer[i] == '"' and input_buffer[i - 1] != '\\':
                n += 1
            i += 1
        input_buffer += the_client.client_sock.recv(4096).decode("utf-8")
