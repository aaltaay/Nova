import os
os.environ['PYTHONIOENCODING'] = 'utf-8:backslashreplace'
os.environ['PYTHONUTF8'] = '1'
import multiprocessing as mp


def child():
    import sys
    print('CHILD sys.stdout.encoding =', sys.stdout.encoding, flush=True)
    print('CHILD PYTHONIOENCODING =', os.environ.get('PYTHONIOENCODING'), flush=True)
    print('\u2192 unicode test ok', flush=True)


if __name__ == '__main__':
    ctx = mp.get_context('spawn')
    p = ctx.Process(target=child)
    p.start()
    p.join()
