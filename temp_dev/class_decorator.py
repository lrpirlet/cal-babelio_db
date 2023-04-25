
import time
import random
from psutil import cpu_count

TIME_INTERVAL = 1      # this is the minimum interval between 2 access to the web (when decorator decorate ret_soup)
last_time_used = 0 # time.time() + 5
print("last_time_used 8: ", last_time_used)

class Un_par_un(object):
    '''
    This is a class decorator.
    Purpose: execute the decorated function with a minimum of x seconds
    between each execution...
    assume that: the calling module will wait long enough before timeout
    '''
    def __init__(self,fnctn):
        self.function = fnctn
        self.last_time = last_time_used
        self._memory = []

    def __call__(self, *args, **kwargs):
        print("self.last_time : ", self.last_time)
        interval_time = self.last_time - time.time() + TIME_INTERVAL
        if interval_time > 0:
            time.sleep(interval_time)
      # call decorated function
        result = self.function(*args, **kwargs)
        self._memory.append((result, time.asctime()))
        self.last_time = time.time()
      # return result of function
        return result

    def get_memory(self):
        return self._memory

    def get_last_time(self):
        return self.last_time

@Un_par_un
def square(n,rndm):
    return (n, n*n, rndm)

start = time.asctime()
time.sleep(TIME_INTERVAL*(7%cpu_count()))
print("TIME_INTERVAL*(7%cpu_count()) : ", TIME_INTERVAL*(7%cpu_count()))

last_time_used = square.get_last_time()
print("last_time_used 48: ", last_time_used)
print("square.get_last_time() : ", square.get_last_time())

for i in range(6):
    rndm = int(random.random()*2 + .5)
    time.sleep(rndm)
    print("rndm : ", rndm)
    print("Square of number is:", square(i, rndm))

print("start : ", start)
for i in (square.get_memory()):
    print("Quand : ",i[1],"n : ", i[0][0] ," ; square : ", i[0][1], "wait : ", i[0][2])

last_time_used = square.get_last_time()
print("last_time_used 64: ", last_time_used)
print("square.get_last_time() : ", square.get_last_time())

for i in range(6):
    rndm = int(random.random()*2 + .5)
    time.sleep(rndm)
    print("rndm : ", rndm)
    print("Square of number is:", square(i, rndm))

for i in (square.get_memory()):
    print("Quand : ",i[1],"n : ", i[0][0] ," ; square : ", i[0][1], "wait : ", i[0][2])