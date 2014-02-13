from contextlib import contextmanager
from functools import wraps
import re
from fabric.colors import green, blue, yellow, red
from fabric.context_managers import cd, prefix, hide
from fabric.decorators import task, roles
from fabric.state import env
from fabric.api import sudo as _sudo
from fabric.api import run

__author__ = 'rudy'


def _print(output):
    print
    print output
    print


def print_command(command):
    _print(blue("$ ", bold=True) +
           yellow(command, bold=True) +
           red(" ->", bold=True))


def log_call(func):
    @wraps(func)
    def logged(*args, **kawrgs):
        header = "-" * len(func.__name__)
        _print(green("\n".join([header, func.__name__, header]), bold=True))
        return func(*args, **kawrgs)
    return logged


@task
@roles('application','cron','database','db_slave')
def sudo(command, show=True):
    """
    Runs a command as sudo.
    """
    if show:
        print_command(command)
    with hide("running"):
        return _sudo(command)


@task
@roles('application','cron')
def pip(packages):
    """
    Installs one or more Python packages within the virtual environment.
    """
    with virtualenv():
        return sudo("pip install %s" % packages)


######################################
# Context for virtualenv and project #
######################################
@contextmanager
def activate_venv():
    with prefix("source %s/bin/activate" % env.venv_path):
        yield


@contextmanager
def virtualenv():
    """
    Runs commands within the project's virtualenv.
    """
    with cd(env.venv_path):
        with prefix("source %s/bin/activate" % env.venv_path):
            yield


@contextmanager
def project():
    """
    Runs commands within the project's directory.
    """
    with activate_venv():
        with cd(env.proj_path):
            yield

