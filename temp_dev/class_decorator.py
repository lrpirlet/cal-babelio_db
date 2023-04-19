
import time
import random
from psutil import cpu_count

TIME_INTERVAL = 1      # this is the minimum interval between 2 access to the web (when decorator decorate ret_soup)

class Un_par_un(object):
    '''
    This is a class decorator.
    Purpose: execute the decorated function with a minimum of x seconds
    between each execution...
    assume that: the calling module will wait long enough before timeout
    '''
    def __init__(self,fnctn):
        self.function = fnctn
        self.last_time = 0.0
        self._memory = []

    def __call__(self, *args, **kwargs):
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


@Un_par_un
def square(n,rndm):
    return (n, n*n, rndm)

start = time.asctime()
time.sleep(TIME_INTERVAL*(7%cpu_count()))

for i in range(6):
    rndm = int(random.random()*2 + .5)
    time.sleep(rndm)
    print("Square of number is:", square(i, rndm))

print("start : ", start)
for i in (square.get_memory()):
    print("Quand : ",i[1],"n : ", i[0][0] ," ; square : ", i[0][1], "wait : ", i[0][2])
