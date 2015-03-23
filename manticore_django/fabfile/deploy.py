import os
import re
import sys
from getpass import getpass, getuser
from glob import glob
from contextlib import contextmanager
from posixpath import join
import tempfile
from StringIO import StringIO
import traceback
from time import sleep
from fabric.context_managers import settings
from fabric.api import env, cd, run as _run, hide, task, get, puts, put, roles, execute, parallel
from fabric.contrib.console import confirm
from fabric.contrib.files import exists, upload_template, _escape_for_regex, append
from fabric.colors import red
from fabric.utils import *
import simplejson
from utils import log_call, pip, print_command, sudo, project

################
# Config setup #
################

# removes the port


# this function has to be defined before load_environment()
def check_db_password(password):
    chars = set('$()@') # characters to block
    return not any((c in chars) for c in password)


def get_host(host_name):
    if host_name.find(":") != -1:
        return host_name[0:host_name.find(":")]
    else:
        return host_name


def load_environment(conf, show_info):
    if show_info:
        print simplejson.dumps(conf, sort_keys=True, indent=4)

    if not "APPLICATION_HOSTS" in conf or len(conf["APPLICATION_HOSTS"]) == 0:
        abort("No application hosts are defined")
    if not "DATABASE_HOSTS" in conf or len(conf["DATABASE_HOSTS"]) == 0:
        abort("No database hosts are defined")

    env.db_pass = conf.get("DB_PASS", None)
    env.admin_pass = conf.get("ADMIN_PASS", None)
    env.user = conf.get("SSH_USER", getuser())
    env.password = conf.get("SSH_PASS", None)
    env.key_filename = conf.get("SSH_KEY_PATH", None)
    env.roledefs = {
        'application': conf.get("APPLICATION_HOSTS"),
        'database': conf.get("DATABASE_HOSTS")[0:1],
        'db_slave': conf.get("DATABASE_HOSTS")[1:],
        'cron': conf.get("CRON_HOSTS", conf.get("APPLICATION_HOSTS")),
    }
    env.application_hosts = conf.get("APPLICATION_HOSTS") # used for our own consumption
    env.cron_hosts = conf.get("CRON_HOSTS", conf.get("APPLICATION_HOSTS")) # used for our own consumption
    env.database_hosts = conf.get("DATABASE_HOSTS") # used for matching public and private database host IP addresses
    env.private_database_hosts = conf.get("PRIVATE_DATABASE_HOSTS", ["127.0.0.1"])
    env.primary_database_host = env.private_database_hosts[0] # the first listed private database host is the master, used by local_settings.py.template
    env.private_application_hosts = conf.get("PRIVATE_APPLICATION_HOSTS", ["127.0.0.1"])
    env.private_cron_hosts = conf.get("PRIVATE_CRON_HOSTS", env.private_application_hosts)
    if conf.get("LIVE_HOSTNAME"):
        tmp_hosts = list()
        tmp_hosts.extend(conf.get("APPLICATION_HOSTS"))
        if conf.get("LIVE_HOSTNAME") and not conf.get("LIVE_HOSTNAME") in tmp_hosts: # don't duplicate any host names
            tmp_hosts.append(conf.get("LIVE_HOSTNAME"))
        if not "127.0.0.1" in tmp_hosts: # nginx always comes from local host
            tmp_hosts.append("127.0.0.1")

        env.allowed_hosts = ",".join(["'%s'" % get_host(host) for host in tmp_hosts]) # used by local_settings.py.template to set Django's allowed hosts
    else:
        env.allowed_hosts = ",".join(["'%s'" % get_host(host) for host in conf.get("APPLICATION_HOSTS")]) # used by local_settings.py.template to set Django's allowed hosts

    assert len(env.private_database_hosts) == len(env.database_hosts), "Same number of DATABASE_HOSTS and PRIVATE_DATABASE_HOSTS must be listed"
    assert len(env.private_application_hosts) == len(env.application_hosts), "Same number of APPLICATION_HOSTS and PRIVATE_APPLICATION_HOSTS must be listed"
    assert len(env.private_cron_hosts) == len(env.cron_hosts), "Same number of CRON_HOSTS and PRIVATE_CRON_HOSTS must be listed"

    env.proj_name = conf.get("PROJECT_NAME", os.getcwd().split(os.sep)[-1])
    env.venv_home = conf.get("VIRTUALENV_HOME", "/home/%s" % env.user)
    env.venv_path = "%s/%s" % (env.venv_home, env.proj_name)
    env.proj_dirname = "project"
    env.proj_path = conf.get("PROJECT_PATH", "%s/%s" % (env.venv_path, env.proj_dirname))
    env.manage = "%s/bin/python %s/project/manage.py" % (env.venv_path, env.venv_path)

    env.domains = conf.get("DOMAINS", [conf.get("LIVE_HOSTNAME", env.application_hosts[0])])
    env.domains_nginx = " ".join(env.domains)
    env.domains_python = ", ".join(["'%s'" % s for s in env.domains])
    env.ssl_disabled = "#" if len(env.domains) > 1 or conf.get("SSL_DISABLED", True) else ""
    env.redirect = "" if conf.get("REDIRECT", False) else "#"
    env.compress = conf.get("COMPRESS", False)
    env.sitename = conf.get("SITENAME", "Default")
    env.repo_url = conf.get("REPO_URL", "")
    env.repo_branch = conf.get("REPO_BRANCH", "master")
    env.git = True
    env.reqs_path = conf.get("REQUIREMENTS_PATH", None)
    env.gunicorn_port = conf.get("GUNICORN_PORT", 8000)
    env.locale = conf.get("LOCALE", "en_US.UTF-8")
    env.linux_distro = conf.get("LINUX_DISTRO", "wheezy")
    env.bower = conf.get("BOWER", False)

    env.secret_key = conf.get("SECRET_KEY", "")
    env.nevercache_key = conf.get("NEVERCACHE_KEY", "")

    env.deploy_my_public_key = conf.get("DEPLOY_MY_PUBLIC_KEY")
    env.deploy_ssh_key_path = conf.get("DEPLOY_SSH_KEY_PATH")
    env.deploy_db_cluster_key_path = conf.get("DEPLOY_DB_CLUSTER_SSH_KEY_PATH")
    env.apt_requirements = conf.get("APT_REQUIREMENTS", [])
    env.install_extras = conf.get("INSTALL_EXTRAS", [])
    env.db_extensions = conf.get("DB_EXTENSIONS", [])

    # safety check the db password
    if not check_db_password(env.db_pass):
        abort("The database password contains disallowed special characters.")

if sys.argv[0].split(os.sep)[-1] in ("fab", "fab-script.py"):
    # Ensure we import settings from the current dir
    try:
        global_conf = {}
        global_conf = __import__("fabric_settings", globals(), locals(), [], 0).FABRIC
        try:
            env.settings = global_conf # save settings to switch later
            env.mode = "development"
            load_environment(env.settings[env.mode], False)

        except (KeyError, ValueError):
            raise ImportError
    except (ImportError, AttributeError):
        if not confirm("Warning, no hosts defined: Are you sure you want to continue?"):
            print "\nAborting!"
            exit()


##################
# Template setup #
##################

# Each template gets uploaded at deploy time, only if their
# contents has changed, in which case, the reload command is
# also run.
#
# If a role entry is specified, the template is uploaded only for the given role: application, cron

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
        "owner": "root",
    },
    "cron": {
        "local_path": "deploy/crontab",
        "remote_path": "/etc/cron.d/%(proj_name)s",
        "owner": "root",
        "mode": "600",
        "role": "cron",
    },
    "gunicorn": {
        "local_path": "deploy/gunicorn.conf.py.template",
        "remote_path": "%(proj_path)s/gunicorn.conf.py",
        "owner": "root",
    },
    "settings": {
        "local_path": "deploy/%(mode)s_settings.py", # local task changes this filename
        "remote_path": "%(proj_path)s/local_settings.py",
    },
    "celery": {
        "local_path": "deploy/celeryd.conf",
        "remote_path": "/etc/supervisor/conf.d/%(proj_name)s.celery.conf",
        "required_module": "celery",
        "reload_command": "supervisorctl reload",
    },
}

# Additional templates are created in code.
#
#  ssh
#       ~/.ssh/authorized_keys
#       ~/.ssh/config
#       ~/.ssh/%(DEPLOY_SSH_KEY_PATH.basename())s
#
#  ssh_db
#       ~postgres/.ssh/known_hosts
#       ~postgres/.ssh/config
#       ~postgres/.ssh/authorized_keys
#       ~postgres/.ssh/$(DEPLOY_DB_CLUSTER_SSH_KEY_PATH.basename())s
#
#  postgresql
#      /etc/postgresql/9.2/main/postgresql.conf
#      /etc/postgresql/9.2/main/pg_hba.conf
#
#  db_slave
#      /var/lib/postgresql/9.2/main/recovery.conf
#      /var/lib/postgresql/9.2/archive
#
#  database, db_slave
#      /var/tmp/pg_basebackup_%(proj_name)s.tar.bz2


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

    Downloaded from https://github.com/fabric/fabric/pull/658

    """
    changes_done = set()
    options = dict(comment_char=comment_char, setter_char=setter_char)

    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=True) as f:

        # Download the remote file into the temporary file
        get(remote_path, f, use_sudo=use_sudo)

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
                    line = "%s %s %s\n" % (setting[0], setter_char, setting[1])
                    print line
                    newlines.append(line)
                elif type == CONFIG_FILE_RECORDS:
                    line = "\t".join(setting) + "\n"
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


def append_to_remote_file_top(remote_filename, line):
    """
    Replaces the given line with the same at the top of the file.
    """
    if not exists(remote_filename):
        append(remote_filename, line)
    else:
        # read the file and look for the string not using regex
        test = run("cat %s" % remote_filename, show=False)
        if test.find(line) != -1:
            # this code moves the following line to the top of the file
            file = StringIO()
            get(remote_filename, file)
            new_file = [line]
            new_file.extend([l for l in file.getvalue().split("\n") if l != line])
            new_text = "\n".join(new_file) + "\n"
            put(StringIO(new_text), remote_filename)
        else:
            append(remote_filename, line)


def fancy_append(remote_filename, line):
    """
    Fixes append() because it duplicates content of authorized_keys. Returns False if no operation, True if a file was appended.
    """
    if not exists(remote_filename):
        append(remote_filename, line)
    else:
        # read the file and look for the string not using regex
        test = run("cat %s" % remote_filename, show=False)
        if test.find(line) != -1:
            return True
        else:
            append(remote_filename, line)


def check_requirements_file(module):
    """
    Checks a requirements file to see if a module is installed.
    """
    with open(env.reqs_path, "r") as f:
        return f.read().find(module) != -1

######################################
# Context for virtualenv and project #
######################################


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


@task
@roles('application','cron','database','db_slave')
def run(command, show=True):
    """
    Runs a shell comand on the remote server.
    """
    if show:
        print_command(command)
    with hide("running"):
        return _run(command)


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
    if not os.path.exists(local_path):
        project_root = os.path.dirname(os.path.abspath(__file__))
        local_path = os.path.join(project_root, local_path)
    remote_path = template["remote_path"]
    reload_command = template.get("reload_command")
    owner = template.get("owner")
    mode = template.get("mode")
    remote_data = ""
    required_module = template.get("required_module")

    # block uploading certain files (e.g., celery configuration) if it is not installed in requirements
    if required_module and not check_requirements_file(required_module):
        return

    if exists(remote_path):
        with hide("stdout"):
            remote_data = sudo("cat %s" % remote_path, show=False)
    print "local_path: %s " % local_path
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
        if not check_db_password(env.db_pass):
            abort("The password you provided contains disallowed special characters")

    return env.db_pass


@task
@roles('application','cron','database','db_slave')
def apt(packages):
    """
    Installs one or more system packages via apt.
    """
    return sudo("apt-get install -y -q " + packages)


def postgres(command):
    """
    Runs the given command as the postgres user.
    """
    show = not command.startswith("psql")
    return run("sudo -u root sudo -u postgres %s" % command, show=show)


@task
@roles('database')
def psql(sql, show=True):
    """
    Runs SQL against the project's database.
    """
    out = postgres('psql -c "%s"' % sql)
    if show:
        print_command(sql)
    return out


def backup(filename):
    """
    Backs up the database.
    """
    return postgres("pg_dump -Fc %s > %s" % (env.proj_name, filename))


def restore(filename):
    """
    Restores the database.
    """
    return postgres("pg_restore -c -d %s %s" % (env.proj_name, filename))


@task
@roles('application','cron')
def python(code, show=True):
    """
    Runs Python code in the project's virtual environment, with Django loaded.
    """
    setup = "import os; os.environ[\'DJANGO_SETTINGS_MODULE\']=\'settings\'; import django; django.setup();"
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
@roles('application','cron')
def manage(command, use_sudo=False):
    """
    Runs a Django management command.
    """
    combined_command = "%s %s" % (env.manage, command)
    if use_sudo:
        return sudo(combined_command)
    else:
        return run(combined_command)


@task
@roles('application','cron')
def rabbitmqctl(command):
    """
    Runs commands for RabbitMQ.
    """
    sudo("rabbitmqctl %s" % command)

#########################
# SSH key setup         #
#########################

@roles('application','cron','database','db_slave')
def copymysshkey():
    if env.deploy_my_public_key and len(env.deploy_my_public_key) > 0:
        with open(os.path.expanduser(env.deploy_my_public_key)) as f:
            run("mkdir -p ~/.ssh")
            fancy_append("~/.ssh/authorized_keys", f.readline().rstrip('\n'))

@roles('application','cron')
def copydeploykey():
    # we do not copy the deployment ssh key (which accesses your repo) onto the database server
    if env.deploy_ssh_key_path and len(env.deploy_ssh_key_path) > 0:
        run("mkdir -p ~/.ssh")
        put(env.deploy_ssh_key_path, "~/.ssh/%s" % os.path.basename(env.deploy_ssh_key_path),mode=0600)
        append_to_remote_file_top("~/.ssh/config", "IdentityFile ~/.ssh/%s" % os.path.basename(env.deploy_ssh_key_path))

@task
@log_call
@roles('database','db_slave')
def copy_db_ssh_keys():
    """
    Deploys SSH keys for database servers to talk to each other.
    """
    if env.deploy_db_cluster_key_path and len(env.deploy_db_cluster_key_path) > 0:
        with settings(sudo_user='postgres'):
            home_dir = run("echo ~postgres").rstrip('\n')
            if home_dir == "~postgres":
                abort("postgres user account hasn't been created yet. Run this command again after installing postgresql.")
            run("mkdir -p %s/.ssh" % home_dir)

            # add private key
            remote_path = "%s/.ssh/%s" % (home_dir, os.path.basename(env.deploy_db_cluster_key_path))
            put(env.deploy_db_cluster_key_path, remote_path, mode=0600)

            # add public key and register it
            pub_key = run("ssh-keygen -y -f %s" % remote_path, show=False)
            fancy_append("%s/.ssh/authorized_keys" % home_dir, pub_key.rstrip('\n'))
            append_to_remote_file_top("%s/.ssh/config" % home_dir, "IdentityFile %s" % remote_path)

            # create known hosts
            # WARNING: this has a risk of man in the middle attack because we don't check the identity of each host
            for private_db_ip_addr in env.private_database_hosts:
                ext_known_host = run("ssh-keyscan %s" % private_db_ip_addr)
                fancy_append("%s/.ssh/known_hosts" % home_dir, ext_known_host)

        # return to root user and then change the owner of postgres
        sudo("chown -R postgres:postgres %s/.ssh" % home_dir)

@task
@log_call
def copysshkeys():
    """
    Copies your local SSH public key onto the server for remote access (run once only, does not check for duplicates).
    Also, installs DEPLOY_SSH_KEY_PATH to the application/cron server.
    """
    execute(copymysshkey)
    execute(copydeploykey)

#########################
# Install and configure #
#########################

@task
@roles('application','cron','database','db_slave')
def install_prereq():
    locale = "LC_ALL=%s" % env.locale
    with hide("stdout"):
        if locale not in sudo("cat /etc/default/locale"):
            sudo("update-locale %s" % locale)
            run("exit")
    sudo("apt-get update -y -q")
    apt("git-core supervisor libpq-dev")
    sudo("ln -sf /usr/share/zoneinfo/UTC /etc/localtime")

@task
@parallel
@roles('application','cron')
def installapp():
    put(StringIO("deb http://www.rabbitmq.com/debian/ testing main"), "/etc/apt/sources.list.d/rabbitmq.list", use_sudo=True)
    sudo("wget --quiet -O - http://www.rabbitmq.com/rabbitmq-signing-key-public.asc | sudo apt-key add -")
    sudo("apt-get update")
    apt("nginx libjpeg-dev python-dev python-setuptools "
        "memcached libffi-dev rabbitmq-server")
    sudo("easy_install pip")
    sudo("pip install virtualenv --no-use-wheel")
    apt(" ".join(env.apt_requirements))

@task
@parallel
@roles('database','db_slave')
def installdb():
    put(StringIO("deb http://apt.postgresql.org/pub/repos/apt/ %s-pgdg main" % env.linux_distro), "/etc/apt/sources.list.d/pgdg.list", use_sudo=True)
    sudo("wget --quiet -O - http://apt.postgresql.org/pub/repos/apt/ACCC4CF8.asc | sudo apt-key add -")
    sudo("apt-get update")
    apt("postgresql-9.2 postgresql-contrib-9.2 bzip2 rsync") # bzip2 for compression


@task
@roles("database",'db_slave')
@log_call
def uninstalldb():
    """
    Stop and uninstall the database. Data directory is untouched.
    """
    sudo("/etc/init.d/postgresql stop")
    sudo("apt-get remove postgresql")


@task
@log_call
def installextras():
    for install_extra in env.install_extras:
        execute(globals()[install_extra])


@task
@log_call
def install():
    """
    Installs the base system, Python requirements, and timezone for all servers.
    """
    execute(install_prereq)
    execute(installapp)
    execute(installdb)
    execute(installextras)

@task
@parallel
@roles('application', 'cron')
def install_phantom_js():
    sudo("wget https://phantomjs.googlecode.com/files/phantomjs-1.9.2-linux-x86_64.tar.bz2")
    sudo("tar xvjf phantomjs-1.9.2-linux-x86_64.tar.bz2")
    sudo("mv phantomjs-1.9.2-linux-x86_64 /usr/lib")
    sudo("ln -s /usr/lib/phantomjs-1.9.2-linux-x86_64/bin/phantomjs /usr/bin/.")

#########################
# Create                #
#########################

@roles('application','cron','database')
def create_prereq():
    """
    Create virtual environment directory and project path within
    """
    if not exists(env.venv_home):
        prompt = raw_input("\nProject directory doesn't exist: %s\nWould you like "
                           "to create it? (yes/no) " % env.venv_home)
        if prompt.lower() != "yes":
            print "\nAborting!"
            return False

        sudo("mkdir %s" % env.venv_home)

@roles('application','cron')
def createapp1():
    # Create virtualenv
    with cd(env.venv_home):
        create_virtual_env = False
        if exists(env.venv_path):
            # If virtual environment exists, prompt the user if they'd like to remove it
            prompt = raw_input("\nVirtualenv exists: %s\nWould you like "
                               "to replace it? (yes/no) " % env.proj_name)
            if prompt.lower() == "yes":
                removeapp()
                create_virtual_env = True
        else:  # Else, the virtual environment doesn't exist and we need to create ite
            create_virtual_env = True
        
        if create_virtual_env:
            run("virtualenv %s --distribute" % env.proj_name)
        
        # If the project has not been cloned yet from git, we need to intialize it and it's submodules
        if not exists(env.proj_path):
            run("git clone -b %s %s %s" % (env.repo_branch, env.repo_url, env.proj_path))
            with project():
                run("git submodule init")
                run("git submodule update")

@task
@roles('application','cron')
@parallel
def createapp2():
    """
    Continuation of create. Used if the database already exists. Upload certificate and site name.
    """
    # Set up SSL certificate.
    if not env.ssl_disabled:
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
                    parts = (crt_file, key_file, env.domains[0])
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
        pip("gunicorn setproctitle psycopg2 "
            "django-compressor python-memcached")
        manage("migrate --noinput")
        python("from django.conf import settings;"
               "from django.contrib.sites.models import Site;"
               "import sys;"
               "sys.path.append(os.path.abspath('..'));"
               "Site.objects.filter(id=settings.SITE_ID).update(domain='%s');"
               % env.domains[0])
        for domain in env.domains:
            python("from django.contrib.sites.models import Site;"
                   "import sys;"
                   "sys.path.append(os.path.abspath('..'));"
                   "Site.objects.get_or_create(domain='%s');" % domain)
        if env.admin_pass:
            pw = env.admin_pass
            user_py = ("from mezzanine.utils.models import get_user_model;"
                       "import sys;"
                       "sys.path.append(os.path.abspath('..'));"
                       "User = get_user_model();"
                       "u, _ = User.objects.get_or_create(username='admin');"
                       "u.is_staff = u.is_superuser = True;"
                       "u.set_password('%s');"
                       "u.save();" % pw)
            python(user_py, show=False)
            shadowed = "*" * len(pw)
            print_command(user_py.replace("'%s'" % pw, "'%s'" % shadowed))

def get_private_db_host_from_public_host():
    if not env.host_string in env.database_hosts:
        abort("Could not recognize the database host %s" % env.host_string)
    host_index = env.database_hosts.index(env.host_string)
    private_host = env.private_database_hosts[host_index]
    return (host_index, private_host)


def write_postgres_conf():
    # Configure database server to listen to appropriate ports. Tested with Debian 6 and Postgres 9.2
    (host_index, private_host) = get_private_db_host_from_public_host()

    postgres_conf = [
                           ("port", "5432"),
                           ("listen_addresses","'%s'" % ",".join([env.host_string, private_host, "127.0.0.1"])), # public IP, private IP, localhost
                           ("wal_level","hot_standby"),
                           ("max_wal_senders", str(len(env.private_database_hosts)+1)),
                           ("wal_keep_segments", "32"),
                       ]

    if host_index < len(env.private_database_hosts) - 1: # for every host less than the last one, configure cascading replication
        postgres_conf.extend([("archive_mode", "on"),
                              ("archive_command", "'rsync -aq -e ssh %p postgres@" + env.private_database_hosts[host_index + 1] + ":/var/lib/postgresql/9.2/archive/%f'"),
                              ("archive_timeout", "3600"),
                              ])
    else:
        postgres_conf.extend([("archive_mode", "off"),])

    if host_index > 0: # modifying a slave database
        postgres_conf.append(("hot_standby", "on"))

    modify_config_file("/etc/postgresql/9.2/main/postgresql.conf", postgres_conf, use_sudo=True)
    sudo("chown postgres /etc/postgresql/9.2/main/postgresql.conf")

def write_hba_conf():
    client_list = [('host', env.proj_name, env.proj_name, '%s/32' % client, 'md5') for client in env.private_application_hosts]
    client_list.extend([('host', env.proj_name, env.proj_name, '%s/32' % client, 'md5') for client in env.private_cron_hosts if client not in env.private_application_hosts])
    client_list.extend([('host', 'replication', 'replicator%s' % env.proj_name, '%s/32' % client, 'trust') for client in env.private_database_hosts])
    client_list.append(('local', 'replication', 'postgres', 'trust'))
    modify_config_file('/etc/postgresql/9.2/main/pg_hba.conf', client_list, type="records", use_sudo=True)
    sudo("chown postgres /etc/postgresql/9.2/main/pg_hba.conf")


@roles("database")
def createdb_master():
    # create virtual environment directory and project path within
    if not exists(env.venv_path):
        prompt = raw_input("\nProject directory doesn't exist: %s"
                           "\nWould you like to create it? (yes/no) "
                           % env.venv_path)
        if prompt.lower() != "yes":
            print "\nAborting!"
            return False

        sudo("mkdir %s" % env.venv_path)

    write_postgres_conf()
    write_hba_conf()
    # Configure permissions for application servers
    with settings(warn_only=True):
        sudo("rm /var/lib/postgresql/9.2/main/recovery.conf") # erase all settings in the replication conf

    restartdb()

@roles('database')
def createdb_snapshot_master():
    run("pg_basebackup -U postgres -D - -P -Ft | bzip2 > /var/tmp/pg_basebackup_%s.tar.bz2" % env.proj_name)
    get("/var/tmp/pg_basebackup_%s.tar.bz2" % env.proj_name, "/var/tmp/pg_basebackup_%s.tar.bz2" % env.proj_name) # copy from master /var/tmp to this computer's /var/tmp

@roles('db_slave')
def stop_slave_db():
    if not env.host_string or len(env.host_string) == 0:
        return

    sudo("/etc/init.d/postgresql stop")

@roles('db_slave')
def createdb_slave():
    if not env.host_string or len(env.host_string) == 0:
        return

    (host_index, private_host) = get_private_db_host_from_public_host()

    sudo("/etc/init.d/postgresql stop")

    write_postgres_conf()
    write_hba_conf()

    # Clone from the master database
    put("/var/tmp/pg_basebackup_%s.tar.bz2" % env.proj_name, "/var/tmp/pg_basebackup_%s.tar.bz2" % env.proj_name)

    # Remove old archive directory
    with cd("/var/lib/postgresql/9.2/"):
        with settings(warn_only=True):
            run("rm -rf archive")
        sudo("mkdir -p /var/lib/postgresql/9.2/archive")
        sudo("chown postgres /var/lib/postgresql/9.2/archive")

    with cd("/var/lib/postgresql/9.2/main/"):
        run("rm -rf *")
        run("tar -xjvf /var/tmp/pg_basebackup_%s.tar.bz2" % env.proj_name)
        sudo("chown -R postgres:postgres /var/lib/postgresql/9.2/main")

    # Configure recovery for slave
    put(StringIO("standby_mode = 'on'\n"
                 "primary_conninfo = 'host=" + env.private_database_hosts[host_index-1] + " port=5432 user=replicator" + env.proj_name + "'\n"
                 "trigger_file = '/tmp/pg_failover_trigger'\n"
                 "restore_command = 'cp /var/lib/postgresql/9.2/archive/%f %p'\n"
                 "archive_cleanup_command = '/usr/lib/postgresql/9.2/bin/pg_archivecleanup /var/lib/postgresql/9.2/archive/ %r'\n"
                 ), "/var/lib/postgresql/9.2/main/recovery.conf") # erase all settings in the replication conf, or create the file as needed

    sudo("/etc/init.d/postgresql start")

    # wait a few seconds for streaming replication to start
    retries = 0
    while True:
        retries = retries + 1
        result = run("ps -ef | grep receiver")
        if result.find("postgres: wal receiver process") == -1:
            if retries > 5:
                abort("Slave database did not start streaming replication")
            else:
                sleep(1)
        else:
            print("Slave database started with streaming")
            break

@roles("database")
def createdb_extensions(warn_on_account_creation=False):
    with settings(warn_only=True):
        for extension in env.db_extensions:
            postgres('psql -c "CREATE EXTENSION {0}" -d {1}'.format(extension, env.proj_name))


@roles("database")
def createdb_accounts(warn_on_account_creation=False):
    with settings(warn_only=warn_on_account_creation):
        # Create DB and DB user.
        pw = db_pass()
        psql("CREATE USER replicator%s REPLICATION LOGIN ENCRYPTED PASSWORD '%s';" % (env.proj_name, pw.replace("'", "\'")), show=False)
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
def createdb(warn_on_account_creation=False):
    """
    Sets up the database configuration, and then creates the database and superuser account.
    """
    execute(stop_slave_db)
    execute(createdb_master)
    execute(createdb_accounts, warn_on_account_creation)
    execute(createdb_snapshot_master)
    execute(createdb_slave)
    execute(createdb_extensions)

@task
@roles("database")
@log_call
def upgradedb():
    """
    Upgrade 8.4 to 9.2 Postgres database. Assumes a live running instance of Postgresql 8.4.
    """
    backupdb()
    installdb()
    sudo("/etc/init.d/postgresql stop")
    run("su - postgres -c \"/usr/lib/postgresql/9.2/bin/pg_upgrade -u postgres -b %s -B %s -d %s -D %s -o '-D %s' -O '-D %s'\"" 
        % ("/usr/lib/postgresql/8.4/bin/","/usr/lib/postgresql/9.2/bin/","/var/lib/postgresql/8.4/main/","/var/lib/postgresql/9.2/main/","/etc/postgresql/8.4/main/","/etc/postgresql/9.2/main/"))
    sudo("apt-get remove postgresql-8.4")
    sudo("rm /usr/lib/postgresql/8.4/bin/*") # remove old database version to prevent conflict in running postgresql commands
    apt("postgresql-9.2")
    sudo("/etc/init.d/postgresql start")
    createdb_master()

@task
@roles("application","cron")
@log_call
def create_rabbit(warn_on_duplicate_accounts=True):
    """
    Creates the RabbitMQ account.
    """

    if warn_on_duplicate_accounts == "off" or warn_on_duplicate_accounts == "no":
        warn_on_duplicate_accounts = False

    # For security purposes we remove guest account from all servers.
    with settings(warn_only=True):
        rabbitmqctl("delete_user guest")

    with settings(warn_only=warn_on_duplicate_accounts):
        rabbitmqctl("add_user %s %s" % (env.proj_name, env.admin_pass))
        rabbitmqctl("add_vhost %s" % env.proj_name)
        rabbitmqctl('set_permissions -p %s %s ".*" ".*" ".*"' % (env.proj_name, env.proj_name))

@task
@log_call
def create(warn_on_duplicate_accounts=True):
    """
    Create a new virtual environment for a project. Pulls the project's repo from version control, adds system-level configs for the project, and initialises the database with the live host.
    """

    if warn_on_duplicate_accounts == "off" or warn_on_duplicate_accounts == "no":
        warn_on_duplicate_accounts = False

    execute(create_prereq)
    execute(createapp1)
    execute(create_rabbit, warn_on_duplicate_accounts)
    createdb(warn_on_duplicate_accounts)
    execute(createapp2)

    return True

#########################
# Remove                #
#########################

@task
@roles("application",'cron')
@log_call
def removeapp():
    """
    Removes all traces of the application from the application server.
    """
    if exists(env.venv_path):
        sudo("rm -rf %s" % env.venv_path)
    for template in get_templates().values():
        remote_path = template["remote_path"]
        if exists(remote_path):
            sudo("rm %s" % remote_path)

@task
@roles("database")
@log_call
def removedb():
    """
    Removes all data from the database. USE WITH CAUTION.
    """
    with settings(warn_only=True):    
        psql("DROP DATABASE IF EXISTS %s;" % env.proj_name)
        psql("DROP USER IF EXISTS %s;" % env.proj_name)
        psql("DROP USER IF EXISTS replicator%s;" % env.proj_name)

    # Configure database server to listen to appropriate ports. Tested with Debian 6 and Postgres 9.2
    warn("TODO modify /etc/postgresql/9.2/main/pg_hba.conf")
    warn("TODO modify /etc/postgresql/9.2/main/postgresql.conf")

@task
@roles("application","cron")
@log_call
def remove_rabbit():
    with settings(warn_only=True):
        rabbitmqctl("delete_user %s" % env.proj_name)
        rabbitmqctl("delete_vhost %s" % env.proj_name)

@task
@log_call
def remove():
    """
    Blow away the current project.
    """
    execute(removeapp)
    execute(removedb)
    execute(remove_rabbit)

##############
# Restart    #
##############

@task
@log_call
@roles("application","cron")
def restart_rabbit():
    """
    Restart RabbitMQ process
    """
    sudo("invoke-rc.d rabbitmq-server restart")

@task
@log_call
@roles("application",'cron')
def restartapp():
    """
    Restarts the gunicorn and celery process.
    """
    pid_path = "%s/gunicorn.pid" % env.proj_path
    if exists(pid_path):
        sudo("kill -HUP `cat %s`" % pid_path)
    else:
        start_args = (env.proj_name, env.proj_name)
        if env.mode != "vagrant": # gunicorn is turned off by local task
            sudo("supervisorctl start %s:gunicorn_%s" % start_args)

    if check_requirements_file("celery"):
        sudo("supervisorctl restart celery_%s" % env.proj_name)

@task
@log_call
@roles("database",'db_slave')
def restartdb():
    """
    Restarts postgres.
    """
    sudo("/etc/init.d/postgresql restart") # command specific to Debian

@task
@log_call
@roles("application","cron")
def restart_celery():
    if check_requirements_file("celery"):
        sudo("supervisorctl restart celery_%s" % env.proj_name)

@task
@log_call
def restart():
    """
    Restart gunicorn worker processes, celery, and the database.
    """
    execute(restart_celery)
    execute(restartapp)
    execute(restartdb)

def createdirs():
    # Helper method for deployapp1_application_templates and deployapp1_cron_templates
    if not exists(env.venv_path):
        prompt = raw_input("\nVirtualenv doesn't exist: %s\nWould you like "
                           "to create it? (yes/no) " % env.proj_name)
        if prompt.lower() != "yes":
            print "\nAborting!"
            return False
        create()

##############
# Deployment #
##############

@roles("application")
@parallel
def deployapp1_application_templates():
    if not env.host_string:
        return

    createdirs()
    for name in get_templates():
        template = get_templates()[name]
        if not "role" in template or template["role"] == "application":
            upload_template_and_reload(name)

@roles("cron")
@parallel
def deployapp1_cron_templates():
    if not env.host_string:
        return

    createdirs()
    for name in get_templates():
        template = get_templates()[name]
        if not "role" in template or template["role"] == "cron":
            upload_template_and_reload(name)

@roles("application",'cron')
def deployapp2(collect_static=True):
    with project():
        static_dir = static()
        if exists(static_dir):
            sudo("tar -cf last.tar %s" % static_dir)
        git = env.git
        last_commit = "git rev-parse HEAD" if git else "hg id -i"
        sudo("%s > last.commit" % last_commit)
        with update_changed_requirements():
            run("git pull origin {0} -f".format(env.repo_branch) if git else "hg pull && hg up -C")
        run("git submodule init")
        run("git submodule sync")
        run("git submodule update")
        if env.mode != "vagrant" and collect_static:
            # If we're using bower, make sure we install our javascript files before collecting static and compressing
            if env.bower:
                run("bower install")

            manage("collectstatic -v 0 --noinput", True)

            # TODO: move this to a task that runs locally instead of on all application/cron servers
            if env.compress:
                manage("compress")
                manage("syncfiles -e'media/' --static")

        manage("syncdb --noinput")
        manage("migrate --noinput")
    restartapp()
    restart_celery()

@log_call
@roles("database","db_slave")
def deploydb_hba():
    """
    Deploys the permission list for the database.
    """
    write_hba_conf()

@task
@log_call
def deployapp():
    """
    Deploy the application without upgrading the database. Useful for old version of Postgres.
    """
    deploy(True)


@task
@log_call
def deployapp_without_static():
    """
    Deploy the application without running collectstatic and upgrading the database. Useful for old version of Postgres.
    """
    deploy(True, collect_static=False)


@task
@log_call
def deploy(skip_db=False, collect_static=True):
    """
    Deploy latest version of the project.
    Check out the latest version of the project from version
    control, install new requirements, sync and migrate the database,
    collect any new static assets, and restart gunicorn's work
    processes for the project.
    """

    execute(deployapp1_application_templates)
    execute(deployapp1_cron_templates)
    if not skip_db:
        execute(backupdb)
        execute(deploydb_hba)
    execute(deployapp2, collect_static=collect_static)

    return True

#########################
# Backup and restore    #
#########################

@task
@log_call
@roles("database")
def backupdb():
    """
    Back up the database. No history of previous backups.
    """
    with cd(env.venv_path):
        backup("last-%s.db" % env.proj_name)

@task
@log_call
@roles("application",'cron')
def rollbackapp():
    """
    Restores to the previous application deployment.
    """
    with project():
        with update_changed_requirements():
            update = "git checkout" if env.git else "hg up -C"
            run("%s `cat last.commit`" % update)
        with cd(join(static(), "..")):
            run("tar -xf %s" % join(env.proj_path, "last.tar"))
    
    restartapp()
    restart_celery()

@task
@log_call
@roles("database")
def rollbackdb():
    """
    Restores to the previous deployment's database.
    """
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
    execute(rollbackdb)
    execute(rollbackapp)

#########################
# Other administration  #
#########################

@task
@log_call
@roles("application","cron")
def monitor_rabbit(enabled, administrator="off"):
    """
    Changes the monitoring status of RabbitMQ. Restarts the server.
    """
    if enabled != "on" and enabled != "off":
        abort("enabled has to be on or off")
        return

    if administrator != "on" and administrator != "off":
        abort("administrator has to be on or off")
        return

    if enabled=="on":
        sudo("rabbitmq-plugins enable rabbitmq_management")
        if administrator=="on":
            rabbitmqctl("set_user_tags %s administrator" % env.proj_name)
        else:
            rabbitmqctl("set_user_tags %s management" % env.proj_name)
    else:
        sudo("rabbitmq-plugins disable rabbitmq_management")
        rabbitmqctl("set_user_tags %s" % env.proj_name)
    restart_rabbit()

    if enabled=="on":
        print("Monitoring at http://%s:15672" % (env.host_string))

@task
@log_call
def all():
    """
    Installs everything required on a new system and deploy.
    From the base software, up to the deployed project.
    """
    copysshkeys()
    install()
    execute(copy_db_ssh_keys)
    if create():
        deploy()


########################
# Environment tasks
########################

@task
@log_call
def development(show_info=False):
    env.mode = "development"
    load_environment(env.settings[env.mode], show_info)

@task
@log_call
def staging(show_info=False):
    env.mode = "staging"
    load_environment(env.settings[env.mode], show_info)


@task
@log_call
def production(show_info=False):
    env.mode = "production"
    load_environment(env.settings[env.mode], show_info)

########################
# Vagrant tasks
########################

@task
@log_call
@roles("application", "cron", "database", "db_slave")
def locales():
    # http://people.debian.org/~schultmc/locales.html
    append("/etc/locale.gen", "en_US.UTF-8 UTF-8", use_sudo=True)
    sudo("/usr/sbin/locale-gen")

@task
@log_call
@roles("database","db_slave")
def fix_db_permissions():
    sudo("chmod o+r /etc/postgresql/9.2/main/pg_hba.conf")


@task
@log_call
def vagrant(show_info=False):
    """
    Disables nginx, gunicorn, and cron setup. Use for Vagrant setup.
    """

    env.mode = "vagrant"
    env.forward_agent = True
    load_environment(env.settings[env.mode], show_info)
    env.manage = "%s/bin/python /vagrant/%s/manage.py" % (env.venv_path, env.proj_name)

    if "nginx" in templates:
        del templates["nginx"]

    if "cron" in templates:
        del templates["cron"]

    if "gunicorn" in templates:
        del templates["gunicorn"]

    if env.venv_home.startswith("/vagrant/"):
        abort("NEVER specify your virtual environment home as the shared directory between host and vm\n"
              "You must reconfigure VIRTUALENV_HOME in your settings.py/%s_settings.py" % env.mode)

@task
@log_call
def working(show_info=False):
    """
    Alternative of vagrant task that uses /vagrant shared directory instead of repository-committed changes.
    """
    vagrant(show_info)
    env.manage = "%s/bin/python /vagrant/%s/manage.py" % (env.venv_path, env.proj_name)


@task
@log_call
def up(warn_on_duplicate_accounts=True):
    """
    Sets up a Vagrant instance with the selected project
    """

    if warn_on_duplicate_accounts == "off" or warn_on_duplicate_accounts == "no":
        warn_on_duplicate_accounts = False

    vagrant()
    env.manage = "%s/bin/python /vagrant/%s/manage.py" % (env.venv_path, env.proj_name)

    execute(locales)
    copysshkeys()
    execute(install_prereq)
    execute(installdb)
    execute(fix_db_permissions)
    execute(installapp)
    execute(copy_db_ssh_keys)
    if create(warn_on_duplicate_accounts):
        deploy()
