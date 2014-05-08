from _ssl import SSLError
from swiftclient import ClientException


def retry_cloudfiles(method, *args):
    done, tries = False, 0
    while not done:
        try:
            result = method(*args)
            return result
        except SSLError:
            pass
        except ClientException:
            pass

        tries += 1

        # Try at max, 10 times before quitting
        if tries >= 10:
            done = True