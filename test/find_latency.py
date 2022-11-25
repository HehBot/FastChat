from sys import argv
num_files = int(argv[1])
num = int(argv[2])
avg = 0
for i in range(num_files):
    file_name = "client"+str(i+1)+"/client"+str(i+1)+".out"
    f = open(file_name,'r')
    lines = f.readlines()
    count = 1
    tot = 0
    tot_time = 0
    for line in lines:
        if count>num*6:
            if count%6==3:
                csec = float(line[-8:])
                cmin = float(line[-11:-9])
                time = (60*cmin+csec)
            elif count%6==4:
                csec = float(line[-8:])
                cmin = float(line[-11:-9])
                time = time - 60*cmin-csec
                tot = tot+1
                tot_time = tot_time+time
        count = count+1

    avg = avg+(tot_time/tot)

print(avg/num_files)
