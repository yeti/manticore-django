import os
import re
import sys
from functools import wraps
from getpass import getpass, getuser
from glob import glob
from contextlib import contextmanager
from posixpath import join
import hashlib
import tempfile
from StringIO import StringIO
import traceback

from fabric.context_managers import settings
from fabric.api import env, cd, prefix, sudo as _sudo, run as _run, hide, task, get, puts, put, roles, execute
from fabric.contrib.files import exists, upload_template, _escape_for_regex
from fabric.colors import yellow, green, blue, red


####################
#  Utility Methods #
####################

CONFIG_FILE_NORMAL = "normal"
CONFIG_FILE_RECORDS = "records"

def modify_config_file(remote_path, settings=None, comment_char='#', setter_char='=', type=CONFIG_FILE_NORMAL,
    use_sudo=False, backup=True):

    """
    Alter the settings of an existing remote config file, trying to uncomment found settings, adding them otherwise.

    The config file is loaded to a local temporary file, processed, and uploaded back to the ``remote_path``.

    By default, backup is made remotely. Set ``backup`` to False to prevent this behavior.

    Two kinds of config files are currently supported.
    Default config file ``type`` is 'normal' where lines look like this:

        # - Connection Settings -
        listen_addresses = 'localhost' # what IP address(es) to listen on;
        #port = 5432

    The ``settings`` must be a list of tuples :

        settings = [('listen_addresses', "'*'"), ('port', '5433')]

    The script will change the config file to :

        # - Connection Settings -
        listen_addresses = '*' # what IP address(es) to listen on;
        port = 5433

    Notice how the line with the port setting was uncommented and set to a new value.
    If an existing line is not found, it is added.

    The ``comment_char`` defaults to '#' and ``setter_char``defaults to '='.

    A basic 'records' config file ``type`` is also supported. Ex: an pg_hba.conf file :

    # TYPE  DATABASE        USER            ADDRESS                 METHOD

    # "local" is for Unix domain socket connections only
    local   all             all                                     peer
    # IPv4 local connections:
    host    all             all             127.0.0.1/32            md5
    # IPv6 local connections:
    host    all             all             ::1/128                 md5
    # Allow replication connections from localhost, by a user with the
    # replication privilege.
    #local   replication     postgres                                peer
    #host    replication     postgres        127.0.0.1/32            md5
    #host    replication     postgres        ::1/128                 md5


    In such a file, we would change the IPv4 local connection to 'trust' and enable local replication like this :
    modify_config_file('/etc/postgresql/9.1/main/pg_hba.conf',
                [('host', 'all', 'all', '127.0.0.1/32','trust'),
                ('local', 'replication', '', 'peer')], type="records")

    By default, the file will be copied to ``remote_path`` as the logged-in
    user; specify ``use_sudo=True`` to use `sudo` instead.

    """
    changes_done = set()
    options = dict(comment_char=comment_char, setter_char=setter_char)

    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=True) as f:

        # Download the remote file into the temporary file
        a = get(remote_path, f)

        # Rewind the file to the beginning
        f.file.seek(0)

        # We're going to read each line and put them into newlines
        newlines = list()

        for line in f.file.readlines():

            # Compare each line with the wanted changes
            for setting in settings:
                # Check for a possible mistake of the user
                if not isinstance(setting, list) and not isinstance(setting, tuple):
                    tb = traceback.format_exc()
                    abort(tb + "\nChanges must be a tuple/list of tuples/lists.\n%s is not a list nor a tuple." % (setting,))

                # Case of a normal config file : each line is of the kind some_variable = some_value
                if type == CONFIG_FILE_NORMAL:
                    key, value = setting

                    # Search for a line of the form : some_variable = some_value
                    # or commented: #some_variable = some_value
                    # We preserve the ending \n.
                    search = ("\s*(?P<is_commented>%(comment_char)s*)(?P<left_chunk>\s*"+_escape_for_regex(key)
                              +"\s*%(setter_char)s\s*)(?P<right_chunk>\s*.*\n*)") % options
                    m = re.match(search, line)

                    if m:
                        # A match was found. Check for a comment at the end of the line,
                        # like some_variable = some_value # this is some comment
                        r = m.groupdict()
                        right_chunk = r['right_chunk']
                        comment = "\n"
                        if right_chunk is not None:
                            # We will capture the comment at the end of the line, if any
                            m2 = re.match("(?P<old_value>.*?)(?P<comment>\s*%(comment_char)s+.*\n*)" % options, right_chunk)
                            if m2:
                                comment = m2.groupdict()['comment']

                        puts('Found line:     ' + line, end='')

                        # It's not rare to find multiple commented versions of a setting in a config file.
                        # If the change was applied in the loop before, make sure we don't set the variable twice in
                        # this case.
                        if setting in changes_done:
                            if r['is_commented']:
                                # This is a commented setting, leave it so.
                                puts('Left it commented.')
                            else:
                                # This is a setting that's not commented, but we set a similar setting earlier in the
                                # loop either because we found a commented version and uncommented it then  applied the
                                # new value, or because it was a duplicate.
                                # In any case, we comment this new setting so our first setting takes precedence.
                                puts('Commented it:   '+red(comment_char) + line)
                                # Recreate the line using the new value set by the user
                                line = comment_char + line
                        else:
                            # Recreate the line using the new value set by the user
                            line = r['left_chunk'] + str(value) + comment

                            puts('Replaced with:  '+r['left_chunk'] + red(value) + comment)

                        # Mark the change as done
                        changes_done.add(setting)

                elif type == CONFIG_FILE_RECORDS:
                    escaped_change = [_escape_for_regex(t) for t in setting]
                    search = ("\s*(?P<is_commented>%(comment_char)s*)(?P<first_values>\s*"
                              + "(\s+)".join(escaped_change[:-1]+[')(?P<right_chunk>.*\n*)'])) % options

                    m = re.match(search, line)
                    if m:
                        r = m.groupdict()
                        right_chunk = r['right_chunk']
                        comment = "\n"
                        if right_chunk is not None:
                            # We will capture the comment at the end of the line, if any
                            m2 = re.match(".*?(?P<comment>\s*%(comment_char)s+.*\n*)" % options, right_chunk)
                            if m2:
                                comment = m2.groupdict()['comment']

                        puts('Found line:     ' + line, end='')

                        if setting in changes_done:
                            if r['is_commented']:
                                puts('Left it commented')
                            else:
                                puts('Commented it:   '+red(comment_char) + line)
                                # Recreate the line using the new value set by the user
                                line = comment_char + line
                        else:
                            # Recreate the line using the new value set by the user
                            line = r['first_values'] + str(setting[-1]) + comment
                            puts('Replaced with:  '+ r['first_values'] + red(str(setting[-1])) + comment)


                        changes_done.add(setting)

            # append the line
            newlines.append(line)

        # So far, some changes have been satisfied : those that were possible by removing the comment on existing lines
        # and setting a new value.
        # Let's now add new lines for remaining changes.
        for setting in settings:
            if not setting in changes_done:
                if type == CONFIG_FILE_NORMAL:
                    line = "%s %s %s" % (setting[0], setter_char, setting[1])
                    print line
                    newlines.append(line)
                elif type == CONFIG_FILE_RECORDS:
                    line = "\t".join(setting)
                    print line
                    newlines.append(line)

        func = use_sudo and sudo or run

        if backup:
            func("cp %s{,.bak}" % remote_path)

        newlines.append("")

        with tempfile.NamedTemporaryFile(delete=True) as new_file:
            new_file.writelines(newlines)

            # Upload the file.
            put(
                local_path=new_file,
                remote_path=remote_path,
                use_sudo=use_sudo
                #mirror_local_mode=mirror_local_mode,
                #mode=mode
            )

################
# Config setup #
################

conf = {}
if sys.argv[0].split(os.sep)[-1] in ("fab",             # POSIX
                                     "fab-script.py"):  # Windows
    # Ensure we import settings from the current dir
    try:
        conf = __import__("settings", globals(), locals(), [], 0).FABRIC
        try:
            conf["APPLICATION_HOSTS"][0]
            conf["DATABASE_HOSTS"][0]
        except (KeyError, ValueError):
            raise ImportError
    except (ImportError, AttributeError):
        print "Aborting, no hosts defined."
        exit()

env.db_pass = conf.get("DB_PASS", None)
env.admin_pass = conf.get("ADMIN_PASS", None)
env.user = conf.get("SSH_USER", getuser())
env.password = conf.get("SSH_PASS", None)
env.key_filename = conf.get("SSH_KEY_PATH", None)
env.roledefs = {
    'application' : conf.get("APPLICATION_HOSTS"),
    'database' : conf.get("DATABASE_HOSTS"),
}
env.private_database_hosts = conf.get("PRIVATE_DATABASE_HOSTS", ["127.0.0.1"])
env.primary_database_host = env.private_database_hosts[0] # the first listed private database host is the master, used by live_settings.py
env.private_application_hosts = conf.get("PRIVATE_APPLICATION_HOSTS", ["127.0.0.1"])
env.hosts.extend(conf.get("APPLICATION_HOSTS"))
env.hosts.extend(conf.get("DATABASE_HOSTS"))
env.allowed_hosts = ",".join(["'%s'" % host for host in conf.get("APPLICATION_HOSTS")]) # used by live_settings.py to set Django's allowed hosts

env.proj_name = conf.get("PROJECT_NAME", os.getcwd().split(os.sep)[-1])
env.venv_home = conf.get("VIRTUALENV_HOME", "/home/%s" % env.user)
env.venv_path = "%s/%s" % (env.venv_home, env.proj_name)
env.proj_dirname = "project"
env.proj_path = "%s/%s" % (env.venv_path, env.proj_dirname)
env.manage = "%s/bin/python %s/project/manage.py" % (env.venv_path,
                                                     env.venv_path)
env.live_host = conf.get("LIVE_HOSTNAME", env.hosts[0] if env.hosts else None)
env.repo_url = conf.get("REPO_URL", "")
env.git = env.repo_url.startswith("git") or env.repo_url.endswith(".git")
env.reqs_path = conf.get("REQUIREMENTS_PATH", None)
env.gunicorn_port = conf.get("GUNICORN_PORT", 8000)
env.locale = conf.get("LOCALE", "en_US.UTF-8")
env.linux_distro = conf.get("LINUX_DISTRO", "squeeze")

##################
# Template setup #
##################

# Each template gets uploaded at deploy time, only if their
# contents has changed, in which case, the reload command is
# also run.

templates = {
    "nginx": {
        "local_path": "deploy/nginx.conf",
        "remote_path": "/etc/nginx/sites-enabled/%(proj_name)s.conf",
        "reload_command": "service nginx restart",
    },
    "supervisor": {
        "local_path": "deploy/supervisor.conf",
        "remote_path": "/etc/supervisor/conf.d/%(proj_name)s.conf",
        "reload_command": "supervisorctl reload",
    },
    "cron": {
        "local_path": "deploy/crontab",
        "remote_path": "/etc/cron.d/%(proj_name)s",
        "owner": "root",
        "mode": "600",
    },
    "gunicorn": {
        "local_path": "deploy/gunicorn.conf.py",
        "remote_path": "%(proj_path)s/gunicorn.conf.py",
    },
    "settings": {
        "local_path": "deploy/live_settings.py",
        "remote_path": "%(proj_path)s/local_settings.py",
    },
}


######################################
# Context for virtualenv and project #
######################################

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
    with virtualenv():
        with cd(env.proj_dirname):
            yield


@contextmanager
def update_changed_requirements():
    """
    Checks for changes in the requirements file across an update,
    and gets new requirements if changes have occurred.
    """
    reqs_path = join(env.proj_path, env.reqs_path)
    get_reqs = lambda: run("cat %s" % reqs_path, show=False)
    old_reqs = get_reqs() if env.reqs_path else ""
    yield
    if old_reqs:
        new_reqs = get_reqs()
        if old_reqs == new_reqs:
            # Unpinned requirements should always be checked.
            for req in new_reqs.split("\n"):
                if req.startswith("-e"):
                    if "@" not in req:
                        # Editable requirement without pinned commit.
                        break
                elif req.strip() and not req.startswith("#"):
                    if not set(">=<") & set(req):
                        # PyPI requirement without version.
                        break
            else:
                # All requirements are pinned.
                return
        pip("-r %s/%s" % (env.proj_path, env.reqs_path))


###########################################
# Utils and wrappers for various commands #
###########################################

def _print(output):
    print
    print output
    print


def print_command(command):
    _print(blue("$ ", bold=True) +
           yellow(command, bold=True) +
           red(" ->", bold=True))


@task
def run(command, show=True):
    """
    Runs a shell comand on the remote server.
    """
    if show:
        print_command(command)
    with hide("running"):
        return _run(command)


@task
def sudo(command, show=True):
    """
    Runs a command as sudo.
    """
    if show:
        print_command(command)
    with hide("running"):
        return _sudo(command)


def log_call(func):
    @wraps(func)
    def logged(*args, **kawrgs):
        header = "-" * len(func.__name__)
        _print(green("\n".join([header, func.__name__, header]), bold=True))
        return func(*args, **kawrgs)
    return logged


def get_templates():
    """
    Returns each of the templates with env vars injected.
    """
    injected = {}
    for name, data in templates.items():
        injected[name] = dict([(k, v % env) for k, v in data.items()])
    return injected


def upload_template_and_reload(name):
    """
    Uploads a template only if it has changed, and if so, reload a
    related service.
    """
    template = get_templates()[name]
    local_path = template["local_path"]
    remote_path = template["remote_path"]
    reload_command = template.get("reload_command")
    owner = template.get("owner")
    mode = template.get("mode")
    remote_data = ""
    if exists(remote_path):
        with hide("stdout"):
            remote_data = sudo("cat %s" % remote_path, show=False)
    with open(local_path, "r") as f:
        local_data = f.read()
        # Escape all non-string-formatting-placeholder occurrences of '%':
        local_data = re.sub(r"%(?!\(\w+\)s)", "%%", local_data)
        if "%(db_pass)s" in local_data:
            env.db_pass = db_pass()
        local_data %= env
    clean = lambda s: s.replace("\n", "").replace("\r", "").strip()
    if clean(remote_data) == clean(local_data):
        return
    upload_template(local_path, remote_path, env, use_sudo=True, backup=False)
    if owner:
        sudo("chown %s %s" % (owner, remote_path))
    if mode:
        sudo("chmod %s %s" % (mode, remote_path))
    if reload_command:
        sudo(reload_command)


def db_pass():
    """
    Prompts for the database password if unknown.
    """
    if not env.db_pass:
        env.db_pass = getpass("Enter the database password: ")
    return env.db_pass


@task
def apt(packages):
    """
    Installs one or more system packages via apt.
    """
    return sudo("apt-get install -y -q " + packages)


@task
def pip(packages):
    """
    Installs one or more Python packages within the virtual environment.
    """
    with virtualenv():
        return sudo("pip install %s" % packages)


def postgres(command):
    """
    Runs the given command as the postgres user.
    """
    show = not command.startswith("psql")
    return run("sudo -u root sudo -u postgres %s" % command, show=show)


@task
def psql(sql, show=True):
    """
    Runs SQL against the project's database.
    """
    out = postgres('psql -c "%s"' % sql)
    if show:
        print_command(sql)
    return out


@task
def backup(filename):
    """
    Backs up the database.
    """
    return postgres("pg_dump -Fc %s > %s" % (env.proj_name, filename))


@task
def restore(filename):
    """
    Restores the database.
    """
    return postgres("pg_restore -c -d %s %s" % (env.proj_name, filename))


@task
def python(code, show=True):
    """
    Runs Python code in the project's virtual environment, with Django loaded.
    """
    setup = "import os; os.environ[\'DJANGO_SETTINGS_MODULE\']=\'settings\';"
    full_code = 'python -c "%s%s"' % (setup, code.replace("`", "\\\`"))
    with project():
        result = run(full_code, show=False)
        if show:
            print_command(code)
    return result


def static():
    """
    Returns the live STATIC_ROOT directory.
    """
    return python("from django.conf import settings;"
                  "print settings.STATIC_ROOT", show=False).split("\n")[-1]


@task
def manage(command):
    """
    Runs a Django management command.
    """
    return run("%s %s" % (env.manage, command))


#########################
# Install and configure #
#########################

@task
@log_call
@roles('application')
def installapp():
    apt("nginx libjpeg-dev python-dev python-setuptools "
        "libpq-dev memcached libffi-dev")
    sudo("easy_install pip")
    sudo("pip install virtualenv mercurial")

@task
@log_call
@roles('database')
def installdb():
    put(StringIO("deb http://apt.postgresql.org/pub/repos/apt/ %s-pgdg main" % env.linux_distro), "/etc/apt/sources.list.d/pgdg.list")
    sudo("wget --quiet -O - http://apt.postgresql.org/pub/repos/apt/ACCC4CF8.asc | sudo apt-key add -")
    sudo("apt-get update")
    apt("postgresql-9.2")


@task
@roles("database")
@log_call
def uninstalldb():
    """
    Stop and uninstall the database.
    """
    sudo("/etc/init.d/postgresql stop")
    sudo("apt-get remove postgresql")

@task
@log_call
def install():
    """
    Installs the base system and Python requirements for the entire server.
    """
    locale = "LC_ALL=%s" % env.locale
    with hide("stdout"):
        if locale not in sudo("cat /etc/default/locale"):
            sudo("update-locale %s" % locale)
            run("exit")
    sudo("apt-get update -y -q")
    apt("git-core supervisor")
    execute(installapp)
    execute(installdb)

@task
@log_call
@roles('application')
def createapp1():
    # Create virtualenv
    with cd(env.venv_home):
        if exists(env.proj_name):
            prompt = raw_input("\nVirtualenv exists: %s\nWould you like "
                               "to replace it? (yes/no) " % env.proj_name)
            if prompt.lower() != "yes":
                print "\nAborting!"
                return False
            remove()
        run("virtualenv %s --distribute" % env.proj_name)
        vcs = "git" if env.git else "hg"
        run("%s clone %s %s" % (vcs, env.repo_url, env.proj_path))
        with project():
            run("git submodule init")
            run("git submodule update")

@task
@log_call
@roles('application')
def createapp2():
    # Set up SSL certificate.
    conf_path = "/etc/nginx/conf"
    if not exists(conf_path):
        sudo("mkdir %s" % conf_path)
    with cd(conf_path):
        crt_file = env.proj_name + ".crt"
        key_file = env.proj_name + ".key"
        if not exists(crt_file) and not exists(key_file):
            try:
                crt_local, = glob(join("deploy", "*.crt"))
                key_local, = glob(join("deploy", "*.key"))
            except ValueError:
                parts = (crt_file, key_file, env.live_host)
                sudo("openssl req -new -x509 -nodes -out %s -keyout %s "
                     "-subj '/CN=%s' -days 3650" % parts)
            else:
                upload_template(crt_local, crt_file, use_sudo=True)
                upload_template(key_local, key_file, use_sudo=True)

    # Set up project.
    upload_template_and_reload("settings")
    with project():
        if env.reqs_path:
            pip("-r %s/%s" % (env.proj_path, env.reqs_path))
        pip("gunicorn setproctitle south psycopg2 "
            "django-compressor python-memcached")
        manage("createdb --noinput --nodata")
        python("from django.conf import settings;"
               "from django.contrib.sites.models import Site;"
               "site, _ = Site.objects.get_or_create(id=settings.SITE_ID);"
               "site.domain = '" + env.live_host + "';"
               "site.save();")
        if env.admin_pass:
            pw = env.admin_pass
            user_py = ("from mezzanine.utils.models import get_user_model;"
                       "User = get_user_model();"
                       "u, _ = User.objects.get_or_create(username='admin');"
                       "u.is_staff = u.is_superuser = True;"
                       "u.set_password('%s');"
                       "u.save();" % pw)
            python(user_py, show=False)
            shadowed = "*" * len(pw)
            print_command(user_py.replace("'%s'" % pw, "'%s'" % shadowed))

@task
@log_call
@roles("database")
def createdb_config():
    # create virtual environment directory and project path within
    if not exists(env.venv_path):
        prompt = raw_input("\nProject directory doesn't exist: %s\nWould you like "
                           "to create it? (yes/no) " % env.venv_path)
        if prompt.lower() != "yes":
            print "\nAborting!"
            return False

        sudo("mkdir %s" % env.venv_path)

    # Configure database server to listen to appropriate ports. Tested with Debian 6 and Postgres 9.2
    modify_config_file("/etc/postgresql/9.2/main/postgresql.conf",[("port", "5432"), ("listen_addresses","'%s'" % ",".join(env.private_database_hosts))])
    client_list = [('host', env.proj_name, env.proj_name, '%s/32' % client, 'md5') for client in env.private_application_hosts]
    modify_config_file('/etc/postgresql/9.2/main/pg_hba.conf', client_list, type="records")
    restart()

@task
@log_call
@roles("database")
def createdb_database():
    # Create DB and DB user.
    pw = db_pass()
    user_sql_args = (env.proj_name, pw.replace("'", "\'"))
    user_sql = "CREATE USER %s WITH ENCRYPTED PASSWORD '%s';" % user_sql_args
    psql(user_sql, show=False)
    shadowed = "*" * len(pw)
    print_command(user_sql.replace("'%s'" % pw, "'%s'" % shadowed))
    psql("CREATE DATABASE %s WITH OWNER %s ENCODING = 'UTF8' "
         "LC_CTYPE = '%s' LC_COLLATE = '%s' TEMPLATE template0;" %
         (env.proj_name, env.proj_name, env.locale, env.locale))

@task
@log_call
@roles('database')
def createdb():
    execute(createdb_config)
    execute(createdb_database)

@task
@roles("database")
@log_call
def upgradedb():
    """
    Upgrade 8.4 to 9.2 Postgres database.
    """
    execute(installdb)
    apt("postgresql-contrib-9.2")
    sudo("/etc/init.d/postgresql stop")
    run("su - postgres -c \"/usr/lib/postgresql/9.2/bin/pg_upgrade -u postgres -b %s -B %s -d %s -D %s -o '-D %s' -O '-D %s'\"" 
        % ("/usr/lib/postgresql/8.4/bin/","/usr/lib/postgresql/9.2/bin/","/var/lib/postgresql/8.4/main/","/var/lib/postgresql/9.2/main/","/etc/postgresql/8.4/main/","/etc/postgresql/9.2/main/"))
    sudo("apt-get remove postgresql-8.4")
    sudo("/etc/init.d/postgresql start")
    execute(createdb_config)

@task
@log_call
def create():
    """
    Create a new virtual environment for a project.
    Pulls the project's repo from version control, adds system-level
    configs for the project, and initialises the database with the
    live host.
    """

    # create virtual environment directory and project path within
    if not exists(env.venv_home):
        prompt = raw_input("\nProject directory doesn't exist: %s\nWould you like "
                           "to create it? (yes/no) " % env.venv_home)
        if prompt.lower() != "yes":
            print "\nAborting!"
            return False

        sudo("mkdir %s" % env.venv_home)

    execute(createapp1)
    execute(createdb)
    execute(createapp2)

    return True


@roles("application")
@log_call
def removeapp():
    if exists(env.venv_path):
        sudo("rm -rf %s" % env.venv_path)
    for template in get_templates().values():
        remote_path = template["remote_path"]
        if exists(remote_path):
            sudo("rm %s" % remote_path)

@roles("database")
@log_call
def removedb():
    with settings(warn_only=True):    
        psql("DROP DATABASE %s;" % env.proj_name)
        psql("DROP USER %s;" % env.proj_name)

    # Configure database server to listen to appropriate ports. Tested with Debian 6 and Postgres 9.2
    puts("TODO modify /etc/postgresql/9.2/main/pg_hba.conf")
    puts("TODO modify /etc/postgresql/9.2/main/postgresql.conf")

@task
@log_call
def remove():
    """
    Blow away the current project.
    """
    execute(removeapp)
    execute(removedb)

##############
# Deployment #
##############

@task
@log_call
@roles("application")
def restartapp():
    pid_path = "%s/gunicorn.pid" % env.proj_path
    if exists(pid_path):
        sudo("kill -HUP `cat %s`" % pid_path)
    else:
        start_args = (env.proj_name, env.proj_name)
        sudo("supervisorctl start %s:gunicorn_%s" % start_args)

@task
@log_call
@roles("database")
def restartdb():
    sudo("/etc/init.d/postgresql restart") # command specific to Debian


@task
@log_call
def restart():
    """
    Restart gunicorn worker processes for the project.
    """
    execute(restartapp)
    execute(restartdb)

@task
@log_call
@roles("application")
def deployapp1():
    if not exists(env.venv_path):
        prompt = raw_input("\nVirtualenv doesn't exist: %s\nWould you like "
                           "to create it? (yes/no) " % env.proj_name)
        if prompt.lower() != "yes":
            print "\nAborting!"
            return False
        create()
    for name in get_templates():
        upload_template_and_reload(name)

@task
@log_call
@roles("database")
def deploydb():
    with cd(env.venv_path):
        backup("last-%s.db" % env.proj_name)


@task
@log_call
@roles("application")
def deployapp2():
    with project():
        static_dir = static()
        if exists(static_dir):
            run("tar -cf last.tar %s" % static_dir)
        git = env.git
        last_commit = "git rev-parse HEAD" if git else "hg id -i"
        run("%s > last.commit" % last_commit)
        with update_changed_requirements():
            run("git pull origin master -f" if git else "hg pull && hg up -C")
        run("git submodule init")
        run("git submodule sync")
        run("git submodule update")
        manage("collectstatic -v 0 --noinput")
        manage("syncdb --noinput")
        manage("migrate --noinput")
    restart()    

@task
@log_call
def deploy():
    """
    Deploy latest version of the project.
    Check out the latest version of the project from version
    control, install new requirements, sync and migrate the database,
    collect any new static assets, and restart gunicorn's work
    processes for the project.
    """

    execute(deployapp1)
    execute(deploydb)
    execute(deployapp2)

    return True


@task
@log_call
@roles("application")
def rolebackapp():
    with project():
        with update_changed_requirements():
            update = "git checkout" if env.git else "hg up -C"
            run("%s `cat last.commit`" % update)
        with cd(join(static(), "..")):
            run("tar -xf %s" % join(env.proj_path, "last.tar"))
    
    restart()

@task
@log_call
@roles("database")
def rolebackdb():
    with cd(env.venv_path):
        restore("last-%s.db" % env.proj_name)

@task
@log_call
def rollback():
    """
    Reverts project state to the last deploy.
    When a deploy is performed, the current state of the project is
    backed up. This includes the last commit checked out, the database,
    and all static files. Calling rollback will revert all of these to
    their state prior to the last deploy.
    """
    execute(rolebackdb)
    execute(rolebackapp)


@task
@log_call
def all():
    """
    Installs everything required on a new system and deploy.
    From the base software, up to the deployed project.
    """
    install()
    if create():
        deploy()
