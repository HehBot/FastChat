import threading
import time
import curses
stdscr = curses.initscr()
curses.echo()

def myFunc():
    while True:
        time.sleep(1)
        print("Hello")



def main(stdsrc):
    t1 = threading.Thread(target=myFunc)
    t1.start()

    while True:
        x = stdscr.getstr(25, 0)
        print(":why")

curses.wrapper(main)