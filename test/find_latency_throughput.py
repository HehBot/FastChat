from sys import argv

num_files = int(argv[1])
arr=[]
avg = 0

for i in range(num_files):
    file_name = "client" + str(i + 1) + "/client" + str(i + 1) + ".out"
    f = open(file_name,'r')
    lines = f.readlines()
    count = -1
    tot = 0
    tot_time = 0

    recv_time = None
    onb_time = (60 * float(lines[0][-11:-9]) + float(lines[0][-8:]))

    lines = lines[1:]

    for line in lines:
        count = count + 1
        if count % 6 == 1:
            csec = float(line[-8:])
            cmin = float(line[-11:-9])
            recv_time = (60 * cmin + csec)
        elif count % 6 == 2:
            csec = float(line[-8:])
            cmin = float(line[-11:-9])
            sent_time = 60 * cmin + csec
            if onb_time > sent_time:
                continue
            time = recv_time - sent_time
            tot = tot + 1
            arr.append(time)
            tot_time = tot_time + time

    avg = avg + (tot_time/tot)
print("Average latency = " + str(1000 * avg/num_files) + " ms")
arr.sort()
print(arr)
