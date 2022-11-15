import threading
import time

def Myfunc():
    while True:
        time.sleep(1)
        print("Hello")

t1 = threading.Thread(target=Myfunc)

t1.start()

while True:
    x = input()
    print(":why"+x)
