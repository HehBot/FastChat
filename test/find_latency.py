from sys import argv

num_files = int(argv[1])
avg = 0
worked = True
for i in range(num_files):
    file_name = "client" + str(i + 1) + "/client" + str(i + 1) + ".out"
    f = open(file_name,'r')
    lines = f.readlines()
    count = -1
    tot = 0
    tot_time = 0
    recv_time = None
    onb_time = (60 * float(lines[0][-11:-9]) + float(lines[0][-8:]))

    lines = lines[1:-1]
    for line in lines:
        if line == "\n" or line=="":
            continue
        if  "Sending" in line :
            continue
        count = count + 1
        if count % 4 == 0:
            csec = float(line[-8:])
            cmin = float(line[-11:-9])
            recv_time = (60 * cmin + csec)
        elif count % 4 == 1:
            csec = float(line[-8:])
            cmin = float(line[-11:-9])
            sent_time = 60 * cmin + csec
            if onb_time > sent_time:
                continue
            time = recv_time - sent_time
            tot = tot + 1
            tot_time = tot_time + time
    if count!= 4*num_files-1:
        print(f'ERROR IN {file_name}')
        print(f'count is {count} instead of {6*num_files}')
        worked = False
    avg = avg + (tot_time/tot)

if worked:
    print("All data has been received")
print("Average latency = " + str(1000 * avg/num_files) + " ms")
