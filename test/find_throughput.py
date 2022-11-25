from sys import argv

num_files = int(argv[1])
avg = 0
for i in range(num_files):
    file_name = "client" + str(i + 1) + "/client" + str(i + 1) + ".out"
    f = open(file_name,'r')
    lines = f.readlines()
    count = 0
    is_start = True
    lines = lines[1:]
    for line in lines:
        if line[:7]=="Sending":
            csec = float(line[-8:])
            cmin = float(line[-11:-9])
            if is_start:
                is_start=False
                start = (60 * cmin + csec)
            else: 
                end = (60 * cmin + csec)

            count = count+1
        
    print(count)
    print((end-start)/count)
